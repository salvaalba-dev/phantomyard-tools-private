"""Exact-source patch preparation never changes the inspected native checkout."""
from pathlib import Path
import os
import tempfile
import unittest

import native_ingress_patch as native

SOURCE = Path(os.environ.get('PHANTOMVIEW_NATIVE_SOURCE',
                            Path(__file__).resolve().parents[2] / 'phantombot-inspect'))


@unittest.skipUnless(SOURCE.is_dir(), 'Pinned native source checkout is required for patch preparation')
class NativeIngressPatchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in native.INPUTS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((SOURCE / name).read_text(encoding='utf-8'), encoding='utf-8')

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_supported_sources_keep_receipt_routing_and_add_provenance(self):
        before = self.snapshot()
        result = native.patch(self.root)
        self.assertEqual(set(result), {*native.INPUTS, native.HELPER})
        telegram = (self.root / 'src/channels/telegram/parse.ts').read_text(encoding='utf-8')
        self.assertEqual(telegram.count('...(sourceMessage ? { sourceMessage } : {})'), 3)
        channel = (self.root / 'src/channels/phantomchat/channel.ts').read_text(encoding='utf-8')
        self.assertIn('nostrSourceMessage(rumor.id, rumor.created_at)', channel)
        self.assertIn('...(messageId ? { messageId } : {})', channel)
        self.assertIn('unwrapNip17Message(event, secretKey)', channel)
        for name in ('README.md', 'AGENTS.md'):
            self.assertIn(native.NOTE, (self.root / name).read_text(encoding='utf-8'))
        self.assertNotEqual(before, self.snapshot())

    def test_drift_in_any_input_is_refused_before_writing(self):
        target = self.root / 'AGENTS.md'
        target.write_text(target.read_text(encoding='utf-8') + '\nUnexpected change\n', encoding='utf-8')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'Unsupported native ingress source'):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())

    def test_existing_helper_and_reapplication_are_refused(self):
        helper = self.root / native.HELPER
        helper.write_text('operator content')
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())
        helper.unlink()
        native.patch(self.root)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            native.patch(self.root)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
