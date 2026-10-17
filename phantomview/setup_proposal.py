"""Prepare a detached first-setup review; never apply policy or classify notes."""
import argparse
import copy
import hashlib
import html
import json
from collections import Counter
from pathlib import Path, PurePosixPath

from channel_identity import HumanDirectory
from classification_proposal import build_proposal, render_html as render_classification
from preview_human_access import preview


MAX_BYTES = 16 * 1024 * 1024
MAX_NOTES = 20000


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def _principals(org, field):
    rows = org.get(field)
    if (not isinstance(rows, list) or len(rows) > 2000
            or any(not isinstance(row, dict) or not isinstance(row.get('id'), str)
                   or not row['id'] for row in rows)):
        raise ValueError('Explicit bounded principal lists required')
    result = {row['id']: row for row in rows}
    if len(result) != len(rows):
        raise ValueError('Duplicate principal identifiers')
    return result


def folder_inventory(org, index, source):
    """Count eligible metadata only; source selection is not content approval."""
    oid = org['organization']['id']
    actors = _principals(org, 'actors')
    if (not isinstance(source, str) or not source
            or index.get('config', {}).get('org_files') != [source]):
        raise ValueError('Exactly one matching selected organization source required')
    snapshot = index.get('snapshot', {})
    organizations = snapshot.get('organizations')
    if (not isinstance(organizations, list) or len(organizations) != 1
            or organizations[0].get('id') != oid or organizations[0].get('source') != source):
        raise ValueError('Collector organization/source selection mismatch')
    collected = snapshot.get('actors')
    if not isinstance(collected, list) or len(collected) > 2000:
        raise ValueError('Bounded collector actor list required')
    seen_actors, seen_paths, counts = set(), set(), Counter()
    total = excluded = 0
    for actor in collected:
        if (not isinstance(actor, dict) or actor.get('id') not in actors
                or actor.get('org') != oid or actor.get('source') != source
                or actor['id'] in seen_actors):
            raise ValueError('Collector actor/source mismatch or duplicate')
        aid = actor['id']
        seen_actors.add(aid)
        notes = actor.get('knowledge', [])
        if not isinstance(notes, list) or total + len(notes) > MAX_NOTES:
            raise ValueError('Bounded knowledge metadata required')
        for note in notes:
            total += 1
            if not isinstance(note, dict):
                raise ValueError('Invalid note metadata')
            if (actor.get('searchable') is not True or note.get('searchable') is not True
                    or note.get('unavailable', False) is not False
                    or note.get('truncated', False) is not False):
                excluded += 1
                continue
            path = note.get('path')
            if not isinstance(path, str):
                raise ValueError('Canonical relative knowledge path required')
            parsed = PurePosixPath(path)
            if (str(parsed) != path or parsed.is_absolute() or '\\' in path
                    or '..' in parsed.parts or len(parsed.parts) < 2
                    or parsed.parts[0] != 'kb' or any(ord(c) < 32 for c in path)):
                raise ValueError('Canonical relative knowledge path required')
            if (aid, path) in seen_paths:
                raise ValueError('Duplicate eligible knowledge path')
            seen_paths.add((aid, path))
            counts[aid, str(parsed.parent)] += 1
    if seen_actors != set(actors):
        raise ValueError('Collector actor inventory is incomplete')
    return {'organization': oid, 'categories': copy.deepcopy(org['policies']['security_categories']),
            'generated_at': snapshot.get('collected_at'), 'excluded_entries': excluded,
            'folders': [{'actor': aid, 'folder': folder, 'notes': count}
                        for (aid, folder), count in sorted(counts.items())]}


def prepare(org, index, *, source, counterparts, absolute_owner, organization_personas):
    """Use explicit stable IDs. No name matching, grant inference or live writes."""
    for value in (org, index):
        if len(json.dumps(value, allow_nan=False).encode()) > MAX_BYTES:
            raise ValueError('Proposal input exceeds size limit')
    proposed = copy.deepcopy(org)
    humans = _principals(proposed, 'humans')
    actors = _principals(proposed, 'actors')
    if absolute_owner not in humans:
        raise ValueError('Absolute owner must be an explicit registered human ID')
    assignments = list(counterparts)
    pairs = {}
    for assignment in assignments:
        if not isinstance(assignment, str):
            raise ValueError('Expected unique HUMAN=PERSONA assignments')
        human, sep, persona = assignment.partition('=')
        if not sep or human not in humans or persona not in actors or human in pairs:
            raise ValueError('Expected unique existing HUMAN=PERSONA assignments')
        existing = humans[human].get('counterpart_persona')
        if existing is not None and existing != persona:
            raise ValueError('Existing counterpart conflict requires separate review')
        pairs[human] = persona
        humans[human]['counterpart_persona'] = persona
    selected = list(organization_personas)
    if (not selected or len(set(selected)) != len(selected)
            or any(persona not in actors for persona in selected)):
        raise ValueError('Explicit unique organization persona IDs required')
    policies = proposed.get('policies', {})
    if 'phantomview' in policies:
        raise ValueError('Existing viewer policy requires a separate migration review')
    declared = policies.get('security_categories', {})
    if not isinstance(declared.get('category-0'), dict):
        raise ValueError('Existing category zero declaration required')
    declared['category-0']['owner'] = absolute_owner
    oid = proposed['organization']['id']
    policies['phantomview'] = {
        'scope_definitions': {oid: {'kind': 'organization', 'label': 'Organization'}},
        'persona_scope_grants': {persona: [oid] for persona in sorted(selected)},
        'human_action_grants': {}, 'project_grants': {},
    }
    directory = HumanDirectory(proposed)
    matrix = preview(proposed)
    inventory = folder_inventory(proposed, index, source)
    access = {'organization': oid, 'preview_only': True, 'live_access_changed': False,
              'policy': directory.scope.policy, 'policy_revision': directory.scope.revision}
    classification = build_proposal(inventory, access, confidential_category='category-3')
    return {'schema_version': 1, 'status': 'draft', 'activation_supported': False,
            'live_access_changed': False, 'organization': oid,
            'source': source, 'source_revision': fingerprint(org),
            'collector_revision': fingerprint(index),
            'proposed_revision': fingerprint(proposed), 'proposed_org': proposed,
            'counterparts': dict(sorted(pairs.items())), 'absolute_owner': absolute_owner,
            'organization_personas': sorted(selected), 'access_preview': matrix,
            'classification': classification}


