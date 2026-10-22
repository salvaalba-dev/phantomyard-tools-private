"""Restored native blobs remain exact, bounded and confined to the chosen store."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from working_documents import collect


class RelocatedDocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.raw = b'%PDF-1.4\nReviewed original\n%%EOF'
        self.hash = hashlib.sha256(self.raw).hexdigest()
        self.selected = self.root / 'selected'
        self.current = self.selected / 'blobs' / self.hash[:2] / self.hash
        self.current.parent.mkdir(parents=True, mode=0o700)
        self.current.write_bytes(self.raw)
        self.current.chmod(0o600)
        self.old = self.root / 'previous' / 'blobs' / self.hash[:2] / self.hash
        self.node = {'urn': 'urn:example:doc:report', 'kind': 'doc', 'slug': 'report',
                     'owners': ['executive'], 'category': 'category-2', 'parentMac': 'reports',
                     'contentHash': self.hash, 'size': len(self.raw),
                     'locations': [{'backend': 'local', 'path': str(self.old)}]}
        self.binding = {'urn': self.node['urn'], 'actor': 'lead', 'format': 'application/pdf',
                        'sha256': self.hash, 'original': True, 'display': {'title': 'Report', 'version': 'v3.0'}}
        self.actor = {'id': 'lead', 'org': 'example', 'role': 'executive', 'searchable': True}

    def read(self):
        return collect({'manifest': {'org': 'example'}, 'nodes': [self.node, {'kind': 'folder', 'mac': 'reports', 'slug': 'Reports'}]},
                       self.selected / 'manifest.yaml', [self.binding], [self.actor], lambda _: True)

    def test_absent_canonical_location_uses_verified_restored_blob(self):
        result = self.read()[self.node['urn']]
        self.assertEqual(result['original']['sha256'], self.hash)
        self.assertEqual(result['original']['version'], 'v3.0')
        self.assertEqual(self.node['locations'][0]['path'], str(self.old))

    def test_present_external_location_is_not_redirected_even_if_identical(self):
        self.old.parent.mkdir(parents=True)
        for raw in (self.raw, b'corrupt'):
            self.old.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.read()

    def test_noncanonical_or_mismatched_location_is_rejected(self):
        for path in (self.old.with_name('other'), self.root / 'missing.pdf',
                     self.old.parent.parent / 'ff' / self.hash):
            self.node['locations'][0]['path'] = str(path)
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.read()

    def test_bad_restored_content_size_and_missing_blob_are_rejected(self):
        self.current.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.read()
        self.current.write_bytes(self.raw)
        self.node['size'] += 1
        with self.assertRaises(ValueError):
            self.read()
        self.node['size'] -= 1
        self.current.unlink()
        with self.assertRaises(OSError):
            self.read()

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlink support')
    def test_linked_original_or_restored_path_is_rejected(self):
        self.old.parent.mkdir(parents=True)
        self.old.symlink_to(self.current)
        with self.assertRaises(ValueError):
            self.read()
        self.old.unlink()
        self.current.unlink()
        target = self.root / 'target'
        target.write_bytes(self.raw)
        self.current.symlink_to(target)
        with self.assertRaises(ValueError):
            self.read()

    def test_external_reference_never_uses_local_restore(self):
        self.node['locations'] = [{'backend': 'ssh', 'path': str(self.old)}]
        with self.assertRaises(ValueError):
            self.read()

