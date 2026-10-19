"""Offline metadata review and atomic publication under a protected operator root.

No web routes, model tools or automatic classification are registered here.
Hashes provide consistency, not reviewer authentication. Root ownership and write
access are trusted deployment responsibilities.
"""
import json
import os
from pathlib import Path
import stat

from channel_identity import HumanDirectory
from resource_review import revision
from scoped_backend import MAX_SCAN_BYTES, PrivateRecordStore, ProjectionCatalog
from scoped_knowledge import HEX
from source_adapter import encode, prepare_like


def validate(bundle):
    fields = {'schema_version', 'sequence', 'previous_revision', 'reviewer',
              'organization_revision', 'draft_revision', 'decision_revision',
              'catalog', 'sources', 'revision'}
    if (not isinstance(bundle, dict) or not fields <= set(bundle)
            or set(bundle) - (fields | {'organization_links', 'profile_fields'})
            or 'organization_links' in bundle and bundle['organization_links'] is not True
            or 'profile_fields' in bundle and bundle['profile_fields'] is not True
            or type(bundle['schema_version']) is not int or bundle['schema_version'] != 1
            or type(bundle['sequence']) is not int or bundle['sequence'] < 1
            or not isinstance(bundle['reviewer'], str) or not bundle['reviewer']):
        raise ValueError('Invalid projection approval revision')
    for field in ('organization_revision', 'draft_revision', 'decision_revision', 'revision'):
        if not isinstance(bundle[field], str) or not HEX.fullmatch(bundle[field]):
            raise ValueError('Invalid approval fingerprint')
    parent = bundle['previous_revision']
    if (bundle['sequence'] == 1 and parent is not None
            or bundle['sequence'] > 1 and (not isinstance(parent, str) or not HEX.fullmatch(parent))):
        raise ValueError('Invalid projection history link')
    catalog = ProjectionCatalog(bundle['catalog'])
    sources = bundle['sources']
    if (not isinstance(sources, list) or len(sources) != len(catalog.document['resources'])
            or any(not isinstance(row, dict) or set(row) != {'id', 'provenance'} for row in sources)
            or [row['id'] for row in sources] != [row['id'] for row in catalog.document['resources']]):
        raise ValueError('Approval provenance must match the complete catalog')
    for row in sources:
        provenance = row['provenance']
        if (not isinstance(provenance, dict) or set(provenance) != {'collection', 'identity', 'source_sha256'}
                or any(not isinstance(provenance[key], str) or not provenance[key] for key in provenance)
                or not HEX.fullmatch(provenance['source_sha256'])):
            raise ValueError('Invalid approved source provenance')
    if revision({key: value for key, value in bundle.items() if key != 'revision'}) != bundle['revision']:
        raise ValueError('Approval revision does not match its contents')
    if len(encode(bundle)) > MAX_SCAN_BYTES:
        raise ValueError('Approval exceeds storage bounds')
    return json.loads(encode(bundle))


