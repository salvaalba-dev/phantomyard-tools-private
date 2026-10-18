"""Wrong bases and changed proposals must fail before invoking Git."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock_patch

import phantomorg_category_limits_patch as proposal


class CategoryPreparationTests(unittest.TestCase):
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
