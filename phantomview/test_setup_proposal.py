"""Detached setup drafts preserve authority and never approve discovery metadata."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from setup_proposal import folder_inventory, prepare, render_html
from test_channel_identity import organization


SOURCE = '/selected/org.yaml'


class SetupProposalTests(unittest.TestCase):
    def setUp(self):
        self.org = organization()
        for human in self.org['humans']:
            human.pop('counterpart_persona', None)
        self.org['policies']['security_categories']['category-3'] = {'label': 'Confidential'}
        self.org['roles'][0]['security_exceptions'] = ['category-3']
        self.org['actors'][1]['actor_exceptions'] = ['category-4-project']
        self.index = {'config': {'org_files': [SOURCE]}, 'snapshot': {
            'organizations': [{'id': 'example', 'source': SOURCE}],
            'actors': [{'id': actor['id'], 'org': 'example', 'source': SOURCE,
                        'searchable': True, 'knowledge': [
                            {'path': 'kb/infra/example.md', 'searchable': True},
                            {'path': 'kb/hidden.md', 'searchable': False}]}
                       for actor in self.org['actors']]}}
        self.arguments = {'source': SOURCE, 'counterparts': [
            'owner=coordinator', 'secretary=administrator', 'accountant=treasurer'],
            'absolute_owner': 'owner',
            'organization_personas': ['coordinator', 'administrator', 'treasurer']}

    def draft(self):
        return prepare(self.org, self.index, **self.arguments)

    def test_draft_preserves_source_and_every_existing_grant(self):
        original, index = copy.deepcopy(self.org), copy.deepcopy(self.index)
        result = self.draft()
        proposed = copy.deepcopy(result['proposed_org'])
        for human in proposed['humans']:
            human.pop('counterpart_persona', None)
        del proposed['policies']['phantomview']
        self.assertEqual(proposed, original)
        self.assertEqual(self.org, original)
        self.assertEqual(self.index, index)
        self.assertFalse(result['live_access_changed'])
        self.assertFalse(result['activation_supported'])
        self.assertEqual(result['status'], 'draft')
        view = result['proposed_org']['policies']['phantomview']
        self.assertEqual(view['human_action_grants'], {})
        self.assertEqual(view['project_grants'], {})
        self.assertEqual(list(view['scope_definitions']), ['example'])
        grants = result['classification']['access_preview']['personas']
        self.assertIn('category-3', grants['coordinator'])
        self.assertIn('category-4-project', grants['administrator'])
        for rule in result['classification']['rules']:
            self.assertFalse(rule['approved'])
            self.assertEqual(rule['suggested_category'], 'category-3')
            self.assertIsNone(rule['project'])

    def test_independent_owner_needs_no_counterpart(self):
        self.arguments['absolute_owner'] = 'unbound'
        result = self.draft()
        absolute = next(row for row in result['access_preview']['humans'] if row['category_zero'])
        self.assertEqual(absolute['human'], 'unbound')
        self.assertIsNone(absolute['counterpart'])
        self.assertEqual(result['proposed_org']['policies']['security_categories']['category-0']['owner'], 'unbound')

    def test_email_only_is_not_authenticated_or_channel_eligible(self):
        self.org['humans'][2].pop('telegram_user_id')
        self.org['humans'][2]['email'] = 'accountant@example.org'
        row = next(row for row in self.draft()['access_preview']['humans'] if row['human'] == 'accountant')
        self.assertFalse(row['eligible_after_trusted_channel_integration'])
        self.assertEqual(row['registered_channels'], [])

    def test_conflicting_or_ambiguous_bindings_are_rejected(self):
        for assignments in (['missing=coordinator'], ['owner=missing'],
                            ['owner=coordinator', 'owner=administrator'],
                            ['owner=coordinator', 'secretary=coordinator']):
            self.arguments['counterparts'] = assignments
            with self.subTest(assignments=assignments), self.assertRaises(ValueError):
                self.draft()
        self.arguments['counterparts'] = ['owner=coordinator']
        self.org['humans'][0]['counterpart_persona'] = 'administrator'
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.draft()

    def test_existing_view_policy_is_not_overwritten(self):
        self.org['policies']['phantomview'] = {}
        with self.assertRaisesRegex(ValueError, 'migration review'):
            self.draft()

    def test_invalid_owner_and_scope_selection_are_rejected(self):
        for key, value in (('absolute_owner', 'Unknown Name'), ('organization_personas', []),
                           ('organization_personas', ['missing']),
                           ('organization_personas', ['coordinator', 'coordinator'])):
            with self.subTest(key=key, value=value):
                arguments = self.arguments | {key: value}
                with self.assertRaises(ValueError):
                    prepare(self.org, self.index, **arguments)

    def test_source_and_complete_actor_selection_are_required(self):
        variants = []
        changed = copy.deepcopy(self.index)
        changed['config']['org_files'].append('/another/org.yaml')
        variants.append(changed)
        changed = copy.deepcopy(self.index)
        changed['snapshot']['organizations'][0]['source'] = '/stale/org.yaml'
        variants.append(changed)
        changed = copy.deepcopy(self.index)
        changed['snapshot']['actors'].pop()
        variants.append(changed)
        changed = copy.deepcopy(self.index)
        changed['snapshot']['actors'][0]['org'] = 'other'
        variants.append(changed)
        for index in variants:
            with self.subTest(index=index), self.assertRaises(ValueError):
                prepare(self.org, index, **self.arguments)

    def test_unknown_private_project_and_root_folders_stay_unclassified(self):
        self.index['snapshot']['actors'][0]['knowledge'] = [
            {'path': path, 'searchable': True} for path in (
                'kb/root.md', 'kb/projects/sample/plan.md',
                'kb/private/notes.md', 'kb/unknown/notes.md')]
        rules = [row for row in self.draft()['classification']['rules'] if row['actor'] == 'coordinator']
        self.assertEqual(len(rules), 4)
        self.assertTrue(all(row['suggested_category'] is None for row in rules))

    def test_unavailable_truncated_and_nonsearchable_are_excluded(self):
        self.index['snapshot']['actors'][0]['knowledge'] += [
            {'path': 'kb/infra/unavailable.md', 'searchable': True, 'unavailable': True},
            {'path': 'kb/infra/truncated.md', 'searchable': True, 'truncated': True}]
        result = self.draft()['classification']
        self.assertEqual(result['excluded_entries'], 5)
        self.assertEqual(sum(row['notes'] for row in result['rules']), 3)

    def test_invalid_paths_and_duplicate_metadata_are_rejected(self):
        for path in ('/kb/note.md', 'kb/../note.md', 'kb//note.md', 'kb\\note.md', 'kb'):
            self.index['snapshot']['actors'][0]['knowledge'][0]['path'] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.draft()
        self.index['snapshot']['actors'][0]['knowledge'] = [
            {'path': 'kb/example.md', 'searchable': True}] * 2
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.draft()

    def test_fingerprints_are_stable_and_change_with_source(self):
        first = self.draft()
        self.assertEqual(first, self.draft())
        self.org['organization']['name'] = 'Changed organization'
        self.assertNotEqual(first['source_revision'], self.draft()['source_revision'])
        self.index['snapshot']['collected_at'] = 'Later observation'
        self.assertNotEqual(first['collector_revision'], self.draft()['collector_revision'])

    def test_report_escapes_values_and_omits_contacts(self):
        self.org['humans'][0]['email'] = 'private-contact@example.org'
        result = self.draft()
        result['source'] = '<script>'
        report = render_html(result)
        self.assertIn('&lt;script&gt;', report)
        self.assertNotIn('<script>', report)
        self.assertNotIn('private-contact@example.org', report)
        self.assertIn('No live permissions changed', report)

    def test_input_and_note_bounds(self):
        from unittest.mock import patch
        with patch('setup_proposal.MAX_BYTES', 20), self.assertRaises(ValueError):
            self.draft()
        with patch('setup_proposal.MAX_NOTES', 1), self.assertRaises(ValueError):
            folder_inventory(self.org, self.index, SOURCE)

    def test_cli_writes_only_detached_files_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            org_path, index_path = root / 'org.json', root / 'collector.json'
            org_path.write_text(json.dumps(self.org), encoding='utf-8')
            index_path.write_text(json.dumps(self.index), encoding='utf-8')
            command = [sys.executable, str(Path(__file__).with_name('setup_proposal.py')),
                       '--org', str(org_path), '--index', str(index_path), '--source', SOURCE,
                       '--absolute-owner', 'owner', '--counterpart', 'owner=coordinator',
                       '--organization-persona', 'coordinator', '--output', str(root / 'review')]
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({p.name for p in (root / 'review').iterdir()},
                             {'index.html', 'classification.html', 'proposal.json', 'proposed-org.json'})
            before = {p.name: p.read_bytes() for p in (root / 'review').iterdir()}
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'review').iterdir()})
            self.assertEqual(json.loads(org_path.read_text(encoding='utf-8')), self.org)
            command[-1] = str(Path(__file__).parent / 'private-output-forbidden')
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('outside the repository', result.stderr)
            self.assertFalse(Path(command[-1]).exists())


if __name__ == '__main__':
    unittest.main()
