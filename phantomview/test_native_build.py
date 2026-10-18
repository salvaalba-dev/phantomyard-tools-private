"""Regression coverage for reviewed build inputs and artifact compatibility."""
import copy
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_build as build


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.document = json.loads((build.HERE / 'native-host-example.json').read_text())

    def test_normalized_routes_are_the_exact_bytes_hashed_and_prepared(self):
        normalized = copy.deepcopy(self.document['routes'])
        normalized[0]['persona'] = 'normalized'
        with patch.object(build.host, 'validate_routes', return_value=normalized):
            build.canonical_routes(json.dumps(self.document), self.root / 'build')
        raw = (self.root / 'build/routes.json').read_bytes()
        self.assertEqual(json.loads(raw)['routes'], normalized)
        self.assertEqual((self.root / 'build/routes.sha256').read_text(), hashlib.sha256(raw).hexdigest())
        if os.name == 'posix':
            for name in ('routes.json', 'routes.sha256'):
                self.assertEqual(stat.S_IMODE((self.root / 'build' / name).stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((self.root / 'build').stat().st_mode), 0o700)

    def test_invalid_input_never_creates_the_output_directory(self):
        for raw in ('{"schema_version":1,"schema_version":1}', 'x' * 65537):
            with self.subTest(raw_size=len(raw)), self.assertRaises(ValueError):
                build.canonical_routes(raw, self.root / 'rejected')
            self.assertFalse((self.root / 'rejected').exists())

    def test_verified_tag_and_package_versions_are_recorded_separately(self):
        sha = build.host.reviewed.SOURCE_REVISION
        result = build.version_metadata({'version': '0.1.0'}, sha, sha, 'v1.1.433', 'a' * 40)
        self.assertEqual(result['package_version'], '0.1.0')
        self.assertEqual(result['release_version'], '1.1.433')
        self.assertEqual(result['native_version'], '1.1.433-phantomview.aaaaaaa')
        with self.assertRaisesRegex(ValueError, 'must agree'):
            build.version_metadata({'version': '0.1.0'}, sha, 'b' * 40, 'v1.1.433', 'a' * 40)
        with self.assertRaisesRegex(ValueError, 'must agree'):
            build.version_metadata({'version': '0.1.0'}, 'b' * 40, 'b' * 40, 'v1.1.433', 'a' * 40)
        for tag in ('v1.2', 'v01.2.3', '1.2.3', 'v1.2.3\n'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                build.version_metadata({'version': '0.1.0'}, sha, sha, tag, 'a' * 40)

    def test_stamping_refuses_package_drift_and_uses_the_verified_release(self):
        source = self.root / 'source'
        (source / 'src/lib').mkdir(parents=True)
        raw = b'{"version":"0.1.0"}'
        (source / 'package.json').write_bytes(raw)
        (source / 'src/version.ts').write_text('export const VERSION = "0.1.0-dev";')
        sha = build.host.reviewed.SOURCE_REVISION
        document = build.version_metadata({'version': '0.1.0'}, sha, sha, 'v1.1.433', 'a' * 40)
        document['package_sha256'] = hashlib.sha256(raw).hexdigest()
        (source / 'package.json').write_bytes(raw + b'\n')
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            build.stamp(source, document)
        self.assertIn('0.1.0-dev', (source / 'src/version.ts').read_text())
        (source / 'package.json').write_bytes(raw)
        build.stamp(source, document)
        self.assertIn(document['native_version'], (source / 'src/version.ts').read_text())
        asset = source / 'src/lib/vscodeExtensionAsset.generated.ts'
        asset.write_text('export const VSCODE_EXTENSION_VERSION = "1.1.433";')
        build.embedded_version(source, document)
        asset.write_text('export const VSCODE_EXTENSION_VERSION = "1.1.432";')
        with self.assertRaises(ValueError):
            build.embedded_version(source, document)

    def test_archived_verifier_reproduces_the_reviewed_sources_without_a_fork_checkout(self):
        site = self.root / 'site'
        site.mkdir()
        destination = self.root / 'verifier'
        digest = build.install_verifier(destination, site)
        manifest = json.loads((build.HERE / 'build-sources/verifier-manifest.json').read_text())
        self.assertEqual(digest, manifest['archive_sha256'])
        for name, row in manifest['files'].items():
            raw = (destination / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                             row['git_blob'])
        self.assertEqual((site / 'phantomview-verifier.pth').read_text().strip(), str(destination.resolve()))

    def test_corrupt_archive_refuses_before_any_extraction_or_python_path_write(self):
        sources = self.root / 'build-sources'
        sources.mkdir()
        manifest = json.loads((build.HERE / 'build-sources/verifier-manifest.json').read_text())
        (sources / 'verifier-manifest.json').write_text(json.dumps(manifest))
        (sources / manifest['archive']).write_bytes(b'corrupted')
        site = self.root / 'site'
        site.mkdir()
        with patch.object(build, 'HERE', self.root), self.assertRaisesRegex(ValueError, 'digest mismatch'):
            build.install_verifier(self.root / 'verifier', site)
        self.assertFalse((self.root / 'verifier').exists())
        self.assertEqual(list(site.iterdir()), [])

    def test_test_receipt_refuses_skipped_failed_or_missing_groups(self):
        environment = {'TEST_' + name.upper(): 'success' for name in build.TEST_GROUPS}
        self.assertTrue(all(value == 'success' for value in build.test_results(environment).values()))
        for name in build.TEST_GROUPS:
            for status in ('failure', 'skipped', 'cancelled', None):
                with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                    build.test_results(environment | {'TEST_' + name.upper(): status})

    def test_glibc_comparison_uses_numeric_versions_and_refuses_unknown_hosts(self):
        self.assertEqual(build.required_glibc('GLIBC_2.9 GLIBC_2.25 GLIBC_2.2.5'), '2.25')
        self.assertEqual(build.check_glibc('2.25', 'glibc 2.39'), '2.39')
        self.assertEqual(build.check_glibc('2.25', 'glibc 2.25'), '2.25')
        for text in ('musl 1.2.5', 'glibc 2.24', '', 'glibc unknown'):
            with self.subTest(host=text), self.assertRaises(ValueError):
                build.check_glibc('2.25', text)
        for symbols in ('', 'GLIBC_PRIVATE GLIBC_2.25'):
            with self.subTest(symbols=symbols), self.assertRaises(ValueError):
                build.required_glibc(symbols)

    def test_host_preflight_rejects_digest_mismatch_before_inspection(self):
        binary = self.root / 'binary'
        binary.write_bytes(b'not-an-executable')
        with patch.object(build, 'elf_metadata') as inspect:
            with self.assertRaisesRegex(ValueError, 'verified digest'):
                build.check_host(binary, '0' * 64)
            inspect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
