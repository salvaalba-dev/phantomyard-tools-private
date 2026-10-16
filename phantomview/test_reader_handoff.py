"""Reader lifecycle shares one gate and closes the private listener on shutdown."""
from contextlib import ExitStack, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
import phantomview as pv
from reader_handoff import ReaderHandoff
from test_access_gate import ACCESS
from test_view_permissions import scoped_organization
from trusted_handoff import PeerPolicy


def gate():
    return IdentifiedGate(ACCESS, {'identities': ['a' * 64], 'actor': 'coordinator'},
                          'https://view.example', 8789,
                          directory_loader=lambda: HumanDirectory(scoped_organization()))


class ReaderServeTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.server = types.SimpleNamespace(server_port=8765,
                                            serve_forever=lambda: self.events.append('http_serve'),
                                            server_close=lambda: self.events.append('http_closed'))
        self.obs = types.SimpleNamespace(config={}, refresh=lambda: None)
        self.gate = gate()
        self.handoff = Mock()
        self.handoff.start.side_effect = lambda server: self.events.append('handoff_started')
        self.handoff.close.side_effect = lambda: self.events.append('handoff_closed')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(pv, 'ThreadingHTTPServer', return_value=self.server))
        self.stack.enter_context(patch.object(pv.threading, 'Thread'))
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.stack.enter_context(redirect_stdout(StringIO()))

    def test_listener_lifetime_is_inside_the_http_reader_lifetime(self):
        pv.serve(self.obs, 8765, False, self.gate, handoff=self.handoff)
        self.handoff.start.assert_called_once_with(self.server)
        self.assertIs(self.server.gate, self.gate)
        self.assertEqual(self.events, ['handoff_started', 'http_serve', 'handoff_closed', 'http_closed'])

    def test_startup_failure_closes_http_socket_before_serving(self):
        self.handoff.start.side_effect = ValueError('Private listener unavailable')
        with self.assertRaises(ValueError):
            pv.serve(self.obs, 8765, False, self.gate, handoff=self.handoff)
        self.assertEqual(self.events, ['http_closed'])

    def test_http_exception_still_stops_private_handoff(self):
        self.server.serve_forever = Mock(side_effect=OSError('test failure'))
        with self.assertRaises(OSError):
            pv.serve(self.obs, 8765, False, self.gate, handoff=self.handoff)
        self.assertEqual(self.events, ['handoff_started', 'handoff_closed', 'http_closed'])

    def test_handoff_shutdown_failure_still_closes_http_socket(self):
        self.handoff.close.side_effect = RuntimeError('test failure')
        with self.assertRaises(RuntimeError):
            pv.serve(self.obs, 8765, False, self.gate, handoff=self.handoff)
        self.assertEqual(self.events, ['handoff_started', 'http_serve', 'http_closed'])

    def test_default_reader_has_no_private_listener(self):
        pv.serve(self.obs, 8765, False, self.gate)
        self.assertEqual(self.events, ['http_serve', 'http_closed'])
        self.handoff.start.assert_not_called()


@unittest.skipUnless(sys.platform == 'linux', 'Linux socket lifecycle required')
class ReaderSocketTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'native.sock'
        self.gate = gate()
        uid = os.getuid()
        policy = PeerPolicy(uid + 10000, frozenset({uid + 20000}))
        self.runtime = ReaderHandoff(self.path, os.getgid(), policy, self.gate)
        self.addCleanup(self.runtime.close)
        self.server = types.SimpleNamespace(gate=self.gate)

    def test_other_gate_cannot_share_recipient_bindings(self):
        with self.assertRaises(ValueError):
            self.runtime.start(types.SimpleNamespace(gate=gate()))
        self.assertFalse(self.path.exists())

    def test_real_listener_rejects_unknown_peer_and_stops_without_stale_socket(self):
        self.runtime.start(self.server)
        self.assertTrue(self.runtime.healthy)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3)
            connection.connect(str(self.path))
            self.assertEqual(connection.recv(1), b'')
        self.runtime.close()
        self.assertFalse(self.runtime.healthy)
        self.assertFalse(self.path.exists())
        with self.assertRaises(ValueError):
            self.runtime.start(self.server)

    def test_shutdown_preserves_operator_replacement_file(self):
        self.runtime.start(self.server)
        self.path.unlink()
        self.path.write_text('operator replacement', encoding='utf-8')
        self.runtime.close()
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'operator replacement')


if __name__ == '__main__':
    unittest.main()
