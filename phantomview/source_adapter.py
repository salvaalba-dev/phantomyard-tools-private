"""Inert metadata adapter over selected collector snapshots; never grants access."""
import argparse
import json
import os
from pathlib import Path

from channel_identity import HumanDirectory
from resource_review import revision
from scoped_backend import MAX_RECORD_BYTES, MAX_RECORDS, MAX_SCAN_BYTES
from scoped_knowledge import digest

SECTIONS = {
    'organizations': ('organization', ('id', 'name', 'display_name', 'sector')),
    'departments': ('department', ('id', 'name')),
    'roles': ('role', ('id', 'name', 'description', 'functions')),
    'actors': ('persona', ('id', 'tools', 'installed', 'runtime', 'installation_label')),
    'humans': ('human', ('id', 'name', 'role')),
    'documents': ('document', ('slug', 'kind', 'integrity')),
}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def eligible(row):
    return (isinstance(row, dict) and ('searchable' not in row or row['searchable'] is True)
            and not row.get('unavailable') and row.get('secret') is not True
            and row.get('confidential') is not True
            and row.get('visibility') not in ('private', 'secret', 'restricted', 'confidential'))


def source_revision(collection, source):
    """Exclude only collector observation clocks, preserving substantive evidence."""
    if collection == 'actors' and isinstance(source.get('diagnostics'), dict):
        diagnostics = dict(source['diagnostics'])
        diagnostics.pop('checked_at', None)
        if isinstance(diagnostics.get('checks'), list):
            diagnostics['checks'] = [{key: value for key, value in check.items() if key != 'age_minutes'}
                                     if isinstance(check, dict) else check for check in diagnostics['checks']]
        source = source | {'diagnostics': diagnostics}
    return revision(source)


def clean(row, fields):
    output = {}
    for field in fields:
        value = row.get(field)
        if isinstance(value, str) and len(value) <= 4000:
            output[field] = value
        elif type(value) is bool or value is None:
            output[field] = value
        elif isinstance(value, list) and len(value) <= 128 and all(isinstance(item, str) and len(item) <= 500 for item in value):
            output[field] = list(value)
    return output


