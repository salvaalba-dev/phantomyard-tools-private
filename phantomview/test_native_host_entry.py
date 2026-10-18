"""Offline host composition preserves native bootstrap and refuses unsafe input."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import native_host_entry as host
from test_native_ingress_patch import SOURCE

EXAMPLE = Path(__file__).with_name('native-host-example.json')


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(EXAMPLE.read_text(encoding='utf-8'))

    def test_explicit_routes_are_copied_and_preserve_both_channels(self):
        routes = host.validate_routes(self.document)
        self.assertEqual([r['channel'] for r in routes], ['telegram', 'phantomchat'])
        self.document['routes'][0]['persona'] = 'changed'
        self.assertEqual(routes[0]['persona'], 'coordinator')

    def test_no_credentials_identities_grants_or_runtime_options(self):
        for field in ('secretKey', 'sender', 'human', 'categories', 'trustBoundary', 'modelUids'):
            with self.subTest(field=field):
                document = copy.deepcopy(self.document)
                document['routes'][0][field] = 'forbidden'
                with self.assertRaises(ValueError):
                    host.validate_routes(document)

    def test_malformed_routes_and_ambiguous_accounts_refuse(self):
        variants = [None, {}, {'schema_version': True, 'routes': []},
                    {'schema_version': 1, 'routes': []},
                    {'schema_version': 1, 'routes': self.document['routes'] * 33}]
        invalid = {'persona': ['', '../other'], 'channel': ['web', []],
                   'scopeId': ['', 'project\nother'], 'issuerUid': [0, True, -1, 2**32],
                   'readerUid': [0, 12001, False],
                   'origin': ['http://view.example', 'https://view.example/',
                              'https://user:pass@view.example', 'https://view.example?q=1',
                              'https://view.example#c=secret', 'https://VIEW.example',
                              'https://view.example:443', 'https://view.example:0'],
                   'python': ['relative', '/opt/../bin/python', '//usr/bin/python', '/'],
                   'clientScript': ['/opt/./client.py', '/opt/client.py\n'],
                   'socketPath': ['/run//reader.sock', 'C:\\reader.sock']}
        for key, values in invalid.items():
            for value in values:
                document = copy.deepcopy(self.document)
                document['routes'][0][key] = value
                variants.append(document)
        duplicate = copy.deepcopy(self.document)
        duplicate['routes'][1]['channel'] = 'telegram'
        variants.append(duplicate)
        mixed = copy.deepcopy(self.document)
        mixed['routes'][1]['issuerUid'] = 12003
        variants.append(mixed)
        for document in variants:
            with self.subTest(document=document), self.assertRaises(ValueError):
                host.validate_routes(document)

    def test_handoff_socket_path_has_the_same_bound_as_conversation_paths(self):
        self.document['routes'][0]['socketPath'] = '/' + 'a' * 99
        self.assertEqual(len(host.validate_routes(self.document)[0]['socketPath']), 100)
        for size in (101, 107, 108):
            with self.subTest(bytes=size):
                self.document['routes'][0]['socketPath'] = '/' + 'a' * (size - 1)
                with self.assertRaisesRegex(ValueError, 'at most 100 bytes'):
                    host.validate_routes(self.document)

    def test_cli_rejects_duplicate_and_oversized_input_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'routes.json'
            for raw in (b'{"schema_version":1,"schema_version":1,"routes":[]}',
                        b'x' * 65537, b'[' * 2000 + b']' * 2000):
                path.write_bytes(raw)
                output, error = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(error):
                    self.assertEqual(host.main(['private-source-marker', str(path)]), 2)
                self.assertEqual(output.getvalue(), '')
                self.assertNotIn('private-source-marker', error.getvalue())
                self.assertNotIn(str(path), error.getvalue())

    def test_conversation_routes_require_matching_channels_and_unique_private_sockets(self):
        for field, value in (('conversationGroup', 0), ('conversationGroup', True),
                             ('conversationSocketPath', '/run/phantomview/reader.sock'),
                             ('conversationSocketPath', 'relative')):
            document = copy.deepcopy(self.document)
            document['routes'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                host.validate_routes(document)
        document = copy.deepcopy(self.document)
        document['routes'][1]['conversationGroup'] += 1
        with self.assertRaises(ValueError):
            host.validate_routes(document)
        self.assertEqual(len(host.conversation_routes(host.validate_routes(self.document))), 1)


@unittest.skipUnless(SOURCE.is_dir(), 'Pinned native source checkout is required')
class HostEntryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(SOURCE / 'src', self.root / 'src')
        for name in host.reviewed.ROOT_FILES:
            shutil.copyfile(SOURCE / name, self.root / name)
        self.document = json.loads(EXAMPLE.read_text(encoding='utf-8'))

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_registers_only_cli_run_and_preserves_bootstrap_and_other_commands(self):
        before = self.snapshot()
        report = host.prepare(self.root, self.document)
        after = self.snapshot()
        self.assertEqual(before['src/index.ts'], after['src/index.ts'])
        self.assertEqual(before['src/cli/index.ts'], after['src/cli/index.ts'])
        self.assertEqual(before['bun.lock'], after['bun.lock'])
        self.assertFalse(report['activation_ready'])
        self.assertEqual(report['route_count'], 2)
        entry = after[host.ENTRY].decode()
        self.assertIn('authenticatedCommands: phantomViewStartupCommands(phantomViewHostRoutes)', entry)
        self.assertEqual(entry.count('phantomViewStartupCommands(phantomViewHostRoutes)'), 1)
        self.assertIn('ifNotRunning: Boolean(args["if-not-running"])', entry)
        self.assertIn('Object.freeze(', after[host.ROUTES].decode())
        self.assertLess(entry.index('const lock = acquireRunLock'), entry.index('await startPersonaConversations'))
        self.assertIn('await personaRuntime?.close()', entry)
        self.assertIn('onCompletion?:', after['src/cli/ask.ts'].decode())
        self.assertIn('screenedHold: chunk.meta?.screenedHold === true', after['src/cli/ask.ts'].decode())
        self.assertTrue((self.root / host.CONVERSATION_HELPER).is_file())
        for name in ('README.md', 'AGENTS.md'):
            self.assertIn(host.NOTE, after[name].decode())
        with self.assertRaises(ValueError):
            host.prepare(self.root, self.document)
        self.assertEqual(after, self.snapshot())

    def test_source_drift_and_existing_host_file_refuse_before_any_writes(self):
        for name in ('src/index.ts', 'bun.lock', host.ROUTES):
            with self.subTest(name=name):
                target = self.root / name
                original = target.read_bytes() if target.exists() else None
                target.write_bytes(b'operator-owned-drift')
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    host.prepare(self.root, self.document)
                self.assertEqual(before, self.snapshot())
                if original is None:
                    target.unlink()
                else:
                    target.write_bytes(original)

    def test_invalid_deployment_route_does_not_modify_reviewed_source(self):
        before = self.snapshot()
        self.document['routes'][0]['issuerUid'] = 0
        with self.assertRaises(ValueError):
            host.prepare(self.root, self.document)
        self.assertEqual(before, self.snapshot())

    def test_omitted_conversation_routes_keep_native_ask_and_lifecycle_unchanged(self):
        for route in self.document['routes']:
            for field in host.CONVERSATION:
                route.pop(field)
        original = (self.root / 'src/cli/ask.ts').read_bytes()
        host.prepare(self.root, self.document)
        self.assertEqual((self.root / 'src/cli/ask.ts').read_bytes(), original)
        self.assertFalse((self.root / host.CONVERSATION_HELPER).exists())
        self.assertNotIn('startPersonaConversations', (self.root / host.ENTRY).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
