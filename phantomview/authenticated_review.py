"""Authenticated, audited reclassification proposals; never publishes a catalog."""
import uuid
from itertools import islice

from projection_review import read_json, root_path, write_new
from resource_review import revision
from scoped_backend import MAX_SCAN_BYTES, ProjectionCatalog, ScopedBackend
from session_audit import Ledger
from source_adapter import encode


class ReviewService:
    def __init__(self, backend, root):
        if not isinstance(backend, ScopedBackend) or not isinstance(backend.gate.audit, Ledger):
            raise ValueError('Review requires a scoped backend and protected session audit ledger')
        self.backend, self.gate, self.root = backend, backend.gate, root_path(root)

    def _context(self, headers):
        recipient, directory = self.gate.identified_scope(headers)
        grants = directory.scope.policy['view_access']['human_action_grants'].get(recipient.human, {})
        if not grants.get('resource.classify'):
            raise PermissionError('Explicit classification authority required')
        catalog = ProjectionCatalog(self.backend.catalog_loader())
        view = self.backend.state(headers)
        visible = {row['id']: row for row in view['resources'] + view['relations']}
        candidates = []
        for row in catalog.document['resources']:
            if row['id'] not in visible:
                continue
            resource = {'organization': recipient.organization, **{
                key: row[key] for key in ('category', 'scope', 'project', 'secret')}}
            if not directory.allows_action(recipient, 'resource.classify', row['scope']['id'], resource=resource):
                continue
            categories = [category for category in directory.scope.policy['personas'][recipient.persona]['categories']
                          if category != 'category-0' and category != row['category'] and directory.allows_action(
                              recipient, 'resource.classify', row['scope']['id'], resource=resource | {'category': category})]
            if directory.scope.is_absolute(recipient.human):
                categories = [category for category in directory.scope.policy['category_zero']['categories']
                              if category != 'category-0' and category != row['category'] and directory.allows_action(
                                  recipient, 'resource.classify', row['scope']['id'], resource=resource | {'category': category})]
            if categories:
                candidates.append({key: row[key] for key in ('id', 'kind', 'category', 'scope', 'project', 'secret', 'payload_sha256')}
                                  | {'allowed_categories': sorted(categories), 'data': visible[row['id']]['data']})
        current, _ = self.gate.identified_scope(headers)
        if current != recipient or ProjectionCatalog(self.backend.catalog_loader()).revision != catalog.revision:
            raise ValueError('Review authority or catalog changed')
        if not candidates:
            raise PermissionError('No visible resources have an authorized category change')
        response = {'schema_version': 1, 'organization': recipient.organization, 'scope_id': recipient.scope_id,
                    'base_revision': revision({'authority_revision': directory.authority_revision, 'resources': candidates}),
                    'view_revision': view['view_revision'], 'resources': candidates}
        if len(encode(response)) > MAX_SCAN_BYTES:
            raise ValueError('Review projection exceeds bounds')
        return recipient, response, catalog.revision

    def view(self, headers):
        return self._context(headers)[1]

    def propose(self, headers, body):
        fields = {'request_id', 'base_revision', 'view_revision', 'changes'}
        if (not isinstance(body, dict) or set(body) != fields or not isinstance(body['request_id'], str)
                or str(uuid.UUID(body['request_id'])) != body['request_id']
                or not isinstance(body['changes'], list) or not 1 <= len(body['changes']) <= 100):
            raise ValueError('A bounded explicit review proposal is required')
        recipient, view, catalog_revision = self._context(headers)
        if any(body[key] != view[key] for key in ('base_revision', 'view_revision')):
            raise ValueError('Review is stale; refresh current records')
        candidates = {row['id']: row for row in view['resources']}
        changes, seen = [], set()
        for change in body['changes']:
            if (not isinstance(change, dict) or set(change) != {'id', 'payload_sha256', 'category'}
                    or not isinstance(change['id'], str) or change['id'] in seen):
                raise ValueError('Unique fingerprinted category decisions are required')
            row = candidates.get(change['id'])
            if (row is None or change['payload_sha256'] != row['payload_sha256']
                    or change['category'] not in row['allowed_categories']):
                raise PermissionError('Proposed resource or category is unavailable')
            seen.add(change['id'])
            changes.append({'id': row['id'], 'payload_sha256': row['payload_sha256'],
                            'from': {key: row[key] for key in ('category', 'scope', 'project', 'secret')},
                            'to': {key: row[key] for key in ('scope', 'project', 'secret')} | {'category': change['category']}})
        proposal = {'schema_version': 1, 'status': 'pending', 'request_id': body['request_id'],
                    'recipient': recipient.metadata(), 'base_revision': view['base_revision'],
                    'view_revision': view['view_revision'], 'catalog_revision': catalog_revision,
                    'changes': sorted(changes, key=lambda row: row['id'])}
        proposal['revision'] = revision(proposal)
        root_path(self.root)
        target = self.root / (body['request_id'] + '.json')
        if not target.exists() and sum(1 for _ in islice(self.root.iterdir(), 1000)) >= 1000:
            raise OSError('Review queue requires operator maintenance')
        self.gate.audit_event(headers, 'review_requested', request_id=body['request_id'], status='queued')
        try:
            write_new(target, proposal)
        except FileExistsError:
            if read_json(target) != proposal:
                raise ValueError('Review request conflicts with an existing proposal') from None
        # Storage alone is not acceptance. Recheck policy, content and grants before acknowledgement.
        current, checked, current_catalog = self._context(headers)
        if current != recipient or checked != view or current_catalog != catalog_revision:
            raise ValueError('Review changed while recording the proposal')
        self.gate.audit_event(headers, 'review_proposed', request_id=body['request_id'], status='queued')
        return {'request_id': body['request_id'], 'status': 'pending', 'published': False}
