"""Synthetic project and organization boundaries with independent write rights."""
import copy
from dataclasses import replace
import unittest

from channel_identity import HumanDirectory
from scoped_knowledge import retrieve
from test_channel_identity import context, organization
from test_scoped_knowledge import note_fixture


def scoped_organization():
    org = organization()
    org['departments'] = [{'id': 'board'}]
    org['policies']['security_categories']['category-3'] = {}
    org['policies']['phantomview'] = {
        'project_grants': {'coordinator': ['river-project', 'other-project'],
                           'administrator': ['river-project'], 'treasurer': ['river-project']},
        'scope_definitions': {'example': {'kind': 'organization', 'label': 'Example Organization'},
                              'board': {'kind': 'department', 'label': 'Board'},
                              'river-project': {'kind': 'project', 'label': 'River Project'},
                              'other-project': {'kind': 'project', 'label': 'Other Project'}},
        'persona_scope_grants': {'coordinator': ['example', 'river-project', 'other-project'],
                                 'administrator': ['example', 'river-project'],
                                 'treasurer': ['river-project']},
        'human_action_grants': {'secretary': {'view.personal.edit': ['example', 'river-project']},
                                'accountant': {'resource.edit': ['river-project']}},
    }
    return org


def project_resource(project='river-project', **changes):
    return {'organization': 'example', 'category': 'category-1', 'secret': False,
            'scope': {'kind': 'project', 'id': project}, 'project': project} | changes


