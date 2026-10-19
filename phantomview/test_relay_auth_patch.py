"""Fail-closed preparation, exact-byte provenance and cache isolation tests."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock_patch

import relay_auth_patch as overlay


class RelayAuthPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'node_modules/nostr-tools'
        self.package.mkdir(parents=True)
        (self.package / 'package.json').write_text(json.dumps({'name': 'nostr-tools', 'version': overlay.VERSION}))
        self.raw = '\n'.join([overlay.OLD_SEND, overlay.OLD_AUTH]
                             + [old for old, _ in overlay.EXTRA_REPLACEMENTS]).encode()
        self.paths = ('lib/esm/pool.js', 'lib/esm/abstract-relay.js')
        for relative in self.paths:
            path = self.package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.raw)
        self.expected = {relative: overlay.digest(self.raw) for relative in self.paths}
        self.mock = mock_patch.object(overlay, 'EXPECTED_INPUTS', self.expected)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def test_patch_records_exact_input_and_output_bytes(self):
        manifest = overlay.patch(self.root)
        self.assertIs(manifest['activation_ready'], False)
        self.assertIs(manifest['installed'], False)
        overlay.verify_manifest(self.root, manifest)
        for row in manifest['files']:
            self.assertEqual(row['before_sha256'], overlay.digest(self.raw))
            self.assertEqual(row['after_sha256'], overlay.digest((self.package / row['path']).read_bytes()))

    def test_drift_in_last_file_refuses_before_any_write(self):
        changed = self.package / self.paths[-1]
        changed.write_bytes(self.raw + b'\n// drift\n')
        before = {path: (self.package / path).read_bytes() for path in self.paths}
        with self.assertRaises(ValueError):
            overlay.patch(self.root)
        self.assertEqual(before, {path: (self.package / path).read_bytes() for path in self.paths})

    def test_duplicate_or_missing_method_is_refused(self):
        for text in (overlay.OLD_AUTH, overlay.OLD_SEND, self.raw.decode() + overlay.OLD_AUTH):
            with self.subTest(text_length=len(text)), self.assertRaises(ValueError):
                overlay.transform(text)

    def test_second_application_is_refused(self):
        overlay.patch(self.root)
        with self.assertRaises(ValueError):
            overlay.patch(self.root)

    def test_wrong_version_is_refused_without_modification(self):
        (self.package / 'package.json').write_text('{"name":"nostr-tools","version":"9.0.0"}')
        with self.assertRaises(ValueError):
            overlay.patch(self.root)
        self.assertEqual((self.package / self.paths[0]).read_bytes(), self.raw)

    def test_hardlinked_package_cache_is_not_modified(self):
        cached = self.root / 'shared-cache.js'
        os.link(self.package / self.paths[0], cached)
        overlay.patch(self.root)
        self.assertEqual(cached.read_bytes(), self.raw)
        self.assertNotEqual((self.package / self.paths[0]).read_bytes(), self.raw)

    def test_receipt_refuses_post_patch_drift_or_forged_provenance(self):
        manifest = overlay.patch(self.root)
        with self.assertRaises(ValueError):
            overlay.verify_manifest(self.root, manifest | {'patch_sha256': '0' * 64})
        changed = self.package / self.paths[0]
        changed.write_bytes(changed.read_bytes() + b'\n// drift\n')
        with self.assertRaises(ValueError):
            overlay.verify_manifest(self.root, manifest)


if __name__ == '__main__':
    unittest.main()
