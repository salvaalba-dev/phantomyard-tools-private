"""Offline, operator-controlled review records for selected KB resources.

No HTTP routes, model tools or live configuration changes are registered here.
Hashes detect changes; they do not authenticate a reviewer. The application must
protect both review inputs and stored revisions from browser and model writers.
"""
import json
import os
from pathlib import Path, PurePosixPath
import stat

from assistant_scope import Scope
from scoped_knowledge import Catalog, HEX, MAX_PAYLOAD_BYTES, digest

MAX_REVISION_BYTES = 1024 * 1024


def revision(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def source_key(organization, actor, path):
    """Stable source identity across content updates, distinct from payload IDs."""
    return revision([organization, actor, path])


def _policy(org):
    scope = Scope.from_org(org)
    if 'view_access' not in scope.policy:
        raise ValueError('Explicit PhantomOrg scopes are required before resource review')
    return scope


def _classifications(catalog, org, scope):
    definitions = scope.policy['view_access']['scope_definitions']
    categories = org['policies']['security_categories']
    if catalog['organization'] != scope.policy['organization']:
        raise ValueError('Resource organization does not match PhantomOrg')
    for row in catalog['resources']:
        assigned = row.get('scope')
        if (row['actor'] not in scope.policy['personas'] or row['category'] not in categories
                or not isinstance(assigned, dict)
                or definitions.get(assigned['id'], {}).get('kind') != assigned['kind']):
            raise ValueError('Every reviewed resource needs an existing actor, category and exact scope')
        project = row['project']
        if (assigned['kind'] == 'project' and project != assigned['id']
                or assigned['kind'] != 'project' and project is not None
                or row['category'].startswith('category-4') and project is None):
            raise ValueError('Project classification must match an explicit project scope')


def _current(row, organization, snapshot, note_loader):
    matches = [(actor, note) for actor in snapshot.get('actors', [])
               for note in actor.get('knowledge', []) if note.get('id') == row['id']]
    if len(matches) != 1:
        raise ValueError('Reviewed source is missing or ambiguous in the current snapshot')
    actor, note = matches[0]
    if (actor.get('org') != organization or actor.get('id') != row['actor']
            or actor.get('searchable') is not True or note.get('searchable') is not True
            or note.get('unavailable') or note.get('path') != row['path']):
        raise ValueError('Reviewed source is excluded or no longer matches its provenance')
    raw = note_loader(row['id'])
    if (not isinstance(raw, bytes) or len(raw) > MAX_PAYLOAD_BYTES
            or digest(raw) != row['payload_sha256']):
        raise ValueError('Reviewed content changed or became unavailable; prepare a fresh review')
    payload = json.loads(raw)
    if (not isinstance(payload, dict) or payload.get('id') != row['id']
            or payload.get('actor') != f"{organization}:actors:{row['actor']}"
            or payload.get('path') != row['path'] or payload.get('truncated') is not False
            or not isinstance(payload.get('content'), str)
            or not isinstance(payload.get('title'), str) or len(payload['title']) > 500):
        raise ValueError('Reviewed payload identity is invalid or incomplete')


def decisions_from_folders(draft, org, review):
    """Expand an exact-folder human review over one fingerprinted batch only.

    The caller records decisions after reviewing every selected folder's current
    contents. No recursion, folder-name inference or future-content approval.
    """
    scope = _policy(org)
    header = {'schema_version': 1, 'review_revision': revision(draft),
              'organization_revision': revision(org), 'policy_revision': scope.revision}
    if (not isinstance(review, dict) or set(review) != set(header) | {'rules'}
            or any(review[key] != value for key, value in header.items())
            or type(review['schema_version']) is not int or not isinstance(review['rules'], list)):
        raise ValueError('Folder review must bind the exact draft and authoritative organization')
    rules = {}
    fields = {'actor', 'folder', 'category', 'scope', 'project', 'secret', 'reviewed'}
    for rule in review['rules']:
        if (not isinstance(rule, dict) or set(rule) != fields or rule['reviewed'] is not True
                or not isinstance(rule['actor'], str) or not isinstance(rule['folder'], str)):
            raise ValueError('Explicit reviewed exact-folder decisions are required')
        path = PurePosixPath(rule['folder'])
        if (str(path) != rule['folder'] or path.is_absolute() or '..' in path.parts
                or not path.parts or path.parts[0] != 'kb' or '\\' in rule['folder']):
            raise ValueError('Expected a canonical relative KB folder')
        key = (rule['actor'], rule['folder'])
        if key in rules:
            raise ValueError('Duplicate folder review')
        rules[key] = rule
    rows, used = [], set()
    for row in draft.get('resources', []):
        key = (row.get('actor'), str(PurePosixPath(row.get('path', '')).parent))
        if key not in rules:
            continue
        used.add(key)
        rows.append({field: rules[key][field] for field in ('category', 'scope', 'project', 'secret')}
                    | {'id': row['id'], 'payload_sha256': row['payload_sha256']})
    if used != set(rules) or not rows:
        raise ValueError('Every reviewed folder must select current fingerprinted candidates')
    decisions = header | {'resources': rows}
    # Reuse approval validation for payload and provenance checks when publishing.
    return json.loads(json.dumps(decisions))


def approve_review(draft, decisions, org, snapshot_loader, note_loader, *, reviewer, previous=None):
    """Build an immutable review revision from explicit, independently reviewed decisions.

    This is a trusted operator boundary, not authorization for a browser caller.
    Partial batches are allowed; omitted notes receive no approval. No previous
    classifications are carried forward implicitly, including changed content.
    """
    scope = _policy(org)
    if (not isinstance(draft, dict) or draft.get('status') != 'draft'
            or set(draft) != {'schema_version', 'organization', 'status', 'resources'}):
        raise ValueError('A fingerprinted resource review draft is required')
    if any(row.get('secret') is not None for row in draft['resources']):
        raise ValueError('Draft secret reviews must remain unset')
    Catalog(draft | {'status': 'approved', 'resources': [row | {'secret': False} for row in draft['resources']]})
    if draft['organization'] != scope.policy['organization']:
        raise ValueError('Draft organization does not match PhantomOrg')
    if (not isinstance(decisions, dict)
            or set(decisions) != {'schema_version', 'review_revision', 'policy_revision', 'organization_revision', 'resources'}
            or type(decisions['schema_version']) is not int or decisions['schema_version'] != 1
            or decisions['review_revision'] != revision(draft)
            or decisions['policy_revision'] != scope.revision
            or decisions['organization_revision'] != revision(org)
            or not isinstance(decisions['resources'], list) or not decisions['resources']):
        raise ValueError('Explicit decisions must bind the current draft and policy revisions')
    if reviewer not in scope.policy['humans']:
        raise ValueError('Record a declared human reviewer supplied by the trusted operator')
    candidates = {row['id']: row for row in draft['resources']}
    rows = []
    fields = {'id', 'payload_sha256', 'category', 'scope', 'project', 'secret'}
    for decision in decisions['resources']:
        if not isinstance(decision, dict) or set(decision) != fields:
            raise ValueError('Every decision needs an explicit category, scope, project and secret review')
        candidate = candidates.get(decision['id'])
        if candidate is None or decision['payload_sha256'] != candidate['payload_sha256']:
            raise ValueError('Decision does not bind a fingerprinted candidate revision')
        rows.append(candidate | decision)
    rows.sort(key=lambda row: (row['actor'], row['path']))
    catalog = Catalog(draft | {'status': 'approved', 'resources': rows}).resources()
    _classifications(catalog, org, scope)
    for row in rows:
        _current(row, catalog['organization'], snapshot_loader(), note_loader)
    parent, sequence = None, 1
    if previous is not None:
        # Historical policy changes do not erase earlier review records.
        validated = _validate(previous)
        if validated['catalog']['organization'] != catalog['organization']:
            raise ValueError('Previous review belongs to another organization')
        parent, sequence = previous['revision'], previous['sequence'] + 1
    bundle = {
        'schema_version': 1, 'sequence': sequence, 'previous_revision': parent,
        'organization_revision': revision(org), 'policy_revision': scope.revision,
        'review_revision': revision(draft), 'decision_revision': revision(decisions),
        'reviewer': reviewer, 'catalog': catalog,
        'sources': [{'source_key': source_key(catalog['organization'], row['actor'], row['path']),
                     'id': row['id'], 'payload_sha256': row['payload_sha256']} for row in rows],
    }
    # Detect exclusions or content changes while preparing the batch.
    for row in rows:
        _current(row, catalog['organization'], snapshot_loader(), note_loader)
    bundle['revision'] = revision(bundle)
    _validate(bundle)
    return bundle


def _validate(bundle):
    fields = {'schema_version', 'sequence', 'previous_revision', 'organization_revision',
              'policy_revision', 'review_revision', 'decision_revision', 'reviewer',
              'catalog', 'sources', 'revision'}
    if (not isinstance(bundle, dict) or set(bundle) != fields
            or type(bundle['schema_version']) is not int or bundle['schema_version'] != 1
            or type(bundle['sequence']) is not int or bundle['sequence'] < 1
            or not isinstance(bundle['reviewer'], str) or not bundle['reviewer']
            or not isinstance(bundle['sources'], list)):
        raise ValueError('Invalid versioned resource review')
    for field in ('organization_revision', 'policy_revision', 'review_revision', 'decision_revision', 'revision'):
        if not isinstance(bundle[field], str) or not HEX.fullmatch(bundle[field]):
            raise ValueError('Invalid review revision digest')
    parent = bundle['previous_revision']
    if (bundle['sequence'] == 1 and parent is not None
            or bundle['sequence'] > 1 and (not isinstance(parent, str) or not HEX.fullmatch(parent))):
        raise ValueError('Invalid review history link')
    if revision({key: value for key, value in bundle.items() if key != 'revision'}) != bundle['revision']:
        raise ValueError('Resource review revision does not match its contents')
    catalog = Catalog(bundle['catalog']).resources()
    expected = [{'source_key': source_key(catalog['organization'], row['actor'], row['path']),
                 'id': row['id'], 'payload_sha256': row['payload_sha256']} for row in catalog['resources']]
    if bundle['sources'] != expected:
        raise ValueError('Source provenance does not match reviewed resources')
    return json.loads(json.dumps(bundle))


def reviewed_catalog(bundle, org):
    """Materialize a protected revision for retrieval only under unchanged authority."""
    validated = _validate(bundle)
    scope = _policy(org)
    if validated['policy_revision'] != scope.revision or validated['organization_revision'] != revision(org):
        raise ValueError('PhantomOrg changed; review classifications against the current authority')
    _classifications(validated['catalog'], org, scope)
    return validated['catalog']


def _root(root):
    path = Path(root)
    if (not path.is_absolute() or not path.is_dir() or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError('A fixed private revision directory without symlink parents is required')
    return path


def save_revision(root, bundle):
    """Exclusively create a bounded revision; never replace history or activate it.

    The operator must protect directory ownership/ACLs (including on Windows).
    There is no active pointer, rollback executor or authority signature here.
    """
    validated = _validate(bundle)
    raw = json.dumps(validated, sort_keys=True, indent=2, allow_nan=False).encode() + b'\n'
    if len(raw) > MAX_REVISION_BYTES:
        raise ValueError('Resource review revision exceeds storage bounds')
    path = _root(root) / (validated['revision'] + '.json')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def load_revision(root, ident, org):
    if not isinstance(ident, str) or not HEX.fullmatch(ident):
        raise ValueError('Expected an opaque review revision')
    path = _root(root) / (ident + '.json')
    if path.is_symlink():
        raise ValueError('Review revision cannot be a symlink')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Review revision must be a regular file')
        raw = stream.read(MAX_REVISION_BYTES + 1)
    if len(raw) > MAX_REVISION_BYTES:
        raise ValueError('Resource review revision exceeds storage bounds')
    bundle = json.loads(raw)
    reviewed_catalog(bundle, org)
    if bundle['revision'] != ident:
        raise ValueError('Requested review revision does not match the stored record')
    return bundle
