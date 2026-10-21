"""Prepare document refresh batches without changing publication or native history."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

from working_documents import bindings, collect, current_nodes

FORMATS = {'markdown', 'text/plain', 'html-text', 'application/pdf', 'image/png', 'image/jpeg'}
MAX_DOCUMENTS = 16  # The existing collector binding limit also applies to batches.


def fingerprint(value):
    """Bind a plan to exact structured inputs, excluding observation clocks."""
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _matrix(value, organization):
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'organization', 'documents'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['organization'] != organization or not isinstance(value['documents'], list)
            or len(value['documents']) > MAX_DOCUMENTS):
        raise ValueError('A bounded document matrix for the selected organization is required')
    result = {}
    prefix = 'urn:' + organization + ':doc:'
    for row in value['documents']:
        if (not isinstance(row, dict) or not {'urn', 'actor', 'category', 'format'} <= set(row)
                or set(row) - {'urn', 'actor', 'category', 'format', 'display'}
                or not isinstance(row['urn'], str) or not row['urn'].startswith(prefix)
                or len(row['urn']) <= len(prefix) or len(row['urn']) > 512
                or row['urn'] in result
                or not isinstance(row['actor'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', row['actor'])
                or not isinstance(row['category'], str) or not row['category'] or len(row['category']) > 100
                or not isinstance(row['format'], str) or row['format'] not in FORMATS):
            raise ValueError('Matrix entries need unique documents and explicit persona, category and format')
        # Reuse the collector schema, including binary display metadata checks.
        sample = {key: copy.deepcopy(item) for key, item in row.items() if key != 'category'}
        bindings([sample | {'sha256': '0' * 64, 'original': True}])
        result[row['urn']] = row
    return result


def prepare(manifest, source, matrix, actors, permitted, previous=None):
    """Resolve selected revisions and prepare a deterministic, inert batch.

    Matrix categories are assertions about the native source, never ACL grants.
    The caller supplies the existing collector eligibility predicate. The normal
    PhantomOrg projection review and publication remain mandatory downstream.
    """
    organization = manifest.get('manifest', {}).get('org')
    if not isinstance(organization, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}', organization):
        raise ValueError('An explicit native organization is required')
    selected = _matrix(matrix, organization)
    previous = [] if previous is None else previous
    prior = {row['urn']: row for row in bindings(previous)}
    nodes = current_nodes(manifest)  # Invalid lineage aborts the entire plan.
    documents = {row['urn']: row for row in nodes if row.get('kind') == 'doc'}
    prepared, pending = [], []
    for urn, node in sorted(documents.items()):
        # Do not expose the identities of hidden or ineligible native records.
        if (not permitted(node) or node.get('secret') is True or node.get('confidential') is True
                or node.get('visibility') in {'private', 'secret', 'restricted', 'confidential'}):
            continue
        row = selected.get(urn)
        if row is None:
            pending.append({'urn': urn, 'reason': 'not-in-matrix'})
            continue
        if node.get('category') != row['category']:
            pending.append({'urn': urn, 'reason': 'classification-changed'})
            continue
        content_hash = node.get('contentHash')
        if not isinstance(content_hash, str) or re.fullmatch(r'[a-f0-9]{64}', content_hash) is None:
            pending.append({'urn': urn, 'reason': 'missing-content-fingerprint'})
            continue
        binding = {key: copy.deepcopy(item) for key, item in row.items() if key != 'category'}
        binding.update(sha256=content_hash, original=True)
        try:
            # All existing owner, path, size, hash, format and secret checks apply.
            payload = collect(manifest, source, [binding], actors, permitted)[urn]
        except (ValueError, OSError, UnicodeError):
            # Errors can contain private paths or source content; report a fixed code.
            pending.append({'urn': urn, 'reason': 'source-validation-failed'})
            continue
        prepared.append({'urn': urn, 'category': row['category'], 'binding': binding,
                         'action': 'unchanged' if prior.get(urn) == binding else 'refresh' if urn in prior else 'add',
                         'payload_sha256': fingerprint(payload)})
    for urn in sorted(set(selected) - set(documents)):
        pending.append({'urn': urn, 'reason': 'missing-native-document'})
    removed = sorted(set(prior) - set(selected))
    excluded = sorted(set(prior) - {row['urn'] for row in prepared})
    inputs = {'manifest': fingerprint(manifest), 'matrix': fingerprint(matrix),
              'actors': fingerprint(actors), 'previous': fingerprint(previous)}
    return {'schema_version': 1, 'organization': organization, 'input_revisions': inputs,
            'prepared': prepared, 'pending': sorted(pending, key=lambda row: row['urn']),
            'removed_bindings': removed, 'excluded_bindings': excluded, 'publication_required': True,
            'mutations_performed': False}


def main(argv=None):
    """Print a private plan from protected snapshots; never apply it implicitly."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, help='Selected native JSON or YAML manifest')
    parser.add_argument('--matrix', required=True, help='Protected organization document matrix')
    parser.add_argument('--snapshot', required=True, help='Existing collector snapshot containing personas')
    parser.add_argument('--config', required=True, help='Existing collector configuration containing prior bindings')
    args = parser.parse_args(argv)
    from organization_authority import _parse, _read
    from phantomview import search_policy

    def load(filename):
        path = Path(filename).absolute()
        if path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
            raise ValueError('Structured snapshot files must use JSON or YAML')
        return _parse(_read(path), path.suffix.lower())

    manifest, matrix, snapshot, config = [load(path) for path in
                                         (args.manifest, args.matrix, args.snapshot, args.config)]
    if (not isinstance(snapshot, dict) or not isinstance(snapshot.get('actors'), list)
            or not isinstance(config, dict)):
        raise ValueError('A collector snapshot and configuration are required')
    plan = prepare(manifest, args.manifest, matrix, snapshot['actors'], search_policy,
                   config.get('working_documents', []))
    print(json.dumps(plan, sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
