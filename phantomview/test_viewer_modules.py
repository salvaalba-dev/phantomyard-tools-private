"""Standard scoped navigation and inert modules do not create access grants."""
import copy
import json
from pathlib import Path
from dataclasses import replace
import unittest

from channel_identity import HumanDirectory
from test_channel_identity import context
from test_view_permissions import scoped_organization
from viewer_modules import ModuleRegistry, validate_module


def projects():
    return {'schema_version': 1, 'api_version': 1, 'id': 'project-management', 'version': '1.0.0',
            'label': 'Project management', 'scope_kinds': ['project'],
            'sections': [{'id': 'partners', 'label': 'Partners', 'kind': 'partner', 'view': 'cards'},
                         {'id': 'tasks', 'label': 'Assigned tasks', 'kind': 'task', 'view': 'table'}]}


class ViewerModuleTests(unittest.TestCase):
    def setUp(self):
        self.directory = HumanDirectory(scoped_organization())
        self.recipient = self.directory.resolve(**context('102', 'administrator'), scope_id='river-project')
        self.report = {'default_persona': {'resolved': 'administrator', 'exists': True, 'served': True, 'provenance': 'config'}}
        self.projection = {'schema_version': 1, 'organization': 'example', 'scope_id': 'river-project',
            'policy_revision': self.recipient.policy_revision, 'view_revision': 'a' * 64,
            'complete_corpus': False, 'resources': [{'id': 'b' * 64, 'kind': 'partner', 'data': {'name': 'PRIVATE_SENTINEL'}},
                                                   {'id': 'c' * 64, 'kind': 'task', 'data': {}}]}

    def navigation(self, modules=(), **options):
        return ModuleRegistry(modules).navigation(directory=self.directory, recipient=self.recipient,
            projection=self.projection, default_report=self.report, **options)

    def test_initial_navigation_is_standard_and_uses_only_visible_resource_kinds(self):
        result = self.navigation()
        self.assertEqual([row['id'] for row in result['core']], ['core:partner', 'core:task'])
        self.assertEqual(result['modules'], [])
        self.assertEqual(result['assistant'], {'persona': 'administrator', 'eligible': True, 'source': 'runtime-default'})
        self.assertNotIn('PRIVATE_SENTINEL', str(result))

    def test_optional_module_adds_namespaced_sections_without_replacing_the_core(self):
        validate_module(json.loads(Path(__file__).with_name('example-project-module.json').read_text()))
        result = self.navigation([projects()])
        module = result['modules'][0]
        self.assertEqual(module['sections'][0]['id'], 'project-management:partners')
        self.assertEqual(module['sections'][1]['count'], 1)
        self.assertEqual(module['assistant'], result['assistant'])
        self.assertEqual(len(result['core']), 2)

    def test_module_assistant_override_is_local_and_does_not_change_the_default(self):
        module = projects() | {'assistant': {'persona': 'treasurer'}}
        result = self.navigation([module], assistant_authorized=lambda recipient, persona: True)
        self.assertEqual(result['assistant']['persona'], 'administrator')
        self.assertEqual(result['modules'][0]['assistant']['persona'], 'treasurer')
        self.assertEqual(self.recipient.persona, 'administrator')

    def test_installing_a_module_does_not_authorize_another_assistant(self):
        module = projects() | {'assistant': {'persona': 'treasurer'}}
        route = self.navigation([module])['modules'][0]['assistant']
        self.assertFalse(route['eligible'])
        self.assertIsNone(route['persona'])
        self.assertFalse(self.navigation([module], assistant_authorized=lambda *args: 1)['modules'][0]['assistant']['eligible'])

    def test_adapter_cannot_extend_target_persona_scope(self):
        module = projects() | {'assistant': {'persona': 'treasurer'}}
        recipient = self.directory.resolve(**context('102', 'administrator'), scope_id='example')
        projection = self.projection | {'scope_id': 'example'}
        module['scope_kinds'] = ['organization']
        result = ModuleRegistry([module]).navigation(directory=self.directory, recipient=recipient,
            projection=projection, default_report=self.report, assistant_authorized=lambda *args: True)
        self.assertFalse(result['modules'][0]['assistant']['eligible'])

    def test_unknown_persona_or_unverified_runtime_default_is_rejected(self):
        with self.assertRaises(ValueError):
            self.navigation([projects() | {'assistant': {'persona': 'unknown'}}])
        self.report['default_persona']['served'] = False
        result = self.navigation()
        self.assertFalse(result['assistant']['eligible'])
        self.assertEqual(len(result['core']), 2)

    def test_module_scope_or_missing_data_never_adds_empty_or_foreign_menus(self):
        module = projects()
        module['scope_kinds'] = ['organization']
        self.assertEqual(self.navigation([module])['modules'], [])
        self.projection['resources'] = []
        self.assertEqual(self.navigation([projects()])['modules'], [])

    def test_stale_session_foreign_projection_and_duplicate_records_are_refused(self):
        for changes in ({'scope_id': 'example'}, {'organization': 'other'}, {'policy_revision': 'd' * 64},
                        {'complete_corpus': True}, {'resources': self.projection['resources'] * 2}):
            original = self.projection
            self.projection = original | changes
            with self.assertRaises(ValueError):
                self.navigation()
            self.projection = original
        self.recipient = replace(self.recipient, policy_revision='f' * 64)
        with self.assertRaises(ValueError):
            self.navigation()

    def test_code_urls_permission_grants_and_incompatible_manifests_are_rejected(self):
        for changes in ({'script': 'module.py'}, {'source_url': 'https://example.test'},
                        {'permissions': ['all']}, {'api_version': 2}, {'schema_version': True},
                        {'id': 'core'}, {'label': '<script>'}, {'sections': []}):
            with self.assertRaises(ValueError):
                validate_module(projects() | changes)

    def test_duplicate_installation_and_sections_are_refused(self):
        with self.assertRaises(ValueError):
            ModuleRegistry([projects(), projects()])
        module = projects()
        module['sections'] *= 2
        with self.assertRaises(ValueError):
            validate_module(module)

    def test_registry_keeps_an_installation_snapshot(self):
        module = projects()
        registry = ModuleRegistry([module])
        module['label'] = 'Changed outside registry'
        first = registry.navigation(directory=self.directory, recipient=self.recipient,
            projection=self.projection, default_report=self.report)
        second = copy.deepcopy(first)
        first['modules'][0]['label'] = 'Changed output'
        self.assertEqual(second['modules'][0]['label'], 'Project management')
        fresh = registry.navigation(directory=self.directory, recipient=self.recipient,
            projection=self.projection, default_report=self.report)
        self.assertEqual(fresh['modules'][0]['label'], 'Project management')


if __name__ == '__main__':
    unittest.main()
