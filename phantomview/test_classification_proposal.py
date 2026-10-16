"""Review drafts must never become implicit permissions."""
import copy
import unittest

from classification_proposal import build_proposal, render_html
from assistant_scope import Scope


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {'organization': 'example', 'categories': {
            'category-0': {}, 'category-1': {}, 'category-2': {}, 'category-3': {}},
            'folders': [{'actor': 'guide', 'folder': 'kb/normas', 'notes': 2}]}

    def test_draft_is_inert_and_exact(self):
        result = build_proposal(self.inventory)
        self.assertFalse(result['activation_supported'])
        self.assertEqual(result['default_access'], 'deny')
        rule = result['rules'][0]
        self.assertFalse(rule['approved'])
        self.assertFalse(rule['recursive'])
        self.assertEqual(rule['suggested_category'], 'category-1')
        self.assertEqual(rule['status'], 'draft')

    def test_project_root_import_and_secrets_remain_unclassified(self):
        for folder in ('kb', 'kb/docs/manuals', 'kb/projects/almaponia', 'kb/credentials'):
            with self.subTest(folder=folder):
                self.inventory['folders'][0]['folder'] = folder
                result = build_proposal(self.inventory)['rules'][0]
                self.assertIsNone(result['suggested_category'])
                self.assertIsNone(result['project'])

    def test_unknown_category_is_not_invented(self):
        del self.inventory['categories']['category-1']
        self.assertIsNone(build_proposal(self.inventory)['rules'][0]['suggested_category'])

    def test_invalid_paths_and_counts_are_rejected(self):
        for folder in ('/kb', 'kb/../secrets', 'kb//normas', 'kb/./normas', 'kb\\normas', 'kb/\n'):
            with self.subTest(folder=folder):
                self.inventory['folders'][0]['folder'] = folder
                with self.assertRaises(ValueError):
                    build_proposal(self.inventory)
        self.inventory['folders'][0]['folder'] = 'kb'
        for count in (True, 0, -1, '2'):
            self.inventory['folders'][0]['notes'] = count
            with self.assertRaises(ValueError):
                build_proposal(self.inventory)

    def test_duplicates_rejected_but_other_persona_kept_separate(self):
        self.inventory['folders'].append(copy.deepcopy(self.inventory['folders'][0]))
        with self.assertRaises(ValueError):
            build_proposal(self.inventory)
        self.inventory['folders'][1]['actor'] = 'other'
        self.assertEqual(len(build_proposal(self.inventory)['rules']), 2)

    def test_stable_order_and_escaped_report(self):
        self.inventory['folders'].append({'actor': 'other', 'folder': 'kb/<script>', 'notes': 1})
        first = build_proposal(self.inventory)
        self.inventory['folders'].reverse()
        self.assertEqual(first, build_proposal(self.inventory))
        report = render_html(first)
        self.assertNotIn('<script>', report)
        self.assertIn('&lt;script&gt;', report)

    def access_preview(self):
        policy = {'organization': 'example',
                  'humans': {'owner': {}, 'member': {'counterpart_persona': 'lead'}, 'unbound': {}},
                  'personas': {'lead': {'categories': ['category-2', 'category-3'], 'projects': []}},
                  'category_zero': {'owner': 'owner', 'categories': list(self.inventory['categories'])}}
        scope = Scope(policy)
        return {'organization': 'example', 'preview_only': True, 'live_access_changed': False,
                'policy': policy, 'policy_revision': scope.revision}

    def test_human_scope_and_absolute_owner_are_separate(self):
        self.inventory['folders'][0]['folder'] = 'kb/infra'
        self.inventory['categories']['category-3']['label'] = 'Existing source meaning'
        result = build_proposal(self.inventory, self.access_preview(), 'category-3')
        rule = result['rules'][0]
        self.assertEqual(rule['suggested_category'], 'category-3')
        self.assertEqual(rule['category_label'], 'Existing source meaning')
        self.assertEqual(rule['human_category_scope'], ['member'])
        self.assertEqual(result['access_preview']['absolute_humans'], [{'human': 'owner', 'counterpart': None}])
        report = render_html(result)
        self.assertIn('Category 0 · Absolute human information access', report)
        self.assertIn('Existing source meaning', report)

    def test_incompatible_or_active_preview_is_rejected(self):
        for key, value in (('organization', 'other'), ('live_access_changed', True),
                           ('preview_only', False), ('policy_revision', 'incorrect')):
            preview = self.access_preview()
            preview[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_proposal(self.inventory, preview)

    def test_changed_category_set_is_rejected(self):
        preview = self.access_preview()
        self.inventory['categories']['category-4'] = {}
        with self.assertRaises(ValueError):
            build_proposal(self.inventory, preview)

    def test_category_zero_cannot_be_selected_for_folders(self):
        with self.assertRaises(ValueError):
            build_proposal(self.inventory, confidential_category='category-0')


if __name__ == '__main__':
    unittest.main()
