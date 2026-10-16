"""Review drafts must never become implicit permissions."""
import copy
import unittest

from classification_proposal import build_proposal, render_html


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


if __name__ == '__main__':
    unittest.main()
