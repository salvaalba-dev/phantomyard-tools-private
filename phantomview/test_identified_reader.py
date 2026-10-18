"""Assembled publication-to-HTTP flow with real signatures and synthetic senders.

HTTP fixtures call the in-process trusted issuance seam; Linux account tests
separately verify the private socket. No production channel or user is contacted.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import uuid

from authority_publication import META, PublishedAuthority
from channel_identity import HumanDirectory
import identified_reader as reader
from projection_review import PublishedProjection, approve
from resource_review import revision
from session_audit import Ledger
from source_adapter import prepare
from test_channel_identity import context
from test_source_adapter import snapshot
from test_view_permissions import scoped_organization

try:
    from coincurve import PrivateKey
    from phantomblog import access
except ImportError:
    PrivateKey = None


class ReaderDependencyTests(unittest.TestCase):
    def test_missing_crypto_refuses_with_actionable_message_before_any_socket(self):
        import builtins
        original = builtins.__import__
        def unavailable(name, *args, **kwargs):
            if name == 'coincurve':
                raise ImportError('synthetic failure')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=unavailable):
            with self.assertRaisesRegex(ValueError, r'phantomblog\[access\]'):
                reader.signed_access()


@unittest.skipIf(PrivateKey is None, 'Install the reviewed PhantomBlog access extra')
class PublishedReaderTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.root.chmod(0o700)
        self.private = self.root / 'authority'
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.index, self.source = self.root / 'index.json', self.root / 'source.json'
        self.org, self.snapshot = scoped_organization(), snapshot()
        self.org['humans'][1]['email'] = 'private-registry-marker@example.invalid'
        self.snapshot['organizations'][0]['source'] = str(self.source)
        self.ticks = [100]
        self.publish_authority()
        self.authority = PublishedAuthority(self.private, self.index, 'example', str(self.source),
                                             max_age=30, clock=lambda: self.ticks[0])
        self.projection_root = self.root / 'projection'
        self.projection_root.mkdir(mode=0o700)
        self.projection_root.chmod(0o700)
        draft = prepare(self.snapshot, HumanDirectory(self.org))
        self.hidden = next(row['id'] for row in draft['resources'] if row['kind'] == 'document')
        decisions = {'schema_version': 1, 'draft_revision': revision(draft),
                     'organization_revision': revision(self.org), 'resources': [
            {key: row[key] for key in ('id', 'payload_sha256')} | {
                'category': 'category-3' if row['id'] == self.hidden else 'category-1',
                'scope': {'kind': 'organization', 'id': 'example'}, 'project': None, 'secret': False}
            for row in draft['resources']]}
        bundle = approve(draft, decisions, self.org, lambda: self.snapshot, reviewer='owner')
        publisher = PublishedProjection(self.projection_root, self.authority.read, self.authority.snapshot)
        publisher.publish(bundle, draft, expected_revision=None)
        self.key = PrivateKey()
        self.audit = Ledger(self.root / 'audit.sqlite')
        self.options = dict(authority=self.authority, projection_root=self.projection_root,
            actor='administrator', identities=[self.key.public_key_xonly.format().hex()],
            origin='https://view.example:8790', port=0, issuer_uid=29002,
            socket_path=self.root / 'native.sock', socket_group=29002, audit=self.audit)
        self.application = reader.PublishedReader(**self.options)
        self.session_ticks = [0]
        self.application.gate.clock = lambda: self.session_ticks[0]
        self.application.gate.links.clock = lambda: self.session_ticks[0]
        self.server = self.application._make_server()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')
        path.chmod(0o600)

    def publish_authority(self):
        source_snapshot = self.snapshot | {'digest': revision(self.snapshot)}
        metadata = {'schema_version': 1, 'source': str(self.source), 'organization': 'example',
                    'snapshot_source': str(self.source), 'organization_revision': revision(self.org),
                    'snapshot_digest': source_snapshot['digest'], 'published_at': self.ticks[0]}
        self.write(self.private / 'organization.json', self.org | {META: metadata})
        self.write(self.index, {'config': {'org_files': [str(self.source)]}, 'snapshot': source_snapshot})

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def authorization(self):
        event = {'pubkey': self.key.public_key_xonly.format().hex(), 'created_at': int(time.time()),
                 'kind': 27235, 'tags': [['u', self.options['origin'] + '/api/access-link'],
                    ['method', 'POST'], ['payload', hashlib.sha256(b'{}').hexdigest()],
                    ['nonce', uuid.uuid4().hex]], 'content': ''}
        event['id'] = access.event_digest(event)
        event['sig'] = self.key.sign_schnorr(bytes.fromhex(event['id'])).hex()
        return 'Nostr ' + base64.b64encode(json.dumps(event).encode()).decode()

    def issue(self, sender='102', persona='administrator'):
        return self.application.gate.issue_identified(self.authorization(), self.options['origin'],
            **context(sender, persona, scope_id='example')).split('#c=')[1]

    def request(self, method, path, body=None, cookie='', **extra):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            headers = {'Content-Type': 'application/json', 'Cookie': cookie, **extra}
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            result = connection.getresponse()
            raw = result.read()
            return result.status, json.loads(raw), result.getheader('Set-Cookie')
        finally:
            connection.close()

    def login(self):
        status, _, cookie = self.request('POST', '/api/redeem', {'code': self.issue()})
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        self.assertIn('Secure', cookie)
        parsed = SimpleCookie(cookie)
        return 'phantomview=' + parsed['phantomview'].value

    def test_publication_to_http_uses_one_gate_and_never_reads_original_source(self):
        self.assertFalse(self.source.exists())
        self.assertIs(self.server.gate, self.application.backend.gate)
        cookie = self.login()
        status, view, _ = self.request('GET', '/api/state', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(view['navigation']['assistant']['persona'], 'administrator')
        self.assertNotIn(self.hidden, json.dumps(view))
        self.assertNotIn('private-registry-marker', json.dumps(view))
        self.assertNotIn(META, json.dumps(view))
        self.assertNotIn(str(self.source), json.dumps(view))
        self.assertTrue(self.audit.export())
        self.assertEqual(self.request('GET', '/api/resource/' + self.hidden, cookie=cookie)[0], 404)
        self.assertEqual(self.request('POST', '/api/search', {'query': 'NEVER_COPY'}, cookie=cookie)[1]['results'], [])

    def test_browser_issuance_and_all_legacy_data_paths_stay_closed(self):
        cookie = self.login()
        for method, path in (('POST', '/api/access-link'), ('GET', '/api/knowledge/' + self.hidden),
                             ('GET', '/api/assistant/status'), ('POST', '/api/config'),
                             ('GET', '/api/phantombot/status'), ('GET', '/api/future-export')):
            with self.subTest(path=path):
                result = self.request(method, path, {} if method == 'POST' else None,
                                      cookie=cookie, Authorization=self.authorization())
                self.assertEqual(result[0], 403)

    def test_signed_but_unidentified_link_cannot_create_a_session(self):
        gate = self.application.gate
        code = gate.issue(self.authorization(), self.options['origin']).split('#c=')[1]
        self.assertEqual(self.request('POST', '/api/redeem', {'code': code})[0], 401)
        self.assertEqual(gate.sessions, {})
        self.assertEqual(gate.recipients, {})

    def test_expired_and_concurrently_redeemed_links_do_not_create_extra_sessions(self):
        code = self.issue()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.request('POST', '/api/redeem', {'code': code})[0], range(4)))
        self.assertEqual(results.count(200), 1)
        self.assertEqual(results.count(401), 3)
        expired = self.issue()
        self.session_ticks[0] = 301
        self.assertEqual(self.request('POST', '/api/redeem', {'code': expired})[0], 401)

    def test_current_publication_expiry_and_policy_change_deny_existing_cookie(self):
        cookie = self.login()
        self.ticks[0] = 130
        self.assertEqual(self.request('GET', '/api/state', cookie=cookie)[0], 401)
        self.ticks[0] = 110
        self.org['humans'][1].pop('counterpart_persona')
        self.publish_authority()
        self.assertEqual(self.request('GET', '/api/state', cookie=cookie)[0], 401)

    def test_revocation_logout_and_expiry_deny_existing_sessions(self):
        for operation in ('revoke', 'logout', 'expire'):
            with self.subTest(operation=operation):
                cookie = self.login()
                gate = self.application.gate
                if operation == 'revoke':
                    gate.revoke(next(iter(gate.session_ids.values())))
                elif operation == 'logout':
                    self.assertEqual(self.request('POST', '/api/logout', {}, cookie=cookie)[0], 200)
                else:
                    self.session_ticks[0] += gate.seconds
                self.assertEqual(self.request('GET', '/api/state', cookie=cookie)[0], 401)

    def test_changed_snapshot_or_missing_projection_refuses_startup(self):
        self.snapshot['actors'][0]['tools'].append('new-tool')
        self.publish_authority()
        with self.assertRaises(ValueError):
            reader.PublishedReader(**self.options)
        self.assertEqual(self.request('GET', '/api/state', cookie=self.login())[0], 401)

    def test_unknown_counterpart_origin_and_missing_approval_do_not_gain_access(self):
        for sender, persona in (('unknown', 'administrator'), ('103', 'administrator'),
                                ('102', 'coordinator')):
            with self.subTest(sender=sender, persona=persona), self.assertRaises(ValueError):
                self.issue(sender, persona)
        self.assertEqual(self.application.gate.recipient_links, {})
        cookie = self.login()
        self.assertEqual(self.request('GET', '/api/state', cookie=cookie, Origin='https://other.example')[0], 403)
        (self.projection_root / 'active.json').rename(self.projection_root / 'inactive.json')
        with self.assertRaises((ValueError, OSError)):
            reader.PublishedReader(**self.options)
        self.assertEqual(self.request('GET', '/api/state', cookie=cookie)[0], 503)

    def test_peer_policy_failure_opens_no_socket_and_discards_pending_state(self):
        self.login()
        with patch.object(reader, 'DaemonPeerPolicy', side_effect=ValueError('unsupported account')), \
                patch.object(self.application, '_make_server') as bind:
            with self.assertRaises(ValueError):
                self.application.serve()
        bind.assert_not_called()
        self.assertIsNone(self.application.server)
        self.assertEqual(self.application.gate.sessions, {})
        self.assertEqual(self.application.gate.recipient_links, {})

    def test_serve_closes_both_sockets_and_discards_sessions_on_handoff_failure(self):
        self.login()
        fake_server, handoff = Mock(), Mock()
        handoff.start.side_effect = ValueError('synthetic bind failure')
        with patch.object(reader, 'DaemonPeerPolicy') as policy, \
                patch.object(reader, 'ReaderHandoff', return_value=handoff), \
                patch.object(self.application, '_make_server', return_value=fake_server):
            with self.assertRaises(ValueError):
                self.application.serve()
        policy.assert_called_once_with(29002)
        handoff.start.assert_called_once_with(fake_server)
        handoff.close.assert_called_once()
        fake_server.server_close.assert_called_once()
        fake_server.serve_forever.assert_not_called()
        self.assertEqual(self.application.gate.sessions, {})
        with self.assertRaises(ValueError):
            self.application.serve()

    def test_serve_connects_same_gate_and_closes_after_http_failure(self):
        fake_server, handoff = Mock(), Mock()
        fake_server.serve_forever.side_effect = OSError('synthetic HTTP failure')
        with patch.object(reader, 'DaemonPeerPolicy', return_value='fixed-peer-policy'), \
                patch.object(reader, 'ReaderHandoff', return_value=handoff) as factory, \
                patch.object(self.application, '_make_server', return_value=fake_server):
            with self.assertRaises(OSError):
                self.application.serve()
        self.assertIs(factory.call_args.args[-1], self.application.gate)
        handoff.start.assert_called_once_with(fake_server)
        handoff.close.assert_called_once()
        fake_server.server_close.assert_called_once()


    def test_stop_event_exits_request_loop_and_cleans_up_without_shutdown_thread(self):
        stop = threading.Event()
        fake_server, handoff = Mock(), Mock()
        fake_server.handle_request.side_effect = stop.set
        with patch.object(reader, 'DaemonPeerPolicy'), \
                patch.object(reader, 'ReaderHandoff', return_value=handoff), \
                patch.object(self.application, '_make_server', return_value=fake_server):
            self.application.serve(stop_event=stop)
        fake_server.handle_request.assert_called_once()
        fake_server.serve_forever.assert_not_called()
        handoff.close.assert_called_once()
        fake_server.server_close.assert_called_once()
        self.assertEqual(self.application.gate.sessions, {})


if __name__ == '__main__':
    unittest.main()
