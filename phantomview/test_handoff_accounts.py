"""Disposable Linux CI checks with permanently dropped numeric process UIDs.

Run only in an ephemeral CI runner as root with PHANTOMVIEW_ACCOUNT_TESTS=1.
No users, groups, services or production configuration are created or changed.
"""
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import sys
import tempfile
import unittest

from handoff_client import ReaderPolicy, request_access
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
            with bind_listener(self.path, ISSUER) as listener:
                listener.settimeout(6)
                os.write(self.ready_write, b'1')
                connection, _ = listener.accept()
                accepted = serve_connection(connection, gate, PeerPolicy(ISSUER, frozenset({MODEL})))
            code = captured[0].split('#c=')[1]
            cookie = gate.redeem(code)
            recipient, _ = gate.identified_scope({'Cookie': 'phantomview=' + cookie})
            replay_rejected = False
            try:
                gate.redeem(code)
            except signatures.access.core.Invalid:
                replay_rejected = True
            return {'accepted': accepted, 'human': recipient.human, 'scope': recipient.scope_id,
                    'replay_rejected': replay_rejected}

        server = self.start(reader)
        native = finish(spawn(ISSUER, lambda: {'fragment_only': '/#c=' in self.native()}))
        result = finish(server)
        self.assertEqual(native, {'ok': True, 'value': {'fragment_only': True}})
        self.assertEqual(result, {'ok': True, 'value': {'accepted': True, 'human': 'owner',
                                                     'scope': 'river-project', 'replay_rejected': True}})

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