def prepare(snapshot, directory):
    """Create bounded draft records with raw-source fingerprints and no ACL grants.

    Findings/procedures retain source dependencies. KB bodies, diagnostics, source
    paths, installation inventory and history require separate reviewed adapters.
    """
    if not isinstance(directory, HumanDirectory) or not isinstance(snapshot, dict):
        raise ValueError('A trusted organization directory and selected collector snapshot are required')
    if len(encode(snapshot)) > MAX_SCAN_BYTES:
        raise ValueError('Selected snapshot exceeds adapter bounds')
    for collection in (*SECTIONS, 'findings', 'procedures', 'edges'):
        rows = snapshot.get(collection, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Collector collections must contain objects in lists')
    oid = directory.scope.policy['organization']
    organizations = [row for row in snapshot.get('organizations', []) if row.get('id') == oid]
    if len(organizations) != 1 or not eligible(organizations[0]):
        raise ValueError('Exactly one eligible selected organization is required')
    records, review, aliases, selected, omitted = {}, {}, {}, [], []

    def add(collection, identity, kind, source, data, requires=(), endpoints=None):
        if not isinstance(identity, str) or not identity or len(identity) > 512:
            raise ValueError('An explicit bounded source identity is required')
        ident = revision([oid, collection, identity])
        if ident in records:
            raise ValueError('Duplicate source identity; review ambiguous collector entries')
        record = {'id': ident, 'kind': kind, 'data': data}
        raw = encode(record)
        if len(raw) > MAX_RECORD_BYTES or len(records) >= MAX_RECORDS:
            raise ValueError('Adapted records exceed projection bounds')
        records[ident] = record
        row = {'id': ident, 'kind': kind, 'category': None, 'scope': None, 'project': None,
               'secret': None, 'payload_sha256': digest(raw),
               'provenance': {'collection': collection, 'identity': identity, 'source_sha256': source_revision(collection, source)}}
        if requires:
            row['requires'] = sorted(set(requires))
        if endpoints is not None:
            row['endpoints'] = endpoints
        review[ident] = row
        selected.append([collection, identity, source_revision(collection, source)])
        return ident

    for collection, (kind, fields) in SECTIONS.items():
        rows = snapshot.get(collection, [])
        if not isinstance(rows, list):
            raise ValueError('Collector collections must be lists')
        for source in rows:
            if not isinstance(source, dict):
                raise ValueError('Collector entries must be objects')
            owner = source.get('id') if collection == 'organizations' else source.get('org')
            if owner != oid:
                continue
            if not eligible(source):
                omitted.append({'collection': collection, 'reason': 'source-excluded'})
                continue
            identity = source.get('urn') if collection == 'documents' else source.get('id')
            data = clean(source, fields)
            data['title'] = next((source[key] for key in ('display_name', 'name', 'slug', 'id', 'urn')
                                  if isinstance(source.get(key), str) and source[key]), '')[:4000]
            ident = add(collection, identity, kind, source, data)
            alias = identity if collection in ('organizations', 'documents') else f'{oid}:{collection}:{identity}'
            if source.get('key', alias) != alias:
                raise ValueError('Collector key does not match its selected organization and identity')
            if alias in aliases:
                raise ValueError('Ambiguous source reference')
            aliases[alias] = ident

    def reference(value):
        if not isinstance(value, str) or not value:
            return None
        if value in aliases:
            return aliases[value]
        matches = [ident for alias, ident in aliases.items() if alias.startswith(oid + ':') and alias.endswith(':' + value)]
        return matches[0] if len(matches) == 1 else None

    for source in snapshot.get('findings', []):
        if not eligible(source) or source.get('org', oid) != oid:
            continue
        entity = source.get('entity')
        parent = aliases.get(entity) if isinstance(entity, str) else None
        if parent is None:
            omitted.append({'collection': 'findings', 'reason': 'unresolved-source'})
            continue
        identity = source.get('id') or revision([entity, source.get('severity'), source.get('title')])
        add('findings', identity, 'finding', source, clean(source, ('title', 'severity')), [parent])

    for source in snapshot.get('procedures', []):
        if not isinstance(source, dict) or source.get('org') != oid or not eligible(source):
            continue
        if source.get('source_note') or source.get('origin') == 'knowledge':
            omitted.append({'collection': 'procedures', 'reason': 'reviewed-kb-adapter-required'})
            continue
        dependencies = []
        if source.get('origin') == 'documents':
            parent = aliases.get(source.get('source_document', ''))
        elif source.get('origin') == 'organization':
            parent = aliases.get(oid)
        else:
            parent = None
        if parent is None:
            omitted.append({'collection': 'procedures', 'reason': 'unresolved-source'})
            continue
        dependencies.append(parent)
        steps, unresolved = [], False
        if not isinstance(source.get('steps', []), list):
            raise ValueError('Procedure steps must be a list')
        for step in source.get('steps', []):
            if not isinstance(step, dict):
                raise ValueError('Procedure steps must be objects')
            for field in ('actor', 'from', 'to'):
                if step.get(field):
                    target = reference(step[field])
                    if target is None:
                        unresolved = True
                    else:
                        dependencies.append(target)
            steps.append(clean(step, ('action', 'input', 'output')))
        if unresolved or len(set(dependencies)) > 128:
            omitted.append({'collection': 'procedures', 'reason': 'unresolved-step-dependency'})
            continue
        data = clean(source, ('title', 'description', 'kind', 'partial')) | {'steps': steps}
        add('procedures', source.get('id'), 'procedure', source, data, dependencies)

    for source in snapshot.get('edges', []):
        if not isinstance(source, dict) or not eligible(source) or source.get('org', oid) != oid:
            continue
        left, right = aliases.get(source.get('from')), aliases.get(source.get('to'))
        if left is None or right is None:
            omitted.append({'collection': 'edges', 'reason': 'unresolved-endpoint'})
            continue
        kind, label = source.get('type'), source.get('label', '')
        if not isinstance(kind, str) or not isinstance(label, str):
            raise ValueError('Relationship type and label must be strings')
        identity = source.get('id') or revision([source['from'], source['to'], kind, label])
        add('edges', identity, 'relationship', source,
            {'source': left, 'target': right, 'type': kind, 'label': label}, endpoints=[left, right])

    draft = {'schema_version': 1, 'organization': oid, 'status': 'draft', 'activation_supported': False,
             'authority_revision': directory.authority_revision, 'source_revision': revision(sorted(selected)),
             'resources': sorted(review.values(), key=lambda row: row['id']),
             'records': sorted(records.values(), key=lambda row: row['id']), 'omitted': omitted,
             'unsupported': ['knowledge-bodies', 'diagnostics', 'installation', 'history']}
    if len(encode(draft)) > MAX_SCAN_BYTES:
        raise ValueError('Private adapter draft exceeds output bounds')
    return draft


def write_draft(path, draft):
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink() or not path.parent.is_dir()
            or any(parent.is_symlink() for parent in path.parents)
            or draft.get('status') != 'draft' or draft.get('activation_supported') is not False):
        raise ValueError('A private absolute new output path and inert draft are required')
    raw = encode(draft) + b'\n'
    if len(raw) > MAX_SCAN_BYTES:
        raise ValueError('Adapter draft exceeds output bounds')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description='Prepare an inert projection review from a selected collector export')
    parser.add_argument('--snapshot', required=True, help='Trusted collector JSON snapshot')
    parser.add_argument('--organization', required=True, help='Trusted private PhantomOrg JSON source')
    parser.add_argument('--output', required=True, help='Absolute new private draft path')
    args = parser.parse_args()
    def read_json(path):
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_SCAN_BYTES + 1)
        if len(raw) > MAX_SCAN_BYTES:
            raise ValueError('Adapter input exceeds bounds')
        return json.loads(raw)
    source = read_json(args.snapshot)
    org = read_json(args.organization)
    draft = prepare(source.get('snapshot', source), HumanDirectory(org))
    write_draft(args.output, draft)


if __name__ == '__main__':
    main()
