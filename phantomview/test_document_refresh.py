"""Batch preparation preserves classification and isolates invalid document sources."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from document_refresh import prepare


class DocumentRefreshTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root.chmod(0o700)
        (self.root / 'blobs').mkdir(mode=0o700)
        self.actor = {'id': 'coordinator', 'org': 'example', 'role': 'executive', 'searchable': True}
        self.raw = b'<h1>Code of conduct</h1><p>Act with integrity.</p>'
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.path = self.root / 'blobs' / self.digest
        self.path.write_bytes(self.raw)
        self.path.chmod(0o600)
        self.node = {'kind': 'doc', 'urn': 'urn:example:doc:policies/conduct', 'slug': 'conduct',
                     'mac': 'a' * 64, 'parentMac': 'b' * 64, 'previous': None,
                     'category': 'category-2', 'owners': ['executive'], 'contentHash': self.digest,
                     'size': len(self.raw), 'locations': [{'backend': 'local', 'path': str(self.path)}]}
        self.folder = {'kind': 'folder', 'mac': 'b' * 64, 'slug': 'policies', 'parentMac': 'c' * 64}
        self.manifest = {'manifest': {'org': 'example', 'rootMac': 'c' * 64},
                         'nodes': [self.folder, self.node]}
        self.row = {'urn': self.node['urn'], 'actor': 'coordinator', 'category': 'category-2', 'format': 'html-text'}
        self.matrix = {'schema_version': 1, 'organization': 'example', 'documents': [self.row]}

    def plan(self, previous=None, permitted=lambda _: True):
        return prepare(self.manifest, self.root / 'manifest.yaml', self.matrix, [self.actor], permitted, previous)

    def test_initial_plan_is_deterministic_private_and_does_not_write(self):
        inputs = copy.deepcopy((self.manifest, self.matrix))
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        plan = self.plan()
        self.assertEqual(plan, self.plan())
        self.assertEqual(plan['prepared'][0]['action'], 'add')
        self.assertEqual(plan['prepared'][0]['binding']['sha256'], self.digest)
        self.assertTrue(plan['publication_required'])
        self.assertFalse(plan['mutations_performed'])
        self.assertNotIn(str(self.root), json.dumps(plan))
        self.assertNotIn('Act with integrity', json.dumps(plan))
        self.assertEqual((self.manifest, self.matrix), inputs)
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_registered_revision_prepares_refresh_without_manual_hash_edit(self):
        prior = self.plan()['prepared'][0]['binding']
        raw = b'<h1>Code of conduct</h1><p>Updated approved content.</p>'
        path = self.root / 'blobs' / hashlib.sha256(raw).hexdigest()
        path.write_bytes(raw)
        path.chmod(0o600)
        latest = self.node | {'mac': 'd' * 64, 'previous': self.node['mac'],
                             'contentHash': path.name, 'size': len(raw),
                             'locations': [{'backend': 'local', 'path': str(path)}]}
        self.manifest['nodes'].insert(0, latest)  # Array order must not choose the version.
        plan = self.plan([prior])
        self.assertEqual(plan['prepared'][0]['action'], 'refresh')
        self.assertEqual(plan['prepared'][0]['binding']['sha256'], path.name)
        self.assertEqual(len(self.manifest['nodes']), 3)
        self.assertEqual(self.node['contentHash'], self.digest)

    def test_unchanged_document_needs_no_new_binding(self):
        binding = self.plan()['prepared'][0]['binding']
        self.assertEqual(self.plan([binding])['prepared'][0]['action'], 'unchanged')

    def test_category_change_is_an_exception_even_if_owner_is_unchanged(self):
        binding = self.plan()['prepared'][0]['binding']
        self.node['category'] = 'category-3'
        plan = self.plan([binding])
        self.assertFalse(plan['prepared'])
        self.assertEqual(plan['pending'][0]['reason'], 'classification-changed')
        self.assertEqual(plan['excluded_bindings'], [self.node['urn']])

    def test_unmapped_missing_and_removed_sources_are_reported(self):
        old = self.plan()['prepared'][0]['binding']
        self.matrix['documents'] = []
        plan = self.plan([old])
        self.assertEqual(plan['pending'][0]['reason'], 'not-in-matrix')
        self.assertEqual(plan['removed_bindings'], [self.node['urn']])
        self.matrix['documents'] = [self.row | {'urn': 'urn:example:doc:policies/missing'}]
        self.assertIn('missing-native-document', [row['reason'] for row in self.plan()['pending']])

    def test_hidden_sources_do_not_leak_into_pending_reports(self):
        self.matrix['documents'] = []
        self.assertFalse(self.plan(permitted=lambda _: False)['pending'])
        self.node['confidential'] = True
        self.assertFalse(self.plan()['pending'])

    def test_invalid_source_does_not_block_other_documents_or_leak_path(self):
        extra = self.node | {'urn': 'urn:example:doc:policies/missing', 'mac': 'e' * 64,
                             'slug': 'missing', 'locations': [{'backend': 'local', 'path': str(self.root / 'blobs' / 'absent')}]}
        self.manifest['nodes'].append(extra)
        self.matrix['documents'].append(self.row | {'urn': extra['urn']})
        plan = self.plan()
        self.assertEqual(len(plan['prepared']), 1)
        self.assertEqual(plan['pending'][0]['reason'], 'source-validation-failed')
        self.assertNotIn('absent', json.dumps(plan))

    def test_changed_bytes_secret_text_and_wrong_owner_are_rejected(self):
        self.path.write_bytes(b'Changed after registration')
        self.assertFalse(self.plan()['prepared'])
        self.path.write_bytes(self.raw)
        self.actor['role'] = 'another-role'
        self.assertFalse(self.plan()['prepared'])

    def test_invalid_history_aborts_instead_of_selecting_an_arbitrary_version(self):
        self.manifest['nodes'].append(self.node | {'mac': 'e' * 64})
        with self.assertRaises(ValueError):
            self.plan()

    def test_matrix_cannot_add_scope_inference_duplicate_sources_or_unknown_fields(self):
        for patch in [{'category': 2}, {'actor': '../other'}, {'urn': 'urn:other:doc:policies/conduct'},
                      {'format': 'application/octet-stream'}, {'allow_all': True},
                      {'display': {'title': 'Unexpected text override'}}]:
            with self.subTest(patch=patch):
                self.matrix['documents'] = [self.row | patch]
                with self.assertRaises(ValueError):
                    self.plan()
        self.matrix['documents'] = [self.row, self.row]
        with self.assertRaises(ValueError):
            self.plan()

    def test_pdf_metadata_is_required_and_signature_checked(self):
        self.matrix['documents'] = [self.row | {'format': 'application/pdf', 'display': {'title': 'Policy PDF'}}]
        self.assertFalse(self.plan()['prepared'])  # HTML bytes cannot become PDF by relabeling.
        del self.matrix['documents'][0]['display']
        with self.assertRaises(ValueError):
            self.plan()

    def test_cli_reads_protected_inputs_and_only_prints_the_batch(self):
        from document_refresh import main
        values = {'manifest': self.manifest, 'matrix': self.matrix,
                  'snapshot': {'actors': [self.actor]}, 'config': {'working_documents': []}}
        arguments = []
        for name, value in values.items():
            path = self.root / (name + '.json')
            path.write_text(json.dumps(value), encoding='utf-8')
            path.chmod(0o600)
            arguments.extend(['--' + name, str(path)])
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            main(arguments)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan['prepared'][0]['action'], 'add')
        self.assertEqual(set(path.name for path in self.root.iterdir()),
                         {'blobs', 'manifest.json', 'matrix.json', 'snapshot.json', 'config.json'})


if __name__ == '__main__':
    unittest.main()
