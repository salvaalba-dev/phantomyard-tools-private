"""Explicit whole-daemon trust retains peer checks; isolated defaults stay strict."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch

import handoff_client as client
import trusted_handoff as server
from test_trusted_handoff import Connection


class DaemonPolicyTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(server.sys, 'platform', 'linux'))
        self.stack.enter_context(patch.object(server.socket, 'SO_PEERCRED', 17, create=True))
        self.stack.enter_context(patch.object(server.socket, 'AF_UNIX', 1, create=True))
        self.uid = self.stack.enter_context(patch.object(server.os, 'getuid', return_value=100, create=True))

    def test_daemon_account_is_explicit_and_unknown_peers_are_still_denied(self):
        policy = server.DaemonPeerPolicy(200)
        self.assertIsInstance(policy, server.PeerPolicy)
        policy.verify(Connection(b'', uid=200))
        with self.assertRaises(ValueError):
            policy.verify(Connection(b'', uid=201))
        denied = Connection(b'PRIVATE_FRAME', uid=201)
        self.assertFalse(server.serve_connection(denied, None, policy))
        self.assertEqual((denied.reads, denied.output), (0, b''))
        for issuer, models in ((0, frozenset()), (100, frozenset()),
                               (True, frozenset()), (200, frozenset({300})), (200, set())):
            with self.subTest(issuer=issuer, models=models), self.assertRaises(ValueError):
                server.DaemonPeerPolicy(issuer, models)
        with self.assertRaises(ValueError):
            server.PeerPolicy(200, frozenset({200}))

    def test_daemon_client_still_requires_the_configured_separate_reader(self):
        self.uid.return_value = 200
        policy = client.DaemonReaderPolicy(100)
        self.assertIsInstance(policy, client.ReaderPolicy)
        policy.verify(Connection(b'', uid=100))
        with self.assertRaises(ValueError):
            policy.verify(Connection(b'', uid=101))
        for receiver, models in ((0, frozenset()), (200, frozenset()),
                                 (100, frozenset({200})), (100, set())):
            with self.subTest(receiver=receiver, models=models), self.assertRaises(ValueError):
                client.DaemonReaderPolicy(receiver, models)
        with self.assertRaises(ValueError):
            client.ReaderPolicy(100, frozenset())

    def test_root_and_unsupported_platforms_do_not_gain_a_fallback(self):
        self.uid.return_value = 0
        for constructor, account in ((server.DaemonPeerPolicy, 200), (client.DaemonReaderPolicy, 100)):
            with self.assertRaises(ValueError):
                constructor(account)
        self.uid.return_value = 100
        with patch.object(server.sys, 'platform', 'win32'):
            with self.assertRaises(ValueError):
                server.DaemonPeerPolicy(200)
