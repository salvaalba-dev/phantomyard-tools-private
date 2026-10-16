"""Private handoff rejects model accounts before reading identity claims."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_signed_recipient as signatures
from test_view_permissions import scoped_organization
import trusted_handoff as handoff


def frame(document):
    raw = json.dumps(document).encode()
    return struct.pack('!I', len(raw)) + raw


def request(**changes):
    return {'schema_version': 1, 'authorization': 'Nostr synthetic-event',
            'channel': 'telegram', 'sender': '101', 'direct': True,
            'principal_authenticated': True, 'scope_id': 'example'} | changes


class Connection:
    family = 1

    def __init__(self, raw, uid=200):
        self.raw, self.uid = raw, uid
        self.reads, self.output, self.closed = 0, b'', False

    def getsockopt(self, *args):
        return struct.pack('3i', 1234, self.uid, 200)

    def settimeout(self, seconds):
        self.timeout = seconds

    def recv(self, length):
        self.reads += 1
        result, self.raw = self.raw[:length], self.raw[length:]
        return result

    def sendall(self, raw):
        self.output += raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def response(self):
        length = struct.unpack('!I', self.output[:4])[0]
        return json.loads(self.output[4:4 + length])


class HandoffSetup:
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(handoff.sys, 'platform', 'linux'))
        self.stack.enter_context(patch.object(handoff.socket, 'SO_PEERCRED', 17, create=True))
        self.stack.enter_context(patch.object(handoff.socket, 'AF_UNIX', 1, create=True))
        self.stack.enter_context(patch.object(handoff.os, 'getuid', return_value=100, create=True))
        self.policy = handoff.PeerPolicy(200, frozenset({300, 301}))


class HandoffTests(HandoffSetup, unittest.TestCase):
    def test_separate_accounts_are_mandatory(self):
        for issuer, models in ((100, frozenset({300})), (200, frozenset()),
                               (200, frozenset({200})), (200, frozenset({100})),
                               (0, frozenset({300})), (True, frozenset({300})),
                               (200, {300}), (200, frozenset({True})), (200, frozenset({0}))):
            with self.subTest(issuer=issuer, models=models), self.assertRaises(ValueError):
                handoff.PeerPolicy(issuer, models)

    def test_unsupported_platform_cannot_fall_back_to_network_or_claimed_identity(self):
        with patch.object(handoff.sys, 'platform', 'win32'), self.assertRaises(ValueError):
            handoff.PeerPolicy(200, frozenset({300}))

    def test_unknown_or_model_peer_is_rejected_before_read_or_reply(self):
        for uid in (0, 100, 300, 301, 999):
            connection = Connection(frame(request()), uid)
            self.assertFalse(handoff.serve_connection(connection, object(), self.policy))
            self.assertEqual(connection.reads, 0)
            self.assertEqual(connection.output, b'')
            self.assertTrue(connection.closed)

    def test_network_socket_is_not_an_authenticated_handoff(self):
        connection = Connection(frame(request()))
        connection.family = socket.AF_INET
        self.assertFalse(handoff.serve_connection(connection, object(), self.policy))
        self.assertEqual(connection.reads, 0)

    def test_missing_peer_credentials_fail_before_read(self):
        connection = Connection(frame(request()))
        connection.getsockopt = lambda *args: b''
        self.assertFalse(handoff.serve_connection(connection, object(), self.policy))
        self.assertEqual(connection.reads, 0)

    def test_payload_rejects_identity_overrides_and_unauthenticated_contexts(self):
        for change in ({'human': 'owner'}, {'persona': 'administrator'}, {'origin': 'https://other.example'},
                       {'scope_id': None}, {'scope_id': ''}, {'direct': False}, {'direct': 1},
                       {'principal_authenticated': False}, {'principal_authenticated': 1},
                       {'channel': 'email'}, {'sender': 101}, {'schema_version': True}):
            connection = Connection(frame(request(**change)))
            self.assertFalse(handoff.serve_connection(connection, object(), self.policy))
            self.assertEqual(connection.response(), {'schema_version': 1, 'error': 'Verified access handoff denied'})

    def test_bounded_truncated_and_duplicate_frames_fail_generically(self):
        duplicate = b'{"schema_version":1,"schema_version":1}'
        for raw in (struct.pack('!I', handoff.MAX_FRAME + 1), b'\x00', frame(request())[:-1],
                    struct.pack('!I', len(duplicate)) + duplicate, b'\x00\x00\x00\x00'):
            connection = Connection(raw)
            self.assertFalse(handoff.serve_connection(connection, object(), self.policy))
            self.assertEqual(connection.response()['error'], 'Verified access handoff denied')

    def test_fixed_origin_and_persona_come_from_reader_not_request(self):
        class Gate:
            origin = 'https://view.example'
            policy = {'actor': 'coordinator'}

            def issue_identified(self, authorization, origin, **context):
                self.arguments = authorization, origin, context
                return self.origin + '/#c=synthetic-grant'

        gate = Gate()
        connection = Connection(frame(request()))
        self.assertTrue(handoff.serve_connection(connection, gate, self.policy))
        self.assertEqual(gate.arguments[1], gate.origin)
        self.assertEqual(gate.arguments[2]['persona'], 'coordinator')
        self.assertEqual(set(connection.response()), {'schema_version', 'link'})

    def test_gate_errors_never_echo_credentials_or_exception_text(self):
        class Gate:
            origin, policy = 'https://view.example', {'actor': 'coordinator'}

            def issue_identified(self, *args, **kwargs):
                raise ValueError('private sender and credential details')

        connection = Connection(frame(request()))
        self.assertFalse(handoff.serve_connection(connection, Gate(), self.policy))
        self.assertNotIn(b'private sender', connection.output)
        self.assertNotIn(b'Nostr', connection.output)

    def test_total_read_deadline_cannot_be_extended_by_fragmented_input(self):
        connection = Connection(frame(request()))
        with patch.object(handoff.time, 'monotonic', side_effect=[0, 4, 4]):
            self.assertFalse(handoff.serve_connection(connection, object(), self.policy))
        self.assertEqual(connection.reads, 0)
        self.assertTrue(connection.closed)


@unittest.skipUnless(sys.platform == 'linux', 'Linux kernel credentials and socket permissions required')
class LinuxSocketTests(unittest.TestCase):
    def test_real_kernel_peer_account_is_rejected_before_read(self):
        uid = os.getuid()
        policy = handoff.PeerPolicy(uid + 10000, frozenset({uid + 20000}))
        client, server = socket.socketpair()
        with client:
            self.assertFalse(handoff.serve_connection(server, object(), policy))
            self.assertEqual(client.recv(1), b'')

    def test_private_socket_permissions_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            os.chmod(root, 0o750)
            path = Path(root) / 'native.sock'
            listener = handoff.bind_listener(path, os.getgid())
            try:
                self.assertEqual(path.stat().st_mode & 0o777, 0o660)
                with self.assertRaises(ValueError):
                    handoff.bind_listener(path, os.getgid())
            finally:
                listener.close()

    def test_writable_directory_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            os.chmod(root, 0o777)
            with self.assertRaises(ValueError):
                handoff.bind_listener(Path(root) / 'native.sock', os.getgid())
            os.chmod(root, 0o750)
            (Path(root) / 'alias').symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                handoff.bind_listener(Path(root) / 'alias' / 'native.sock', os.getgid())


@unittest.skipIf(signatures.PrivateKey is None, 'Real-signature handoff requires PhantomBlog access extra')
class SignedHandoffTests(HandoffSetup, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.fixture = signatures.SignedRecipientTests()
        self.fixture.setUp()
        self.fixture.org = scoped_organization()

    def issue(self, **changes):
        document = request(authorization=self.fixture.authorization(self.fixture.signed()), **changes)
        connection = Connection(frame(document))
        success = handoff.serve_connection(connection, self.fixture.gate, self.policy)
        return success, connection.response()

    def test_signed_handoff_produces_single_use_scoped_session(self):
        success, response = self.issue(scope_id='river-project')
        self.assertTrue(success)
        link = response['link']
        self.assertNotIn('river-project', link)
        cookie = self.fixture.gate.redeem(link.split('#c=')[1])
        recipient, _ = self.fixture.gate.identified_scope({'Cookie': 'phantomview=' + cookie})
        self.assertEqual(recipient.human, 'owner')
        self.assertEqual(recipient.scope_id, 'river-project')
        with self.assertRaises(signatures.access.core.Invalid):
            self.fixture.gate.redeem(link.split('#c=')[1])

    def test_unknown_human_and_unpermitted_counterpart_fail_closed(self):
        for sender in ('999', '102'):
            success, response = self.issue(sender=sender)
            self.assertFalse(success)
            self.assertNotIn('link', response)
        self.assertEqual(self.fixture.gate.recipient_links, {})

    def test_replay_and_policy_revocation_still_apply(self):
        document = request(authorization=self.fixture.authorization(self.fixture.signed()))
        first, second = Connection(frame(document)), Connection(frame(document))
        self.assertTrue(handoff.serve_connection(first, self.fixture.gate, self.policy))
        self.assertFalse(handoff.serve_connection(second, self.fixture.gate, self.policy))
        self.fixture.org['humans'][0]['telegram_user_id'] = 999
        with self.assertRaises(ValueError):
            self.fixture.gate.redeem(first.response()['link'].split('#c=')[1])

    def test_valid_peer_cannot_bypass_schnorr_signature_validation(self):
        event = self.fixture.signed()
        event['sig'] = '0' * 128
        connection = Connection(frame(request(authorization=self.fixture.authorization(event))))
        self.assertFalse(handoff.serve_connection(connection, self.fixture.gate, self.policy))
        self.assertNotIn('link', connection.response())
        self.assertEqual(self.fixture.gate.recipient_links, {})


if __name__ == '__main__':
    unittest.main()
