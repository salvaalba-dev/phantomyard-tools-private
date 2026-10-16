"""Deterministic procedure discovery from selected orgs and exported readable KB.

No source traversal, remote fetches, model calls, execution or source writes.
"""
import hashlib
import json
import re
import unicodedata

MAX_SCAN_BYTES = 8_000_000
MAX_NOTE_CHARS = 200_000
MAX_PROCEDURES = 150
MAX_ITEMS = 40


def normalize(value):
    value = ''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def procedural(value):
    return bool(re.search(r'\b(?:proced\w*|protocol\w*|workflow\w*|checklist\w*|pipeline\w*|sop|playbook\w*|normas?|normativa|reglamento\w*)\b', normalize(value)))


def ident(*parts):
    return 'auto-' + hashlib.sha256('\0'.join(parts).encode()).hexdigest()[:32]


def allowed(row):
    return (row.get('searchable') is not False and row.get('confidential') is not True
            and str(row.get('visibility', row.get('classification', ''))).casefold()
            not in {'private', 'confidential', 'restricted', 'secret'})


def clean(value):
    return value[:2000] if isinstance(value, str) else ''


def markdown_sections(content, title):
    """Keep sections and contiguous lists separate; never invent a global order."""
    lines = content.splitlines()
    if lines and lines[0].strip() == '---':
        end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == '---'), None)
        if end is None:
            return []
        lines = lines[end + 1:]
    sections, current, fence = [], {'title': title, 'lines': [], 'level': 0}, None
    for number, line in enumerate(lines, 1):
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token[0]
            elif token[0] == fence:
                fence = None
            continue
        if fence:
            continue
        heading = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line)
        if heading:
            if current['lines'] or current['level'] == 1:
                sections.append(current)
            current = {'title': heading[2], 'lines': [], 'level': len(heading[1])}
        else:
            current['lines'].append(line)
    if current['lines']:
        sections.append(current)
    return sections


def list_groups(lines):
    groups, group, kind, previous, base_indent = [], [], None, None, 0
    for line in lines:
        match = re.match(r'^(\s*)(?:(\d+)[.)]|([-+*]))\s+(.+)', line)
        if match:
            # Nested lists belong to their parent item, not another workflow step.
            indent, number, bullet, action = match.groups()
            depth = len(indent.expandtabs(4))
            if (group and depth > base_indent) or (not group and depth > 3):
                if group:
                    group[-1] = clean(group[-1] + ' ' + action)
                continue
            following = 'ordered' if number else 'rules'
            number = int(number) if number else None
            if group and (depth < base_indent or kind != following or (number is not None and previous is not None and number != previous + 1)):
                    groups.append((kind, group))
                    group = []
            if not group:
                base_indent = depth
            kind, previous = following, number
            group.append(clean(action))
        elif line.strip():
            if group and line.startswith(('  ', '\t')):
                group[-1] = clean(group[-1] + ' ' + line.strip())
            elif group:
                groups.append((kind, group))
                group, kind, previous = [], None, None
        # Markdown allows blank lines between list items.
    if group:
        groups.append((kind, group))
    return groups


