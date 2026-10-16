"""Identified review requires independent write grants and a healthy audit sink."""
import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import uuid
from unittest.mock import patch

import phantomview as pv

from authenticated_review import ReviewService
from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from session_audit import Ledger
from test_access_gate import ACCESS
from test_channel_identity import context
from test_scoped_backend import ProjectionFixture


class ReviewFixture(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spool = self.root / 'proposals'
        self.spool.mkdir()
        self.org['policies']['access_levels']['board']['categories'].append(3)
        self.org['policies']['phantomview']['human_action_grants']['secretary']['resource.classify'] = ['example']
        self.authenticate()

    def authenticate(self, sender='102', persona='administrator', scope='example'):
        self.catalog['authority_revision'] = HumanDirectory(self.org).authority_revision
        self.gate = IdentifiedGate(ACCESS, {'identities': ['a' * 64], 'actor': persona},
                                   'https://view.example', 8789, audit=Ledger(self.root / 'audit.sqlite'),
                                   directory_loader=lambda: HumanDirectory(self.org))
        self.backend.gate = self.gate
        link = self.gate.issue_identified('Nostr test-signed-event', self.gate.origin,
                                          **context(sender, persona), scope_id=scope)
        self.headers = {'Cookie': 'phantomview=' + self.gate.redeem(link.split('#c=')[1])}
        self.service = ReviewService(self.backend, self.spool)

    def proposal(self):
        view = self.service.view(self.headers)
        row = next(row for row in view['resources'] if row['id'] == self.public)
        return {'request_id': str(uuid.uuid4()), 'base_revision': view['base_revision'],
                'view_revision': view['view_revision'], 'changes': [
                    {'id': row['id'], 'payload_sha256': row['payload_sha256'], 'category': 'category-3'}]}


class AuthenticatedReviewTests(ReviewFixture):

    def test_visible_classifiable_sources_only_and_category_zero_is_never_a_label(self):
        view = self.service.view(self.headers)
        self.assertNotIn(self.other, json.dumps(view))
        self.assertNotIn(self.project, {row['id'] for row in view['resources']})
        self.assertTrue(all('category-0' not in row['allowed_categories'] for row in view['resources']))

    def test_denied_additions_do_not_change_public_review_revisions_or_candidates(self):
        before = self.service.view(self.headers)
        self.add('Excluded project record', 'partner', scope='other-project')
        self.assertEqual(self.service.view(self.headers), before)

    def test_read_access_and_category_zero_do_not_grant_classification(self):
        for sender, persona in [('102', 'administrator'), ('101', 'coordinator')]:
            self.org['policies']['phantomview']['human_action_grants'].pop('secretary', None)
            self.authenticate(sender, persona)
            self.loaded.clear()
            with self.assertRaises(PermissionError):
                self.service.view(self.headers)
            self.assertEqual(self.loaded, [])

    def test_proposal_is_audited_idempotent_and_never_publishes(self):
        body = self.proposal()
        original = json.dumps(self.catalog, sort_keys=True)
        result = self.service.propose(self.headers, body)
        self.assertEqual(result, self.service.propose(self.headers, body))
        self.assertEqual(result['status'], 'pending')
        self.assertIs(result['published'], False)
        files = list(self.spool.glob('*.json'))
        self.assertEqual(len(files), 1)
        stored = json.loads(files[0].read_bytes())
        self.assertEqual(stored['recipient']['human'], 'secretary')
        self.assertEqual(stored['changes'][0]['from']['category'], 'category-1')
        self.assertEqual(stored['changes'][0]['to']['category'], 'category-3')
        self.assertNotIn('data', stored['changes'][0])
        self.assertNotIn(self.headers['Cookie'], json.dumps(stored))
        self.assertEqual(json.dumps(self.catalog, sort_keys=True), original)
        self.assertFalse((self.spool / 'active.json').exists())
        events = self.gate.audit.export()
        self.assertEqual([row['event'] for row in events], ['session_created', 'review_requested', 'review_proposed'])
        self.assertNotIn('secretary', json.dumps(events))

    def test_identity_scope_and_secret_overrides_are_rejected(self):
        for field, value in [('human', 'owner'), ('scope', 'other-project'), ('secret', False)]:
            body = self.proposal()
            body['changes'][0][field] = value
            with self.assertRaises(ValueError):
                self.service.propose(self.headers, body)
        self.assertEqual(list(self.spool.iterdir()), [])

    def test_denied_record_category_zero_noop_and_unknown_category_are_rejected(self):
        for category in ('category-0', 'category-999', 'category-1'):
            body = self.proposal()
            body['changes'][0]['category'] = category
            with self.assertRaises(PermissionError):
                self.service.propose(self.headers, body)
        body = self.proposal()
        body['changes'][0]['id'] = self.other
        with self.assertRaises(PermissionError):
            self.service.propose(self.headers, body)

    def test_stale_catalog_payload_and_revoked_policy_block_staging(self):
        body = self.proposal()
        self.replace(self.public, {'title': 'Updated current record'})
        with self.assertRaises(ValueError):
            self.service.propose(self.headers, body)
        body = self.proposal()
        self.org['policies']['phantomview']['human_action_grants']['secretary'].pop('resource.classify')
        with self.assertRaises(ValueError):
            self.service.propose(self.headers, body)
        self.assertEqual(list(self.spool.iterdir()), [])

    def test_missing_or_failed_audit_cannot_acknowledge_a_proposal(self):
        body = self.proposal()
        with patch.object(self.gate.audit, 'record', side_effect=OSError('Private path')):
            with self.assertRaises(OSError):
                self.service.propose(self.headers, body)
        self.assertEqual(list(self.spool.iterdir()), [])
        self.gate.audit = None
        with self.assertRaises(ValueError):
            ReviewService(self.backend, self.spool)

    def test_logout_and_unidentified_cookies_cannot_review(self):
        body = self.proposal()
        self.gate.logout(self.headers)
        with self.assertRaises(ValueError):
            self.service.propose(self.headers, body)
        token = self.gate.create_session()
        with self.assertRaises(ValueError):
            self.service.view({'Cookie': 'phantomview=' + token})

    def test_duplicate_changes_and_request_id_conflicts_fail_before_acceptance(self):
        body = self.proposal()
        body['changes'] *= 2
        with self.assertRaises(ValueError):
            self.service.propose(self.headers, body)
        self.assertEqual(list(self.spool.iterdir()), [])
        body = self.proposal()
        self.service.propose(self.headers, body)
        view = self.service.view(self.headers)
        row = next(row for row in view['resources'] if row['id'] == self.hidden)
        body['changes'] = [{'id': row['id'], 'payload_sha256': row['payload_sha256'], 'category': 'category-1'}]
        with self.assertRaises(ValueError):
            self.service.propose(self.headers, body)
        self.assertEqual(len(list(self.spool.iterdir())), 1)

    def test_audit_failure_after_storage_leaves_only_an_unapproved_pending_artifact(self):
        body = self.proposal()
        record = self.gate.audit.record
        def fail_completion(event, *args, **kwargs):
            if event == 'review_proposed':
                raise OSError('Audit unavailable')
            return record(event, *args, **kwargs)
        with patch.object(self.gate.audit, 'record', side_effect=fail_completion):
            with self.assertRaises(OSError):
                self.service.propose(self.headers, body)
        proposal = json.loads(next(self.spool.iterdir()).read_bytes())
        self.assertEqual(proposal['status'], 'pending')
        self.assertFalse((self.spool / 'active.json').exists())

    def test_revocation_during_storage_prevents_acknowledgement(self):
        from authenticated_review import write_new
        body = self.proposal()
        def revoke(path, value):
            write_new(path, value)
            self.org['policies']['phantomview']['human_action_grants']['secretary'].pop('resource.classify')
        with patch('authenticated_review.write_new', side_effect=revoke):
            with self.assertRaises(ValueError):
                self.service.propose(self.headers, body)
        self.assertNotIn('review_proposed', [row['event'] for row in self.gate.audit.export()])

    def test_mismatched_review_embedding_fails_before_creating_a_server(self):
        with patch('phantomview.ThreadingHTTPServer') as server:
            with self.assertRaises(ValueError):
                pv.serve(None, 0, False, gate=self.gate, review_service=self.service)
            server.assert_not_called()


class ReviewHTTPTests(ReviewFixture):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), pv.Handler)
        self.server.gate = self.gate
        self.server.scoped_backend = self.backend
        self.server.review_service = self.service
        self.server.access_errors = (ValueError, self.gate.access.core.Invalid)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, origin=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            headers = self.headers | {'Content-Type': 'application/json'}
            if origin is not None:
                headers['Origin'] = origin
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_identified_http_review_stages_only_an_audited_pending_proposal(self):
        self.assertEqual(self.request('GET', '/api/review')[0], 200)
        status, result = self.request('POST', '/api/review', self.proposal())
        self.assertEqual(status, 202)
        self.assertEqual(result['status'], 'pending')
        self.assertFalse(result['published'])

    def test_unconfigured_review_and_legacy_or_publish_routes_remain_closed(self):
        self.server.review_service = None
        for method in ('GET', 'POST'):
            self.assertEqual(self.request(method, '/api/review', {} if method == 'POST' else None)[0], 403)
        self.assertEqual(self.loaded, [])
        self.server.review_service = self.service
        for path in ('/api/config', '/api/review/publish', '/api/review/approve'):
            self.assertEqual(self.request('POST', path, {})[0], 403)

    def test_origin_query_claims_and_logged_out_review_are_rejected(self):
        self.assertEqual(self.request('POST', '/api/review', self.proposal(), origin='https://untrusted.invalid')[0], 403)
        self.assertEqual(self.request('GET', '/api/review?human=owner')[0], 400)
        self.assertEqual(self.request('POST', '/api/logout', {})[0], 200)
        self.assertEqual(self.request('GET', '/api/review')[0], 401)
