"""Published byte parity must not become a runtime activation claim."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_release_review as native


class ReleaseReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.binary = self.root / 'binary'
        self.content = b'offline reviewed binary fixture\0'
        self.binary.write_bytes(self.content)
        self.baseline = self.root / 'release.json'
        self.metadata = {
            'schema_version': 1, 'repository': 'phantomyard/phantombot',
            'source_revision': native.SOURCE_REVISION, 'tag': 'v1.1.fixture',
            'asset_size': len(self.content),
            'asset_sha256': hashlib.sha256(self.content).hexdigest(),
        }
        self.write_metadata()
        override = patch.object(native, 'BASELINE', self.baseline)
        override.start()
        self.addCleanup(override.stop)

    def write_metadata(self):
        self.baseline.write_text(json.dumps(self.metadata), encoding='utf-8')

    def test_byte_parity_never_claims_activation_or_modifies_binary(self):
        result = native.review(self.binary)
        self.assertTrue(result['published_asset_matches'])
        self.assertFalse(result['activation_ready'])
        self.assertIn('native-startup-binding', result['remaining_work'])
        self.assertEqual(self.binary.read_bytes(), self.content)

    def test_same_size_drift_and_truncation_are_rejected(self):
        for content in (b'x' * len(self.content), self.content[:-1], self.content + b'x'):
            self.binary.write_bytes(content)
            with self.assertRaises(ValueError):
                native.review(self.binary)

    def test_wrong_source_and_invalid_asset_metadata_are_rejected(self):
        for key, value in [('source_revision', '0' * 40), ('repository', 'other/repo'),
                           ('asset_size', True), ('asset_size', native.MAX_BINARY_BYTES + 1),
                           ('asset_sha256', 'g' * 64), ('asset_sha256', 'a' * 63)]:
            with self.subTest(key=key, value=value):
                saved = self.metadata[key]
                self.metadata[key] = value
                self.write_metadata()
                with self.assertRaises(ValueError):
                    native.review(self.binary)
                self.metadata[key] = saved

    def test_link_and_directory_targets_are_rejected(self):
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda path: path == self.binary or original(path)):
            with self.assertRaises(ValueError):
                native.review(self.binary)
        with self.assertRaises(ValueError):
            native.review(self.root)

    def test_cli_reports_generic_failure_without_path_or_content(self):
        self.binary.write_bytes(b'private-marker')
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            self.assertEqual(native.main([str(self.binary)]), 2)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn(str(self.binary), error.getvalue())
        self.assertNotIn('private-marker', error.getvalue())

    def test_committed_release_metadata_is_bound_to_source_review(self):
        baseline = json.loads(Path(native.__file__).with_name('native-release-review.json')
                              .read_text(encoding='utf-8'))
        self.assertEqual(baseline['source_revision'], native.SOURCE_REVISION)
        self.assertEqual(baseline['asset_name'], 'phantombot-' + baseline['tag'] + '-linux-x64')


if __name__ == '__main__':
    unittest.main()
