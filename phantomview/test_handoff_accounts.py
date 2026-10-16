"""Disposable Linux CI checks with permanently dropped numeric process UIDs.

Run only in an ephemeral CI runner as root with PHANTOMVIEW_ACCOUNT_TESTS=1.
No users, groups, services or production configuration are created or changed.
"""
import json
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import os
from pathlib import Path
import select
import signal
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest

from handoff_client import ReaderPolicy, request_access
from native_access_command import DirectMessage, NativeAccessCommand, Outcome
from reader_handoff import ReaderHandoff
from scoped_backend import ScopedBackend
from scoped_http import dispatch as scoped_dispatch
from test_scoped_backend import ProjectionFixture
import phantomview as pv
import test_signed_recipient as signatures
from test_view_permissions import scoped_organization
from trusted_handoff import PeerPolicy, bind_listener, serve_connection

READER, ISSUER, MODEL = 29001, 29002, 29003
ENABLED = (sys.platform == 'linux' and getattr(os, 'geteuid', lambda: -1)() == 0
           and os.environ.get('PHANTOMVIEW_ACCOUNT_TESTS') == '1')


def spawn(uid, operation):
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            # A common test group deliberately permits socket connection; UID
            # checks must still reject the model account after it connects.
            os.setgroups([])
            os.setgid(ISSUER)
            os.setuid(uid)
            result = {'ok': True, 'value': operation()}
        except BaseException as error:
            result = {'ok': False, 'error': type(error).__name__}
        raw = json.dumps(result).encode()
        os.write(write_fd, raw)
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    return pid, read_fd


def finish(child):
    pid, fd = child
    try:
        if not select.select([fd], [], [], 12)[0]:
            os.kill(pid, signal.SIGKILL)
            raise AssertionError('Disposable handoff test child timed out')
        raw = os.read(fd, 32768)
        return json.loads(raw)
    finally:
        os.close(fd)
        os.waitpid(pid, 0)


