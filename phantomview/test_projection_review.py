"""Offline approval, publication leases and current-source enforcement."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from channel_identity import HumanDirectory
from projection_review import PublishedProjection, approve, validate
from resource_review import revision
from source_adapter import prepare
from scoped_backend import ScopedBackend
from test_scoped_backend import ProjectionFixture
from test_source_adapter import snapshot
from test_view_permissions import scoped_organization


class ProjectionReviewTests(unittest.TestCase):
    def setUp(self):
        self.org = scoped_organization()
        self.source = snapshot()
        self.draft = prepare(self.source, HumanDirectory(self.org))
        self.decisions = {'schema_version': 1, 'draft_revision': revision(self.draft),
                          'organization_revision': revision(self.org), 'resources': [
            {key: row[key] for key in ('id', 'payload_sha256')} | {
                'category': 'category-1', 'scope': {'kind': 'organization', 'id': 'example'},
                'project': None, 'secret': False} for row in self.draft['resources']]}
        self.reviewer = next(iter(HumanDirectory(self.org).scope.policy['humans']))

    def approval(self, previous=None):
        return approve(self.draft, self.decisions, self.org, lambda: self.source,
                       reviewer=self.reviewer, previous=previous)

    def test_profile_mode_survives_approval_and_requires_new_payload_decisions(self):
        self.draft = prepare(self.source, HumanDirectory(self.org), profile_fields=True)
        with self.assertRaises(ValueError):
            self.approval()
        self.decisions['draft_revision'] = revision(self.draft)
        candidates = {row['id']: row for row in self.draft['resources']}
        for row in self.decisions['resources']:
            row['payload_sha256'] = candidates[row['id']]['payload_sha256']
        bundle = self.approval()
        self.assertIs(bundle['profile_fields'], True)
        with tempfile.TemporaryDirectory() as root:
            publisher = self.publisher(root)
            publisher.publish(bundle, self.draft, expected_revision=None)
            self.assertEqual(publisher.active()[1], bundle)
        invalid = copy.deepcopy(bundle)
        invalid['profile_fields'] = False
        invalid['revision'] = revision({key: value for key, value in invalid.items() if key != 'revision'})
        with self.assertRaises(ValueError):
            validate(invalid)

    def publisher(self, root):
        return PublishedProjection(root, lambda: self.org, lambda: self.source)

    def test_approval_binds_sources_decisions_authority_and_declared_reviewer(self):
        bundle = self.approval()
        self.assertEqual(bundle['sequence'], 1)
        self.assertEqual(validate(bundle), bundle)
        self.assertNotIn('records', bundle)
        self.assertEqual(len(bundle['sources']), len(bundle['catalog']['resources']))
        with self.assertRaises(ValueError):
            approve(self.draft, self.decisions, self.org, lambda: self.source, reviewer='unknown')
        self.decisions['resources'][0]['secret'] = None
        with self.assertRaises(ValueError):
            self.approval()

    def test_organization_link_mode_survives_review_publication_and_current_source_checks(self):
        self.source['actors'][0]['role'] = 'executive'
        self.source['roles'][0]['department'] = 'board'
        self.source['humans'] = [{'org': 'example', 'id': 'owner', 'name': 'Owner'}]
        self.draft = prepare(self.source, HumanDirectory(self.org), organization_links=True)
        self.decisions = {'schema_version': 1, 'draft_revision': revision(self.draft),
                          'organization_revision': revision(self.org), 'resources': [
            {key: row[key] for key in ('id', 'payload_sha256')} | {
                'category': 'category-1', 'scope': {'kind': 'organization', 'id': 'example'},
                'project': None, 'secret': False} for row in self.draft['resources']]}
        bundle = self.approval()
        self.assertIs(bundle['organization_links'], True)
        invalid = copy.deepcopy(bundle)
        invalid['organization_links'] = False
        invalid['revision'] = revision({key: value for key, value in invalid.items() if key != 'revision'})
        with self.assertRaises(ValueError):
            validate(invalid)
        with tempfile.TemporaryDirectory() as root:
            publisher = self.publisher(root)
            publisher.publish(bundle, self.draft, expected_revision=None)
            self.assertEqual(publisher.active()[1], bundle)
            self.source['actors'][0]['role'] = 'different-role'
            with self.assertRaises(ValueError):
                publisher.active()

    def test_stale_draft_source_and_authority_are_rejected(self):
        for change in ('source', 'draft', 'authority', 'decisions'):
            with self.subTest(change=change):
                self.setUp()
                if change == 'source':
                    self.source['actors'][0]['tools'].append('drive')
                elif change == 'draft':
                    self.draft['records'][0]['data']['title'] = 'Forged'
                elif change == 'authority':
                    self.org['organization']['name'] = 'Changed organization'
                else:
                    self.decisions['draft_revision'] = 'f' * 64
                with self.assertRaises(ValueError):
                    self.approval()

    def test_missing_dependencies_duplicates_and_invalid_categories_fail_closed(self):
        original = copy.deepcopy(self.decisions)
        persona = next(row['id'] for row in self.draft['resources'] if row['kind'] == 'persona')
        self.decisions['resources'] = [row for row in self.decisions['resources'] if row['id'] != persona]
        with self.assertRaises(ValueError):
            self.approval()
        self.decisions = copy.deepcopy(original)
        self.decisions['resources'].append(self.decisions['resources'][0])
        with self.assertRaises(ValueError):
            self.approval()
        for category in ('category-0', 'category-999'):
            self.decisions = copy.deepcopy(original)
            self.decisions['resources'][0]['category'] = category
            with self.assertRaises(ValueError):
                self.approval()

    def test_unknown_scope_and_project_mismatch_are_rejected(self):
        self.decisions['resources'][0]['scope']['id'] = 'missing'
        with self.assertRaises(ValueError):
            self.approval()
        self.setUp()
        self.decisions['resources'][0]['project'] = 'river-project'
        with self.assertRaises(ValueError):
            self.approval()

    def test_partial_batch_is_allowed_only_with_complete_dependencies(self):
        organization = next(row['id'] for row in self.draft['resources'] if row['kind'] == 'organization')
        self.decisions['resources'] = [row for row in self.decisions['resources'] if row['id'] == organization]
        self.assertEqual(len(self.approval()['catalog']['resources']), 1)

    def test_publication_separates_metadata_payloads_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as root:
            publisher = self.publisher(root)
            first = self.approval()
            publisher.publish(first, self.draft, expected_revision=None)
            self.assertEqual(publisher.catalog(), first['catalog'])
            ident = first['catalog']['resources'][0]['id']
            self.assertEqual(json.loads(publisher.record(ident))['id'], ident)
            self.assertIsNone(publisher.record('f' * 64))
            self.decisions['resources'][0]['secret'] = True
            second = self.approval(first)
            publisher.publish(second, self.draft, expected_revision=first['revision'])
            self.assertEqual(second['sequence'], 2)
            self.assertEqual(publisher.catalog(), second['catalog'])
            self.assertEqual(json.loads((Path(root) / first['revision'] / 'approval.json').read_bytes()), first)
            self.assertNotIn('records', json.loads((Path(root) / second['revision'] / 'approval.json').read_bytes()))

    def test_stale_lease_and_writer_lock_leave_active_revision_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            publisher = self.publisher(root)
            first = self.approval()
            publisher.publish(first, self.draft, expected_revision=None)
            with self.assertRaises(ValueError):
                publisher.publish(self.approval(first), self.draft, expected_revision=None)
            lock = Path(root) / 'publish.lock'
            lock.write_text('another writer', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                publisher.publish(self.approval(first), self.draft, expected_revision=first['revision'])
            self.assertEqual(lock.read_text(), 'another writer')
            self.assertEqual(publisher.catalog(), first['catalog'])

    def test_source_removal_or_authority_change_invalidates_active_loaders(self):
        for change in ('remove', 'exclude', 'authority'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root:
                self.setUp()
                publisher = self.publisher(root)
                bundle = self.approval()
                publisher.publish(bundle, self.draft, expected_revision=None)
                if change == 'remove':
                    self.source['actors'] = []
                elif change == 'exclude':
                    self.source['actors'][0]['searchable'] = False
                else:
                    self.org['organization']['name'] = 'New name'
                with self.assertRaises(ValueError):
                    publisher.catalog()
                with self.assertRaises(ValueError):
                    publisher.record(bundle['catalog']['resources'][0]['id'])

    def test_failed_atomic_switch_keeps_old_catalog_and_immutable_generations(self):
        with tempfile.TemporaryDirectory() as root:
            publisher = self.publisher(root)
            first = self.approval()
            publisher.publish(first, self.draft, expected_revision=None)
            second = self.approval(first)
            with patch('projection_review.os.replace', side_effect=OSError('Simulated failure')):
                with self.assertRaises(OSError):
                    publisher.publish(second, self.draft, expected_revision=first['revision'])
            self.assertEqual(publisher.catalog(), first['catalog'])
            self.assertTrue((Path(root) / second['revision'] / 'approval.json').exists())
            self.assertFalse((Path(root) / 'publish.lock').exists())

    def test_tampered_history_or_source_cannot_be_published(self):
        bundle = self.approval()
        bundle['sources'][0]['provenance']['identity'] = 'forged'
        with self.assertRaises(ValueError):
            validate(bundle)
        bundle['revision'] = revision({key: value for key, value in bundle.items() if key != 'revision'})
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                self.publisher(root).publish(bundle, self.draft, expected_revision=None)

    def test_decision_order_does_not_change_approval_and_reclassified_hashes_are_checked(self):
        first = self.approval()
        self.decisions['resources'].reverse()
        self.assertEqual(self.approval(), first)
        first['catalog']['resources'][0]['category'] = 'category-999'
        first['revision'] = revision({key: value for key, value in first.items() if key != 'revision'})
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                self.publisher(root).publish(first, self.draft, expected_revision=None)


class PublishedBackendTests(ProjectionFixture):
    def test_published_loaders_feed_backend_and_source_removal_invalidates_search(self):
        source = snapshot()
        draft = prepare(source, HumanDirectory(self.org))
        decisions = {'schema_version': 1, 'draft_revision': revision(draft),
                     'organization_revision': revision(self.org), 'resources': [
            {key: row[key] for key in ('id', 'payload_sha256')} | {
                'category': 'category-1', 'scope': {'kind': 'organization', 'id': 'example'},
                'project': None, 'secret': row['kind'] == 'persona'} for row in draft['resources']]}
        reviewer = next(iter(HumanDirectory(self.org).scope.policy['humans']))
        bundle = approve(draft, decisions, self.org, lambda: source, reviewer=reviewer)
        with tempfile.TemporaryDirectory() as root:
            publisher = PublishedProjection(root, lambda: self.org, lambda: source)
            publisher.publish(bundle, draft, expected_revision=None)
            backend = ScopedBackend(self.gate, publisher.catalog, publisher.record)
            view = backend.state(self.headers)
            self.assertEqual(view['counts']['organization'], 1)
            for hidden in ('persona', 'finding', 'procedure'):
                self.assertNotIn(hidden, view['counts'])
            source['actors'] = []
            with self.assertRaises(ValueError):
                backend.search(self.headers, 'Foundation')


if __name__ == '__main__':
    unittest.main()