def discover(org_sources, actors, note_payloads, documents=()):
    result, scanned, omitted, duplicates = [], 0, 0, {}
    partial = False
    for org, source in org_sources:
        if not allowed(org):
            continue
        oid = org['organization']['id']
        rules = [r for r in org.get('escalation_matrix', []) if isinstance(r, dict) and allowed(r)]
        if rules:
            result.append({'id': ident(oid, 'escalation'), 'org': oid, 'title': 'Declared escalation rules',
                           'title_key': 'Declared escalation rules', 'description': '', 'kind': 'rules',
                           'origin': 'organization', 'source': source, 'source_note': '', 'source_owner': '',
                           'max_hops': org.get('communication', {}).get('max_hops'),
                           'steps': [{'actor': '', 'from': clean(r.get('from')), 'to': clean(r.get('to')),
                                      'action': clean(r.get('condition')), 'input': '', 'output': ''} for r in rules[:MAX_ITEMS]],
                           'partial': len(rules) > MAX_ITEMS})
        for row in org.get('procedures', []):
            if not isinstance(row, dict) or not allowed(row) or not isinstance(row.get('steps'), list):
                continue
            result.append({'id': ident(oid, source, str(row.get('id', row.get('title', '')))), 'org': oid,
                           'title': clean(row.get('title')), 'description': clean(row.get('description')),
                           'kind': 'ordered', 'origin': 'organization', 'source': source,
                           'source_note': '', 'source_owner': '',
                           'steps': [{k: clean(s.get(k)) for k in ('actor', 'action', 'input', 'output')}
                                     for s in row['steps'][:MAX_ITEMS] if isinstance(s, dict) and allowed(s)],
                           'partial': len(row['steps']) > MAX_ITEMS})
    for actor in actors:
        if actor.get('searchable') is False:
            continue
        for note in actor.get('knowledge', []):
            if note.get('searchable') is not True or note.get('truncated') or note.get('unavailable'):
                continue
            payload = note_payloads.get(note.get('id'))
            if not payload or payload.get('actor') != actor['key'] or payload.get('truncated'):
                continue
            content = payload.get('content', '')
            if not isinstance(content, str):
                continue
            cost = len(content.encode())
            if scanned + cost > MAX_SCAN_BYTES or len(content) > MAX_NOTE_CHARS:
                omitted += 1
                partial = True
                if procedural(note['title']) and len(result) < MAX_PROCEDURES:
                    result.append({'id': ident(actor['key'], note['path'], 'document'), 'org': actor['org'],
                                   'title': clean(note['title']), 'description': '', 'kind': 'document',
                                   'origin': 'knowledge', 'source': note['path'], 'source_note': note['id'],
                                   'source_owner': actor['id'], 'source_owners': [actor['id']],
                                   'source_title': note['title'], 'steps': [], 'partial': True})
                continue
            scanned += cost
            sections = markdown_sections(content, note['title'])
            whole = procedural(note['title']) or any(s['level'] == 1 and procedural(s['title']) for s in sections)
            note_rows, document_section = [], None
            for section_number, section in enumerate(sections):
                if not whole and not procedural(section['title']):
                    continue
                # Link-only indexes are navigation, not procedural instructions.
                visible = [line.strip() for line in section['lines'] if line.strip()]
                if not visible or all(re.fullmatch(r'(?:[-*+]\s+)?\[.*?\]\(.*?\)', line) for line in visible):
                    continue
                document_section = document_section or section
                groups = list_groups(section['lines'])
                for group_number, (kind, items) in enumerate(groups):
                    if len(items) < 2:
                        continue
                    note_rows.append({'id': ident(actor['key'], note['path'], str(section_number), str(group_number)),
                                   'org': actor['org'], 'title': clean(section['title']), 'description': '',
                                   'kind': kind, 'origin': 'knowledge', 'source': note['path'],
                                   'source_note': note['id'], 'source_owner': actor['id'],
                                   'source_title': note['title'], 'source_modified': note.get('modified_at'),
                                   'steps': [{'actor': '', 'action': item, 'input': '', 'output': ''} for item in items[:MAX_ITEMS]],
                                   'partial': len(items) > MAX_ITEMS})
            if not note_rows and document_section:
                note_rows.append({'id': ident(actor['key'], note['path'], 'document'), 'org': actor['org'],
                                  'title': clean(note['title']), 'description': '', 'kind': 'document',
                                  'origin': 'knowledge', 'source': note['path'], 'source_note': note['id'],
                                  'source_owner': actor['id'], 'source_title': note['title'],
                                  'source_modified': note.get('modified_at'), 'steps': []})
            for row_number, row in enumerate(note_rows):
                # Only byte-identical complete source documents can be coalesced.
                signature = ident(actor['org'], content, str(row_number), row['title'], row['kind'], json.dumps(row['steps'], sort_keys=True))
                reference = {'note': note['id'], 'owner': actor['id'], 'path': note['path']}
                existing = duplicates.get(signature)
                if existing is not None:
                    if len(existing['source_refs']) < 100:
                        existing['source_refs'].append(reference)
                        existing['source_owners'] = sorted(set(existing['source_owners'] + [actor['id']]))
                    else:
                        existing['partial'] = partial = True
                elif len(result) < MAX_PROCEDURES:
                    row['source_refs'] = [reference]
                    row['source_owners'] = [actor['id']]
                    result.append(row)
                    duplicates[signature] = row
                else:
                    partial = True
    for document in documents:
        if document.get('searchable') is False or not (procedural(document.get('slug', '')) or procedural(document.get('kind', ''))):
            continue
        result.append({'id': ident(document['org'], document.get('urn', ''), document.get('slug', '')),
                       'org': document['org'], 'title': clean(document.get('slug') or document.get('urn')),
                       'description': '', 'kind': 'document', 'origin': 'documents',
                       'source_document': document.get('urn', ''),
                       'source': clean(document.get('location') or document.get('source')),
                       'source_note': '', 'source_owner': '', 'steps': []})
    return result[:MAX_PROCEDURES], {'automatic': True, 'partial': partial or len(result) > MAX_PROCEDURES, 'omitted_notes': omitted}
