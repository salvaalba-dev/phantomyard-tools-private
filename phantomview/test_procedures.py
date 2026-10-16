import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import phantomview as pv
from procedures import discover


class ProcedureDiscoveryTests(unittest.TestCase):
    def fixture(self, content, searchable=True):
        actor = {'id': 'coordinator', 'key': 'example:actors:coordinator', 'org': 'example', 'knowledge': [
            {'id': 'a' * 64, 'title': 'Meetings', 'path': 'kb/Meetings.md', 'searchable': searchable}]}
        payloads = {'a' * 64: {'actor': actor['key'], 'content': content}}
        return actor, payloads

    def test_protocol_heading_discovers_sections_without_flattening_branches(self):
        actor, payloads = self.fixture('# Meeting protocol\n## Entry\n1. Read agenda\n2. Join room\n## Exit\n- Record outcome\n- Leave room\n')
        rows, status = discover([], [actor], payloads)
        self.assertEqual([r['kind'] for r in rows], ['ordered', 'rules'])
        self.assertEqual(rows[0]['title'], 'Entry')
        self.assertEqual([s['action'] for s in rows[0]['steps']], ['Read agenda', 'Join room'])
        self.assertEqual(rows[0]['source_note'], 'a' * 64)
        self.assertEqual(rows[0]['source_owner'], 'coordinator')
        self.assertEqual(rows[0]['steps'][0]['actor'], '')
        self.assertFalse(status['partial'])

    def test_code_indexes_nested_lists_and_number_resets(self):
        actor, payloads = self.fixture('# Protocol\n```sh\n1. Never run this\n2. Ignored\n```\n## Links\n- [Agenda](agenda.md)\n- [Team](team.md)\n## Action\n1. Read\n  - Nested detail\n2. Discuss\n1. Review\n2. Finish\n')
        rows, _ = discover([], [actor], payloads)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['steps'][0]['action'], 'Read Nested detail')
        self.assertNotIn('Never run', json.dumps(rows))
        self.assertNotIn('Agenda', json.dumps(rows))

    def test_private_truncated_stale_and_foreign_notes_are_not_imported(self):
        actor, payloads = self.fixture('# Protocol\n1. Private action\n2. Complete', searchable=False)
        self.assertEqual(discover([], [actor], payloads)[0], [])
        actor['knowledge'][0]['searchable'] = True
        payloads['a' * 64]['actor'] = 'foreign:actors:coordinator'
        self.assertEqual(discover([], [actor], payloads)[0], [])
        actor['knowledge'] = []
        self.assertEqual(discover([], [actor], payloads)[0], [])
        actor, payloads = self.fixture('# Protocol\n1. Read\n2. Act')
        actor['knowledge'][0]['truncated'] = True
        self.assertEqual(discover([], [actor], payloads)[0], [])

    def test_declared_conditions_stay_rules_and_documents_are_references_only(self):
        org = {'organization': {'id': 'example'}, 'escalation_matrix': [
            {'from': 'staff', 'to': 'lead', 'condition': 'Blocked'},
            {'from': 'lead', 'to': 'staff', 'condition': 'Need detail'}], 'communication': {'max_hops': 3}}
        rows, _ = discover([(org, '/selected/org.yaml')], [], {}, [
            {'org': 'example', 'urn': 'urn:protocol', 'slug': 'safety-protocol', 'location': 'https://external.invalid/file'}])
        self.assertEqual(rows[0]['kind'], 'rules')
        self.assertEqual(rows[0]['max_hops'], 3)
        self.assertEqual(rows[1]['kind'], 'document')
        self.assertEqual(rows[1]['source_document'], 'urn:protocol')
        self.assertEqual(rows[1]['steps'], [])

    def test_budgets_are_reported_without_exceeding_the_bound(self):
        actor, payloads = self.fixture('# Protocol\n1. Read\n2. Act')
        with patch('procedures.MAX_SCAN_BYTES', 2):
            rows, status = discover([], [actor], payloads)
        self.assertEqual(rows, [])
        self.assertTrue(status['partial'])
        self.assertEqual(status['omitted_notes'], 1)
        actor['knowledge'][0]['title'] = 'Protocol'
        with patch('procedures.MAX_SCAN_BYTES', 2):
            rows, status = discover([], [actor], payloads)
        self.assertEqual(rows[0]['kind'], 'document')
        self.assertTrue(rows[0]['partial'])
        self.assertEqual(rows[0]['source_note'], 'a' * 64)

    def test_identical_copies_share_cards_but_keep_source_links_and_owners(self):
        actor, payloads = self.fixture('# Protocol\n1. Read\n2. Act')
        second = {**actor, 'id': 'lead', 'key': 'example:actors:lead', 'knowledge': [
            {**actor['knowledge'][0], 'id': 'b' * 64}]}
        payloads['b' * 64] = {**payloads['a' * 64], 'actor': second['key']}
        rows, _ = discover([], [actor, second], payloads)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source_owners'], ['coordinator', 'lead'])
        self.assertEqual(len(rows[0]['source_refs']), 2)
        payloads['b' * 64]['content'] += '\nDifferent approval condition.'
        self.assertEqual(len(discover([], [actor, second], payloads)[0]), 2)

    def test_setup_refresh_updates_and_removals_need_no_manual_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = root / 'personas' / 'atlas' / 'kb'
            profile.mkdir(parents=True)
            note = profile / 'protocol.md'
            note.write_text('# Protocol\n1. Read agenda\n2. Join', encoding='utf-8')
            obs = pv.Observatory(root / 'config.json')
            cfg = pv.default_config()
            cfg.update(mode='existing', personas_dir=str(profile.parent.parent), procedures_file='')
            first = obs.configure(cfg)
            self.assertIsNone(first['error'])
            automatic = next(p for p in first['snapshot']['procedures'] if p['origin'] == 'knowledge')
            obs.refresh()
            self.assertEqual(len(obs.history), 1)
            note.write_text('# Protocol\n1. Read revised agenda\n2. Join', encoding='utf-8')
            second = obs.refresh()
            changed = next(p for p in second['snapshot']['procedures'] if p['id'] == automatic['id'])
            self.assertIn('revised', changed['steps'][0]['action'])
            self.assertNotEqual(changed['source_note'], automatic['source_note'])
            self.assertTrue(any(c['kind'] == 'procedures' and c['action'] == 'changed' for c in obs.history[-1]['changes']))
            note.unlink()
            self.assertFalse(any(p['origin'] == 'knowledge' for p in obs.refresh()['snapshot']['procedures']))
            obs.config['auto_procedures'] = False
            self.assertEqual(obs.refresh()['snapshot']['procedures'], [])


if __name__ == '__main__':
    unittest.main()
