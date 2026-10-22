"""One registered original can have several explicit owner associations without ACL grants."""
import copy
import json
import unittest

from document_refresh import prepare
import test_document_refresh as refresh_fixture
import test_working_documents as working_fixture
from working_documents import bindings, collect, recipients, validated


class SharedDocumentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = working_fixture.WorkingDocumentTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.other = {'id': 'project-lead', 'org': 'example', 'role': 'project', 'searchable': True}
        self.fixture.node['owners'].append('project')
        self.binding = self.fixture.binding | {'related_actors': ['project-lead']}

    def collect(self, actors=None):
        return collect(self.fixture.manifest, self.fixture.root / 'manifest.json', [self.binding],
                       actors or [self.fixture.actor, self.other], lambda _: True)

    def test_one_original_keeps_its_fingerprint_and_all_explicit_owner_associations(self):
        before = copy.deepcopy(self.fixture.manifest)
        documents = self.collect()
        self.assertEqual(len(documents), 1)
        value = next(iter(documents.values()))
        self.assertEqual(recipients(value), ['coordinator', 'project-lead'])
        self.assertEqual(value['source_sha256'], self.fixture.binding['sha256'])
        self.assertEqual(before, self.fixture.manifest)
        self.assertNotIn('category', value)
        self.assertEqual(validated(value), value)
        from document_groups import check_members
        group = {'id': 'urn:example:document:minutes', 'title': 'Minutes', 'version': 'v1.0'}
        first = value | {'document_group': group, 'original': {'media_type': 'application/pdf'}}
        second = value | {'document_group': group, 'original': {'media_type': 'text/plain'},
                          'actor': 'project-lead', 'related_actors': ['coordinator']}
        check_members([first, second])
        with self.assertRaises(ValueError):
            check_members([first, second | {'actor': 'coordinator', 'related_actors': []}])

    def test_secondary_personas_require_exact_visible_native_ownership_in_the_same_organization(self):
        for changes in [{'role': 'finance'}, {'org': 'other'}, {'searchable': False}, {'id': 'missing'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.collect([self.fixture.actor, self.other | changes])
        with self.assertRaises(ValueError):
            self.collect([self.fixture.actor, self.other, dict(self.other)])

    def test_association_schema_is_bounded_unique_and_never_accepts_permissions(self):
        for extra in [[], ['coordinator'], ['project-lead', 'project-lead'], 'project-lead',
                      ['../other'], ['a' + str(i) for i in range(8)], [{'category': 'category-0'}]]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                bindings([self.binding | {'related_actors': extra}])
        self.assertEqual(recipients(self.fixture.binding), ['coordinator'])
        with self.assertRaises(ValueError):
            bindings([self.binding, self.binding])

    def test_batch_planning_preserves_shared_associations_without_publishing(self):
        fixture = refresh_fixture.DocumentRefreshTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.node['owners'].append('project')
        matrix = copy.deepcopy(fixture.matrix)
        matrix['documents'][0]['related_actors'] = ['project-lead']
        plan = prepare(fixture.manifest, fixture.root / 'manifest.yaml', matrix,
                       [fixture.actor, self.other], lambda _: True)
        self.assertEqual(len(plan['prepared']), 1)
        self.assertEqual(plan['prepared'][0]['binding']['related_actors'], ['project-lead'])
        self.assertFalse(plan['mutations_performed'])
        self.assertTrue(plan['publication_required'])

    def test_collector_emits_two_document_links_and_only_one_document(self):
        import phantomview as pv
        root = self.fixture.root
        organization = {'version': 1, 'organization': {'id': 'example', 'name': 'Example Organization'},
                        'departments': [],
                        'roles': [{'id': 'executive'}, {'id': 'project'}],
                        'actors': [{'id': 'coordinator', 'role': 'executive'}, {'id': 'project-lead', 'role': 'project'}]}
        paths = {'org.json': organization, 'manifest.json': self.fixture.manifest}
        for name, value in paths.items():
            path = root / name
            path.write_text(json.dumps(value), encoding='utf-8')
            path.chmod(0o600)
        observer = pv.Observatory(root / 'config.json')
        state = observer.configure({'mode': 'existing', 'org_files': [str(root / 'org.json')],
            'docs_manifests': [str(root / 'manifest.json')], 'working_documents': [self.binding],
            'auto_procedures': False})
        self.assertIsNone(state['error'])
        documents = [row for row in state['snapshot']['documents'] if 'working_document' in row]
        self.assertEqual(len(documents), 1)
        links = [row for row in state['snapshot']['edges'] if row['type'] == 'documentation']
        self.assertEqual({row['from'] for row in links}, {'example:actors:coordinator', 'example:actors:project-lead'})
        self.assertEqual({row['to'] for row in links}, {self.fixture.node['urn']})

    def test_shared_associations_still_require_individual_projection_classification(self):
        from channel_identity import HumanDirectory
        from source_adapter import prepare as projection
        from test_source_adapter import snapshot
        from test_view_permissions import scoped_organization
        source = snapshot()
        source['actors'].append({'org': 'example', 'id': 'project-lead', 'key': 'example:actors:project-lead',
                                 'searchable': True, 'role': 'project'})
        document = source['documents'][0]
        document['working_document'] = next(iter(self.collect().values()))
        source['edges'].extend({'from': 'example:actors:' + actor, 'to': document['urn'],
                                'type': 'documentation', 'label': 'Working document'}
                               for actor in recipients(document['working_document']))
        draft = projection(source, HumanDirectory(scoped_organization()), profile_fields=True)
        files = [row for row in draft['records'] if row['kind'] == 'document']
        self.assertEqual(len(files), 1)
        links = [row for row in draft['records'] if row['kind'] == 'relationship'
                 and row['data'].get('target') == files[0]['id']]
        self.assertEqual(len(links), 2)
        for record in [files[0], *links]:
            decision = next(row for row in draft['resources'] if row['id'] == record['id'])
            self.assertIsNone(decision['category'])
            self.assertIsNone(decision['scope'])


if __name__ == '__main__':
    unittest.main()
