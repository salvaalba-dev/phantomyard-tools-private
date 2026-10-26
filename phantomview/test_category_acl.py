"""Declared native hierarchy, scope isolation and explicit human restrictions."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from category_acl import can_read
from channel_identity import HumanDirectory
from sync_category_acl import generate
from test_channel_identity import context
from test_view_permissions import project_resource, scoped_organization


def hierarchy(*, explicit=False):
    org = scoped_organization()
    org['policies']['security_categories'].update({
        'category-4': {}, 'category-4-river': {}, 'category-4-harbor': {},
    })
    org['policies']['access_levels']['board']['categories'] = [1, 4]
    if explicit:
        for label in ('category-4-river', 'category-4-harbor'):
            org['policies']['security_categories'][label]['parent'] = 'category-4'
    return org


class CategoryACLTests(unittest.TestCase):
    def recipient(self, org):
        directory = HumanDirectory(org)
        return directory, directory.resolve(**context('102', 'administrator'), scope_id='river-project')

    def test_declared_parent_grant_reaches_child_in_both_native_modes(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                org = hierarchy(explicit=explicit)
                directory, recipient = self.recipient(org)
                self.assertTrue(can_read(org, 'administrator', 'category-4-river'))
                self.assertTrue(directory.permits(recipient, project_resource(category='category-4-river')))

    def test_explicit_parent_is_authoritative_even_when_names_disagree(self):
        org = hierarchy(explicit=True)
        org['policies']['security_categories']['category-4-river']['parent'] = 'category-3'
        directory, recipient = self.recipient(org)
        self.assertFalse(directory.permits(recipient, project_resource(category='category-4-river')))
        org['policies']['security_categories']['category-9-project'] = {'parent': 'category-4'}
        directory, recipient = self.recipient(org)
        self.assertTrue(directory.permits(recipient, project_resource(category='category-9-project')))

    def test_child_never_grants_parent_sibling_or_numeric_lower_category(self):
        org = hierarchy()
        org['policies']['access_levels']['board']['categories'] = []
        org['actors'][1]['actor_exceptions'] = ['category-4-river']
        directory, recipient = self.recipient(org)
        self.assertTrue(directory.permits(recipient, project_resource(category='category-4-river')))
        for category in ('category-4', 'category-4-harbor', 'category-1', 'category-0', 'category-4-river-unknown'):
            with self.subTest(category=category):
                self.assertFalse(directory.permits(recipient, project_resource(category=category)))

    def test_declared_longest_prefix_does_not_authorize_undeclared_suffix(self):
        org = hierarchy()
        org['policies']['security_categories']['category-4-river-budget'] = {}
        org['policies']['access_levels']['board']['categories'] = []
        org['actors'][1]['actor_exceptions'] = ['category-4-river']
        directory, recipient = self.recipient(org)
        self.assertTrue(directory.permits(recipient, project_resource(category='category-4-river-budget')))
        self.assertFalse(directory.permits(recipient, project_resource(category='category-4-river-budget-secret')))

    def test_category_parent_does_not_expand_project_scope_or_actions(self):
        org = hierarchy(explicit=True)
        directory, recipient = self.recipient(org)
        resource = project_resource(category='category-4-river')
        self.assertFalse(directory.permits(recipient, project_resource('other-project', category='category-4-harbor')))
        self.assertFalse(directory.permits(recipient, resource | {'project': None}))
        self.assertFalse(directory.permits(recipient, resource | {'secret': True}))
        self.assertFalse(directory.allows_action(recipient, 'resource.edit', 'river-project', resource=resource))
        del org['policies']['phantomview']['project_grants']['administrator']
        with self.assertRaises(ValueError):
            HumanDirectory(org)

    def test_exact_human_limit_can_narrow_an_inherited_child(self):
        org = hierarchy(explicit=True)
        org['policies']['phantomview']['human_category_limits'] = {'secretary': ['category-4-river']}
        directory, recipient = self.recipient(org)
        self.assertEqual(directory.scope.human_grants('secretary')['categories'], ['category-4-river'])
        self.assertIn('category-4-harbor', directory.scope.policy['personas']['administrator']['categories'])
        self.assertTrue(directory.permits(recipient, project_resource(category='category-4-river')))
        for category in ('category-4', 'category-4-harbor', 'category-1'):
            self.assertFalse(directory.permits(recipient, project_resource(category=category)))

    def test_human_limit_parent_label_remains_exact_not_a_second_hierarchy(self):
        org = hierarchy()
        org['policies']['phantomview']['human_category_limits'] = {'secretary': ['category-4']}
        directory, recipient = self.recipient(org)
        self.assertFalse(directory.permits(recipient, project_resource(category='category-4-river')))

    def test_unknown_missing_and_cyclic_parent_paths_do_not_grant_access(self):
        for parent in ('missing', 4, 'category-4-river'):
            org = hierarchy(explicit=True)
            org['policies']['security_categories']['category-4-river']['parent'] = parent
            directory, recipient = self.recipient(org)
            self.assertFalse(directory.permits(recipient, project_resource(category='category-4-river')))
        org['policies']['security_categories']['category-4-harbor']['parent'] = 'category-4-river'
        org['policies']['security_categories']['category-4-river']['parent'] = 'category-4-harbor'
        directory, recipient = self.recipient(org)
        self.assertFalse(directory.permits(recipient, project_resource(category='category-4-river')))

    def test_malformed_category_definitions_are_rejected(self):
        for invalid in (None, [], 'category-4'):
            org = hierarchy()
            org['policies']['security_categories']['category-4-river'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                HumanDirectory(org)

    def test_role_exceptions_and_source_changes_use_effective_categories(self):
        org = hierarchy()
        org['policies']['access_levels']['board']['categories'] = [1]
        org['roles'][0]['security_exceptions'] = ['category-4']
        directory, recipient = self.recipient(org)
        self.assertTrue(directory.permits(recipient, project_resource(category='category-4-river')))
        changed = copy.deepcopy(org)
        changed['policies']['security_categories']['category-4-river']['parent'] = None
        with self.assertRaises(ValueError):
            HumanDirectory(changed).validate(recipient)

    def test_source_generation_rejects_changed_input_without_writing(self):
        metadata = json.loads(Path(__file__).with_name('category_acl_source.json').read_text())
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'access.py'
            source.write_text('def can_read(*args): return True\n')
            with self.assertRaisesRegex(ValueError, 'reviewed revision'):
                generate(source, metadata)

    @unittest.skipUnless(os.environ.get('PHANTOMVIEW_NATIVE_ACL_SOURCE'), 'Pinned native source checked in CI')
    def test_generated_subset_matches_pinned_canonical_functions(self):
        metadata = json.loads(Path(__file__).with_name('category_acl_source.json').read_text())
        generated = generate(Path(os.environ['PHANTOMVIEW_NATIVE_ACL_SOURCE']), metadata)
        self.assertEqual(generated, Path(__file__).with_name('category_acl.py').read_text(encoding='utf-8'))
        native = {}
        exec(compile(generated, '<reviewed-native-category-subset>', 'exec'), native)
        for explicit in (False, True):
            org = hierarchy(explicit=explicit)
            scope = HumanDirectory(org).scope
            for actor in org['actors']:
                for category in org['policies']['security_categories']:
                    expected = native['can_read'](org, actor['id'], category)
                    self.assertEqual(category in scope.policy['personas'][actor['id']]['categories'], expected)


if __name__ == '__main__':
    unittest.main()
