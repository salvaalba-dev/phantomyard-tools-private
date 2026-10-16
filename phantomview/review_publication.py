"""Protected operator publication orchestration; never a browser actuator."""
import json

from projection_review import read_json, root_path, validate
from review_consumer import ApprovalConsumer
from scoped_backend import MAX_SCAN_BYTES
from scoped_knowledge import HEX
from source_adapter import encode


class PublicationOutcomeUnknown(RuntimeError):
    """The operator must inspect the pointer before attempting recovery."""


class PublicationCoordinator:
    def __init__(self, consumer):
        if not isinstance(consumer, ApprovalConsumer):
            raise ValueError('Publication requires the protected approval consumer')
        self.consumer, self.publisher, self.gate = consumer, consumer.publisher, consumer.gate

    def publish(self, headers, request_id, decisions, *, expected_revision):
        """Reconcile, audit intent, reauthorize at activation, and report the commit.

        Exact completed retries require current authority and protected receipts.
        Failed staging remains subject to explicit operator recovery.
        """
        if not isinstance(expected_revision, str) or not HEX.fullmatch(expected_revision):
            raise ValueError('An exact existing publication lease is required')
        headers = {'Cookie': headers.get('Cookie', '')}
        raw = encode(decisions)
        if len(raw) > MAX_SCAN_BYTES:
            raise ValueError('Approval decisions exceed bounds')
        decisions = json.loads(raw)
        reviewer = self.gate.identified_scope(headers)[0]
        proposal = self.consumer._proposal(request_id)
        active = self.publisher.active()[1]
        if active['revision'] != expected_revision:
            if active['previous_revision'] != expected_revision:
                raise ValueError('Publication lease no longer matches this request')
            metadata = {'request_id': request_id, 'review_revision': proposal['revision'],
                        'approval_revision': active['revision']}
            events = self.gate.audit.export()
            for event, status in (('review_approved', 'complete'), ('review_publish_requested', 'queued')):
                if not any(row['event'] == event and row['metadata'] == metadata | {'status': status}
                           for row in events):
                    raise PermissionError('Exact protected publication receipts are required for a completed retry')
            previous = validate(read_json(root_path(self.publisher.root / expected_revision) / 'approval.json'))
            if previous['revision'] != expected_revision:
                raise ValueError('Previous approval does not match the publication lease')
            result = self.consumer._prepare(headers, request_id, decisions, previous=previous, active=active)
            if result['approval'] != active:
                raise ValueError('Retry does not match the published approval')
            return self._complete(headers, result, replayed=True)

        result = self.consumer.prepare(headers, request_id, decisions)
        if result['approval']['previous_revision'] != expected_revision:
            raise ValueError('Approval does not extend the requested publication lease')
        self.gate.audit_event(headers, 'review_publish_requested', **self._metadata(result), status='queued')

        def authorize():
            if self.gate.identified_scope(headers)[0] != reviewer:
                raise PermissionError('Publication reviewer changed')
            if self.consumer.prepare(headers, request_id, decisions) != result:
                raise ValueError('Approval evidence changed before activation')

        warning = None
        try:
            self.publisher.publish(result['approval'], result['draft'],
                                   expected_revision=expected_revision, authorize=authorize)
        except Exception:
            # Even cleanup can fail after the atomic switch. Never report that as
            # an uncommitted transaction or automatically overwrite the pointer.
            try:
                pointer = read_json(root_path(self.publisher.root) / 'active.json')
            except (OSError, ValueError) as error:
                raise PublicationOutcomeUnknown(
                    'Inspect the active pointer before recovery; attempted revision: '
                    + result['approval']['revision']) from error
            if pointer != {'revision': result['approval']['revision']}:
                raise
            warning = 'Publisher raised after activation; inspect staging and writer lock before further publication'
        return self._complete(headers, result, replayed=False, warning=warning)

    @staticmethod
    def _metadata(result):
        receipt = result['receipt']
        return {'request_id': receipt['request_id'], 'review_revision': receipt['proposal_revision'],
                'approval_revision': receipt['approval_revision']}

    def _complete(self, headers, result, *, replayed, warning=None):
        audit_confirmed = True
        try:
            self.gate.audit_event(headers, 'review_published', **self._metadata(result), status='complete')
        except (OSError, ValueError):
            audit_confirmed = False
        return {'published': True, 'revision': result['approval']['revision'],
                'request_id': result['receipt']['request_id'], 'replayed': replayed,
                'audit_confirmed': audit_confirmed, 'publication_warning': warning}
