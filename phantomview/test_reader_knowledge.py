"""Protected KB host inputs and real reader composition with synthetic sessions.

The HTTP tests use the existing fake signature verifier. Separate signed reader
tests exercise real cryptography; no production user or channel is contacted.
"""
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from authority_publication import META, PublishedAuthority
from channel_identity import HumanDirectory
from identified_reader import PublishedReader
from projection_review import PublishedProjection, approve
from reader_knowledge import ReaderKnowledgeSource, coordinates
from resource_review import revision
from session_audit import Ledger
from source_adapter import prepare
from test_access_gate import ACCESS
from test_channel_identity import context
from test_reviewed_knowledge import knowledge_fixture
from test_source_adapter import snapshot
from test_view_permissions import scoped_organization


class KnowledgeFixture:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root.chmod(0o700)
        self.payloads = self.root / 'payloads'
        self.payloads.mkdir(mode=0o700)
        self.payloads.chmod(0o700)
        self.review = self.root / 'approved.json'
        self.org = scoped_organization()
        self.fixture = knowledge_fixture(self.org)
        self.payload = self.payloads / (self.fixture['id'] + '.json')
        self.write(self.payload, self.fixture['raw'])
        self.write(self.review, json.dumps(self.fixture['bundle']).encode())
        self.config = {'review_path': str(self.review), 'payload_directory': str(self.payloads)}
        self.source = ReaderKnowledgeSource(self.config, lambda: self.org, lambda: self.fixture['snapshot'])

    def write(self, path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)


