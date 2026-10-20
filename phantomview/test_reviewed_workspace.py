"""Authorized KB discovery, global search and viewer projection share one gate."""
import copy
import json
from unittest.mock import patch

from resource_review import revision, source_key
from reviewed_knowledge import ReviewedKnowledge
from scoped_backend import ScopedBackend
from scoped_knowledge import digest
from test_reviewed_knowledge import knowledge_fixture
from test_scoped_backend import ProjectionFixture


class ReviewedWorkspaceTests(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.source = knowledge_fixture(self.org)
        self.notes = {self.source['id']: self.source['raw']}
        self.note_reads = []
        self.reader = ReviewedKnowledge(self.gate, lambda: self.source['bundle'], lambda: self.org,
                                       lambda: self.source['snapshot'], self.read_note)
        self.backend = ScopedBackend(self.gate, lambda: self.catalog, self.load, reviewed_knowledge=self.reader)

    def read_note(self, ident):
        self.note_reads.append(ident)
        return self.notes.get(ident)

    def revise(self):
        bundle = self.source['bundle']
        rows = bundle['catalog']['resources']
        bundle['sources'] = [{'source_key': source_key('example', row['actor'], row['path']),
                              'id': row['id'], 'payload_sha256': row['payload_sha256']} for row in rows]
        bundle['revision'] = revision({key: value for key, value in bundle.items() if key != 'revision'})

    def add_note(self, title, *, category='category-1', scope='example', ident=None):
        ident = ident or digest(title.encode())
        original = self.source['bundle']['catalog']['resources'][0]
        note = json.loads(self.source['raw'])
        note.update(id=ident, title=title, path='kb/policies/' + ident + '.md')
        raw = json.dumps(note).encode()
        scope_kind = self.org['policies']['phantomview']['scope_definitions'][scope]['kind']
        row = original | {'id': ident, 'path': note['path'], 'category': category,
                          'scope': {'kind': scope_kind, 'id': scope},
                          'project': scope if scope_kind == 'project' else None, 'payload_sha256': digest(raw)}
        self.notes[ident] = raw
        self.source['bundle']['catalog']['resources'].append(row)
        self.source['snapshot']['actors'][0]['knowledge'].append({'id': ident, 'path': note['path'], 'searchable': True})
        self.revise()
        return ident

    def test_current_allowed_titles_create_knowledge_menu_without_body_or_path_disclosure(self):
        view = self.backend.workspace(self.headers)
        self.assertEqual(view['counts']['knowledge'], 1)
        self.assertIn('knowledge', {row['kind'] for row in view['navigation']['core']})
        row = next(row for row in view['resources'] if row['kind'] == 'knowledge')
        self.assertEqual(row['id'], self.source['id'])
        self.assertEqual(row['data']['title'], 'Organization procedures')
        self.assertEqual(row['data']['source'], 'reviewed-knowledge')
        for value in ('Reviewed field procedures.', 'handbook.md', 'DO_NOT_DISCLOSE', 'review_revision'):
            self.assertNotIn(value, json.dumps(view))

    def test_denied_note_never_affects_counts_menu_revision_search_or_loader(self):
        before = self.backend.workspace(self.headers)
        hidden = self.add_note('Undisclosed board title', category='category-3')
        after = self.backend.workspace(self.headers)
        self.assertEqual(before, after)
        self.assertEqual(self.backend.search(self.headers, 'undisclosed')['results'], [])
        self.assertNotIn(hidden, self.note_reads)

    def test_global_search_matches_body_with_case_and_accent_normalization(self):
        result = self.backend.search(self.headers, 'FÍELD PROCEDURES')
        self.assertEqual([row['id'] for row in result['results']], [self.source['id']])
        self.assertNotIn('content', result['results'][0]['data'])
        self.assertEqual(self.backend.search(self.headers, 'absent')['results'], [])
        self.assertEqual(self.backend.search(self.headers, 'organization')['results'][0]['id'], self.source['id'])

    def test_search_merges_title_and_body_matches_without_duplicates(self):
        self.assertEqual(len(self.backend.search(self.headers, 'procedures')['results']), 1)

    def test_project_grant_is_enforced_before_note_read(self):
        denied = self.add_note('Other project instructions', scope='other-project')
        self.backend.workspace(self.headers)
        self.assertEqual(self.backend.search(self.headers, 'other project instructions')['results'], [])
        self.assertNotIn(denied, self.note_reads)

    def test_removed_or_changed_note_disappears_from_menu_count_search_and_detail(self):
        self.notes[self.source['id']] += b' '
        view = self.backend.workspace(self.headers)
        self.assertNotIn('knowledge', view['counts'])
        self.assertNotIn('knowledge', {row['kind'] for row in view['navigation']['core']})
        self.assertIsNone(self.backend.detail(self.headers, self.source['id']))
        self.assertEqual(self.backend.search(self.headers, 'procedures')['results'], [])

    def test_source_excluded_during_later_note_read_discards_complete_listing(self):
        extra = self.add_note('Additional procedures')
        original = self.reader.note_loader
        count = 0
        def changing(ident):
            nonlocal count
            count += 1
            if count == 2:
                self.source['snapshot']['actors'][0]['knowledge'][0]['searchable'] = False
            return original(ident)
        self.reader.note_loader = changing
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)
        self.assertIn(extra, self.note_reads)

    def test_scan_limit_rejects_whole_response_instead_of_partial_counts(self):
        with patch('reviewed_knowledge.MAX_SCAN_BYTES', 1), self.assertRaises(ValueError):
            self.backend.workspace(self.headers)

    def test_opaque_id_collision_cannot_replace_an_existing_resource(self):
        self.add_note('Colliding identity', ident=self.public)
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)

    def test_gate_rebinding_is_rejected_without_opening_knowledge(self):
        self.reader.gate = object()
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)
        self.assertEqual(self.note_reads, [])

    def test_mutation_during_search_discards_body_matches(self):
        original = self.reader.records
        def changing(headers, query=None):
            result = original(headers, query)
            if query:
                self.notes[self.source['id']] += b' '
            return result
        self.reader.records = changing
        with self.assertRaises(ValueError):
            self.backend.search(self.headers, 'field')

    def test_source_scope_change_requires_a_fresh_current_view(self):
        before = copy.deepcopy(self.source['bundle'])
        self.source['bundle']['catalog']['resources'][0].update(
            scope={'kind': 'project', 'id': 'other-project'}, project='other-project')
        self.revise()
        self.assertNotEqual(before, self.source['bundle'])
        self.assertNotIn('knowledge', self.backend.state(self.headers)['counts'])
        self.assertEqual(self.note_reads, [])

    def test_corpus_above_eight_mib_fits_independent_verification_budget(self):
        for index in range(36):
            ident = self.add_note('Large approved note ' + str(index))
            note = json.loads(self.notes[ident])
            note['content'] = 'x' * (240 * 1024)
            raw = json.dumps(note).encode()
            self.notes[ident] = raw
            row = next(row for row in self.source['bundle']['catalog']['resources'] if row['id'] == ident)
            row['payload_sha256'] = digest(raw)
        self.revise()
        total = sum(map(len, self.notes.values()))
        self.assertGreater(total, 8 * 1024 * 1024)
        self.assertLess(total, 16 * 1024 * 1024)
        self.assertEqual(self.backend.state(self.headers)['counts']['knowledge'], 37)
        self.assertEqual(len(self.note_reads), 74)

    def test_verification_pass_remains_bounded_independently(self):
        calls = 0
        def growing(ident):
            nonlocal calls
            calls += 1
            return self.source['raw'] if calls == 1 else b'x' * 1024
        self.reader.note_loader = growing
        with patch('reviewed_knowledge.MAX_SCAN_BYTES', len(self.source['raw'])), self.assertRaises(ValueError):
            self.backend.state(self.headers)
        self.assertEqual(calls, 2)
