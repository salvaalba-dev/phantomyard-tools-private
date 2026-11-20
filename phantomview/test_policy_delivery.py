"""Current receipt binding through HTTP delivery, using a synthetic lock harness."""
from contextlib import contextmanager
import copy
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import authority_publication as publication
from identified_reader import RecipientHandler
import reader_launch
import reader_handoff
import test_authority_publication as fixtures
from test_reader_launch import example


class PolicyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PublicationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.publish()
        self.authority = self.fixture.reader
        self.authority.policy_lock = '/synthetic/policy.lock'
        self.mutex = threading.RLock()
        self.pending = False
        self.committed = {'source': str(self.fixture.source), 'sha256': self.digest()}
        self.bind_publication()

        @contextmanager
        def guard(lock, source):
            self.assertEqual(lock, '/synthetic/policy.lock')
            with self.mutex:
                if self.pending or source != self.committed['source']:
                    raise ValueError('synthetic pending or source mismatch')
                yield copy.deepcopy(self.committed)

        self.addCleanup(patch.stopall)
        patch.object(publication, '_committed_guard', guard).start()
        # Root-controlled read behavior is tested separately on real Linux.
        patch.object(publication, '_protected_read', publication._read).start()

    def digest(self):
        return hashlib.sha256(self.fixture.source.read_bytes()).hexdigest()

    def bind_publication(self):
        path = self.fixture.publication.path
        value = json.loads(path.read_bytes())
        value[publication.META]['source_sha256'] = self.digest()
        path.write_text(json.dumps(value), encoding='utf-8')

    def server(self, handler=RecipientHandler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        server.policy_authority = self.authority
        server.gate = server.scoped_backend = None
        server.token = 'synthetic'
        server.observatory = SimpleNamespace(data=lambda: {'protected': 'current'})
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 3)
        self.addCleanup(server.shutdown)
        return server

    def request(self, server):
        client = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            client.request('GET', '/api/state', headers={'Authorization': 'Bearer synthetic'})
            response = client.getresponse()
            return response.status, response.read()
        finally:
            client.close()

    def test_pending_denies_http_without_reaching_the_protected_backend(self):
        server = self.server()
        self.assertEqual(self.request(server)[0], 200)
        self.pending = True
        server.observatory.data = lambda: self.fail('pending request reached backend')
        status, body = self.request(server)
        self.assertEqual(status, 503)
        self.assertNotIn(b'current', body)

    def test_pending_also_denies_redemption_and_delete_requests(self):
        server = self.server()
        self.pending = True
        for method, path in [('POST', '/api/redeem'), ('DELETE', '/api/scoped-assistant/jobs/test')]:
            client = HTTPConnection('127.0.0.1', server.server_port, timeout=2)
            try:
                client.request(method, path, body=b'')
                response = client.getresponse()
                self.assertEqual(response.status, 503)
                response.read()
            finally:
                client.close()

    def test_unexpired_publication_is_denied_after_commit_until_refreshed(self):
        server = self.server()
        recipient = self.authority().resolve(channel='telegram', sender='101', persona='coordinator',
            direct=True, principal_authenticated=True, scope_id='example')
        self.fixture.org['humans'][0]['telegram_user_id'] = 201
        self.fixture.source.write_text(json.dumps(self.fixture.org), encoding='utf-8')
        self.committed['sha256'] = self.digest()
        self.assertEqual(self.request(server)[0], 503)
        # The old lease has not expired; refreshing the matched publication/index
        # is necessary before even the synthetic protected response can proceed.
        self.assertEqual(self.fixture.ticks[0], 100)
        self.fixture.state = self.fixture.observer.refresh()
        self.fixture.publish()
        self.bind_publication()
        self.assertEqual(self.request(server)[0], 200)
        with self.assertRaises(ValueError):
            self.authority().validate(recipient)

    def test_delivery_pins_one_pair_and_returns_independent_objects(self):
        with self.authority.delivery():
            before = self.authority.read()
            before['organization']['name'] = 'Caller mutation'
            self.assertNotEqual(self.authority.read()['organization'].get('name'), 'Caller mutation')
            self.fixture.index.write_text('{}', encoding='utf-8')
            self.assertTrue(self.authority.snapshot()['digest'])
        with self.assertRaises(ValueError):
            self.authority.read()

    def test_reader_never_opens_private_original_source(self):
        original = publication._read
        def read(path):
            self.assertNotEqual(path, self.fixture.source)
            return original(path)
        with patch.object(publication, '_protected_read', read):
            self.assertEqual(self.request(self.server())[0], 200)

    def test_lock_remains_held_until_http_body_finishes(self):
        entered, release, written, started = (threading.Event() for _ in range(4))
        class Slow(RecipientHandler):
            def send(handler, code, body, *args, **kwargs):
                if code == 200 and isinstance(body, dict) and 'protected' in body:
                    entered.set()
                    if not release.wait(2):
                        raise OSError('synthetic delivery timeout')
                return super().send(code, body, *args, **kwargs)
        server = self.server(Slow)
        results, errors = [], []
        def fetch():
            try:
                results.append(self.request(server))
            except Exception as error:
                errors.append(error)
        def writer():
            started.set()
            with self.mutex:
                self.committed['sha256'] = 'f' * 64
                written.set()
        first, second = threading.Thread(target=fetch), threading.Thread(target=writer)
        first.start()
        try:
            self.assertTrue(entered.wait(1))
            second.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(written.wait(.05))
        finally:
            release.set()
            first.join(3)
            if second.ident is not None:
                second.join(3)
        self.assertFalse(errors)
        self.assertTrue(written.is_set())
        self.assertEqual(results[0][0], 200)
        self.assertEqual(self.request(server)[0], 503)

    def test_missing_hash_cross_source_and_legacy_publications_fail_closed(self):
        for change in ('hash', 'source', 'legacy'):
            self.bind_publication()
            path = self.fixture.publication.path
            document = json.loads(path.read_bytes())
            if change == 'hash':
                document[publication.META]['source_sha256'] = 'f' * 64
            elif change == 'source':
                document[publication.META]['source'] = '/another/source'
            else:
                del document[publication.META]['source_sha256']
            path.write_text(json.dumps(document), encoding='utf-8')
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.authority.read()

    def test_schema_two_requires_one_explicit_nonaliased_lock(self):
        config = example() | {'schema_version': 2, 'policy_lock': '/etc/example/policy.lock'}
        self.assertEqual(reader_launch.validate(config), config)
        for changes in ({'schema_version': 1}, {'policy_lock': config['source_path']},
                        {'policy_lock': '/etc/../unsafe'}, {'policy_lock': None}):
            with self.assertRaises(ValueError):
                reader_launch.validate(config | changes)
        del config['policy_lock']
        with self.assertRaises(ValueError):
            reader_launch.validate(config)

    def test_refused_handoff_closes_connection_before_any_link_is_issued(self):
        runtime = reader_handoff.ReaderHandoff.__new__(reader_handoff.ReaderHandoff)
        runtime._stop = threading.Event()
        runtime._lock = threading.Lock()
        runtime._listener = Mock()
        runtime._failed = False
        runtime.gate = runtime.peer_policy = object()
        runtime.actor = None
        connection = Mock()
        runtime._listener.accept.return_value = (connection, None)
        @contextmanager
        def unavailable():
            runtime._stop.set()
            raise ValueError('pending')
            yield  # this is a failing context manager, not a successful guard
        runtime.authority = SimpleNamespace(policy_lock='/synthetic/lock', delivery=unavailable)
        with patch.object(reader_handoff, 'serve_connection') as issue:
            runtime._run()
        issue.assert_not_called()
        connection.close.assert_called_once()
        self.assertFalse(runtime._failed)
        self.assertIsNone(runtime._connection)
