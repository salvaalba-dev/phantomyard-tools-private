"""Opt-in resource projection; authorize before loading, counting or searching.

Catalogs and loaders are operator-owned dependencies, never request JSON or
document frontmatter. No collector adapter or live activation is installed here.
"""
import json
import os
from pathlib import Path
import re
import stat

from identified_access import IdentifiedGate
from resource_review import revision
from scoped_knowledge import HEX, IDENTIFIER, digest, normalize
from viewer_modules import ModuleRegistry

KINDS = {'organization', 'department', 'role', 'persona', 'human', 'project', 'partner',
         'objective', 'task', 'document', 'knowledge', 'procedure', 'finding', 'component', 'relationship'}
MAX_RECORDS = 2000
MAX_RECORD_BYTES = 65536
MAX_SCAN_BYTES = 8 * 1024 * 1024


class ProjectionCatalog:
    def __init__(self, document):
        if (not isinstance(document, dict)
                or set(document) != {'schema_version', 'organization', 'status', 'resources', 'authority_revision'}
                or type(document['schema_version']) is not int or document['schema_version'] != 1
                or document['status'] != 'approved' or not isinstance(document['organization'], str)
                or not IDENTIFIER.fullmatch(document['organization'])
                or not isinstance(document['authority_revision'], str) or not HEX.fullmatch(document['authority_revision'])
                or not isinstance(document['resources'], list) or len(document['resources']) > MAX_RECORDS):
            raise ValueError('An approved private projection catalog is required')
        fields = {'id', 'kind', 'category', 'scope', 'project', 'secret', 'payload_sha256'}
        seen = {}
        for row in document['resources']:
            if (not isinstance(row, dict) or set(row) - fields - {'endpoints', 'requires'} or not fields <= set(row)
                    or not isinstance(row['id'], str) or not HEX.fullmatch(row['id'])
                    or row['id'] in seen or not isinstance(row['kind'], str) or row['kind'] not in KINDS
                    or not isinstance(row['payload_sha256'], str) or not HEX.fullmatch(row['payload_sha256'])
                    or not isinstance(row['category'], str) or not re.fullmatch(r'category-[1-9][a-z0-9_-]*', row['category'])
                    or type(row['secret']) is not bool
                    or not isinstance(row['scope'], dict) or set(row['scope']) != {'kind', 'id'}
                    or row['scope']['kind'] not in ('organization', 'department', 'project')
                    or not isinstance(row['scope']['id'], str) or not IDENTIFIER.fullmatch(row['scope']['id'])
                    or row['project'] is not None and (not isinstance(row['project'], str)
                                                       or not IDENTIFIER.fullmatch(row['project']))):
                raise ValueError('Invalid classified projection resource')
            if (row['scope']['kind'] == 'project' and row['project'] != row['scope']['id']
                    or row['scope']['kind'] != 'project' and row['project'] is not None):
                raise ValueError('Projection project must match its explicit scope')
            endpoints = row.get('endpoints')
            if row['kind'] == 'relationship':
                if (not isinstance(endpoints, list) or len(endpoints) != 2
                        or any(not isinstance(key, str) or not HEX.fullmatch(key) for key in endpoints)):
                    raise ValueError('Relationship endpoints must be explicit resource IDs')
            elif 'endpoints' in row:
                raise ValueError('Only relationships may declare graph endpoints')
            required = row.get('requires', [])
            if (not isinstance(required, list) or len(required) > 128
                    or any(not isinstance(key, str) or not HEX.fullmatch(key) for key in required)
                    or len(set(required)) != len(required)):
                raise ValueError('Derived-resource dependencies must be unique opaque IDs')
            seen[row['id']] = row
        for row in seen.values():
            if row['kind'] == 'relationship' and any(
                    key not in seen or seen[key]['kind'] == 'relationship' for key in row['endpoints']):
                raise ValueError('Relationships must reference declared nonrelationship resources')
            if any(key not in seen or seen[key]['kind'] == 'relationship' for key in row.get('requires', [])):
                raise ValueError('Derived resources must reference declared nonrelationship sources')
        self.document = json.loads(json.dumps(document, allow_nan=False))
        self.revision = revision(self.document)
        pending = sorted(self.document['resources'], key=lambda row: row['id'])
        self.ordered, ready = [], set()
        while pending:
            batch = [row for row in pending if all(key in ready for key in
                     row.get('requires', []) + row.get('endpoints', []))]
            if not batch:
                raise ValueError('Cyclic projection dependencies are not permitted')
            self.ordered.extend(batch)
            ready.update(row['id'] for row in batch)
            pending = [row for row in pending if row['id'] not in ready]


class PrivateRecordStore:
    """Fixed private export directory plus a fresh collector-selection manifest."""
    def __init__(self, root, manifest_loader, organization):
        self.root = Path(root)
        if (not self.root.is_absolute() or not self.root.is_dir() or self.root.is_symlink()
                or any(parent.is_symlink() for parent in self.root.parents)
                or not callable(manifest_loader) or not isinstance(organization, str)
                or not IDENTIFIER.fullmatch(organization)):
            raise ValueError('A fixed private record store and trusted manifest are required')
        self.manifest_loader, self.organization = manifest_loader, organization

    def __call__(self, ident):
        if not isinstance(ident, str) or not HEX.fullmatch(ident):
            raise ValueError('Invalid opaque resource ID')
        manifest = self.manifest_loader()
        if manifest.get('organization') != self.organization:
            return None
        rows = [row for row in manifest.get('resources', []) if row.get('id') == ident]
        if len(rows) != 1 or rows[0].get('available') is not True or rows[0].get('searchable') is not True:
            return None
        path = self.root / (ident + '.json')
        if path.is_symlink():
            return None
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        except OSError:
            return None
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return None
            return stream.read(MAX_RECORD_BYTES + 1)


