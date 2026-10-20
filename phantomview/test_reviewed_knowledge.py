"""Full-note reads reuse approved scope, current provenance and session revocation."""
import copy
import json
import unittest

from assistant_scope import Scope
from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from resource_review import approve_review, revision
from reviewed_knowledge import ReviewedKnowledge
from scoped_knowledge import digest
from test_access_gate import ACCESS
from test_channel_identity import context
from test_scoped_knowledge import note_fixture
from test_view_permissions import scoped_organization


def knowledge_fixture(org):
    raw, catalog = note_fixture()
    note = json.loads(raw)
    note.update(path='kb/policies/handbook.md', content='Reviewed field procedures.',
                private_source='/private/source', token='DO_NOT_DISCLOSE')
    raw = json.dumps(note).encode()
    row = catalog['resources'][0] | {'path': note['path'], 'payload_sha256': digest(raw)}
    draft = catalog | {'status': 'draft', 'resources': [row | {'secret': None}]}
    snapshot = {'actors': [{'org': 'example', 'id': 'coordinator', 'searchable': True,
                            'knowledge': [{'id': row['id'], 'path': row['path'], 'searchable': True}]}]}
    decisions = {'schema_version': 1, 'review_revision': revision(draft),
                 'organization_revision': revision(org), 'policy_revision': Scope.from_org(org).revision,
                 'resources': [{key: row[key] for key in (
                     'id', 'payload_sha256', 'category', 'project', 'secret')} | {
                         'scope': {'kind': 'organization', 'id': 'example'}}]}
    bundle = approve_review(draft, decisions, org, lambda: snapshot, lambda ident: raw, reviewer='owner')
    return {'raw': raw, 'snapshot': snapshot, 'bundle': bundle, 'id': row['id']}


class ReviewedKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.org = scoped_organization()
        self.login()
        self.source = knowledge_fixture(self.org)
        self.loaded = []
        self.reader = ReviewedKnowledge(self.gate, lambda: self.source['bundle'], lambda: self.org,
                                       lambda: self.source['snapshot'], self.load)

    def login(self, sender='102', persona='administrator', scope='example'):
        self.gate = IdentifiedGate(ACCESS, {'identities': ['a' * 64], 'actor': persona},
                                  'https://view.example', 8789,
                                  directory_loader=lambda: HumanDirectory(self.org))
        if hasattr(self, 'reader'):
            self.reader.gate = self.gate
        link = self.gate.issue_identified('Nostr test-signed-event', self.gate.origin,
                                          **context(sender, persona), scope_id=scope)
        cookie = self.gate.redeem(link.split('#c=')[1])
        self.headers = {'Cookie': 'phantomview=' + cookie}

    def load(self, ident):
        self.loaded.append(ident)
        return self.source['raw']

    def read(self, ident=None):
        return self.reader.detail(self.headers, ident or self.source['id'])

    def classify(self, **changes):
        # Synthetic operator-owned review; production input comes from approve_review.
        bundle = self.source['bundle']
        bundle['catalog']['resources'][0].update(changes)
        bundle['revision'] = revision({key: value for key, value in bundle.items() if key != 'revision'})

    def test_complete_allowed_note_omits_paths_credentials_and_unselected_payload_fields(self):
        result = self.read()
        self.assertEqual(result['content'], 'Reviewed field procedures.')
        self.assertEqual(result['trust'], 'untrusted')
        self.assertEqual(result['format'], 'markdown')
        self.assertIs(result['excerpt_only'], False)
        self.assertEqual(result['scope'], {'kind': 'organization', 'id': 'example'})
        for value in ('/private/', 'DO_NOT_DISCLOSE', 'handbook.md'):
            self.assertNotIn(value, json.dumps(result))
        self.assertEqual(self.loaded, [self.source['id']] * 2)

    def test_denied_and_unknown_notes_are_indistinguishable_and_never_opened(self):
        self.classify(category='category-3')
        for ident in (self.source['id'], 'f' * 64, '../private', 'A' * 64):
            self.assertIsNone(self.read(ident))
        self.assertEqual(self.loaded, [])

    def test_project_scope_never_expands_an_existing_project_session(self):
        self.classify(scope={'kind': 'project', 'id': 'other-project'}, project='other-project')
        self.login(scope='river-project')
        self.assertIsNone(self.read())
        self.assertEqual(self.loaded, [])

    def test_absolute_owner_still_uses_reviewed_current_information_and_secret_exclusion(self):
        self.classify(category='category-3')
        self.login('101', 'coordinator')
        self.assertIsNotNone(self.read())
        self.classify(secret=True)
        self.loaded.clear()
        self.assertIsNone(self.read())
        self.assertEqual(self.loaded, [])

    def test_changed_payload_is_unavailable_without_exposing_its_new_title(self):
        note = json.loads(self.source['raw'])
        note['title'] = 'Unreviewed title'
        self.source['raw'] = json.dumps(note).encode()
        self.assertIsNone(self.read())

    def test_excluded_or_ambiguous_sources_do_not_open_body(self):
        original = copy.deepcopy(self.source['snapshot'])
        for mutate in (lambda actor: actor.update(searchable=False),
                       lambda actor: actor['knowledge'][0].update(unavailable=True),
                       lambda actor: actor['knowledge'].append(copy.deepcopy(actor['knowledge'][0]))):
            self.source['snapshot'] = copy.deepcopy(original)
            mutate(self.source['snapshot']['actors'][0])
            with self.subTest(mutate=mutate):
                self.assertIsNone(self.read())
        self.assertEqual(self.loaded, [])

    def test_source_removed_during_read_discards_complete_response(self):
        def load(ident):
            self.source['snapshot'] = {'actors': []}
            return self.source['raw']
        self.reader.note_loader = load
        self.assertIsNone(self.read())

    def test_logout_during_read_discards_complete_response(self):
        def load(ident):
            self.gate.sessions.clear()
            return self.source['raw']
        self.reader.note_loader = load
        with self.assertRaises((ValueError, self.gate.access.core.Invalid)):
            self.read()

    def test_authority_change_during_read_discards_complete_response(self):
        def load(ident):
            self.org['organization']['name'] = 'Changed authority source'
            return self.source['raw']
        self.reader.note_loader = load
        with self.assertRaises(ValueError):
            self.read()

    def test_review_change_during_read_discards_complete_response(self):
        def load(ident):
            self.classify(category='category-3')
            return self.source['raw']
        self.reader.note_loader = load
        with self.assertRaises(ValueError):
            self.read()

    def test_different_source_authority_is_rejected_before_note_read(self):
        other = copy.deepcopy(self.org)
        other['humans'][1]['telegram_user_id'] = 199
        self.reader.organization_loader = lambda: other
        with self.assertRaises(ValueError):
            self.read()
        self.assertEqual(self.loaded, [])

    def test_stale_or_forged_review_cannot_be_promoted(self):
        self.source['bundle']['catalog']['resources'][0]['category'] = 'category-3'
        with self.assertRaises(ValueError):
            self.read()
        self.assertEqual(self.loaded, [])

    def test_identified_session_is_required_before_private_review_read(self):
        self.headers = {'Cookie': 'phantomview=invalid'}
        def forbidden():
            self.fail('Private review must not be read without an identified session')
        self.reader.review_loader = forbidden
        with self.assertRaises((ValueError, self.gate.access.core.Invalid)):
            self.read()
        self.assertEqual(self.loaded, [])

    def test_result_is_detached_from_authority_and_payload(self):
        result = self.read()
        result['scope']['id'] = 'other-project'
        self.assertEqual(self.read()['scope']['id'], 'example')

    def test_snapshot_revoked_after_second_body_read_rejects_complete_result(self):
        count = 0
        def changing(ident):
            nonlocal count
            count += 1
            if count == 2:
                # Mutate the same object after _current has inspected its metadata.
                self.source['snapshot']['actors'][0]['searchable'] = False
            return self.load(ident)
        self.reader.note_loader = changing
        with self.assertRaisesRegex(ValueError, 'snapshot changed'):
            self.read()
        self.assertEqual(count, 2)
