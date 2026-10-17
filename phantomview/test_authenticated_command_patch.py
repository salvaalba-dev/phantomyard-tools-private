"""Exact-source command hook preparation and standalone synthetic routing checks."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import authenticated_command_patch as native
from test_native_ingress_patch import SOURCE


@unittest.skipUnless(SOURCE.is_dir(), 'Pinned native checkout is required')
class AuthenticatedCommandPatchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in native.provenance.INPUTS | native.INPUTS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((SOURCE / name).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_generic_hooks_run_before_model_dispatch_with_existing_principal_decisions(self):
        native.patch(self.root)
        engine = (self.root / 'src/channels/core/engine.ts').read_text(encoding='utf-8')
        server = (self.root / 'src/channels/phantomchat/server.ts').read_text(encoding='utf-8')
        self.assertLess(engine.index('verifyAuthenticatedCommand(input.authenticatedCommand'),
                        engine.index('const serverStartedAt'))
        self.assertLess(engine.index('"telegram", msg, principalAuthenticated'), engine.index('const isVoice ='))
        self.assertIn('commandPrincipals = new Set(allowedSet)', server)
        self.assertIn('&& !relaySet.has(msg.senderId.toLowerCase())', server)
        loop = server[server.index('for await (const msg of channel.listen(input.signal))'):]
        self.assertLess(loop.index('authenticatedCommand.consume'), loop.index('if (msg.reaction)'))
        for name in ('README.md', 'AGENTS.md'):
            self.assertIn(native.NOTE, (self.root / name).read_text(encoding='utf-8'))
        self.assertTrue((self.root / native.HELPER).is_file())
        self.assertFalse((self.root / native.reviewed.HELPER).exists())

    def test_drift_or_reapplication_refuses_before_writing(self):
        path = self.root / 'src/channels/phantomchat/server.ts'
        original = path.read_text(encoding='utf-8')
        path.write_text(original + '\n// Unsupported drift\n', encoding='utf-8', newline='\n')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())
        path.write_text(original, encoding='utf-8', newline='\n')
        native.patch(self.root)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())

    def test_existing_operator_helper_is_preserved(self):
        path = self.root / native.HELPER
        path.write_text('operator content', encoding='utf-8')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())


@unittest.skipUnless(shutil.which('node'), 'Node.js is required')
class AuthenticatedCommandRuntimeTests(unittest.TestCase):
    def test_standalone_command_routing(self):
        version = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True)
        if int(version.stdout.strip().lstrip('v').split('.')[0]) < 24:
            self.skipTest('Node 24 TypeScript stripping is required for standalone tests')
        result = subprocess.run(['node', '--test', 'test_authenticated_command.cjs'],
            cwd=Path(__file__).parent, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
