"""Protected operator approval consumer; no HTTP route or publication side effect."""
from dataclasses import fields
import json
import uuid

from authenticated_review import ReviewService
from channel_identity import HumanDirectory, Recipient
from projection_review import PublishedProjection, approve, read_json, root_path
from resource_review import revision
from scoped_backend import MAX_SCAN_BYTES
from scoped_knowledge import HEX
from session_audit import Ledger
from source_adapter import encode, prepare

CLASSIFICATION = ('category', 'scope', 'project', 'secret')


class ApprovalConsumer:
    def __init__(self, service, publisher):
        if (not isinstance(service, ReviewService) or not isinstance(publisher, PublishedProjection)
                or service.backend.catalog_loader != publisher.catalog or service.backend.record_loader != publisher.record):
            raise ValueError('Consumer requires the same protected published loaders as the review service')
        self.service, self.publisher, self.gate = service, publisher, service.gate

    def _proposal(self, request_id):
        if not isinstance(self.gate.audit, Ledger):
            raise ValueError('Protected audit evidence is required')
        if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
            raise ValueError('An exact proposal UUID is required')
        root_path(self.service.root)
        proposal = read_json(self.service.root / (request_id + '.json'))
        expected = {'schema_version', 'status', 'request_id', 'recipient', 'base_revision',
                    'view_revision', 'catalog_revision', 'changes', 'revision'}
        if (not isinstance(proposal, dict) or set(proposal) != expected
                or type(proposal['schema_version']) is not int or proposal['schema_version'] != 1
                or proposal['status'] != 'pending' or proposal['request_id'] != request_id
                or not isinstance(proposal['changes'], list) or not 1 <= len(proposal['changes']) <= 100
                or not isinstance(proposal['recipient'], dict)
                or set(proposal['recipient']) != {field.name for field in fields(Recipient)}):
            raise ValueError('Invalid pending proposal')
        for key in ('revision', 'base_revision', 'view_revision', 'catalog_revision'):
            if not isinstance(proposal[key], str) or not HEX.fullmatch(proposal[key]):
                raise ValueError('Invalid proposal revision')
        if revision({key: value for key, value in proposal.items() if key != 'revision'}) != proposal['revision']:
            raise ValueError('Proposal fingerprint does not match its contents')
        if not any(row['event'] == 'review_proposed' and row['metadata'].get('request_id') == request_id
                   and row['metadata'].get('review_revision') == proposal['revision']
                   and row['metadata'].get('status') == 'queued' for row in self.gate.audit.export()):
            raise PermissionError('An exact protected audit receipt is required before approval')
        return proposal

    def prepare(self, headers, request_id, decisions):
        """Approve explicit complete decisions under a current identified reviewer.

        The trusted operator supplies decisions after reviewing the whole current
        catalog. Neither a proposal nor category zero supplies implicit write rights.
        Returned artifacts are private, not browser credentials or signed authority.
        """
        return self._prepare(headers, request_id, decisions)

    def _prepare(self, headers, request_id, decisions, *, previous=None, active=None):
        """Internal reconciliation also supports an audited publication retry."""
        reviewer, directory = self.gate.identified_scope(headers)
        raw = encode(decisions)
        if len(raw) > MAX_SCAN_BYTES:
            raise ValueError('Approval decisions exceed bounds')
        decisions = json.loads(raw)  # Detach caller-owned mutable assignments before authorization.
        proposal = self._proposal(request_id)
        current_publication = self.publisher.active()[1]
        if previous is None:
            previous = current_publication
        if active is None:
            active = previous
        if current_publication != active:
            raise ValueError('Active publication changed during reconciliation')
        org = self.publisher.org_loader()
        if directory.revision != HumanDirectory(org).revision:
            raise ValueError('Reader and publication authority differ')
        actor = directory.validate(Recipient(**proposal['recipient']))
        if proposal['catalog_revision'] != revision(previous['catalog']):
            raise ValueError('Published catalog changed; obtain a fresh proposal')
        current_rows = {row['id']: row for row in previous['catalog']['resources']}
        changes = {}
        for change in proposal['changes']:
            if (not isinstance(change, dict) or set(change) != {'id', 'payload_sha256', 'from', 'to'}
                    or not isinstance(change['id'], str) or change['id'] in changes
                    or not isinstance(change['from'], dict) or set(change['from']) != set(CLASSIFICATION)
                    or not isinstance(change['to'], dict) or set(change['to']) != set(CLASSIFICATION)):
                raise ValueError('Invalid explicit proposal change')
            row = current_rows.get(change['id'])
            if (row is None or row['payload_sha256'] != change['payload_sha256']
                    or change['from'] != {key: row[key] for key in CLASSIFICATION}
                    or any(change['to'][key] != row[key] for key in ('scope', 'project', 'secret'))
                    or change['to']['category'] == row['category'] or change['to']['category'] == 'category-0'):
                raise ValueError('Proposal no longer matches its approved source classification')
            for assignment in (change['from'], change['to']):
                if not directory.allows_action(actor, 'resource.classify', row['scope']['id'],
                                               resource=assignment | {'organization': actor.organization}):
                    raise PermissionError('Proposer no longer has source and destination classification rights')
            changes[row['id']] = change['to']
        if not isinstance(decisions, dict) or not isinstance(decisions.get('resources'), list):
            raise ValueError('An explicit complete decision set is required')
        seen = set()
        for decision in decisions['resources']:
            if (not isinstance(decision, dict) or set(decision) != {'id', 'payload_sha256', *CLASSIFICATION}
                    or not isinstance(decision['id'], str) or decision['id'] in seen):
                raise ValueError('Unique complete reviewed classifications are required')
            row = current_rows.get(decision['id'])
            assignment = {key: decision[key] for key in CLASSIFICATION}
            if (row is None or decision['payload_sha256'] != row['payload_sha256']
                    or assignment != changes.get(decision['id'], {key: row[key] for key in CLASSIFICATION})):
                raise ValueError('Decisions must preserve unrelated classifications and match every proposed change')
            for value in ({key: row[key] for key in CLASSIFICATION}, assignment):
                if not directory.allows_action(reviewer, 'resource.classify', row['scope']['id'],
                                               resource=value | {'organization': reviewer.organization}):
                    raise PermissionError('Reviewer needs explicit read and classification authority for the complete catalog')
            seen.add(row['id'])
        if seen != set(current_rows):
            raise ValueError('Approval cannot silently add or remove catalog records')
        draft = prepare(self.publisher.snapshot_loader(), HumanDirectory(org))
        approval = approve(draft, decisions, org, self.publisher.snapshot_loader, reviewer=reviewer.human, previous=previous)
        current, _ = self.gate.identified_scope(headers)
        if (current != reviewer or self.publisher.active()[1] != active or self._proposal(request_id) != proposal):
            raise ValueError('Session, source publication or proposal changed during approval')
        self.gate.audit_event(headers, 'review_approved', request_id=request_id,
                              review_revision=proposal['revision'], approval_revision=approval['revision'], status='complete')
        return {'approval': approval, 'draft': draft, 'receipt': {
            'request_id': request_id, 'proposal_revision': proposal['revision'], 'approval_revision': approval['revision']}}