def render_html(result):
    """Render the proposal summary without contacts, tokens or executable content."""
    def esc(value):
        return html.escape(str(value), quote=True)
    rows = ''.join('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in (
        row['human'], row['counterpart'] or 'None',
        'Independent category 0' if row['category_zero'] else ', '.join(row['categories']) or 'None',
        ', '.join(row['registered_channels']) or 'No verified-channel identity registered',
        ', '.join(row['available_scopes'] or []) or 'None')) + '</tr>'
        for row in result['access_preview']['humans'])
    classification = result['classification']
    total = sum(row['notes'] for row in classification['rules'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PhantomView setup proposal</title><style>
body{{font:16px/1.6 system-ui;background:#10141c;color:#e6ebf2;margin:32px}}
td,th{{padding:12px;text-align:left;border-bottom:1px solid #34404e}}
code{{overflow-wrap:anywhere}}a{{color:#71d7dc}}.draft{{color:#ffc36a}}
</style><h1>PhantomView setup proposal</h1>
<p>{esc(result['organization'])}</p><p class="draft">DRAFT · No live permissions changed.</p>
<p>Counterparts and the independent absolute human owner require source review.
Existing categories, role grants and exceptions are preserved. Proposed viewer scopes
are organization-only for the explicitly selected personas. No project or action grants are added.</p>
<table><tr><th>Human</th><th>Counterpart</th><th>Category eligibility</th>
<th>Registered channel types</th><th>Proposed scopes</th></tr>{rows}</table>
<p>Registered identity metadata is not proof of authentication or installed channel integration.
Email alone does not qualify. Category 0 does not grant actions or disclose secrets.</p>
<h2>Knowledge classification draft</h2><p>{total} eligible notes in
{len(classification['rules'])} exact folders; {classification['excluded_entries']} excluded entries.</p>
<p><a href="classification.html">Open folder review</a>. Confidential hints use category 3.
Every rule remains unapproved. No note bodies were read, no content hashes approved,
and no folder name establishes access.</p>
<h2>Snapshot binding</h2><p>Source: <code>{esc(result['source'])}</code></p>
<p>Canonical source revision: <code>{esc(result['source_revision'])}</code></p>
<p>Canonical collector revision: <code>{esc(result['collector_revision'])}</code></p>
<p>These fingerprints identify offline inputs; re-read and compare the live source before
any future migration. This tool has no apply operation. Live reader and native-channel
compatibility remain separate prerequisites.</p></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--org', required=True, type=Path)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--counterpart', action='append', default=[])
    parser.add_argument('--absolute-owner', required=True)
    parser.add_argument('--organization-persona', action='append', required=True)
    parser.add_argument('--output', required=True, type=Path,
                        help='New private directory outside the repository')
    args = parser.parse_args()
    import yaml

    repository = Path(__file__).resolve().parent.parent
    destination = args.output.resolve()
    if destination == repository or repository in destination.parents:
        parser.error('Private proposal output must be outside the repository')

    def read(path):
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Proposal input exceeds size limit')
        return data.decode('utf-8')

    result = prepare(yaml.safe_load(read(args.org)), json.loads(read(args.index)),
                     source=args.source, counterparts=args.counterpart,
                     absolute_owner=args.absolute_owner,
                     organization_personas=args.organization_persona)
    # Refuse existing directories; never overwrite a previous review or source.
    args.output.mkdir(mode=0o700)
    files = {'proposal.json': json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False),
             'proposed-org.json': json.dumps(result['proposed_org'], indent=2, ensure_ascii=True),
             'index.html': render_html(result),
             'classification.html': render_classification(result['classification'])}
    for name, content in files.items():
        with (args.output / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(content + '\n')
    print('Detached draft prepared; no live access changed. Keep output private.')


if __name__ == '__main__':
    main()
