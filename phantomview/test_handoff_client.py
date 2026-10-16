"""The native client authenticates its reader before transmitting sender context."""
from contextlib import ExitStack
import struct
import unittest
from unittest.mock import patch

import handoff_client as client
from test_trusted_handoff import Connection, frame


class ClientConnection(Connection):
    def connect(self, destination):
        self.destination = destination


class HandoffClientTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(client.sys, 'platform', 'linux'))
        self.stack.enter_context(patch.object(client.os, 'getuid', return_value=200, create=True))
        self.stack.enter_context(patch.object(client.socket, 'SO_PEERCRED', 17, create=True))
        self.stack.enter_context(patch.object(client.socket, 'AF_UNIX', 1, create=True))
        self.destination = self.stack.enter_context(patch.object(client, '_destination', return_value='/private/native.sock'))
        self.origin = 'https://view.example:8790'
        self.link = self.origin + '/#c=' + 'a' * 43
        self.connection = ClientConnection(frame({'schema_version': 1, 'link': self.link}), uid=100)
        self.factory = self.stack.enter_context(patch.object(client.socket, 'socket', return_value=self.connection))
        self.policy = client.ReaderPolicy(100, frozenset({300}))
        self.context = {'channel': 'telegram', 'sender': '101', 'direct': True,
                        'principal_authenticated': True, 'scope_id': 'river-project'}

    def call(self):
        return client.request_access('/private/native.sock', self.policy, self.origin,
                                     'Nostr synthetic-event', self.context)

    def test_expected_reader_and_exact_fragment_link_are_required(self):
        self.assertEqual(self.call(), self.link)
        self.assertTrue(self.connection.closed)
        self.assertIn(b'river-project', self.connection.output)
        self.assertEqual(self.factory.call_count, 1)

    def test_wrong_peer_receives_no_signed_event_or_sender_bytes(self):
        self.connection.uid = 999
        with self.assertRaisesRegex(ValueError, '^Verified access handoff failed;'):
            self.call()
        self.assertEqual(self.connection.output, b'')
        self.assertEqual(self.connection.reads, 0)

    def test_model_and_shared_accounts_cannot_construct_client_policy(self):
        for receiver, models in ((200, frozenset({300})), (100, frozenset({200})),
                                  (100, frozenset({100})), (100, frozenset()),
                                  (100, frozenset({0})), (True, frozenset({300}))):
            with self.subTest(receiver=receiver, models=models), self.assertRaises(ValueError):
                client.ReaderPolicy(receiver, models)

    def test_unexpected_origin_or_credential_delivery_shape_is_rejected(self):
        for link in ('https://other.example/#c=' + 'a' * 43, self.origin + '/?c=' + 'a' * 43,
                     self.origin + '/#c=short', self.origin + '/#c=' + 'a' * 43 + '&human=owner'):
            self.connection.raw = frame({'schema_version': 1, 'link': link})
            with self.subTest(link=link), self.assertRaises(ValueError):
                self.call()

    def test_invalid_context_is_rejected_before_connection(self):
        self.context['human'] = 'owner'
        with self.assertRaises(ValueError):
            self.call()
        self.factory.assert_not_called()

    def test_bad_response_is_bounded_and_does_not_echo_reader_errors(self):
        for raw in (frame({'schema_version': 1, 'error': 'private server details'}),
                    struct.pack('!I', client.MAX_FRAME + 1), b'\x00',
                    frame({'schema_version': True, 'link': self.link})):
            self.connection.raw = raw
            with self.subTest(raw=raw[:4]), self.assertRaises(ValueError) as raised:
                self.call()
            self.assertNotIn('private server', str(raised.exception))

    def test_invalid_config_and_socket_validation_fail_before_transmission(self):
        for origin in (None, 'http://view.example', 'https://user@view.example',
                       'https://view.example/path', 'https://view.example:bad', 'https://view.example\n'):
            self.origin = origin
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                self.call()
        self.factory.assert_not_called()
        self.origin = 'https://view.example:8790'
        self.destination.side_effect = OSError('private path')
        with self.assertRaises(ValueError):
            self.call()
        self.factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