class ScopedBackend:
    def __init__(self, gate, catalog_loader, record_loader, *, modules=(), default_report_loader=None):
        if not isinstance(gate, IdentifiedGate) or not callable(catalog_loader) or not callable(record_loader):
            raise ValueError('An identified gate and protected projection loaders are required')
        self.gate, self.catalog_loader, self.record_loader = gate, catalog_loader, record_loader
        self.modules = ModuleRegistry(modules)
        if default_report_loader is not None and not callable(default_report_loader):
            raise ValueError('A server-owned runtime default reader is required')
        self.default_report_loader = default_report_loader

    def workspace(self, headers):
        """Compile menus over one current authorized projection, never raw records."""
        recipient, directory = self.gate.identified_scope(headers)
        view = self.state(headers)
        try:
            report = self.default_report_loader() if self.default_report_loader else {}
        except (OSError, ValueError):
            report = {}  # Optional discovery failure cannot replace the identified issuer.
        navigation = self.modules.navigation(directory=directory, recipient=recipient,
                                             projection=view, default_report=report)
        current, _ = self.gate.identified_scope(headers)
        if current != recipient:
            raise ValueError('Session changed while compiling navigation')
        return dict(view, navigation=navigation)

    def state(self, headers):
        recipient, directory = self.gate.identified_scope(headers)
        catalog = ProjectionCatalog(self.catalog_loader())
        if catalog.document['organization'] != recipient.organization:
            raise ValueError('Projection catalog belongs to another organization')
        if catalog.document['authority_revision'] != directory.authority_revision:
            raise ValueError('Review projection classifications against the current authority')
        visible, raw_records, used = {}, {}, 0
        for row in catalog.ordered:
            classification = {'organization': recipient.organization,
                              **{key: row[key] for key in ('category', 'scope', 'project', 'secret')}}
            if not directory.permits(recipient, classification):
                continue
            if not all(key in visible for key in row.get('requires', [])):
                continue
            if row['kind'] == 'relationship' and not all(key in visible for key in row['endpoints']):
                continue  # Do not even load an edge touching a denied, stale or missing node.
            raw = self.record_loader(row['id'])
            if raw is None:
                continue
            if not isinstance(raw, bytes) or len(raw) > MAX_RECORD_BYTES:
                raise ValueError('Projection resource exceeds loader bounds')
            used += len(raw)
            if used > MAX_SCAN_BYTES:
                raise ValueError('Projection exceeds bounded scan; no partial result is released')
            if digest(raw) != row['payload_sha256']:
                continue
            record = json.loads(raw)
            if (not isinstance(record, dict) or set(record) != {'id', 'kind', 'data'}
                    or record['id'] != row['id'] or record['kind'] != row['kind']
                    or not isinstance(record['data'], dict)):
                continue
            # Reject NaN/Infinity and keep the returned data detached from loaders.
            json.dumps(record, allow_nan=False)
            if row['kind'] == 'relationship':
                data = record['data']
                if (set(data) != {'source', 'target', 'type', 'label'}
                        or [data['source'], data['target']] != row['endpoints']
                        or not isinstance(data['type'], str) or not isinstance(data['label'], str)):
                    continue
            visible[row['id']], raw_records[row['id']] = record, raw
        for ident, raw in raw_records.items():
            if self.record_loader(ident) != raw:
                raise ValueError('A selected resource changed or was excluded; refresh the view')
        current, _ = self.gate.identified_scope(headers)
        if current != recipient or ProjectionCatalog(self.catalog_loader()).revision != catalog.revision:
            raise ValueError('Session or projection classification changed')
        resources = [record for record in visible.values() if record['kind'] != 'relationship']
        relations = [record for record in visible.values() if record['kind'] == 'relationship']
        counts = {}
        for record in resources:
            counts[record['kind']] = counts.get(record['kind'], 0) + 1
        counts['relationship'] = len(relations)
        return {'schema_version': 1, 'organization': recipient.organization, 'scope_id': recipient.scope_id,
                'policy_revision': recipient.policy_revision, 'view_revision': revision(list(visible.values())),
                'resources': resources, 'relations': relations, 'counts': counts, 'complete_corpus': False}

    def detail(self, headers, ident):
        if not isinstance(ident, str) or not HEX.fullmatch(ident):
            raise KeyError('Resource unavailable')
        view = self.state(headers)
        return next((row for row in view['resources'] + view['relations'] if row['id'] == ident), None)

    def search(self, headers, query):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
            raise ValueError('Expected a search query of 1 to 200 characters')
        terms = normalize(query).split()[:12]
        if not terms:
            raise ValueError('A searchable query is required')
        view = self.state(headers)
        found = [row for row in view['resources'] + view['relations']
                 if all(term in normalize(json.dumps(row['data'], ensure_ascii=False)) for term in terms)]
        return {'results': found[:100], 'partial': len(found) > 100,
                **{key: view[key] for key in ('organization', 'scope_id', 'policy_revision', 'view_revision')},
                'scope': 'current identified resource projection', 'complete_corpus': False}
