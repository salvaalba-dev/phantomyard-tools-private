"""One-shot framing/configuration tests; kernel peer checks remain in handoff_client."""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import handoff_client
import native_link_client as client


class NativeLinkClientTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(handoff_client.sys, 'platform', 'linux'))
        self.uid = self.stack.enter_context(patch.object(client.os, 'getuid', return_value=200, create=True))
        self.stack.enter_context(patch.object(handoff_client.socket, 'SO_PEERCRED', 17, create=True))
        self.request = self.stack.enter_context(patch.object(client, 'request_access',
            return_value='https://view.example/#c=' + 'a' * 43))
        self.args = ['--socket', '/private/native.sock', '--issuer-uid', '200', '--reader-uid', '100',
            '--model-uid', '300', '--origin', 'https://view.example', '--channel', 'telegram',
            '--scope-id', 'river-project']
        self.document = {'schema_version': 1, 'authorization': 'Nostr synthetic-event',
            'channel': 'telegram', 'sender': '101', 'direct': True,
            'principal_authenticated': True, 'scope_id': 'river-project'}

    def run_frame(self, document=None, *, raw=None, args=None):
        outgoing = io.StringIO()
        raw = json.dumps(self.document if document is None else document).encode() if raw is None else raw
        status = client.run(self.args if args is None else args, io.BytesIO(raw), outgoing)
        return status, json.loads(outgoing.getvalue())

    def test_exact_frame_reuses_the_protected_existing_client(self):
        status, response = self.run_frame()
        self.assertEqual(status, 0)
        self.assertEqual(set(response), {'schema_version', 'link'})
        self.assertEqual(self.request.call_args.args[0], '/private/native.sock')
        self.assertEqual(self.request.call_args.args[3], 'Nostr synthetic-event')
        self.assertEqual(self.request.call_args.args[4], {
            key: self.document[key] for key in ('channel', 'sender', 'direct', 'principal_authenticated', 'scope_id')})
        self.assertNotIn('101', json.dumps(response))

    def test_route_or_authority_overrides_never_reach_ipc(self):
        for changes in ({'channel': 'phantomchat'}, {'scope_id': 'other'}, {'human': 'owner'},
                        {'persona': 'other'}, {'direct': False}, {'principal_authenticated': False}):
            with self.subTest(changes=changes):
                status, response = self.run_frame(self.document | changes)
                self.assertEqual(status, 1)
                self.assertNotIn('link', response)
        self.request.assert_not_called()

    def test_empty_oversized_malformed_and_duplicate_frames_are_rejected(self):
        duplicate = json.dumps(self.document)[:-1] + ',"sender":"102"}'
        for raw in (b'', b'x' * (client.MAX_FRAME + 1), b'{', duplicate.encode(), b'null', b'[]'):
            with self.subTest(raw=raw[:12]):
                self.assertEqual(self.run_frame(raw=raw)[0], 1)
        self.request.assert_not_called()

    def test_unexpected_root_or_model_account_is_denied_before_ipc(self):
        for uid in (0, 201, 300):
            with self.subTest(uid=uid):
                self.uid.return_value = uid
                self.assertEqual(self.run_frame()[0], 1)
        self.uid.return_value = 200
        args = [value if value != '300' else '200' for value in self.args]
        self.assertEqual(self.run_frame(args=args)[0], 1)
        self.request.assert_not_called()

    def test_client_failure_text_is_not_echoed(self):
        self.request.side_effect = ValueError('PRIVATE_SENTINEL signed-event sender')
        status, response = self.run_frame()
        self.assertEqual(status, 1)
        self.assertEqual(response, {'schema_version': 1, 'error': 'Verified access handoff denied'})

    def test_no_configuration_or_unrecognized_flags_fail_closed(self):
        for args in ([], self.args + ['--human', 'owner']):
            self.assertEqual(self.run_frame(args=args)[0], 1)
        self.request.assert_not_called()


class IsolatedClientEntryTests(unittest.TestCase):
    def test_isolated_python_entry_imports_without_environment_and_rejects_invalid_account(self):
        script = Path(__file__).with_name('native_link_client.py')
        result = subprocess.run([sys.executable, '-I', str(script)],
            input=b'PRIVATE_SENTINEL', capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b'PRIVATE_SENTINEL', result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['error'], 'Verified access handoff denied')
