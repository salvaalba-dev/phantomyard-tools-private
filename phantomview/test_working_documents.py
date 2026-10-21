"""Selected document texts remain bounded, inert and separately classified."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from working_documents import MAX_BYTES, MAX_HTML_ORIGINAL_BYTES, bindings, collect, text_content, validated


class WorkingDocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        (self.root / 'blobs').mkdir(mode=0o700)
        self.path = self.root / 'blobs' / 'source'
        self.path.write_bytes(b'<html><head><style>HIDDEN_STYLE</style></head><body><h1>Code of conduct</h1><p>Act with integrity.</p><script>NEVER_RUN()</script></body></html>')
        self.path.chmod(0o600)
        self.actor = {'id': 'coordinator', 'org': 'example', 'role': 'executive', 'searchable': True}
        self.node = {'urn': 'urn:example:conduct', 'kind': 'doc', 'slug': 'conduct', 'owners': ['executive'],
                     'parentMac': 'folder', 'category': 'category-2',
                     'locations': [{'backend': 'local', 'path': str(self.path)}]}
        self.manifest = {'manifest': {'org': 'example'}, 'nodes': [self.node,
            {'kind': 'folder', 'mac': 'folder', 'slug': 'Policies'}]}
        self.binding = {'urn': self.node['urn'], 'actor': self.actor['id'], 'format': 'html-text',
                        'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest()}

    def collect(self):
        return collect(self.manifest, self.root / 'manifest.yaml', [self.binding], [self.actor], lambda _: True)

    def test_unconfigured_documents_are_never_opened(self):
        self.path.unlink()
        self.assertEqual(collect({}, '/missing/manifest.yaml', [], [], lambda _: True), {})

    def test_exact_owner_and_folder_with_inert_html_extraction(self):
        value = self.collect()[self.node['urn']]
        self.assertEqual(value['folder'], 'Policies')
        self.assertEqual(value['format'], 'text/plain')
        self.assertEqual(value['content'], 'Code of conduct\n\nAct with integrity.')
        self.assertNotIn('HIDDEN_STYLE', value['content'])
        self.assertNotIn('NEVER_RUN', value['content'])
        self.assertEqual(value['source_sha256'], self.binding['sha256'])

    def test_original_opt_in_binds_the_current_manifest_version_and_real_size(self):
        self.binding['original'] = True
        self.node.update(contentHash=self.binding['sha256'], size=self.path.stat().st_size)
        value = self.collect()[self.node['urn']]
        self.assertEqual(value['original']['title'], 'Code of conduct')
        self.assertEqual(value['original']['size_bytes'], self.path.stat().st_size)
        self.assertEqual(value['original']['sha256'], self.binding['sha256'])
        self.node['contentHash'] = 'a' * 64
        with self.assertRaises(ValueError):
            self.collect()

    def test_pdf_and_images_publish_reviewed_metadata_without_decoding_binary_content(self):
        for media, raw in [('application/pdf', b'%PDF-1.7\n\xff\xfe Reviewed binary\n%%EOF'),
                           ('image/png', b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x00IEND\xaeB`\x82'),
                           ('image/jpeg', b'\xff\xd8\xff\xe0image\xff\xd9')]:
            with self.subTest(media=media):
                self.path.write_bytes(raw)
                digest = hashlib.sha256(raw).hexdigest()
                self.node.update(contentHash=digest, size=len(raw))
                self.binding.update(format=media, sha256=digest, original=True,
                                    display={'title': 'Reviewed policy', 'version': 'v1.2'})
                value = self.collect()[self.node['urn']]
                self.assertEqual(value['format'], media)
                self.assertEqual(value['content'], 'Reviewed policy v1.2')
                self.assertEqual(value['original']['size_bytes'], len(raw))
                self.assertEqual(value['original']['sha256'], digest)
                self.assertNotIn('Reviewed binary', json.dumps(value))

    def test_binary_bindings_require_reviewed_display_metadata_and_original_opt_in(self):
        base = dict(self.binding, format='application/pdf', original=True, display={'title': 'Policy'})
        for patch in [{'original': False}, {'display': {}}, {'display': {'title': 'Policy', 'url': 'https://other.example'}},
                      {'display': {'title': 'Policy\nInjected'}}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                bindings([base | patch])
        with self.assertRaises(ValueError):
            bindings([base | {'format': 'html-text'}])
        self.binding.update(base)
        with self.assertRaises(ValueError):
            self.collect()  # An HTML blob must not be labeled as PDF.

    def test_pdf_original_larger_than_the_text_limit_keeps_the_projection_small(self):
        raw = b'%PDF-1.7\n' + b'x' * (MAX_BYTES + 1) + b'\n%%EOF'
        self.path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self.node.update(contentHash=digest, size=len(raw))
        self.binding.update(format='application/pdf', sha256=digest, original=True, display={'title': 'Large policy'})
        value = self.collect()[self.node['urn']]
        self.assertLess(len(json.dumps(value)), 2000)
        self.assertEqual(value['original']['size_bytes'], len(raw))

    def test_large_embedded_html_asset_requires_original_opt_in_and_keeps_text_small(self):
        raw = (b'<h1>Policy</h1><img src="data:image/jpeg;base64,'
               + b'A' * (MAX_BYTES + 1) + b'"><p>Policy text.</p>')
        self.path.write_bytes(raw)
        self.binding['sha256'] = hashlib.sha256(raw).hexdigest()
        self.node.update(contentHash=self.binding['sha256'], size=len(raw))
        with self.assertRaises(ValueError):
            self.collect()
        self.binding['original'] = True
        value = self.collect()[self.node['urn']]
        self.assertEqual(value['content'], 'Policy\n\nPolicy text.')
        self.assertEqual(value['original']['size_bytes'], len(raw))
        self.assertLess(len(json.dumps(value)), 2000)

    def test_html_original_asset_allowance_preserves_source_and_text_bounds(self):
        self.binding['original'] = True
        for raw in (b'<h1>Policy</h1>' + b'x' * MAX_HTML_ORIGINAL_BYTES,
                    b'<h1>Policy</h1><p>' + b'x' * (MAX_BYTES + 1) + b'</p>'):
            with self.subTest(size=len(raw)):
                self.path.write_bytes(raw)
                self.binding['sha256'] = hashlib.sha256(raw).hexdigest()
                self.node.update(contentHash=self.binding['sha256'], size=len(raw))
                with self.assertRaises(ValueError):
                    self.collect()

    def test_text_formats_preserve_exact_text(self):
        for format in ['markdown', 'text/plain']:
            self.assertEqual(text_content('Exact text\n', format), ('Exact text\n', format))

    def test_owner_exclusions_and_unclassified_sources_are_rejected(self):
        for patch in [{'owners': ['another-role']}, {'owners': 'executive'}, {'category': None},
                      {'secret': True}, {'visibility': 'restricted'}]:
            with self.subTest(patch=patch):
                manifest = copy.deepcopy(self.manifest)
                manifest['nodes'][0].update(patch)
                with self.assertRaises(ValueError):
                    collect(manifest, self.root / 'manifest.yaml', [self.binding], [self.actor], lambda _: True)
        with self.assertRaises(ValueError):
            collect(self.manifest, self.root / 'manifest.yaml', [self.binding], [self.actor], lambda _: False)

    def history(self):
        first = dict(self.node, parentMac='a' * 64, previous=None,
                     contentHash=self.binding['sha256'])
        def identify(node):
            slug = node['slug'].encode()
            return hashlib.sha256(bytes.fromhex(node['previous'] or node['parentMac'])
                + len(slug).to_bytes(4, 'big') + slug + bytes.fromhex(node['contentHash'])).hexdigest()
        first['mac'] = identify(first)
        latest = dict(first, previous=first['mac'], contentHash='b' * 64)
        latest['mac'] = identify(latest)
        return first, latest

    def test_native_history_resolves_the_tip_independently_of_array_order(self):
        from working_documents import current_nodes
        first, latest = self.history()
        for nodes in ([first, latest], [latest, first]):
            for head in ({}, {self.node['urn']: latest['mac']}):
                with self.subTest(order=nodes[0]['mac'], head=head):
                    manifest = {'nodes': nodes, 'currentVersions': head}
                    self.assertEqual(current_nodes(manifest), [latest])
                    self.assertEqual(len(manifest['nodes']), 2)

    def test_native_history_rejects_stale_heads_branches_and_tampered_predecessors(self):
        from working_documents import current_nodes
        first, latest = self.history()
        for manifest in ({'nodes': [first, latest], 'currentVersions': {first['urn']: first['mac']}},
                         {'nodes': [latest]}, {'nodes': [first, latest, dict(latest)]},
                         {'nodes': [first, dict(latest, previous='c' * 64)]}):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                current_nodes(manifest)

    def test_working_document_fingerprint_must_match_the_current_revision(self):
        first, latest = self.history()
        raw = b'<h1>Updated policy</h1>'
        self.path.write_bytes(raw)
        latest['contentHash'] = hashlib.sha256(raw).hexdigest()
        slug = latest['slug'].encode()
        latest['mac'] = hashlib.sha256(bytes.fromhex(first['mac']) + len(slug).to_bytes(4, 'big')
            + slug + bytes.fromhex(latest['contentHash'])).hexdigest()
        latest['parentMac'] = first['parentMac'] = 'a' * 64
        self.manifest['nodes'] = [latest, first, {'kind': 'folder', 'mac': 'a' * 64, 'slug': 'Policies'}]
        with self.assertRaises(ValueError):
            self.collect()
        self.binding['sha256'] = latest['contentHash']
        self.assertEqual(self.collect()[first['urn']]['content'], 'Updated policy')

    def test_duplicate_versions_and_cross_organization_owners_are_rejected(self):
        self.manifest['nodes'].append(dict(self.node))
        with self.assertRaises(ValueError):
            self.collect()
        self.manifest['nodes'].pop()
        self.actor['org'] = 'other'
        with self.assertRaises(ValueError):
            self.collect()

    def test_external_paths_changed_blobs_and_non_text_sources_are_rejected(self):
        self.node['locations'][0]['path'] = str(self.root / 'outside')
        with self.assertRaises(ValueError):
            self.collect()
        self.node['locations'][0]['path'] = str(self.path)
        self.path.write_bytes(b'Changed source')
        with self.assertRaises(ValueError):
            self.collect()
        for raw in [b'x' * (MAX_BYTES + 1), b'password: PRIVATE_SENTINEL', b'\xff']:
            self.path.write_bytes(raw)
            self.binding['sha256'] = hashlib.sha256(raw).hexdigest()
            with self.assertRaises((ValueError, UnicodeError)):
                self.collect()

    @unittest.skipUnless(os.name == 'posix', 'POSIX links')
    def test_symlinks_cannot_redirect_selected_sources(self):
        outside = self.root / 'outside'
        self.path.rename(outside)
        self.path.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.collect()

    def test_circular_folder_paths_are_rejected(self):
        self.manifest['nodes'][1]['parentMac'] = 'folder'
        with self.assertRaises(ValueError):
            self.collect()

    def test_only_the_declared_store_root_terminates_folder_ancestry(self):
        self.manifest['nodes'][1]['parentMac'] = 'root'
        with self.assertRaises(ValueError):
            self.collect()
        self.manifest['manifest']['rootMac'] = 'root'
        self.assertEqual(self.collect()[self.node['urn']]['folder'], 'Policies')
        self.manifest['nodes'][1].pop('parentMac')
        self.manifest['nodes'][1]['slug'] = '..'
        with self.assertRaises(ValueError):
            self.collect()

    def test_bindings_and_payloads_have_strict_shapes(self):
        for value in [None, [self.binding, self.binding], [self.binding | {'format': 'text/html'}],
                      [self.binding | {'unexpected': 'value'}]]:
            with self.assertRaises(ValueError):
                bindings(value)
        value = self.collect()[self.node['urn']]
        for changes in [{'format': []}, {'folder': '../private'}, {'content': '<script>changed</script>'}]:
            with self.assertRaises(ValueError):
                validated(value | changes)

    def test_adapter_exports_only_opted_in_text_without_inferred_acl(self):
        from channel_identity import HumanDirectory
        from source_adapter import prepare
        from test_source_adapter import snapshot
        from test_view_permissions import scoped_organization
        source = snapshot()
        source['documents'][0]['working_document'] = self.collect()[self.node['urn']]
        directory = HumanDirectory(scoped_organization())
        plain = prepare(source, directory)
        draft = prepare(source, directory, profile_fields=True)
        old = next(row for row in plain['records'] if row['kind'] == 'document')
        new = next(row for row in draft['records'] if row['kind'] == 'document')
        self.assertEqual(old['id'], new['id'])
        self.assertNotIn('content', old['data'])
        self.assertEqual(new['data']['folder'], 'Policies')
        self.assertEqual(new['data']['source'], 'reviewed-working-document')
        self.assertNotIn(str(self.path), json.dumps(new))
        row = next(row for row in draft['resources'] if row['id'] == new['id'])
        self.assertIsNone(row['category'])
        self.assertIsNone(row['scope'])

    def test_collector_links_only_the_selected_document_to_its_declared_owner(self):
        import phantomview as pv
        manifest = copy.deepcopy(self.manifest)
        manifest['manifest']['org'] = 'demo'
        manifest['nodes'][0]['owners'] = [pv.read_source(pv.default_config()['org_files'][0])['actors'][0]['role']]
        manifest['nodes'].append({'urn': 'urn:demo:other', 'kind': 'doc', 'slug': 'Other', 'owners': ['ceo']})
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(manifest))
        observer = pv.Observatory(self.root / 'config.json')
        result = observer.configure(pv.default_config() | {'mode': 'existing', 'docs_manifests': [str(path)],
            'working_documents': [self.binding | {'actor': 'atlas'}]})
        self.assertIsNone(result['error'])
        selected = [row for row in result['snapshot']['documents'] if 'working_document' in row]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['working_document']['actor'], 'atlas')
        links = [row for row in result['snapshot']['edges'] if row.get('type') == 'documentation']
        self.assertEqual([(row['from'], row['to']) for row in links], [('demo:actors:atlas', self.node['urn'])])
