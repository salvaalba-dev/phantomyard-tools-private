"""Exact human restrictions narrow counterpart grants without changing personas."""
import copy
import unittest

from channel_identity import HumanDirectory
from test_channel_identity import context
from test_view_permissions import project_resource, scoped_organization


def restricted_organization():
    org = scoped_organization()
    org['policies']['security_categories']['category-4-river'] = {}
    org['actors'][1]['actor_exceptions'] = ['category-4-river']
    org['policies']['phantomview']['human_category_limits'] = {'secretary': ['category-4-river']}
    return org


class HumanCategoryLimitTests(unittest.TestCase):
    def test_exact_category_and_project_boundaries_preserve_native_persona_grants(self):
        directory = HumanDirectory(restricted_organization())
        recipient = directory.resolve(**context('102', 'administrator'), scope_id='river-project')
        self.assertEqual(directory.scope.human_grants('secretary')['categories'], ['category-4-river'])
        self.assertIn('category-1', directory.scope.policy['personas']['administrator']['categories'])
        self.assertTrue(directory.permits(recipient, project_resource(category='category-4-river')))
        for changes in ({'category': 'category-1'}, {'category': 'category-4'},
                        {'category': None}, {'secret': True}, {'project': 'other-project'},
                        {'scope': {'kind': 'organization', 'id': 'example'}}):
            with self.subTest(changes=changes):
                self.assertFalse(directory.permits(recipient, project_resource(**({'category': 'category-4-river'} | changes))))
        self.assertFalse(directory.allows_action(recipient, 'resource.edit', 'river-project',
                         resource=project_resource(category='category-4-river')))

    def test_invalid_limits_never_grant_or_reinterpret_categories(self):
        for limits in (None, [], {'missing': ['category-1']}, {'unbound': ['category-1']},
                       {'owner': ['category-1']}, {'secretary': []}, {'secretary': 'category-1'},
                       {'secretary': [1]}, {'secretary': ['category-0']},
                       {'secretary': ['category-3']}, {'secretary': ['category-1', 'category-1']}):
            org = restricted_organization()
            org['policies']['phantomview']['human_category_limits'] = limits
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                HumanDirectory(org)

    def test_absence_preserves_inheritance_and_policy_changes_revoke_old_bindings(self):
        original = restricted_organization()
        unrestricted = copy.deepcopy(original)
        del unrestricted['policies']['phantomview']['human_category_limits']
        before, after = HumanDirectory(unrestricted), HumanDirectory(original)
        recipient = before.resolve(**context('102', 'administrator'), scope_id='river-project')
        self.assertTrue(before.permits(recipient, project_resource()))
        self.assertNotEqual(before.authority_revision, after.authority_revision)
        with self.assertRaises(ValueError):
            after.validate(recipient)
        original['policies']['phantomview']['human_category_limits']['secretary'].append('category-1')
        self.assertEqual(after.scope.human_grants('secretary')['categories'], ['category-4-river'])


if __name__ == '__main__':
    unittest.main()