def approve(draft, decisions, org, snapshot_loader, *, reviewer, previous=None):
    """Bind explicit decisions to an exact current draft and full authority revision.

    The operator authenticates and authorizes the reviewer independently. Being a
    declared human, including category zero, does not grant this API to a caller.
    Every selected dependency must be explicitly included in the same approval.
    """
    directory = HumanDirectory(org)
    if not callable(snapshot_loader) or reviewer not in directory.scope.policy['humans']:
        raise ValueError('A trusted source loader and declared operator-supplied reviewer are required')
    if prepare_like(snapshot_loader(), directory, draft) != draft:
        raise ValueError('Draft differs from current selected sources; prepare and review it again')
    header = {'schema_version': 1, 'draft_revision': revision(draft), 'organization_revision': revision(org)}
    if (not isinstance(decisions, dict) or set(decisions) != set(header) | {'resources'}
            or type(decisions['schema_version']) is not int
            or any(decisions[key] != value for key, value in header.items())
            or not isinstance(decisions['resources'], list) or not decisions['resources']):
        raise ValueError('Explicit decisions must bind the exact draft and organization')
    candidates = {row['id']: row for row in draft['resources']}
    fields = {'id', 'payload_sha256', 'category', 'scope', 'project', 'secret'}
    rows, sources = [], []
    definitions = directory.scope.policy['view_access']['scope_definitions']
    categories = org['policies']['security_categories']
    for decision in decisions['resources']:
        if not isinstance(decision, dict) or set(decision) != fields or not isinstance(decision['id'], str):
            raise ValueError('Every selected resource needs a complete explicit classification')
        source = candidates.get(decision['id'])
        if source is None or decision['payload_sha256'] != source['payload_sha256']:
            raise ValueError('Decision does not match a fingerprinted candidate')
        row = {key: value for key, value in source.items() if key != 'provenance'} | decision
        # Shape validation follows below; policy validation never infers numeric hierarchy.
        scope = row['scope']
        if (not isinstance(row['category'], str) or row['category'] not in categories
                or row['category'] == 'category-0' or not isinstance(scope, dict)
                or definitions.get(scope.get('id'), {}).get('kind') != scope.get('kind')
                or row['category'].startswith('category-4') and row['project'] is None):
            raise ValueError('Classification must use an existing information category and exact scope')
        rows.append(row)
        sources.append({'id': source['id'], 'provenance': source['provenance']})
    catalog = {'schema_version': 1, 'organization': draft['organization'], 'status': 'approved',
               'authority_revision': directory.authority_revision, 'resources': sorted(rows, key=lambda row: row['id'])}
    ProjectionCatalog(catalog)
    parent, sequence = None, 1
    if previous is not None:
        old = validate(previous)
        if old['catalog']['organization'] != catalog['organization']:
            raise ValueError('Approval history belongs to another organization')
        parent, sequence = old['revision'], old['sequence'] + 1
    bundle = header | {'sequence': sequence, 'previous_revision': parent, 'reviewer': reviewer,
                       'decision_revision': revision(decisions | {'resources': sorted(decisions['resources'], key=lambda row: row['id'])}),
                       'catalog': catalog,
                       'sources': sorted(sources, key=lambda row: row['id'])}
    if draft.get('organization_links') is True:
        bundle['organization_links'] = True
    if draft.get('profile_fields') is True:
        bundle['profile_fields'] = True
    # Recheck sources after classification work; no stale approval is returned.
    if prepare_like(snapshot_loader(), HumanDirectory(org), draft) != draft:
        raise ValueError('Sources changed during review')
    bundle['revision'] = revision(bundle)
    return validate(bundle)


