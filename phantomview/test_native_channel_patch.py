"""Prepare combined native adapter patches in temporary exact-source copies."""
from pathlib import Path
import tempfile
import unittest

import native_channel_patch as native
from test_native_ingress_patch import SOURCE


@unittest.skipUnless(SOURCE.is_dir(), 'Pinned native source checkout is required')
class NativeChannelPatchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in native.provenance.INPUTS | native.INPUTS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((SOURCE / name).read_text(encoding='utf-8'), encoding='utf-8')

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_hooks_precede_model_dispatch_and_keep_explicit_phantomchat_allowlist(self):
        native.patch(self.root)
        engine = (self.root / 'src/channels/core/engine.ts').read_text(encoding='utf-8')
        server = (self.root / 'src/channels/phantomchat/server.ts').read_text(encoding='utf-8')
        self.assertLess(engine.index('verifyNativeAccess(input.nativeAccess'), engine.index('const serverStartedAt'))
        self.assertLess(engine.index('"telegram", msg, principalAuthenticated'), engine.index('const isVoice ='))
        self.assertIn('const nativeAllowed = new Set(allowedSet)', server)
        self.assertIn('&& !relaySet.has(msg.senderId.toLowerCase())', server)
        loop = server[server.index('for await (const msg of channel.listen(input.signal))'):]
        self.assertLess(loop.index('nativeAccess.consume'), loop.index('if (msg.reaction)'))
        self.assertTrue((self.root / native.HELPER).is_file())
        self.assertTrue((self.root / native.provenance.HELPER).is_file())
        for name in ('README.md', 'AGENTS.md'):
            self.assertIn(native.NOTE, (self.root / name).read_text(encoding='utf-8'))

    def test_changed_dispatcher_refuses_before_provenance_or_hook_writes(self):
        path = self.root / 'src/channels/phantomchat/server.ts'
        path.write_text(path.read_text(encoding='utf-8') + '\n// Unsupported drift\n', encoding='utf-8')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())

    def test_existing_helper_and_reapplication_are_refused(self):
        path = self.root / native.HELPER
        path.write_text('operator content', encoding='utf-8')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())
        path.unlink()
        native.patch(self.root)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
