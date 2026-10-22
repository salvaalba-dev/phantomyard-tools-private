"""Verified Drive copies keep native ownership, identity and per-file authorization."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest

import test_working_documents as fixture
from working_documents import bindings, cache_directory, collect


class CachedDocumentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.WorkingDocumentTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.cache = self.fixture.root / 'cache'
        self.cache.mkdir(mode=0o700)
        self.cache.chmod(0o700)
        self.binding = self.fixture.binding | {'format': 'text/plain', 'original': True,
            'original_only': True, 'display': {'title': 'Meeting transcript'}}
        self.fixture.node['locations'] = [{'backend': 'gdrive', 'ref': 'example_drive_file_123'}]
        self.set_content(b'Reviewed transcript. ' * 8000)

    def set_content(self, raw):
        self.binding['sha256'] = hashlib.sha256(raw).hexdigest()
        self.fixture.node.update(contentHash=self.binding['sha256'], size=len(raw))
        self.path = self.cache / self.binding['sha256']
        self.path.write_bytes(raw)
        self.path.chmod(0o600)

    def collect(self, **kwargs):
        return collect(self.fixture.manifest, self.fixture.root / 'manifest.yaml', [self.binding],
                       [self.fixture.actor], kwargs.pop('permitted', lambda _: True),
                       cache=kwargs.pop('cache', self.cache), **kwargs)

    def test_large_text_original_keeps_small_projection_and_native_source_unchanged(self):
        before = copy.deepcopy(self.fixture.manifest)
        value = self.collect()[self.binding['urn']]
        self.assertEqual(value['content'], 'Meeting transcript')
        self.assertLess(len(json.dumps(value)), 2000)
        self.assertEqual(value['original']['size_bytes'], self.path.stat().st_size)
        self.assertEqual(value['original']['sha256'], self.binding['sha256'])
        self.assertNotIn('version', value['original'])
        self.assertEqual(self.fixture.manifest, before)
        self.assertNotIn('Review', value['content'])

    def test_missing_cache_wrong_hash_size_or_source_never_falls_back(self):
        with self.assertRaises(ValueError):
            self.collect(cache=None)
        original = self.path.read_bytes()
        self.path.write_bytes(original + b'changed')
        with self.assertRaises(ValueError):
            self.collect()
        self.path.write_bytes(original)
        self.fixture.node['size'] += 1
        with self.assertRaises(ValueError):
            self.collect()
        self.fixture.node['size'] -= 1
        self.fixture.node['locations'][0]['backend'] = 'https'
        with self.assertRaises(ValueError):
            self.collect()
        self.fixture.node['locations'] = [{'backend': 'gdrive', 'ref': '../escape'}]
        with self.assertRaises(ValueError):
            self.collect()

    def test_cache_never_grants_ownership_or_eligibility(self):
        with self.assertRaises(ValueError):
            self.collect(permitted=lambda _: False)
        self.fixture.node['owners'] = ['other-role']
        with self.assertRaises(ValueError):
            self.collect()

    def test_metadata_only_requires_reviewed_display_and_original(self):
        for patch in [{'original': False}, {'original_only': False}, {'display': {}},
                      {'display': {'title': 'Transcript', 'category': 'category-0'}}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                bindings([self.binding | patch])

    def test_hidden_text_is_still_checked_for_secrets_utf8_and_nul(self):
        for raw in [b'password=not-a-real-password', b'Hello\x00world', b'\xff\xfe']:
            with self.subTest(raw=raw):
                self.set_content(raw)
                with self.assertRaises((ValueError, UnicodeError)):
                    self.collect()

    @unittest.skipUnless(os.name == 'posix', 'POSIX filesystem protection')
    def test_group_writable_cache_files_and_symlinks_are_rejected(self):
        self.cache.chmod(0o770)
        with self.assertRaises(ValueError):
            self.collect()
        self.cache.chmod(0o700)
        self.path.chmod(0o660)
        with self.assertRaises(ValueError):
            self.collect()
        self.path.chmod(0o600)
        moved = self.cache / 'original'
        self.path.rename(moved)
        self.path.symlink_to(moved)
        with self.assertRaises(ValueError):
            self.collect()
        self.assertEqual(cache_directory(self.cache), self.cache)
        with self.assertRaises(ValueError):
            cache_directory('relative-cache')

    def test_grouping_can_explicitly_retain_missing_version_without_inventing_one(self):
        from document_groups import validated, check_members
        group = {'id': 'urn:example:document:transcript', 'title': 'Meeting transcript'}
        value = self.collect()[self.binding['urn']]
        self.assertEqual(validated(group, value['original'], 'example'), group)
        check_members([value | {'document_group': group}])
        with self.assertRaises(ValueError):
            validated(group, value['original'] | {'version': 'v2'}, 'example')
        with self.assertRaises(ValueError):
            validated(group | {'version': 'v1'}, value['original'], 'example')


if __name__ == '__main__':
    unittest.main()
