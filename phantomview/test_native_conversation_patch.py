"""Prepare the complete worker variant only over a reviewed offline source tree."""
from pathlib import Path
import shutil
import tempfile
import unittest

import native_conversation_patch as native
from native_host_review import ROOT_FILES
from test_native_ingress_patch import SOURCE


@unittest.skipUnless(SOURCE.is_dir(), 'Pinned native source checkout required')
class ConversationPatchTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for name in ROOT_FILES:
            shutil.copyfile(SOURCE / name, self.root / name)
        shutil.copytree(SOURCE / 'src', self.root / 'src')

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_full_variant_keeps_history_screening_and_has_no_trusted_flag(self):
        native.patch(self.root)
        entry = (self.root / 'src/index.ts').read_text(encoding='utf-8')
        self.assertLess(entry.index('process.argv[2] === "__conversation-worker"'), entry.index('await runPhantombotCli()'))
        ask = (self.root / 'src/cli/ask.ts').read_text(encoding='utf-8')
        self.assertIn('noHistory: !input.history', ask)
        self.assertIn('makeScreener(config, persona, conversation, harnesses, memory)', ask)
        self.assertNotIn('trusted: true', ask)
        self.assertIn('toolsMode: "none"', ask)
        self.assertIn('harnesses.filter(h => h.id === "native")', ask)
        for name in ('README.md', 'AGENTS.md'):
            self.assertIn(native.NOTE, (self.root / name).read_text(encoding='utf-8'))
        self.assertTrue((self.root / native.HELPER).is_file())

    def test_source_drift_refuses_before_any_write_and_reapplication_fails(self):
        path = self.root / 'src/cli/ask.ts'
        original = path.read_bytes()
        path.write_bytes(original + b'\n// unsupported\n')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())
        path.write_bytes(original)
        native.patch(self.root)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