@unittest.skipUnless(ENABLED, 'Explicit ephemeral root Linux account-test job required')
class CrossAccountTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(signatures.PrivateKey, 'Install PhantomBlog access dependencies; never skip this job')
        # The runner checkout may be private to its owner. Preload this lazy HTTP
        # dependency before permanent UID drops; never widen checkout permissions.
        self.assertTrue(callable(scoped_dispatch))
        self.folder = tempfile.TemporaryDirectory(prefix='phantomview-handoff-')
        self.addCleanup(self.folder.cleanup)
        os.chown(self.folder.name, READER, ISSUER)
        os.chmod(self.folder.name, 0o750)
        self.path = str(Path(self.folder.name) / 'native.sock')
        self.ready_read, self.ready_write = os.pipe()
        self.addCleanup(os.close, self.ready_read)
        self.addCleanup(os.close, self.ready_write)
        self.fixture = signatures.SignedRecipientTests()
        self.fixture.setUp()
        self.fixture.org = scoped_organization()
        self.authorization = self.fixture.authorization(self.fixture.signed())
        self.done_read, self.done_write = os.pipe()
        self.addCleanup(os.close, self.done_read)
        self.addCleanup(os.close, self.done_write)

    def start(self, operation, uid=READER):
        child = spawn(uid, operation)
        self.assertTrue(select.select([self.ready_read], [], [], 8)[0], 'Reader readiness timed out')
        self.assertEqual(os.read(self.ready_read, 1), b'1')
        return child

    def native(self):
        return request_access(self.path, ReaderPolicy(READER, frozenset({MODEL})),
                              self.fixture.gate.origin, self.authorization,
                              {'channel': 'telegram', 'sender': '101', 'direct': True,
                               'principal_authenticated': True, 'scope_id': 'river-project'})

    def native_command(self):
        delivered = []

        def deliver(channel, sender, link):
            delivered.append((channel, sender, link))
            return True

        handler = NativeAccessCommand(channel='telegram', scope_id='river-project', socket_path=self.path,
                                      policy=ReaderPolicy(READER, frozenset({MODEL})),
                                      origin=self.fixture.gate.origin,
                                      sign_authorization=lambda: self.authorization, deliver_direct=deliver)
        message = DirectMessage('101', '42', int(time.time()), '/phantomview', True, True)
        first, repeated = handler.handle(message), handler.handle(message)
        return {'delivered': first is Outcome.DELIVERED, 'duplicate': repeated is Outcome.DUPLICATE,
                'same_sender': len(delivered) == 1 and delivered[0][:2] == ('telegram', '101'),
                'fragment_only': len(delivered) == 1 and '/#c=' in delivered[0][2]}

    def test_isolated_native_account_receives_real_signed_scoped_single_use_link(self):
        def reader():
            gate = self.fixture.gate
            original = gate.issue_identified
            captured = []

            def issue(*args, **kwargs):
                link = original(*args, **kwargs)
                captured.append(link)
                return link

            gate.issue_identified = issue
            runtime = ReaderHandoff(self.path, ISSUER, PeerPolicy(ISSUER, frozenset({MODEL})), gate)
            projection = ProjectionFixture()
            projection.setUp()
            with pv.ThreadingHTTPServer(('127.0.0.1', 0), pv.Handler) as http:
                http.gate, http.access_errors = gate, (ValueError, gate.access.core.Invalid)
                http.scoped_backend = ScopedBackend(gate, lambda: projection.catalog, projection.load)
                thread = threading.Thread(target=http.serve_forever, daemon=True)
                thread.start()
                try:
                    runtime.start(http)
                    os.write(self.ready_write, b'1')
                    if not select.select([self.done_read], [], [], 8)[0]:
                        raise AssertionError('Native client did not complete')
                    os.read(self.done_read, 1)
                    accepted = runtime.healthy and bool(captured)
                    code = captured[0].split('#c=')[1]
                    connection = HTTPConnection('127.0.0.1', http.server_port, timeout=3)
                    try:
                        body = json.dumps({'code': code})
                        connection.request('POST', '/api/redeem', body, {'Content-Type': 'application/json'})
                        response = connection.getresponse()
                        if response.status != 200:
                            raise AssertionError('HTTP reader rejected native handoff grant')
                        cookie = SimpleCookie(response.getheader('Set-Cookie'))['phantomview'].value
                        response.read()
                        recipient, _ = gate.identified_scope({'Cookie': 'phantomview=' + cookie})
                        connection.request('GET', '/api/state', headers={'Cookie': 'phantomview=' + cookie})
                        response = connection.getresponse()
                        if response.status != 200:
                            raise AssertionError('Scoped projection rejected identified HTTP session')
                        view = json.loads(response.read())
                        scoped_counts = view['counts']
                        if view['scope_id'] != 'river-project' or set(projection.loaded) != {projection.project}:
                            raise AssertionError('HTTP projection read outside the bound project')
                        connection.request('POST', '/api/redeem', body, {'Content-Type': 'application/json'})
                        response = connection.getresponse()
                        replay_rejected = response.status == 401
                        response.read()
                    finally:
                        connection.close()
                finally:
                    runtime.close()
                    http.shutdown()
                    thread.join(timeout=3)
            return {'accepted': accepted, 'human': recipient.human, 'scope': recipient.scope_id,
                    'replay_rejected': replay_rejected, 'socket_removed': not Path(self.path).exists(),
                    'scoped_counts': scoped_counts}

        server = self.start(reader)
        native = finish(spawn(ISSUER, self.native_command))
        os.write(self.done_write, b'1')
        result = finish(server)
        self.assertEqual(native, {'ok': True, 'value': {'delivered': True, 'duplicate': True,
                                                     'same_sender': True, 'fragment_only': True}})
        self.assertEqual(result, {'ok': True, 'value': {'accepted': True, 'human': 'owner',
                                                     'scope': 'river-project', 'replay_rejected': True,
                                                     'socket_removed': True,
                                                     'scoped_counts': {'partner': 1, 'relationship': 0}}})

    def test_model_account_cannot_use_socket_even_with_valid_signing_event(self):
        def reader():
            with bind_listener(self.path, ISSUER) as listener:
                listener.settimeout(6)
                os.write(self.ready_write, b'1')
                connection, _ = listener.accept()
                accepted = serve_connection(connection, self.fixture.gate, PeerPolicy(ISSUER, frozenset({MODEL})))
            return {'accepted': accepted, 'issued': len(self.fixture.gate.recipient_links)}

        def attacker():
            # Bypass the cooperative client and submit directly as a model UID.
            raw = json.dumps({'schema_version': 1, 'authorization': self.authorization,
                              'channel': 'telegram', 'sender': '101', 'direct': True,
                              'principal_authenticated': True, 'scope_id': 'river-project'}).encode()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(3)
                connection.connect(self.path)
                try:
                    connection.sendall(struct.pack('!I', len(raw)) + raw)
                    return {'no_grant': connection.recv(1) == b''}
                except (BrokenPipeError, ConnectionResetError):
                    return {'no_grant': True}

        server = self.start(reader)
        result = finish(spawn(MODEL, attacker))
        self.assertEqual(result, {'ok': True, 'value': {'no_grant': True}})
        self.assertEqual(finish(server), {'ok': True, 'value': {'accepted': False, 'issued': 0}})

    def test_native_client_rejects_unexpected_reader_uid_before_sending_identity(self):
        def reader():
            with bind_listener(self.path, ISSUER) as listener:
                listener.settimeout(6)
                os.write(self.ready_write, b'1')
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(3)
                    return {'received_no_context': connection.recv(1) == b''}

        # Verify the real kernel peer against an unexpected receiver UID without
        # transmitting any request bytes. Path validation has separate coverage.
        server = self.start(reader)

        def native_wrong_receiver():
            policy = ReaderPolicy(READER, frozenset({MODEL}))
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.connect(self.path)
                wrong = ReaderPolicy(MODEL, frozenset({29004}))
                try:
                    wrong.verify(connection)
                except ValueError:
                    return {'wrong_reader_rejected': True, 'configured_reader': policy.receiver_uid == READER}
                return {'wrong_reader_rejected': False}

        result = finish(spawn(ISSUER, native_wrong_receiver))
        self.assertEqual(result, {'ok': True, 'value': {'wrong_reader_rejected': True, 'configured_reader': True}})
        self.assertEqual(finish(server), {'ok': True, 'value': {'received_no_context': True}})


if __name__ == '__main__':
    if not ENABLED:
        raise SystemExit('Run only in the explicit disposable Linux account-test job')
    unittest.main()