class ViewPermissionTests(unittest.TestCase):
    def setUp(self):
        self.org = scoped_organization()
        self.directory = HumanDirectory(self.org)

    def recipient(self, sender='102', persona='administrator', scope='example'):
        return self.directory.resolve(**context(sender, persona), scope_id=scope)

    def test_explicit_scope_required_and_counterpart_scope_inherited(self):
        with self.assertRaises(ValueError):
            self.directory.resolve(**context('102', 'administrator'))
        recipient = self.recipient('103', 'treasurer', 'river-project')
        self.assertEqual(recipient.scope_id, 'river-project')
        for scope in ('example', 'other-project', 'unknown'):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.recipient('103', 'treasurer', scope)

    def test_project_session_cannot_expand_to_another_granted_scope(self):
        recipient = self.recipient(scope='river-project')
        self.assertTrue(self.directory.permits(recipient, project_resource()))
        self.assertFalse(self.directory.permits(recipient, {
            'organization': 'example', 'category': 'category-1', 'secret': False,
            'scope': {'kind': 'organization', 'id': 'example'}}))
        self.assertFalse(self.directory.permits(recipient, project_resource('other-project')))

    def test_organization_session_does_not_imply_all_project_access(self):
        recipient = self.recipient()
        self.assertTrue(self.directory.permits(recipient, project_resource()))
        self.assertFalse(self.directory.permits(recipient, project_resource('other-project')))
        self.assertFalse(self.directory.permits(recipient, project_resource(category='category-3')))

    def test_missing_mismatched_or_forged_scope_cannot_authorize_resource(self):
        recipient = self.recipient()
        for scope in (None, {}, {'kind': 'organization', 'id': 'river-project'},
                      {'kind': 'project', 'id': 'unknown'}, ['river-project']):
            with self.subTest(scope=scope):
                self.assertFalse(self.directory.permits(recipient, project_resource(scope=scope)))
        self.assertFalse(self.directory.permits(recipient, project_resource(project='other-project')))
        with self.assertRaises(ValueError):
            self.directory.validate(replace(recipient, scope_id='other-project'))

    def test_category_zero_is_read_only_without_explicit_actions(self):
        owner = self.recipient('101', 'coordinator')
        self.assertTrue(self.directory.permits(owner, project_resource('other-project', category='category-3')))
        self.assertFalse(self.directory.permits(owner, project_resource(secret=True)))
        for action in ('resource.edit', 'resource.classify', 'view.shared.edit', 'view.personal.edit'):
            with self.subTest(action=action):
                self.assertFalse(self.directory.allows_action(owner, action, 'river-project',
                                 resource=project_resource(), owner='owner'))
        project_owner = self.recipient('101', 'coordinator', 'river-project')
        self.assertFalse(self.directory.permits(project_owner, project_resource('other-project')))

    def test_independent_category_zero_owner_can_enter_through_another_persona(self):
        self.org['policies']['security_categories']['category-0']['owner'] = 'unbound'
        self.org['actors'][0]['actor_exceptions'] = ['category-0']
        self.directory = HumanDirectory(self.org)
        self.assertNotIn('category-0', self.directory.scope.human_grants('owner')['categories'])
        owner = self.recipient('104', 'treasurer', 'other-project')
        self.assertTrue(self.directory.permits(owner, project_resource('other-project', category='category-3')))
        self.assertFalse(self.directory.allows_action(owner, 'view.shared.edit', 'other-project'))

    def test_personal_view_owner_and_shared_view_permissions_are_distinct(self):
        recipient = self.recipient()
        self.assertTrue(self.directory.allows_action(recipient, 'view.personal.edit', 'river-project', owner='secretary'))
        self.assertFalse(self.directory.allows_action(recipient, 'view.personal.edit', 'river-project', owner='owner'))
        self.assertFalse(self.directory.allows_action(recipient, 'view.shared.edit', 'river-project'))
        project = self.recipient(scope='river-project')
        self.assertFalse(self.directory.allows_action(project, 'view.personal.edit', 'example', owner='secretary'))

    def test_resource_edits_need_both_read_access_and_explicit_action(self):
        recipient = self.recipient('103', 'treasurer', 'river-project')
        self.assertTrue(self.directory.allows_action(recipient, 'resource.edit', 'river-project', resource=project_resource()))
        self.assertFalse(self.directory.allows_action(recipient, 'resource.classify', 'river-project', resource=project_resource()))
        for resource in (None, project_resource(secret=True), project_resource(category='category-3'),
                         project_resource('other-project'), project_resource(scope=None)):
            with self.subTest(resource=resource):
                self.assertFalse(self.directory.allows_action(recipient, 'resource.edit', 'river-project', resource=resource))

    def test_scope_or_action_changes_invalidate_existing_recipient(self):
        recipient = self.recipient()
        for field, value in (('persona_scope_grants', {'administrator': ['example']}),
                             ('human_action_grants', {})):
            changed = copy.deepcopy(self.org)
            changed['policies']['phantomview'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                HumanDirectory(changed).validate(recipient)

    def test_invalid_references_and_implicit_project_grants_fail_closed(self):
        mutations = [
            lambda view: view['scope_definitions'].update(unknown={'kind': 'department'}),
            lambda view: view['scope_definitions'].update(other={'kind': 'organization'}),
            lambda view: view['scope_definitions'].update(con={'kind': 'project'}),
            lambda view: view['persona_scope_grants'].update(stranger=['example']),
            lambda view: view['persona_scope_grants'].update(administrator=['unknown']),
            lambda view: view['persona_scope_grants'].update(administrator=['example', 'example']),
            lambda view: view['project_grants'].update(administrator=[]),
            lambda view: view['human_action_grants'].update(stranger={'view.shared.edit': ['example']}),
            lambda view: view['human_action_grants']['secretary'].update(execute=['example']),
        ]
        for mutation in mutations:
            changed = copy.deepcopy(self.org)
            mutation(changed['policies']['phantomview'])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                HumanDirectory(changed)

    def test_scoped_retrieval_keeps_denied_payload_unopened(self):
        recipient = self.recipient(scope='river-project')
        directory = self.directory
        class Gate:
            def identified_scope(self, headers):
                return recipient, directory
        raw, catalog = note_fixture(project='river-project', scope={'kind': 'project', 'id': 'river-project'})
        loaded = []
        def load(ident):
            loaded.append(ident)
            return raw
        self.assertEqual(len(retrieve(Gate(), {}, lambda: catalog, load, 'organization')['notes']), 1)
        loaded.clear()
        catalog['resources'][0]['scope']['id'] = 'other-project'
        self.assertEqual(retrieve(Gate(), {}, lambda: catalog, load, 'organization')['notes'], [])
        self.assertEqual(loaded, [])


if __name__ == '__main__':
    unittest.main()
