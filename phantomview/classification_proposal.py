"""Prepare folder classification drafts from metadata; never grant access."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path, PurePosixPath


def suggest(folder, categories):
    """Folder names provide review hints, not evidence of a note's sensitivity."""
    parts = folder.casefold().split('/')[1:]
    if any(re.search(r'secret|credential|vault|private|personal', part) for part in parts):
        return None, 'exclude', 'Potential secrets or private material: exclude and inspect separately.'
    if not parts or parts[0] in {'inbox', 'docs'}:
        return None, 'split-or-map', 'Mixed or imported material: inspect notes or map verified source classifications.'
    if any(re.search(r'project|proyect', part) for part in parts):
        return None, 'project-required', 'Identify each project and its exact declared category; no umbrella grant.'
    if parts[0] in {'normas', 'norms', 'concepts', 'lessons', 'templates'}:
        category = 'category-1'
        reason = 'Candidate internal reference material; confirm the folder has no sensitive exceptions.'
    elif parts[0] in {'people', 'infra', 'procedures', 'runbooks', 'decisions', 'postmortems'}:
        category = 'category-2'
        reason = 'Conservative confidential candidate; check personal data, secrets and project-specific exceptions.'
    elif parts[0] in {'finance', 'financial', 'accounting', 'finanzas', 'contabilidad'}:
        category = 'category-3'
        reason = 'Sensitive financial candidate; credentials must remain excluded regardless of category.'
    else:
        return None, 'inspect', 'No reliable folder-level hint; review before proposing a category.'
    if category not in categories:
        return None, 'inspect', 'The candidate category is not declared by this organization.'
    return category, 'confirm-content', reason


def build_proposal(inventory):
    """Return an inert draft with exact actor/folder boundaries and no recursion."""
    org = inventory.get('organization')
    categories = inventory.get('categories')
    if not isinstance(org, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', org):
        raise ValueError('An explicit organization ID is required')
    if not isinstance(categories, dict) or not categories:
        raise ValueError('Declared organization categories are required')
    rows = inventory.get('folders')
    if not isinstance(rows, list):
        raise ValueError('Folder inventory required')
    rules, seen = [], set()
    for row in rows:
        actor, folder, notes = row.get('actor'), row.get('folder'), row.get('notes')
        if not isinstance(actor, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', actor):
            raise ValueError('Invalid actor ID')
        if not isinstance(folder, str):
            raise ValueError('Invalid folder')
        path = PurePosixPath(folder)
        if (str(path) != folder or path.is_absolute() or '\\' in folder
                or '..' in path.parts or not path.parts or path.parts[0] != 'kb'
                or any(ord(char) < 32 for char in folder)):
            raise ValueError('Expected a canonical relative KB folder')
        if type(notes) is not int or notes < 1:
            raise ValueError('Positive note count required')
        if (actor, folder) in seen:
            raise ValueError('Duplicate actor/folder boundary')
        seen.add((actor, folder))
        category, review, reason = suggest(folder, categories)
        ident = hashlib.sha256(json.dumps([org, actor, folder]).encode()).hexdigest()[:16]
        rules.append({'id': ident, 'actor': actor, 'folder': folder, 'notes': notes,
                      'recursive': False, 'status': 'draft', 'approved': False,
                      'suggested_category': category, 'project': None,
                      'review': review, 'reason': reason})
    rules.sort(key=lambda row: (row['actor'], row['folder']))
    return {'schema_version': 1, 'organization': org, 'status': 'draft',
            'source_generated_at': inventory.get('generated_at'),
            'default_access': 'deny', 'activation_supported': False,
            'categories': categories, 'rules': rules,
            'excluded_entries': inventory.get('excluded_entries', 0),
            'review_requirements': [
                'Review the contents and exceptions before accepting any folder suggestion.',
                'Category zero is a human grant, never a document classification.',
                'No category ordering or automatic project inheritance.',
                'Folder rules apply only to direct notes of that actor and folder.',
                'Changed contents and new notes require review; this inventory contains no content hashes.',
                'This draft is not an access policy and is not consumed by the assistant.',
            ]}


def render_html(proposal):
    """Render an offline review table without scripts, note bodies or external assets."""
    def esc(value):
        return html.escape(str(value), quote=True)
    rows = ''.join('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in (
        row['actor'], row['folder'], row['notes'], row['suggested_category'] or 'Unclassified',
        row['review'], row['reason'])) + '</tr>' for row in proposal['rules'])
    total = sum(row['notes'] for row in proposal['rules'])
    requirements = ''.join(f'<li>{esc(text)}</li>' for text in proposal['review_requirements'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PhantomView · KB classification review</title>
<style>body{{font:15px/1.5 system-ui;background:#10141c;color:#e6ebf2;margin:32px}}
h1{{font-size:26px}}.draft{{color:#ffc36a}}table{{border-collapse:collapse;width:100%}}
td,th{{text-align:left;padding:10px;border-bottom:1px solid #34404e;vertical-align:top}}
th{{position:sticky;top:0;background:#1c2632}}td:nth-child(2){{overflow-wrap:anywhere}}
small{{color:#adbacb}}</style><h1>PhantomView · KB classification review</h1>
<p>{esc(proposal['organization'])} · {len(proposal['rules'])} exact folders · {total} notes</p>
<p class="draft">DRAFT — No access permissions have been activated.</p>
<small>Snapshot: {esc(proposal['source_generated_at'])}. Excluded entries: {esc(proposal['excluded_entries'])}.</small>
<ul>{requirements}</ul><table><thead><tr><th>Persona</th><th>Folder</th><th>Notes</th>
<th>Suggested category</th><th>Review</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--html', type=Path)
    args = parser.parse_args()
    proposal = build_proposal(json.loads(args.inventory.read_text(encoding='utf-8-sig')))
    # Exclusive creation keeps prior review work intact.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(proposal, stream, ensure_ascii=False, indent=2)
    if args.html:
        with args.html.open('x', encoding='utf-8') as stream:
            stream.write(render_html(proposal))


if __name__ == '__main__':
    main()
