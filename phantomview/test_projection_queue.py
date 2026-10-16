"""Automatic setup/refresh drafting without automatic access approval."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import phantomview as pv
from projection_queue import ReviewQueue
from projection_review import read_json
from resource_review import revision
from test_source_adapter import snapshot
from test_view_permissions import scoped_organization


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.org = scoped_organization()
        self.source = snapshot()
        self.source['actors'][0]['diagnostics']['checks'] = []
        self.queue = ReviewQueue(self.root, lambda: self.org)

    def test_repeated_refresh_reuses_draft_and_never_creates_publication(self):
        first = self.queue.refresh(self.source)
        self.assertEqual(self.queue.refresh(self.source), first)
        self.assertEqual(len(list(self.root.glob('*.draft.json'))), 1)
        self.assertEqual(revision(self.queue.current(self.source)), first['draft_revision'])
        self.assertFalse((self.root / 'active.json').exists())
        self.assertFalse((self.root / 'publish.lock').exists())

    def test_source_changes_and_removals_create_new_drafts_without_grant_inheritance(self):
        first = self.queue.refresh(self.source)
        self.source['actors'][0]['tools'].append('drive')
        second = self.queue.refresh(self.source)
        self.assertNotEqual(first['draft_revision'], second['draft_revision'])
        self.source['actors'] = []
        self.queue.refresh(self.source)
        current = self.queue.current(self.source)
        self.assertNotIn('persona', {row['kind'] for row in current['resources']})
        self.assertTrue(all(row['category'] is None and row['secret'] is None for row in current['resources']))
        self.assertEqual(len(list(self.root.glob('*.draft.json'))), 3)

    def test_observation_clocks_do_not_create_drafts_but_status_changes_do(self):
        diagnostics = {'checked_at': 'first', 'checks': [{'age_minutes': 1, 'status': 'alive'}]}
        self.source['actors'][0]['diagnostics'] = diagnostics
        first = self.queue.refresh(self.source)
        diagnostics['checked_at'] = 'later'
        diagnostics['checks'][0]['age_minutes'] = 2
        self.assertEqual(self.queue.refresh(self.source), first)
        diagnostics['checks'][0]['status'] = 'unavailable'
        self.assertNotEqual(self.queue.refresh(self.source), first)

    def test_changed_authority_invalidates_queue_until_refresh(self):
        self.queue.refresh(self.source)
        self.org['organization']['name'] = 'Updated institution'
        with self.assertRaises(ValueError):
            self.queue.current(self.source)
        self.queue.refresh(self.source)
        self.assertEqual(self.queue.current(self.source)['status'], 'draft')

    def test_unavailable_collection_blocks_current_review_and_preserves_history(self):
        self.queue.refresh(self.source)
        self.queue.unavailable()
        with self.assertRaises(ValueError):
            self.queue.current(self.source)
        self.assertEqual(len(list(self.root.glob('*.draft.json'))), 1)
        self.queue.refresh(self.source)
        self.assertEqual(self.queue.current(self.source)['status'], 'draft')

    def test_writer_lock_and_tampered_draft_fail_closed(self):
        state = self.queue.refresh(self.source)
        lock = self.root / 'queue.lock'
        lock.write_text('busy', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            self.queue.refresh(self.source)
        self.assertEqual(lock.read_text(), 'busy')
        lock.unlink()
        (self.root / (state['draft_revision'] + '.draft.json')).write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.queue.refresh(self.source)
        with self.assertRaises(ValueError):
            self.queue.current(self.source)

    def test_setup_and_refresh_use_operator_queue_and_block_on_collection_failure(self):
        obs = pv.Observatory(self.root / 'config.json', review_queue=self.queue)
        with patch.object(obs, 'collect', side_effect=lambda: copy.deepcopy(self.source)):
            first = obs.configure(pv.default_config())
            self.assertIsNone(first['error'])
            self.assertEqual(self.queue.current(first['snapshot'])['status'], 'draft')
            self.source['actors'][0]['tools'].append('drive')
            self.assertIsNone(obs.refresh()['error'])
        self.assertEqual(len(list(self.root.glob('*.draft.json'))), 2)
        with patch.object(obs, 'collect', side_effect=ValueError('PRIVATE_SOURCE_DETAIL')):
            failed = obs.refresh()
        self.assertIsNotNone(failed['error'])
        self.assertNotIn('PRIVATE_SOURCE_DETAIL', failed['error'])
        self.assertEqual(read_json(self.root / 'review.json')['status'], 'blocked')
        with self.assertRaises(ValueError):
            self.queue.current(failed['snapshot'])

    def test_operator_queue_is_not_loaded_from_web_configuration(self):
        obs = pv.Observatory(self.root / 'config.json')
        config = pv.default_config() | {'mode': 'existing', 'review_root': str(self.root), 'review_org': 'untrusted'}
        with patch.object(obs, 'collect', return_value=self.source):
            self.assertIsNone(obs.configure(config)['error'])
        self.assertFalse((self.root / 'review.json').exists())

    def test_failed_invalidation_and_restart_never_trust_persisted_ready_status(self):
        self.queue.refresh(self.source)
        with patch.object(self.queue, '_save', side_effect=OSError('Storage unavailable')):
            with self.assertRaises(OSError):
                self.queue.unavailable()
        self.assertEqual(read_json(self.root / 'review.json')['status'], 'ready')
        with self.assertRaises(ValueError):
            self.queue.current(self.source)
        restarted = ReviewQueue(self.root, lambda: self.org)
        with self.assertRaises(ValueError):
            restarted.current(self.source)
        restarted.refresh(self.source)
        self.assertEqual(restarted.current(self.source)['status'], 'draft')

    def test_cli_setup_and_sync_prepare_drafts_with_explicit_operator_paths(self):
        organization = self.root / 'organization.json'
        pv.atomic_json(organization, self.org)
        config = self.root / 'config.json'
        options = ['--review-root', str(self.root), '--review-org', str(organization)]
        with patch.object(pv.Observatory, 'collect', side_effect=lambda: copy.deepcopy(self.source)), patch('builtins.print'):
            with patch('sys.argv', ['phantomview', '--config', str(config), 'setup', '--mode', 'existing', *options]):
                pv.main()
            self.source['actors'][0]['tools'].append('drive')
            with patch('sys.argv', ['phantomview', '--config', str(config), 'sync', *options]):
                pv.main()
        self.assertEqual(len(list(self.root.glob('*.draft.json'))), 2)
        self.assertNotIn('review_root', read_json(config))
        self.assertFalse((self.root / 'active.json').exists())


if __name__ == '__main__':
    unittest.main()
