"""Audited proposal -> explicit full review -> approved revision -> publication."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from authenticated_review import ReviewService
from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from projection_review import PublishedProjection, approve
from resource_review import revision
from review_consumer import ApprovalConsumer
from scoped_backend import ScopedBackend
from session_audit import Ledger
from source_adapter import prepare
from test_access_gate import ACCESS
from test_channel_identity import context
from test_source_adapter import snapshot
from test_view_permissions import scoped_organization


class ApprovalConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.org, self.source = scoped_organization(), snapshot()
        self.org['policies']['access_levels']['board']['categories'].append(3)
        self.org['policies']['phantomview']['human_action_grants']['secretary']['resource.classify'] = ['example']
        self.draft = prepare(self.source, HumanDirectory(self.org))
        self.initial_decisions = {'schema_version': 1, 'draft_revision': revision(self.draft),
                                  'organization_revision': revision(self.org), 'resources': [
            {'id': row['id'], 'payload_sha256': row['payload_sha256'], 'category': 'category-1',
             'scope': {'kind': 'organization', 'id': 'example'}, 'project': None, 'secret': False}
            for row in self.draft['resources']]}
        self.spool = self.root / 'spool'
        self.spool.mkdir()
        self.seed('publication')
        self.authenticate()

    def seed(self, folder, project_record=False):
        root = self.root / folder
        root.mkdir()
        decisions = copy.deepcopy(self.initial_decisions)
        if project_record:
            doc = next(row['id'] for row in self.draft['resources'] if row['kind'] == 'document')
            row = next(row for row in decisions['resources'] if row['id'] == doc)
            row.update(scope={'kind': 'project', 'id': 'river-project'}, project='river-project')
            self.initial_decisions = decisions
        self.previous = approve(self.draft, decisions, self.org, lambda: self.source, reviewer='secretary')
        self.publisher = PublishedProjection(root, lambda: self.org, lambda: self.source)
        self.publisher.publish(self.previous, self.draft, expected_revision=None)

    def authenticate(self, sender='102'):
        self.gate = IdentifiedGate(ACCESS, {'identities': ['a' * 64], 'actor': 'administrator'},
                                   'https://view.example', 8789, audit=Ledger(self.root / 'audit.sqlite'),
                                   directory_loader=lambda: HumanDirectory(self.org))
        link = self.gate.issue_identified('Nostr test-signed-event', self.gate.origin,
                                          **context(sender, 'administrator'), scope_id='example')
        self.headers = {'Cookie': 'phantomview=' + self.gate.redeem(link.split('#c=')[1])}
        self.backend = ScopedBackend(self.gate, self.publisher.catalog, self.publisher.record)
        self.service = ReviewService(self.backend, self.spool)
        self.consumer = ApprovalConsumer(self.service, self.publisher)

    def propose(self):
        view = self.service.view(self.headers)
        self.changed = next(row for row in view['resources'] if row['kind'] == 'persona')
        self.request_id = str(uuid.uuid4())
        self.service.propose(self.headers, {'request_id': self.request_id, 'base_revision': view['base_revision'],
            'view_revision': view['view_revision'], 'changes': [{'id': self.changed['id'],
                'payload_sha256': self.changed['payload_sha256'], 'category': 'category-3'}]})
        decisions = copy.deepcopy(self.initial_decisions)
        next(row for row in decisions['resources'] if row['id'] == self.changed['id'])['category'] = 'category-3'
        return decisions

    def test_complete_roundtrip_preserves_unrelated_rows_and_defers_publication(self):
        decisions = self.propose()
        result = self.consumer.prepare(self.headers, self.request_id, decisions)
        self.assertEqual(self.publisher.active()[1], self.previous)
        self.assertEqual(result['approval']['sequence'], 2)
        self.assertEqual(len(result['approval']['catalog']['resources']), len(self.previous['catalog']['resources']))
        self.assertEqual(result, self.consumer.prepare(self.headers, self.request_id, decisions))
        approved = [row for row in self.gate.audit.export() if row['event'] == 'review_approved']
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]['metadata']['approval_revision'], result['approval']['revision'])
        self.publisher.publish(result['approval'], result['draft'], expected_revision=self.previous['revision'])
        row = next(row for row in self.publisher.catalog()['resources'] if row['id'] == self.changed['id'])
        self.assertEqual(row['category'], 'category-3')
        self.assertTrue(self.backend.state(self.headers)['resources'])
        with self.assertRaises(ValueError):
            self.consumer.prepare(self.headers, self.request_id, decisions)

    def test_missing_or_legacy_audit_receipt_cannot_authorize_approval(self):
        decisions = self.propose()
        records = self.gate.audit.export()
        for record in records:
            record['metadata'].pop('review_revision', None)
        with patch.object(self.gate.audit, 'export', return_value=records):
            with self.assertRaises(PermissionError):
                self.consumer.prepare(self.headers, self.request_id, decisions)

    def test_rehashed_tampering_does_not_match_the_acknowledged_proposal(self):
        decisions = self.propose()
        path = self.spool / (self.request_id + '.json')
        proposal = json.loads(path.read_bytes())
        proposal['recipient']['human'] = 'owner'
        proposal['revision'] = revision({key: value for key, value in proposal.items() if key != 'revision'})
        path.write_text(json.dumps(proposal), encoding='utf-8')
        with self.assertRaises(PermissionError):
            self.consumer.prepare(self.headers, self.request_id, decisions)

    def test_addition_removal_duplicates_and_unrelated_changes_are_rejected(self):
        decisions = self.propose()
        for mutation in ('remove', 'add', 'duplicate', 'unrelated'):
            altered = copy.deepcopy(decisions)
            if mutation == 'remove':
                altered['resources'].pop()
            elif mutation == 'add':
                altered['resources'].append(altered['resources'][0] | {'id': 'f' * 64})
            elif mutation == 'duplicate':
                altered['resources'].append(altered['resources'][0])
            else:
                next(row for row in altered['resources'] if row['id'] != self.changed['id'])['category'] = 'category-3'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.consumer.prepare(self.headers, self.request_id, altered)

    def test_category_zero_reviewer_without_explicit_write_grants_is_denied(self):
        decisions = self.propose()
        self.authenticate('101')
        with self.assertRaises(PermissionError):
            self.consumer.prepare(self.headers, self.request_id, decisions)

    def test_reviewer_cannot_reapprove_unchanged_records_outside_write_scope(self):
        self.seed('project-publication', project_record=True)
        self.authenticate()
        decisions = self.propose()
        with self.assertRaises(PermissionError):
            self.consumer.prepare(self.headers, self.request_id, decisions)

    def test_source_and_policy_changes_invalidate_the_pending_approval(self):
        decisions = self.propose()
        self.source['actors'][0]['tools'].append('drive')
        with self.assertRaises(ValueError):
            self.consumer.prepare(self.headers, self.request_id, decisions)
        self.source['actors'][0]['tools'].pop()
        self.org['policies']['phantomview']['human_action_grants']['secretary'].pop('resource.classify')
        with self.assertRaises(ValueError):
            self.consumer.prepare(self.headers, self.request_id, decisions)

    def test_logout_and_audit_failure_produce_no_approved_revision(self):
        decisions = self.propose()
        with patch.object(self.gate.audit, 'record', side_effect=OSError('Audit unavailable')):
            with self.assertRaises(OSError):
                self.consumer.prepare(self.headers, self.request_id, decisions)
        self.assertEqual(self.publisher.active()[1], self.previous)
        self.gate.logout(self.headers)
        with self.assertRaises(ValueError):
            self.consumer.prepare(self.headers, self.request_id, decisions)

    def test_unknown_request_paths_and_mismatched_loaders_fail_closed(self):
        with self.assertRaises(ValueError):
            self.consumer.prepare(self.headers, '../request', {})
        self.backend.catalog_loader = lambda: self.previous['catalog']
        with self.assertRaises(ValueError):
            ApprovalConsumer(self.service, self.publisher)


if __name__ == '__main__':
    unittest.main()