def root_path(root):
    path = Path(root)
    if (not path.is_absolute() or not path.is_dir() or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError('A protected absolute publication directory without symlink parents is required')
    return path


def read_json(path):
    if path.is_symlink():
        raise ValueError('Publication files cannot be symlinks')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Publication input must be a regular file')
        raw = stream.read(MAX_SCAN_BYTES + 1)
    if len(raw) > MAX_SCAN_BYTES:
        raise ValueError('Publication file exceeds bounds')
    return json.loads(raw)


def write_new(path, value):
    raw = encode(value)
    if len(raw) > MAX_SCAN_BYTES:
        raise ValueError('Publication file exceeds bounds')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


class PublishedProjection:
    """Protected loaders for ScopedBackend; payloads remain separate from metadata."""
    def __init__(self, root, org_loader, snapshot_loader):
        self.root = root_path(root)
        if not callable(org_loader) or not callable(snapshot_loader):
            raise ValueError('Trusted live organization and selected snapshot loaders are required')
        self.org_loader, self.snapshot_loader = org_loader, snapshot_loader

    def active(self):
        root_path(self.root)
        pointer = read_json(self.root / 'active.json')
        if (not isinstance(pointer, dict) or set(pointer) != {'revision'}
                or not isinstance(pointer['revision'], str) or not HEX.fullmatch(pointer['revision'])):
            raise ValueError('Invalid active projection pointer')
        generation = root_path(self.root / pointer['revision'])
        bundle = validate(read_json(generation / 'approval.json'))
        if bundle['revision'] != pointer['revision']:
            raise ValueError('Active projection revision mismatch')
        org = self.org_loader()
        draft = prepare_like(self.snapshot_loader(), HumanDirectory(org), bundle)
        if revision(org) != bundle['organization_revision'] or revision(draft) != bundle['draft_revision']:
            raise ValueError('Sources or authority changed; review and publish a new projection')
        return generation, bundle

    def catalog(self):
        return self.active()[1]['catalog']

    def record(self, ident):
        generation, bundle = self.active()
        manifest = {'organization': bundle['catalog']['organization'], 'resources': [
            {'id': row['id'], 'available': True, 'searchable': True} for row in bundle['catalog']['resources']]}
        return PrivateRecordStore(generation, lambda: manifest, manifest['organization'])(ident)

    def publish(self, bundle, draft, *, expected_revision, authorize=None):
        """CAS publication with an exclusive writer lock; never overwrite history.

        A crash can leave an inactive generation or lock. Recovery is an explicit
        operator action after checking no writer is running, never automatic.
        """
        bundle = validate(bundle)
        root_path(self.root)
        if authorize is not None:
            if not callable(authorize):
                raise ValueError('Publication authorization must be a trusted callable')
            authorize()
        if expected_revision is not None and (not isinstance(expected_revision, str) or not HEX.fullmatch(expected_revision)):
            raise ValueError('Expected publication revision must be an exact fingerprint')
        lock = self.root / 'publish.lock'
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            pointer = self.root / 'active.json'
            current = read_json(pointer) if pointer.exists() or pointer.is_symlink() else None
            if current != (None if expected_revision is None else {'revision': expected_revision}):
                raise ValueError('Active revision changed; publication lease rejected')
            if bundle['previous_revision'] != expected_revision:
                raise ValueError('Approval history does not extend the active revision')
            previous = None
            if current is not None:
                previous = validate(read_json(root_path(self.root / expected_revision) / 'approval.json'))
                if (bundle['sequence'] != previous['sequence'] + 1
                        or bundle['catalog']['organization'] != previous['catalog']['organization']):
                    raise ValueError('Publication must extend this organization history')
            org = self.org_loader()
            if (revision(org) != bundle['organization_revision'] or revision(draft) != bundle['draft_revision']
                    or prepare_like(self.snapshot_loader(), HumanDirectory(org), bundle) != draft):
                raise ValueError('Publication inputs changed after approval')
            decisions = {'schema_version': 1, 'draft_revision': bundle['draft_revision'],
                         'organization_revision': bundle['organization_revision'], 'resources': [
                {key: row[key] for key in ('id', 'payload_sha256', 'category', 'scope', 'project', 'secret')}
                for row in bundle['catalog']['resources']]}
            # Approval canonicalizes decisions by ID, independent of UI ordering.
            verified = approve(draft, decisions, org, self.snapshot_loader,
                               reviewer=bundle['reviewer'], previous=previous)
            if verified != bundle:
                raise ValueError('Publication does not match the reviewed classifications')
            candidates = {row['id']: row for row in draft['resources']}
            records = {row['id']: row for row in draft['records']}
            for row, source in zip(bundle['catalog']['resources'], bundle['sources']):
                candidate = candidates.get(row['id'])
                if (candidate is None or source['provenance'] != candidate['provenance']
                        or any(row.get(key) != candidate.get(key) for key in ('kind', 'payload_sha256', 'requires', 'endpoints'))):
                    raise ValueError('Approved provenance or dependency mismatch')
            generation = self.root / bundle['revision']
            generation.mkdir(mode=0o700)
            for row in bundle['catalog']['resources']:
                write_new(generation / (row['id'] + '.json'), records[row['id']])
            write_new(generation / 'approval.json', bundle)
            final_org = self.org_loader()
            if (revision(final_org) != bundle['organization_revision']
                    or prepare_like(self.snapshot_loader(), HumanDirectory(final_org), bundle) != draft):
                raise ValueError('Sources changed while staging publication')
            staged = self.root / 'active.next.json'
            write_new(staged, {'revision': bundle['revision']})
            if authorize is not None:
                authorize()
            os.replace(staged, pointer)
        finally:
            os.close(fd)
            lock.unlink()