class KnowledgeSourceTests(KnowledgeFixture, unittest.TestCase):
    def test_preflight_does_not_read_payloads_or_write_files(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob('*.json')}
        with patch.object(type(self.source.store), '__call__', side_effect=AssertionError('No body reads')):
            self.source.preflight()
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*.json')})
        self.assertEqual(self.source.note(self.fixture['id']), self.fixture['raw'])

    def test_excluded_missing_and_unselected_payloads_are_unavailable(self):
        self.assertIsNone(self.source.note('f' * 64))
        self.assertIsNone(self.source.note('../private'))
        self.fixture['snapshot']['actors'][0]['searchable'] = False
        self.assertIsNone(self.source.note(self.fixture['id']))

    def test_direct_loader_rejects_searchable_unapproved_or_changed_payload(self):
        from scoped_knowledge import digest
        ident = digest(b'unapproved searchable note')
        note = json.loads(self.fixture['raw'])
        note.update(id=ident, path='kb/policies/unapproved.md')
        self.fixture['snapshot']['actors'][0]['knowledge'].append(
            {'id': ident, 'path': note['path'], 'searchable': True})
        self.write(self.payloads / (ident + '.json'), json.dumps(note).encode())
        with patch.object(type(self.source.store), '__call__', side_effect=AssertionError('No unapproved body reads')):
            self.assertIsNone(self.source.note(ident))
        self.write(self.payload, self.fixture['raw'] + b' ')
        self.assertIsNone(self.source.note(self.fixture['id']))

    def test_review_change_is_reloaded_and_authority_drift_is_not_silently_ignored(self):
        bundle = self.fixture['bundle']
        bundle['catalog']['resources'][0]['category'] = 'category-3'
        bundle['revision'] = revision({k: v for k, v in bundle.items() if k != 'revision'})
        self.write(self.review, json.dumps(bundle).encode())
        self.assertEqual(self.source.review()['catalog']['resources'][0]['category'], 'category-3')
        self.org['humans'][0]['email'] = 'changed@example.invalid'
        with self.assertRaises(ValueError):
            self.source.review()

    def test_missing_or_malformed_review_refuses_instead_of_disabling_knowledge(self):
        self.review.unlink()
        with self.assertRaises(OSError):
            self.source.preflight()
        self.write(self.review, b'{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            self.source.review()

    def test_only_explicit_fixed_coordinates_are_accepted(self):
        for value in (None, False, {}, self.config | {'category': 'category-1'},
                      self.config | {'review_path': '../approved.json'}, self.config | {'review_path': str(self.root / 'review.yaml')}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ReaderKnowledgeSource(value, lambda: self.org, lambda: self.fixture['snapshot'])
        detached = coordinates(self.config)
        detached['review_path'] = 'changed'
        self.assertEqual(self.config['review_path'], str(self.review))

    @unittest.skipUnless(os.name == 'posix', 'POSIX ownership and modes')
    def test_group_writable_inputs_and_directory_changes_fail_closed(self):
        self.review.chmod(0o664)
        with self.assertRaises(ValueError):
            self.source.review()
        self.review.chmod(0o600)
        self.payload.chmod(0o664)
        self.assertIsNone(self.source.note(self.fixture['id']))
        self.payload.chmod(0o600)
        self.payloads.chmod(0o770)
        with self.assertRaises(ValueError):
            self.source.note(self.fixture['id'])
        self.payloads.chmod(0o700)
        self.root.chmod(0o770)
        try:
            with self.assertRaises(ValueError):
                self.source.preflight()
        finally:
            self.root.chmod(0o700)

    @unittest.skipUnless(os.name == 'posix', 'POSIX links')
    def test_review_and_payload_links_are_rejected(self):
        original = self.root / 'original.json'
        self.review.rename(original)
        self.review.symlink_to(original)
        with self.assertRaises(ValueError):
            self.source.review()
        with self.assertRaises(ValueError):
            self.source.note(self.fixture['id'])
        # Restore the approval before independently checking the payload link.
        self.review.unlink()
        original.rename(self.review)
        self.payload.unlink()
        self.payload.symlink_to(original)
        self.assertIsNone(self.source.note(self.fixture['id']))


class PublishedKnowledgeHTTPTests(KnowledgeFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.snapshot = snapshot()
        self.snapshot['actors'][0]['knowledge'] = self.fixture['snapshot']['actors'][0]['knowledge']
        self.authority_root = self.root / 'authority'
        self.authority_root.mkdir(mode=0o700)
        self.authority_root.chmod(0o700)
        self.index = self.root / 'index.json'
        self.org_path = self.root / 'source.json'
        self.snapshot['organizations'][0]['source'] = str(self.org_path)
        captured = self.snapshot | {'digest': revision(self.snapshot)}
        metadata = {'schema_version': 1, 'source': str(self.org_path), 'organization': 'example',
                    'snapshot_source': str(self.org_path), 'organization_revision': revision(self.org),
                    'snapshot_digest': captured['digest'], 'published_at': 100}
        self.write(self.authority_root / 'organization.json', json.dumps(self.org | {META: metadata}).encode())
        self.write(self.index, json.dumps({'config': {'org_files': [str(self.org_path)]}, 'snapshot': captured}).encode())
        self.authority = PublishedAuthority(self.authority_root, self.index, 'example', str(self.org_path),
                                            max_age=30, clock=lambda: 100)
        self.projection_root = self.root / 'projection'
        self.projection_root.mkdir(mode=0o700)
        self.projection_root.chmod(0o700)
        draft = prepare(self.snapshot, HumanDirectory(self.org))
        decisions = {'schema_version': 1, 'draft_revision': revision(draft), 'organization_revision': revision(self.org),
                     'resources': [{k: row[k] for k in ('id', 'payload_sha256')} | {
                         'category': 'category-1', 'scope': {'kind': 'organization', 'id': 'example'},
                         'project': None, 'secret': False} for row in draft['resources']]}
        bundle = approve(draft, decisions, self.org, lambda: self.snapshot, reviewer='owner')
        PublishedProjection(self.projection_root, self.authority.read, self.authority.snapshot).publish(bundle, draft, expected_revision=None)
        self.options = dict(authority=self.authority, projection_root=self.projection_root, actor='administrator',
                            identities=['a' * 64], origin='https://view.example:8790', port=0, issuer_uid=29002,
                            socket_path=self.root / 'native.sock', socket_group=29002,
                            audit=Ledger(self.root / 'audit.sqlite'), reviewed_knowledge=self.config)
        with patch('identified_reader.signed_access', return_value=ACCESS):
            self.application = PublishedReader(**self.options)
        self.server = self.application._make_server()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        link = self.application.gate.issue_identified('Nostr test-signed-event', self.options['origin'],
                                                      **context('102', 'administrator'), scope_id='example')
        cookie = self.application.gate.redeem(link.split('#c=')[1])
        self.cookie = 'phantomview=' + cookie

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, *, authenticated=True):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            headers = {'Content-Type': 'application/json', 'Cookie': self.cookie if authenticated else ''}
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_fixed_host_binding_discovers_searches_and_reads_current_notes(self):
        status, state = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(state['counts']['knowledge'], 1)
        self.assertIn('knowledge', {row['kind'] for row in state['navigation']['core']})
        note = next(row for row in state['resources'] if row['kind'] == 'knowledge')
        self.assertEqual(note['data']['actor'], 'coordinator')
        self.assertNotIn('content', note['data'])
        status, search = self.request('POST', '/api/search', {'query': 'FÍELD PROCEDURES'})
        self.assertEqual(status, 200)
        self.assertIn(self.fixture['id'], {row['id'] for row in search['results']})
        status, detail = self.request('GET', '/api/reviewed-knowledge/' + self.fixture['id'])
        self.assertEqual(status, 200)
        self.assertEqual(detail['content'], 'Reviewed field procedures.')
        self.assertEqual(detail['actor'], note['data']['actor'])
        self.assertNotIn('DO_NOT_DISCLOSE', json.dumps(detail))
        self.assertIs(self.application.backend.reviewed_knowledge.gate, self.application.gate)

    def test_state_reads_approval_once_per_scan_with_real_host_loader(self):
        from reader_knowledge import _read
        from resource_review import source_key
        from scoped_knowledge import digest
        # Exercise a real protected file store with more than 8 MiB of content.
        rows = self.fixture['bundle']['catalog']['resources']
        for index in range(36):
            ident = digest(('approved large note ' + str(index)).encode())
            note = json.loads(self.fixture['raw'])
            note.update(id=ident, path='kb/policies/' + ident + '.md', content='x' * (240 * 1024))
            raw = json.dumps(note).encode()
            self.write(self.payloads / (ident + '.json'), raw)
            rows.append(rows[0] | {'id': ident, 'path': note['path'], 'payload_sha256': digest(raw)})
            self.fixture['snapshot']['actors'][0]['knowledge'].append(
                {'id': ident, 'path': note['path'], 'searchable': True})
        bundle = self.fixture['bundle']
        bundle['sources'] = [{'source_key': source_key('example', row['actor'], row['path']),
                              'id': row['id'], 'payload_sha256': row['payload_sha256']} for row in rows]
        bundle['revision'] = revision({k: v for k, v in bundle.items() if k != 'revision'})
        self.write(self.review, json.dumps(bundle).encode())
        # Use the existing projected metadata; only the KB source grows.
        reader = self.application.backend.reviewed_knowledge
        source = ReaderKnowledgeSource(self.config, lambda: self.org, lambda: self.fixture['snapshot'])
        reader.scan_source = source._scan_review
        reader.snapshot_loader = lambda: self.fixture['snapshot']
        headers = {'Cookie': self.cookie}
        with patch('reader_knowledge._read', wraps=_read) as reads:
            state = self.application.backend.state(headers)
            self.assertEqual(state['counts']['knowledge'], 37)
            self.assertEqual(reads.call_count, 1)
            self.application.backend.state(headers)
            self.assertEqual(reads.call_count, 2)
        self.assertIsNotNone(source.note(self.fixture['id']))

    def test_production_state_uses_scan_loader_instead_of_direct_note(self):
        from reader_knowledge import _read
        source = self.application.knowledge_source
        with patch('reader_knowledge._read', wraps=_read) as reads:
            with patch.object(source, 'note', side_effect=AssertionError('Direct loader in scan')):
                status, state = self.request('GET', '/api/state')
            self.assertEqual(status, 200)
            self.assertEqual(state['counts']['knowledge'], 1)
            self.assertEqual(reads.call_count, 1)

    def test_review_replacement_during_final_body_read_discards_response(self):
        source = self.application.knowledge_source
        original = source._note_payload
        calls = 0
        def changing(ident):
            nonlocal calls
            raw = original(ident)
            calls += 1
            if calls == 2:
                replacement = self.root / 'replacement.json'
                self.write(replacement, self.review.read_bytes())
                replacement.replace(self.review)
            return raw
        with patch.object(source, '_note_payload', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'authority or review changed'):
                self.application.backend.state({'Cookie': self.cookie})
        self.assertEqual(calls, 2)

    def test_same_size_review_edit_during_scan_discards_response(self):
        source = self.application.knowledge_source
        original = source._note_payload
        def changing(ident):
            raw = original(ident)
            # No second parse is necessary to reject an in-place same-size edit.
            self.write(self.review, self.review.read_bytes().replace(b'owner', b'other'))
            return raw
        with patch.object(source, '_note_payload', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'authority or review changed'):
                self.application.backend.state({'Cookie': self.cookie})

    def test_reclassified_note_disappears_without_body_reads_or_hidden_titles(self):
        bundle = self.fixture['bundle']
        bundle['catalog']['resources'][0]['category'] = 'category-3'
        bundle['revision'] = revision({k: v for k, v in bundle.items() if k != 'revision'})
        self.write(self.review, json.dumps(bundle).encode())
        with patch.object(type(self.application.knowledge_source.store), '__call__', side_effect=AssertionError('Denied body opened')):
            status, state = self.request('GET', '/api/state')
            self.assertEqual(status, 200)
            self.assertNotIn('knowledge', state['counts'])
            self.assertNotIn('Organization procedures', json.dumps(state))
            self.assertEqual(self.request('GET', '/api/reviewed-knowledge/' + self.fixture['id']),
                             self.request('GET', '/api/reviewed-knowledge/' + 'f' * 64))
            self.assertEqual(self.request('POST', '/api/search', {'query': 'field procedures'})[1]['results'], [])

    def test_changed_payload_never_releases_unreviewed_text(self):
        changed = json.loads(self.fixture['raw']) | {'title': 'Unreviewed replacement', 'content': 'Do not release'}
        self.write(self.payload, json.dumps(changed).encode())
        self.assertEqual(self.request('GET', '/api/reviewed-knowledge/' + self.fixture['id'])[0], 404)
        self.assertNotIn('knowledge', self.request('GET', '/api/state')[1]['counts'])

    def test_unauthenticated_requests_do_not_read_review_or_note_files(self):
        with patch.object(self.application.knowledge_source, 'review', side_effect=AssertionError('Unauthenticated review read')):
            self.assertEqual(self.request('GET', '/api/reviewed-knowledge/' + self.fixture['id'], authenticated=False)[0], 401)

    def test_legacy_route_and_browser_supplied_coordinates_remain_closed(self):
        self.assertEqual(self.request('GET', '/api/knowledge/' + self.fixture['id'])[0], 403)
        self.assertEqual(self.request('GET', '/api/reviewed-knowledge/' + self.fixture['id'] + '?human=owner')[0], 400)
        self.assertEqual(self.request('POST', '/api/search', {'query': 'field', 'review_path': str(self.review)})[0], 401)

    def test_knowledge_disabled_by_default_and_configured_failures_are_not_fallbacks(self):
        with patch('identified_reader.signed_access', return_value=ACCESS):
            app = PublishedReader(**(self.options | {'reviewed_knowledge': None}))
        self.assertIsNone(app.knowledge_source)
        self.assertIsNone(app.backend.reviewed_knowledge)
        self.review.unlink()
        with patch('identified_reader.signed_access', return_value=ACCESS), self.assertRaises(OSError):
            PublishedReader(**self.options)
