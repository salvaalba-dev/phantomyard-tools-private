"""Reviewed scopes cannot silently approve changed, excluded or unclassified notes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from assistant_scope import Scope
from channel_identity import HumanDirectory
from resource_review import approve_review, decisions_from_folders, load_revision, reviewed_catalog, revision, save_revision, source_key
from scoped_knowledge import Catalog, retrieve
from test_channel_identity import context
from test_scoped_knowledge import note_fixture
from test_view_permissions import scoped_organization


class ResourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.org = scoped_organization()
        self.raw, catalog = note_fixture()
        note = json.loads(self.raw)
        note.update(path='kb/policies/example.md', content='Reviewed organization procedures.')
        self.raw = json.dumps(note).encode()
        catalog['resources'][0].update(path=note['path'], payload_sha256=hashlib.sha256(self.raw).hexdigest())
        self.row = catalog['resources'][0]
        self.draft = catalog | {'status': 'draft', 'resources': [self.row | {'secret': None}]}
        self.snapshot = {'actors': [{'org': 'example', 'id': 'coordinator', 'searchable': True,
                                    'knowledge': [{'id': self.row['id'], 'path': self.row['path'],
                                                   'searchable': True}]}]}
        self.decisions = {'schema_version': 1, 'review_revision': revision(self.draft),
                          'organization_revision': revision(self.org),
                          'policy_revision': Scope.from_org(self.org).revision, 'resources': [{
                              key: value for key, value in self.row.items()
                              if key in {'id', 'payload_sha256', 'category', 'project', 'secret'}} | {
                                  'scope': {'kind': 'organization', 'id': 'example'}}]}

    def approve(self, **kwargs):
        return approve_review(self.draft, self.decisions, self.org, lambda: self.snapshot,
                              lambda ident: self.raw, reviewer='owner', **kwargs)

    def test_explicit_review_records_scope_provenance_and_content_revision(self):
        bundle = self.approve()
        catalog = reviewed_catalog(bundle, self.org)
        self.assertEqual(catalog['resources'][0]['scope'], {'kind': 'organization', 'id': 'example'})
        self.assertEqual(bundle['sequence'], 1)
        self.assertIsNone(bundle['previous_revision'])
        self.assertEqual(bundle['sources'][0]['source_key'], source_key('example', 'coordinator', self.row['path']))
        self.assertEqual(bundle['sources'][0]['payload_sha256'], self.row['payload_sha256'])
        self.assertNotIn('content', json.dumps(bundle))
        catalog['resources'][0]['secret'] = True
        self.assertFalse(reviewed_catalog(bundle, self.org)['resources'][0]['secret'])

    def test_draft_cannot_be_promoted_or_implicitly_decided(self):
        with self.assertRaises(ValueError):
            Catalog(self.draft | {'status': 'approved'})
        for field in ('scope', 'secret', 'project', 'category'):
            decisions = copy.deepcopy(self.decisions)
            del decisions['resources'][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                approve_review(self.draft, decisions, self.org, lambda: self.snapshot,
                               lambda ident: self.raw, reviewer='owner')
        self.decisions['resources'] = []
        with self.assertRaises(ValueError):
            self.approve()

    def test_stale_draft_policy_and_payload_decisions_are_rejected(self):
        for field in ('review_revision', 'policy_revision', 'organization_revision'):
            original = self.decisions[field]
            self.decisions[field] = '0' * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.approve()
            self.decisions[field] = original
        self.decisions['resources'][0]['payload_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.approve()

    def test_categories_and_scopes_are_authoritative_not_folder_inferences(self):
        for changes in ({'category': 'category-0'}, {'category': 'category-99'},
                        {'scope': {'kind': 'organization', 'id': 'other'}},
                        {'scope': {'kind': 'project', 'id': 'example'}},
                        {'project': 'river-project'}, {'secret': 0}):
            original = copy.deepcopy(self.decisions['resources'][0])
            self.decisions['resources'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.approve()
            self.decisions['resources'][0] = original

    def test_project_scope_requires_exact_project_but_does_not_grant_access(self):
        self.decisions['resources'][0]['scope'] = {'kind': 'project', 'id': 'other-project'}
        with self.assertRaises(ValueError):
            self.approve()
        self.decisions['resources'][0]['project'] = 'other-project'
        bundle = self.approve()
        directory = HumanDirectory(self.org)
        recipient = directory.resolve(**context('102', 'administrator'), scope_id='example')
        row = reviewed_catalog(bundle, self.org)['resources'][0]
        self.assertFalse(directory.permits(recipient, row | {'organization': 'example'}))

    def test_changed_payload_or_excluded_source_cannot_receive_approval(self):
        for mutate in (lambda: self.snapshot['actors'][0].update(searchable=False),
                       lambda: self.snapshot['actors'][0]['knowledge'][0].update(searchable=False),
                       lambda: self.snapshot['actors'][0]['knowledge'][0].update(unavailable=True),
                       lambda: self.snapshot['actors'][0].update(org='other'),
                       lambda: self.snapshot['actors'][0].update(id='other'),
                       lambda: self.snapshot['actors'][0]['knowledge'][0].update(path='kb/other.md')):
            original = copy.deepcopy(self.snapshot)
            mutate()
            with self.assertRaises(ValueError):
                self.approve()
            self.snapshot = original
        self.raw += b' '
        with self.assertRaises(ValueError):
            self.approve()

    def test_source_removed_during_review_discards_batch(self):
        count = 0

        def snapshots():
            nonlocal count
            count += 1
            return self.snapshot if count == 1 else {'actors': []}

        with self.assertRaises(ValueError):
            approve_review(self.draft, self.decisions, self.org, snapshots,
                           lambda ident: self.raw, reviewer='owner')

    def test_duplicate_source_and_duplicate_decision_are_rejected(self):
        self.snapshot['actors'] *= 2
        with self.assertRaises(ValueError):
            self.approve()
        self.snapshot['actors'] = self.snapshot['actors'][:1]
        self.decisions['resources'] *= 2
        with self.assertRaises(ValueError):
            self.approve()

    def test_category_meaning_changes_invalidate_review_even_with_same_grants(self):
        bundle = self.approve()
        self.org['policies']['security_categories']['category-1']['description'] = 'Revised meaning'
        self.assertEqual(bundle['policy_revision'], Scope.from_org(self.org).revision)
        with self.assertRaises(ValueError):
            reviewed_catalog(bundle, self.org)

    def test_history_links_without_carrying_forward_unreviewed_notes(self):
        first = self.approve()
        second = self.approve(previous=first)
        self.assertEqual(second['previous_revision'], first['revision'])
        self.assertEqual(second['sequence'], 2)
        self.assertNotEqual(second['revision'], first['revision'])
        self.assertEqual(first['catalog'], second['catalog'])
        first['catalog']['resources'][0]['secret'] = True
        with self.assertRaises(ValueError):
            self.approve(previous=first)

    def test_source_identity_survives_content_updates_but_approval_does_not(self):
        first = self.approve()
        note = json.loads(self.raw)
        note.update(id='a' * 64, content='Revised organization procedures')
        self.raw = json.dumps(note).encode()
        self.draft['resources'][0].update(id=note['id'], payload_sha256=hashlib.sha256(self.raw).hexdigest())
        self.snapshot['actors'][0]['knowledge'][0]['id'] = note['id']
        with self.assertRaises(ValueError):
            self.approve(previous=first)
        self.decisions['review_revision'] = revision(self.draft)
        self.decisions['resources'][0].update(id=note['id'], payload_sha256=self.draft['resources'][0]['payload_sha256'])
        second = self.approve(previous=first)
        self.assertEqual(first['sources'][0]['source_key'], second['sources'][0]['source_key'])
        self.assertNotEqual(first['sources'][0]['payload_sha256'], second['sources'][0]['payload_sha256'])

    def test_private_storage_preserves_history_and_rejects_tampering_and_traversal(self):
        bundle = self.approve()
        with tempfile.TemporaryDirectory() as root:
            path = save_revision(root, bundle)
            self.assertEqual(load_revision(root, bundle['revision'], self.org), bundle)
            with self.assertRaises(FileExistsError):
                save_revision(root, bundle)
            with self.assertRaises(ValueError):
                load_revision(root, '../outside', self.org)
            changed = copy.deepcopy(bundle)
            changed['reviewer'] = 'different'
            path.write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_revision(root, bundle['revision'], self.org)
            with self.assertRaises(ValueError):
                save_revision(Path(root).name, bundle)

    def test_legacy_authority_requires_explicit_scope_migration(self):
        self.org['policies'].pop('phantomview')
        with self.assertRaises(ValueError):
            self.approve()

    def test_partial_batches_do_not_approve_omitted_candidates(self):
        second = self.row | {'id': 'b' * 64, 'path': 'kb/policies/pending.md', 'secret': None}
        self.draft['resources'].append(second)
        self.decisions['review_revision'] = revision(self.draft)
        bundle = self.approve()
        self.assertEqual([row['id'] for row in bundle['catalog']['resources']], [self.row['id']])

    def test_source_identity_cannot_be_reassigned_through_review_decisions(self):
        self.decisions['resources'][0]['actor'] = 'administrator'
        with self.assertRaises(ValueError):
            self.approve()

    def folder_review(self):
        return {key: value for key, value in self.decisions.items() if key != 'resources'} | {
            'rules': [{'actor': 'coordinator', 'folder': 'kb/policies', 'reviewed': True,
                       'category': 'category-1', 'project': None, 'secret': False,
                       'scope': {'kind': 'organization', 'id': 'example'}}]}

    def test_bulk_folder_review_matches_current_exact_folder_without_recursion(self):
        review = self.folder_review()
        self.assertEqual(decisions_from_folders(self.draft, self.org, review), self.decisions)
        second = self.row | {'id': 'b' * 64, 'path': 'kb/policies/nested/pending.md', 'secret': None}
        self.draft['resources'].append(second)
        with self.assertRaises(ValueError):
            decisions_from_folders(self.draft, self.org, review)
        review['review_revision'] = revision(self.draft)
        decisions = decisions_from_folders(self.draft, self.org, review)
        self.assertEqual(len(decisions['resources']), 1)

    def test_bulk_review_rejects_unknown_duplicate_unreviewed_and_traversal_folders(self):
        for change in ({'folder': 'kb/unknown'}, {'folder': 'kb/../private'}, {'reviewed': False},
                       {'folder': 'kb//policies'}):
            review = self.folder_review()
            review['rules'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                decisions_from_folders(self.draft, self.org, review)
        review = self.folder_review()
        review['rules'] *= 2
        with self.assertRaises(ValueError):
            decisions_from_folders(self.draft, self.org, review)

    def test_storage_rejects_revision_file_with_another_valid_revision(self):
        first = self.approve()
        second = self.approve(previous=first)
        with tempfile.TemporaryDirectory() as root:
            path = save_revision(root, first)
            path.write_text(json.dumps(second), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_revision(root, first['revision'], self.org)

    def test_reviewed_catalog_uses_existing_authorization_before_payload_reads(self):
        bundle = self.approve()
        bundle['catalog']['resources'][0]['secret'] = True
        bundle['revision'] = revision({key: value for key, value in bundle.items() if key != 'revision'})
        org = self.org

        class Gate:
            def identified_scope(self, headers):
                directory = HumanDirectory(org)
                return directory.resolve(**context('101', 'coordinator'), scope_id='example'), directory

        def denied_loader(ident):
            self.fail('An explicitly excluded payload must never be opened')

        result = retrieve(Gate(), {}, lambda: reviewed_catalog(bundle, org), denied_loader, 'procedures')
        self.assertEqual(result['notes'], [])


if __name__ == '__main__':
    unittest.main()
