"""Source drift must invalidate a host review without modifying the checkout."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_host_review as native
from test_native_ingress_patch import SOURCE


class HostReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'source'
        (self.root / 'src').mkdir(parents=True)
        for name in native.ROOT_FILES:
            (self.root / name).write_text('fixed\n', encoding='utf-8')
        (self.root / 'src/model.ts').write_text('reviewed\n', encoding='utf-8')
        self.baseline = self.root.parent / 'baseline.json'
        self.baseline.write_text(json.dumps({'source_revision': native.SOURCE_REVISION,
                                            'snapshot': native.snapshot(self.root)}), encoding='utf-8')
        override = patch.object(native, 'BASELINE', self.baseline)
        override.start()
        self.addCleanup(override.stop)

    def test_matching_source_never_reports_activation_ready_and_remains_unchanged(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        report = native.review(self.root)
        self.assertTrue(report['source_matches_review'])
        self.assertIs(report['activation_ready'], False)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_new_changed_removed_source_and_dependency_drift_are_rejected(self):
        target = self.root / 'src/model.ts'
        for path in (target, self.root / 'bun.lock', self.root / 'AGENTS.md'):
            saved = path.read_bytes()
            path.write_bytes(saved + b'unsupported')
            with self.assertRaises(ValueError):
                native.review(self.root)
            path.write_bytes(saved)
        target.unlink()
        with self.assertRaises(ValueError):
            native.review(self.root)
        target.write_text('reviewed\n', encoding='utf-8')
        (self.root / 'src/unreviewed.ts').write_text('new', encoding='utf-8')
        with self.assertRaises(ValueError):
            native.review(self.root)

    def test_line_ending_conversion_is_supported(self):
        (self.root / 'src/model.ts').write_bytes(b'reviewed\r\n')
        self.assertTrue(native.review(self.root)['source_matches_review'])

    def test_explicit_daemon_review_does_not_require_retired_account_split(self):
        report = native.review(self.root, 'daemon')
        self.assertEqual(report['trust_boundary'], 'daemon')
        self.assertEqual(report['design'], 'DAEMON_TRUST.md')
        self.assertNotIn('isolated-native-host', report['required_work'])
        self.assertNotIn('ordinary-conversation-forwarding', report['required_work'])
        self.assertIn('native-startup-binding', report['required_work'])
        self.assertFalse(report['activation_ready'])
        self.assertIn('isolated-native-host', native.review(self.root)['required_work'])
        with self.assertRaises(ValueError):
            native.review(self.root, 'unknown')
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(native.main([str(self.root), '--trust-boundary', 'daemon']), 0)
        self.assertEqual(json.loads(output.getvalue())['trust_boundary'], 'daemon')

    def test_limits_and_link_rejection(self):
        with patch.object(native, 'MAX_FILE_BYTES', 3), self.assertRaises(ValueError):
            native.snapshot(self.root)
        with patch.object(native, 'MAX_FILES', 1), self.assertRaises(ValueError):
            native.snapshot(self.root)
        with patch.object(native, 'MAX_TOTAL_BYTES', 5), self.assertRaises(ValueError):
            native.snapshot(self.root)
        # Simulate the platform link observation without requiring Windows link privileges.
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda p: p.name == 'src' or original(p)):
            with self.assertRaises(ValueError):
                native.snapshot(self.root)

    def test_cli_failure_does_not_echo_paths_or_source_contents(self):
        (self.root / 'src/private-marker.ts').write_text('secret-marker', encoding='utf-8')
        out, error = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(error):
            self.assertEqual(native.main([str(self.root)]), 2)
        self.assertEqual(out.getvalue(), '')
        self.assertNotIn(str(self.root), error.getvalue())
        self.assertNotIn('secret-marker', error.getvalue())


@unittest.skipUnless(SOURCE.is_dir(), 'Pinned native source checkout is required')
class PinnedHostReviewTests(unittest.TestCase):
    def test_actual_pinned_tree_matches_committed_review(self):
        report = native.review(SOURCE)
        self.assertTrue(report['source_matches_review'])
        self.assertFalse(report['activation_ready'])


if __name__ == '__main__':
    unittest.main()
