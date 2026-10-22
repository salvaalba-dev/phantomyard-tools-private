"""Logical editions group explicit formats without merging ACL or native histories."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from document_groups import validated
from document_refresh import prepare
from working_documents import collect


class DocumentGroupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root.chmod(0o700)
        (self.root / 'blobs').mkdir(mode=0o700)
        self.group = {'id': 'urn:example:document:conduct', 'title': 'Code of conduct',
                      'code': 'EX-20260101-001', 'version': 'v1.0'}
        self.actors = [{'id': 'coordinator', 'org': 'example', 'role': 'executive', 'searchable': True}]
        self.manifest = {'manifest': {'org': 'example', 'rootMac': 'root'}, 'nodes': [
            {'kind': 'folder', 'mac': 'folder', 'slug': 'policies', 'parentMac': 'root'}]}
        self.bindings = []
        for slug, media, raw in [('conduct-pdf', 'application/pdf', b'%PDF-1.7\nPolicy\n%%EOF'),
                                 ('conduct-source', 'html-text', b'<h1>Code of conduct</h1><p>Act with integrity.</p>')]:
            digest = hashlib.sha256(raw).hexdigest()
            path = self.root / 'blobs' / digest
            path.write_bytes(raw)
            path.chmod(0o600)
            urn = 'urn:example:doc:policies/' + slug
            self.manifest['nodes'].append({'kind': 'doc', 'urn': urn, 'slug': slug, 'category': 'category-2',
                'owners': ['executive'], 'parentMac': 'folder', 'contentHash': digest, 'size': len(raw),
                'meta': {'title': 'Code of conduct', 'version': 'v1.0', 'code': 'EX-20260101-001'},
                'locations': [{'backend': 'local', 'path': str(path)}]})
            binding = {'urn': urn, 'actor': 'coordinator', 'sha256': digest, 'format': media,
                       'original': True, 'document_group': dict(self.group)}
            if media == 'application/pdf':
                binding['display'] = {'title': 'Code of conduct (PDF)', 'code': self.group['code'], 'version': 'v1.0'}
            self.bindings.append(binding)

    def collect(self):
        return collect(self.manifest, self.root / 'manifest.yaml', self.bindings, self.actors, lambda _: True)

    def test_explicit_formats_retain_distinct_source_hashes_and_native_identities(self):
        before = copy.deepcopy(self.manifest)
        documents = list(self.collect().values())
        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0]['document_group'], documents[1]['document_group'])
        self.assertNotEqual(documents[0]['source_sha256'], documents[1]['source_sha256'])
        self.assertEqual(before, self.manifest)

    def test_source_adapter_exports_only_validated_group_metadata(self):
        from source_adapter import profile_data
        document = next(iter(self.collect().values()))
        data = profile_data({'working_document': document}, 'documents')
        self.assertEqual(data['document_group'], self.group)
        self.assertEqual(data['original'], document['original'])

    def test_same_code_or_title_without_explicit_membership_never_creates_a_group(self):
        for row in self.bindings:
            del row['document_group']
        self.assertTrue(all('document_group' not in value for value in self.collect().values()))

    def test_group_cannot_relabel_a_new_version_or_conflicting_document_code(self):
        for patch in [{'version': 'v2.0'}, {'code': 'OTHER-001'}, {'id': 'urn:other:document:conduct'}]:
            with self.subTest(patch=patch):
                self.bindings[0]['document_group'] = self.group | patch
                with self.assertRaises(ValueError):
                    self.collect()

    def test_group_cannot_hide_inconsistent_titles_folders_or_duplicate_formats(self):
        self.bindings[1]['document_group']['title'] = 'Another title'
        with self.assertRaises(ValueError):
            self.collect()
        self.bindings[1]['document_group'] = dict(self.group)
        self.bindings[1] = self.bindings[0] | {'urn': self.bindings[1]['urn']}
        self.manifest['nodes'][2].update(contentHash=self.manifest['nodes'][1]['contentHash'],
            size=self.manifest['nodes'][1]['size'], locations=self.manifest['nodes'][1]['locations'])
        with self.assertRaises(ValueError):
            self.collect()

    def test_format_permission_checks_are_not_inherited_from_another_member(self):
        self.manifest['nodes'][2]['secret'] = True
        with self.assertRaises(ValueError):
            self.collect()

    def test_batch_planning_preserves_explicit_group_membership(self):
        matrix = {'schema_version': 1, 'organization': 'example', 'documents': [
            {key: value for key, value in row.items() if key not in {'sha256', 'original'}} | {'category': 'category-2'}
            for row in self.bindings]}
        plan = prepare(self.manifest, self.root / 'manifest.yaml', matrix, self.actors, lambda _: True)
        self.assertEqual(len(plan['prepared']), 2)
        self.assertTrue(all(row['binding']['document_group'] == self.group for row in plan['prepared']))
        self.assertTrue(plan['publication_required'])

    def test_group_schema_rejects_missing_versions_and_executable_or_permission_fields(self):
        for patch in [{'version': ''}, {'title': 'Policy\nInjected'}, {'url': 'https://other.example'},
                      {'category': 'category-0'}, {'id': 'https://other.example'}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validated(self.group | patch)


if __name__ == '__main__':
    unittest.main()
