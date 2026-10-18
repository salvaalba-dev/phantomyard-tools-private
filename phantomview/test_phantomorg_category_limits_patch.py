"""Wrong bases and changed proposals must fail before invoking Git."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock_patch

import phantomorg_category_limits_patch as proposal


class CategoryPreparationTests(unittest.TestCase):
    def test_git_receives_only_normalized_binary_patch_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proposal.patch'
            path.write_bytes(b'patch\r\ncontext\r\n')
            with mock_patch.object(proposal.subprocess, 'run') as run:
                proposal._apply(Path(directory), path)
                self.assertEqual(run.call_count, 2)
                for call in run.call_args_list:
                    self.assertEqual(call.kwargs['input'], b'patch\ncontext\n')
                    self.assertTrue(call.kwargs['check'])
                    self.assertNotIn('text', call.kwargs)
                self.assertIn('--check', run.call_args_list[0].args[0])
                self.assertNotIn('--check', run.call_args_list[1].args[0])

    def test_drift_rejected_before_git_and_source_writes(self):
        manifest = json.loads(Path(proposal.__file__).with_name('phantomorg-category-limits.manifest.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, row in manifest['files'].items():
                if row['input_sha256_lf'] is not None:
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text('unsupported source\n', encoding='utf-8')
            before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*') if path.is_file()}
            with mock_patch.object(proposal.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Unsupported PhantomOrg'):
                    proposal.patch(root)
                run.assert_not_called()
            self.assertEqual(before, {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in root.rglob('*') if path.is_file()})

    def test_patch_checksum_rejected_before_git(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock_patch.object(proposal, 'digest', return_value='wrong'):
                with mock_patch.object(proposal.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                        proposal.patch(directory)
                    run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
