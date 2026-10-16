"""Authorization must precede KB reads and model evidence construction."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from channel_identity import HumanDirectory
from scoped_knowledge import Catalog, PrivateKBStore, prepare_review, retrieve
from test_channel_identity import context, organization


class FakeGate:
    def __init__(self, org, sender='102', persona='administrator'):
        self.org, self.sender, self.persona = org, sender, persona
        self.calls = 0
        self.on_recheck = lambda: None

    def identified_scope(self, headers):
        self.calls += 1
        if self.calls > 1:
            self.on_recheck()
        directory = HumanDirectory(self.org)
        return directory.resolve(**context(self.sender, self.persona)), directory


def note_fixture(category='category-1', **changes):
    note = {'id': hashlib.sha256(b'example-note').hexdigest(), 'actor': 'example:actors:coordinator',
            'path': 'kb/normas/example.md', 'title': 'Organization procedures',
            'content': 'ALMAPONIA: reviewed field observations.', 'truncated': False}
    raw = json.dumps(note).encode()
    row = {'id': note['id'], 'actor': 'coordinator', 'path': note['path'],
           'category': category, 'project': None, 'secret': False,
           'payload_sha256': hashlib.sha256(raw).hexdigest()} | changes
    catalog = {'schema_version': 1, 'organization': 'example', 'status': 'approved', 'resources': [row]}
    return raw, catalog


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.org = organization()
        self.org['policies']['security_categories']['category-3'] = {}
        self.gate = FakeGate(self.org)
        self.raw, self.catalog = note_fixture()
        self.loaded = []

    def load(self, ident):
        self.loaded.append(ident)
        return self.raw

    def retrieve(self, query='almaponía'):
        return retrieve(self.gate, {}, lambda: self.catalog, self.load, query)

    def test_allowed_evidence_is_bounded_untrusted_and_source_bound(self):
        result = self.retrieve()
        self.assertEqual(len(result['notes']), 1)
        self.assertEqual(self.gate.calls, 2)
        self.assertEqual(result['notes'][0]['trust'], 'untrusted')
        self.assertTrue(result['notes'][0]['excerpt_only'])
        self.assertFalse(result['complete_corpus'])

    def test_denied_note_is_never_opened_or_exposed(self):
        self.catalog['resources'][0]['category'] = 'category-3'
        self.assertEqual(self.retrieve()['notes'], [])
        self.assertEqual(self.loaded, [])

    def test_unclassified_folder_draft_cannot_be_used_as_approved_catalog(self):
        self.catalog['status'] = 'draft'
        with self.assertRaises(ValueError):
            self.retrieve()
        self.assertEqual(self.loaded, [])

    def test_absolute_human_can_read_declared_category_but_not_secret(self):
        self.gate = FakeGate(self.org, '101', 'coordinator')
        self.catalog['resources'][0]['category'] = 'category-3'
        self.assertEqual(len(self.retrieve()['notes']), 1)
        self.catalog['resources'][0]['secret'] = True
        self.loaded.clear()
        self.assertEqual(self.retrieve()['notes'], [])
        self.assertEqual(self.loaded, [])

    def test_project_requires_exact_grant_even_with_category_permission(self):
        self.catalog['resources'][0].update(category='category-4-project', project='project')
        self.org['actors'][1]['actor_exceptions'] = ['category-4-project']
        self.assertEqual(self.retrieve()['notes'], [])
        self.assertEqual(self.loaded, [])
        self.org['policies']['phantomview'] = {'project_grants': {'administrator': ['project']}}
        self.assertEqual(len(self.retrieve()['notes']), 1)

    def test_changed_body_title_or_metadata_needs_review(self):
        for field, value in (('content', 'almaponia: changed'), ('title', 'Changed title'),
                             ('actor', 'other'), ('path', 'kb/other.md'), ('truncated', True)):
            with self.subTest(field=field):
                note = json.loads(self.raw)
                note[field] = value
                self.raw = json.dumps(note).encode()
                self.assertEqual(self.retrieve()['notes'], [])

    def test_rehashed_payload_still_requires_matching_resource_identity(self):
        for field, value in (('actor', 'other'), ('id', 'b' * 64), ('path', 'kb/other.md'), ('truncated', True)):
            with self.subTest(field=field):
                raw, self.catalog = note_fixture()
                note = json.loads(raw)
                note[field] = value
                self.raw = json.dumps(note).encode()
                self.catalog['resources'][0]['payload_sha256'] = hashlib.sha256(self.raw).hexdigest()
                self.assertEqual(self.retrieve()['notes'], [])

    def test_session_expiry_during_retrieval_discards_evidence(self):
        def expire():
            raise ValueError('Session expired')
        self.gate.on_recheck = expire
        with self.assertRaises(ValueError):
            self.retrieve()

    def test_policy_or_catalog_changes_discard_evidence(self):
        self.gate.on_recheck = lambda: self.org['humans'][1].update(telegram_user_id=999)
        with self.assertRaises(ValueError):
            self.retrieve()
        self.org = organization()
        self.gate = FakeGate(self.org)
        self.gate.on_recheck = lambda: self.catalog['resources'][0].update(secret=True)
        with self.assertRaises(ValueError):
            self.retrieve()

    def test_foreign_org_and_undeclared_categories_do_not_read_notes(self):
        self.catalog['organization'] = 'foreign'
        with self.assertRaises(ValueError):
            self.retrieve()
        self.catalog['organization'] = 'example'
        self.catalog['resources'][0]['category'] = 'category-9'
        self.assertEqual(self.retrieve()['notes'], [])
        self.assertEqual(self.loaded, [])

    def test_catalog_rejects_category_zero_duplicates_and_traversal(self):
        for field, value in (('category', 'category-0'), ('path', 'kb/../private.md'), ('secret', 0)):
            changed = copy.deepcopy(self.catalog)
            changed['resources'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                Catalog(changed)
        self.catalog['resources'] *= 2
        with self.assertRaises(ValueError):
            Catalog(self.catalog)

    def test_catalog_does_not_expose_mutable_classifications(self):
        catalog = Catalog(self.catalog)
        catalog.resources()['resources'][0]['secret'] = True
        self.assertFalse(catalog.resources()['resources'][0]['secret'])

    def test_collector_exclusions_and_removed_notes_survive_cached_payloads(self):
        with tempfile.TemporaryDirectory() as folder:
            ident = self.catalog['resources'][0]['id']
            (Path(folder) / (ident + '.json')).write_bytes(self.raw)
            snapshot = {'actors': [{'org': 'example', 'searchable': True,
                                    'knowledge': [{'id': ident, 'searchable': True}]}]}
            store = PrivateKBStore(folder, lambda: snapshot, 'example')
            self.assertEqual(store(ident), self.raw)
            snapshot['actors'][0]['knowledge'][0]['searchable'] = False
            self.assertIsNone(store(ident))
            snapshot['actors'][0]['knowledge'][0]['searchable'] = True
            snapshot['actors'][0]['searchable'] = False
            self.assertIsNone(store(ident))
            snapshot['actors'] = []
            self.assertIsNone(store(ident))

    def test_private_store_rejects_opaque_id_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PrivateKBStore(folder, lambda: {'actors': []}, 'example')
            with self.assertRaises(ValueError):
                store('../catalog')

    def test_selected_note_removed_before_return_discards_evidence(self):
        values = iter([self.raw, None])
        with self.assertRaises(ValueError):
            retrieve(self.gate, {}, lambda: self.catalog, lambda ident: next(values), 'almaponia')

    def test_fingerprint_preparation_cannot_approve_unreviewed_content(self):
        row = self.catalog['resources'][0]
        proposal = {'organization': 'example', 'status': 'draft', 'activation_supported': False,
                    'categories': {'category-1': {}}, 'rules': [
                        {'actor': row['actor'], 'folder': 'kb/normas', 'recursive': False,
                         'approved': False, 'suggested_category': 'category-1'}]}
        snapshot = {'actors': [{'org': 'example', 'id': row['actor'], 'searchable': True,
                                'knowledge': [{'id': row['id'], 'path': row['path'], 'searchable': True}]}]}
        draft = prepare_review(proposal, snapshot, self.load)
        self.assertEqual(len(draft['resources']), 1)
        self.assertEqual(draft['resources'][0]['payload_sha256'], row['payload_sha256'])
        self.assertIsNone(draft['resources'][0]['secret'])
        with self.assertRaises(ValueError):
            Catalog(draft)
        with self.assertRaises(ValueError):
            Catalog(draft | {'status': 'approved'})
        snapshot['actors'][0]['knowledge'][0]['searchable'] = False
        self.assertEqual(prepare_review(proposal, snapshot, self.load)['resources'], [])


if __name__ == '__main__':
    unittest.main()
