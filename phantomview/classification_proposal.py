"""Prepare folder classification drafts from metadata; never grant access."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path, PurePosixPath

from assistant_scope import Scope


def access_summary(preview, organization, categories):
    """Explain declared category grants, never authenticate or authorize a session."""
    if preview is None:
        return None
    if (preview.get('organization') != organization or preview.get('preview_only') is not True
            or preview.get('live_access_changed') is not False):
        raise ValueError('A matching inert access preview is required')
    scope = Scope(preview['policy'])
    if (scope.policy['organization'] != organization
            or preview.get('policy_revision') != scope.revision):
        raise ValueError('Access preview policy revision mismatch')
    zero = scope.policy.get('category_zero')
    if zero and set(zero['categories']) != set(categories):
        raise ValueError('Category declarations differ between the two previews')
    ordinary, absolute = [], []
    for human, binding in sorted(scope.policy['humans'].items()):
        row = {'human': human, 'counterpart': binding.get('counterpart_persona')}
        if scope.is_absolute(human):
            absolute.append(row)
        else:
            grants = scope.human_grants(human)
            row['categories'] = grants['categories'] if grants else []
            ordinary.append(row)
    return {'policy_revision': scope.revision, 'preview_only': True,
            'ordinary_humans': ordinary, 'absolute_humans': absolute,
            'personas': {key: [category for category in value['categories'] if category != 'category-0']
                         for key, value in sorted(scope.policy['personas'].items())}}


def suggest(folder, categories, confidential_category='category-2'):
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
        category = confidential_category
        reason = 'Confidential candidate under the selected existing category; check sensitive and project-specific exceptions.'
    elif parts[0] in {'finance', 'financial', 'accounting', 'finanzas', 'contabilidad'}:
        category = 'category-3'
        reason = 'Sensitive financial candidate; credentials must remain excluded regardless of category.'
    else:
        return None, 'inspect', 'No reliable folder-level hint; review before proposing a category.'
    if category not in categories:
        return None, 'inspect', 'The candidate category is not declared by this organization.'
    return category, 'confirm-content', reason


def build_proposal(inventory, access_preview=None, confidential_category='category-2'):
    """Return an inert draft with exact actor/folder boundaries and no recursion."""
    org = inventory.get('organization')
    categories = inventory.get('categories')
    if not isinstance(org, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', org):
        raise ValueError('An explicit organization ID is required')
    if not isinstance(categories, dict) or not categories:
        raise ValueError('Declared organization categories are required')
    if confidential_category not in {'category-2', 'category-3'}:
        raise ValueError('Confidential draft category must be category-2 or category-3')
    access = access_summary(access_preview, org, categories)
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
        category, review, reason = suggest(folder, categories, confidential_category)
        ident = hashlib.sha256(json.dumps([org, actor, folder]).encode()).hexdigest()[:16]
        rules.append({'id': ident, 'actor': actor, 'folder': folder, 'notes': notes,
                      'recursive': False, 'status': 'draft', 'approved': False,
                      'suggested_category': category, 'project': None,
                      'category_label': categories[category].get('label', '') if category else None,
                      'human_category_scope': ([row['human'] for row in access['ordinary_humans']
                                                if category in row['categories']] if access and category else []),
                      'review': review, 'reason': reason})
    rules.sort(key=lambda row: (row['actor'], row['folder']))
    return {'schema_version': 1, 'organization': org, 'status': 'draft',
            'source_generated_at': inventory.get('generated_at'),
            'default_access': 'deny', 'activation_supported': False,
            'confidential_draft_category': confidential_category,
            'categories': categories, 'rules': rules, 'access_preview': access,
            'excluded_entries': inventory.get('excluded_entries', 0),
            'review_requirements': [
                'Review the contents and exceptions before accepting any folder suggestion.',
                'Category zero is a human grant, never a document classification.',
                'No category ordering or automatic project inheritance.',
                'Category eligibility is not channel authentication, live access or project authorization.',
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
        row['category_label'] or 'Pending review', ', '.join(row['human_category_scope']) or 'Pending / none',
        row['review'], row['reason'])) + '</tr>' for row in proposal['rules'])
    total = sum(row['notes'] for row in proposal['rules'])
    requirements = ''.join(f'<li>{esc(text)}</li>' for text in proposal['review_requirements'])
    category_rows = ''.join(f'<tr><td>{esc(key)}</td><td>{esc(value.get("label", ""))}</td></tr>'
                            for key, value in proposal['categories'].items() if key != 'category-0')
    access = proposal.get('access_preview')
    if access:
        human_rows = ''.join('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in (
            row['human'], row['counterpart'] or 'None', ', '.join(row['categories']) or 'None')) + '</tr>'
            for row in access['ordinary_humans'])
        absolute = ', '.join(row['human'] for row in access['absolute_humans']) or 'None'
        persona_rows = ''.join(f'<tr><td>{esc(persona)}</td><td>{esc(", ".join(grants))}</td></tr>'
                               for persona, grants in access['personas'].items())
        access_html = f'''<h2>Category 0 · Absolute human information access</h2><p>{esc(absolute)}</p>
<p>This independent human privilege is not a document classification or a persona grant.</p>
<h2>Ordinary human category scope · proposed counterpart bindings</h2>
<p>Category eligibility only. Verified channel integration and project checks remain required.</p>
<table><tr><th>Human</th><th>Counterpart</th><th>Declared categories</th></tr>{human_rows}</table>
<h2>Persona grants from PhantomOrg</h2><table><tr><th>Persona</th><th>Declared categories</th></tr>{persona_rows}</table>'''
    else:
        access_html = '<p>Human scope has not been supplied. Category 0 remains an independent human privilege.</p>'
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
<h2>Existing PhantomOrg information categories</h2><table><tr><th>Category</th><th>Source meaning</th></tr>{category_rows}</table>
{access_html}<ul>{requirements}</ul><h2>Folder review</h2><table><thead><tr><th>Persona</th><th>Folder</th><th>Notes</th>
<th>Suggested category</th><th>Source meaning</th><th>Ordinary human category scope</th>
<th>Review</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--html', type=Path)
    parser.add_argument('--access-preview', type=Path,
                        help='Optional inert PhantomOrg access preview without channel identifiers')
    parser.add_argument('--confidential-category', choices=('category-2', 'category-3'), default='category-2',
                        help='Existing category to suggest for confidential folders; never activates access')
    args = parser.parse_args()
    access = json.loads(args.access_preview.read_text(encoding='utf-8-sig')) if args.access_preview else None
    proposal = build_proposal(json.loads(args.inventory.read_text(encoding='utf-8-sig')), access,
                              args.confidential_category)
    # Exclusive creation keeps prior review work intact.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(proposal, stream, ensure_ascii=False, indent=2)
    if args.html:
        with args.html.open('x', encoding='utf-8') as stream:
            stream.write(render_html(proposal))


if __name__ == '__main__':
    main()
