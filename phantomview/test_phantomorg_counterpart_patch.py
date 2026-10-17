"""Reject incompatible source before a counterpart proposal can be prepared."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock_patch

import phantomorg_counterpart_patch as proposal


class PreparationTests(unittest.TestCase):
    def test_drift_is_rejected_before_git_or_writes(self):
        manifest = json.loads(Path(proposal.__file__).with_name("phantomorg-counterpart-source.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in manifest["inputs"]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("unsupported source\n")
            before = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                      for name in manifest["inputs"]}
            with mock_patch.object(proposal.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "Unsupported PhantomOrg"):
                    proposal.patch(root)
                run.assert_not_called()
            self.assertEqual(before, {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                      for name in manifest["inputs"]})

    def test_patch_checksum_mismatch_rejected_before_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock_patch.object(proposal.hashlib, "sha256") as digest:
                digest.return_value.hexdigest.return_value = "wrong"
                with mock_patch.object(proposal.subprocess, "run") as run:
                    with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                        proposal.patch(root)
                    run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
