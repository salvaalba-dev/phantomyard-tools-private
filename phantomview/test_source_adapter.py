"""Selected export adapters produce inert, source-bound drafts without ACL inference."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from channel_identity import HumanDirectory
from scoped_backend import ProjectionCatalog, ScopedBackend
from source_adapter import encode, prepare, write_draft
from test_scoped_backend import ProjectionFixture
from test_view_permissions import scoped_organization


def snapshot():
    return {
        'organizations': [{'id': 'example', 'name': 'Example Foundation', 'source': '/private/org.yaml'}],
        'departments': [{'org': 'example', 'id': 'board', 'key': 'example:departments:board', 'name': 'Board', 'searchable': True}],
        'roles': [{'org': 'example', 'id': 'executive', 'key': 'example:roles:executive', 'name': 'Executive', 'functions': ['Coordinate']}],
        'actors': [{'org': 'example', 'id': 'coordinator', 'key': 'example:actors:coordinator', 'tools': ['email'],
                    'searchable': True, 'knowledge': [{'id': 'a' * 64, 'title': 'Hidden KB title'}],
                    'channels': {'email': 'private@example.invalid'}, 'source': '/private/persona',
                    'diagnostics': {'title': 'Hidden diagnostics'}, 'token': 'NEVER_COPY'}],
        'documents': [{'org': 'example', 'urn': 'urn:example:handbook', 'slug': 'Member handbook',
                       'kind': 'handbook', 'category': 3, 'location': '/private/drive', 'owners': ['private-owner']}],
        'procedures': [{'org': 'example', 'id': 'membership', 'title': 'Membership workflow', 'origin': 'organization',
                        'steps': [{'actor': 'coordinator', 'action': 'Review the application', 'input': 'Application', 'output': 'Decision'}]}],
        'findings': [{'entity': 'example:actors:coordinator', 'severity': 'warning', 'title': 'Profile needs review', 'source': '/private/org.yaml'}],
        'edges': [{'from': 'example:roles:executive', 'to': 'example:actors:coordinator', 'type': 'assignment', 'label': 'Assigned persona'}],
        'sources': [{'path': '/private/source'}], 'history': [{'content': 'Private history'}],
        'installation': {'secret': 'Private setup'},
    }


class SourceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.org = scoped_organization()
        self.directory = HumanDirectory(self.org)
        self.source = snapshot()

    def prepare(self):
        return prepare(self.source, self.directory)

    def test_selected_sections_become_drafts_with_no_inferred_permissions(self):
        draft = self.prepare()
        self.assertEqual({row['kind'] for row in draft['resources']},
                         {'organization', 'department', 'role', 'persona', 'document', 'procedure', 'finding', 'relationship'})
        self.assertEqual(draft['status'], 'draft')
        self.assertIs(draft['activation_supported'], False)
        for row in draft['resources']:
            for field in ('category', 'scope', 'project', 'secret'):
                self.assertIsNone(row[field])
            self.assertEqual(len(row['provenance']['source_sha256']), 64)
        with self.assertRaises(ValueError):
            ProjectionCatalog(draft | {'status': 'approved'})

    def test_organization_links_are_opt_in_unclassified_and_bound_to_visible_endpoints(self):
        self.source['actors'][0]['role'] = 'executive'
        self.source['roles'][0]['department'] = 'board'
        self.source['humans'] = [{'org': 'example', 'id': 'owner', 'name': 'Owner'},
                                 {'org': 'example', 'id': 'unbound', 'name': 'Unbound'}]
        ordinary = self.prepare()
        self.assertNotIn('counterpart', {row['data'].get('type') for row in ordinary['records']})
        draft = prepare(self.source, self.directory, organization_links=True)
        links = [row for row in draft['records'] if row['kind'] == 'relationship']
        self.assertEqual(sum(row['data']['type'] == 'assignment' for row in links), 1)
        self.assertEqual({row['data']['type'] for row in links}, {'assignment', 'membership', 'counterpart'})
        ids = {row['id'] for row in draft['records']}
        for row in draft['resources']:
            if row['kind'] == 'relationship':
                self.assertTrue(set(row['endpoints']) <= ids)
                self.assertIsNone(row['category'])
        owner = next(row['id'] for row in draft['records'] if row['kind'] == 'human' and row['data']['id'] == 'owner')
        self.assertEqual([row['data']['source'] for row in links if row['data']['type'] == 'counterpart'], [owner])
        self.source['humans'][0]['searchable'] = False
        hidden = prepare(self.source, self.directory, organization_links=True)
        self.assertNotIn('counterpart', {row['data'].get('type') for row in hidden['records']})

    def test_payloads_omit_nested_kb_credentials_contacts_paths_diagnostics_and_totals(self):
        payloads = json.dumps(self.prepare()['records'])
        for value in ('Hidden KB title', 'private@example.invalid', 'NEVER_COPY', '/private/',
                      'Hidden diagnostics', 'private-owner', 'Private setup', 'Private history'):
            self.assertNotIn(value, payloads)

    def test_profile_metadata_requires_explicit_mode_and_fresh_unclassified_review(self):
        ordinary = self.prepare()
        enriched = prepare(self.source, self.directory, profile_fields=True)
        persona = next(row for row in enriched['records'] if row['kind'] == 'persona')
        self.assertEqual(persona['data']['contacts'], {'email': 'private@example.invalid'})
        self.assertNotIn('private@example.invalid', json.dumps(ordinary['records']))
        self.assertIs(enriched['profile_fields'], True)
        for row in enriched['resources']:
            self.assertIsNone(row['category'])
            self.assertIsNone(row['secret'])
        for forbidden in ('NEVER_COPY', 'Hidden KB title', '/private/', 'Private history'):
            self.assertNotIn(forbidden, json.dumps(enriched['records']))

    def test_profile_contacts_reject_unsafe_values_and_omit_human_login_identifiers(self):
        self.source['actors'][0]['channels'] = {'website': 'https://user:password@example.invalid',
            'email': 'person@example.invalid?bcc=other@example.invalid', 'npub': 'nsec1' + 'q' * 58,
            'telegram_bot': '../private', 'password': 'NEVER_COPY'}
        self.source['humans'] = [{'org': 'example', 'id': 'owner', 'name': 'Owner',
                                  'email': 'human@example.invalid', 'telegram_user_id': 123456}]
        enriched = prepare(self.source, self.directory, profile_fields=True)
        payloads = json.dumps(enriched['records'])
        for forbidden in ('user:password', 'bcc=', 'nsec1', '../private', 'NEVER_COPY', 'human@example.invalid', '123456'):
            self.assertNotIn(forbidden, payloads)

    def test_profile_legal_metadata_selects_institutional_fields_only(self):
        self.source['organizations'][0]['legal'] = {'legal_name': 'Example Foundation', 'nif': 'EXAMPLE',
            'founders': [{'name': 'Example Human', 'dni': 'NEVER_COPY'}],
            'governing_body': [{'nie': 'NEVER_COPY'}], 'address': {'street': 'Private address'}}
        enriched = prepare(self.source, self.directory, profile_fields=True)
        org = next(row for row in enriched['records'] if row['kind'] == 'organization')
        self.assertEqual(org['data']['legal']['nif'], 'EXAMPLE')
        self.assertNotIn('NEVER_COPY', json.dumps(enriched['records']))
        self.assertNotIn('Private address', json.dumps(enriched['records']))

    def test_profile_mode_recomputes_exactly_and_rejects_ambiguous_flags(self):
        from source_adapter import prepare_like
        draft = prepare(self.source, self.directory, organization_links=True, profile_fields=True)
        self.assertEqual(prepare_like(self.source, self.directory, draft), draft)
        self.assertEqual(prepare_like(self.source, self.directory, self.prepare()), self.prepare())
        with self.assertRaises(ValueError):
            prepare_like(self.source, self.directory, draft | {'profile_fields': False})
        with self.assertRaises(ValueError):
            prepare(self.source, self.directory, profile_fields=1)

    def test_source_identity_is_stable_and_revision_changes_when_source_changes(self):
        first = self.prepare()
        self.source['actors'][0]['tools'].append('drive')
        second = self.prepare()
        a = next(row for row in first['resources'] if row['kind'] == 'persona')
        b = next(row for row in second['resources'] if row['kind'] == 'persona')
        self.assertEqual(a['id'], b['id'])
        self.assertNotEqual(a['payload_sha256'], b['payload_sha256'])
        self.assertNotEqual(a['provenance']['source_sha256'], b['provenance']['source_sha256'])
        self.assertNotEqual(first['source_revision'], second['source_revision'])

    def test_organization_link_fingerprints_ignore_only_existing_observation_clocks(self):
        self.source['actors'][0]['role'] = 'executive'
        diagnostic = self.source['actors'][0]['diagnostics']
        diagnostic.update(checked_at='2026-10-19T10:00:00Z', checks=[{'age_minutes': 1, 'status': 'ok'}])
        first = prepare(self.source, self.directory, organization_links=True)
        diagnostic.update(checked_at='2026-10-19T10:01:00Z', checks=[{'age_minutes': 2, 'status': 'ok'}])
        self.assertEqual(first, prepare(self.source, self.directory, organization_links=True))
        diagnostic['checks'][0]['status'] = 'failed'
        self.assertNotEqual(first, prepare(self.source, self.directory, organization_links=True))

    def test_unrendered_source_changes_still_invalidate_review_fingerprints(self):
        first = self.prepare()
        self.source['actors'][0]['knowledge'][0]['title'] = 'Changed source metadata'
        second = self.prepare()
        a = next(row for row in first['resources'] if row['kind'] == 'persona')
        b = next(row for row in second['resources'] if row['kind'] == 'persona')
        self.assertEqual(a['payload_sha256'], b['payload_sha256'])
        self.assertNotEqual(a['provenance']['source_sha256'], b['provenance']['source_sha256'])

    def test_foreign_organization_data_is_never_adapted(self):
        self.source['actors'].append({'id': 'other', 'org': 'foreign', 'name': 'Foreign persona'})
        self.source['findings'].append({'org': 'foreign', 'entity': 'example:actors:coordinator', 'title': 'Foreign finding'})
        self.assertNotIn('Foreign', json.dumps(self.prepare()))

    def test_source_exclusion_omits_persona_and_derived_records(self):
        self.source['actors'][0]['searchable'] = False
        draft = self.prepare()
        self.assertNotIn('persona', {row['kind'] for row in draft['resources']})
        self.assertNotIn('finding', {row['kind'] for row in draft['resources']})
        self.assertNotIn('procedure', {row['kind'] for row in draft['resources']})
        self.assertNotIn('relationship', {row['kind'] for row in draft['resources']})

    def test_procedure_and_finding_dependencies_reference_selected_opaque_ids(self):
        draft = self.prepare()
        ids = {row['kind']: row['id'] for row in draft['resources']}
        finding = next(row for row in draft['resources'] if row['kind'] == 'finding')
        procedure = next(row for row in draft['resources'] if row['kind'] == 'procedure')
        self.assertEqual(finding['requires'], [ids['persona']])
        self.assertEqual(set(procedure['requires']), {ids['organization'], ids['persona']})

    def test_kb_derived_and_ambiguous_procedures_stay_out(self):
        self.source['procedures'][0].update(origin='knowledge', source_note='a' * 64)
        draft = self.prepare()
        self.assertNotIn('procedure', {row['kind'] for row in draft['resources']})
        self.assertIn({'collection': 'procedures', 'reason': 'reviewed-kb-adapter-required'}, draft['omitted'])

    def test_duplicate_or_foreign_composite_keys_fail_closed(self):
        original = copy.deepcopy(self.source)
        self.source['actors'] *= 2
        with self.assertRaises(ValueError):
            self.prepare()
        self.source = original
        self.source['actors'][0]['key'] = 'foreign:actors:coordinator'
        with self.assertRaises(ValueError):
            self.prepare()

    def test_explicit_document_provenance_is_required_for_derived_procedures(self):
        self.source['procedures'] = [{'org': 'example', 'id': 'handbook', 'title': 'Handbook', 'origin': 'documents', 'steps': []}]
        self.assertNotIn('procedure', {row['kind'] for row in self.prepare()['resources']})
        self.source['procedures'][0]['source_document'] = 'urn:example:handbook'
        draft = self.prepare()
        procedure = next(row for row in draft['resources'] if row['kind'] == 'procedure')
        document = next(row for row in draft['resources'] if row['kind'] == 'document')
        self.assertEqual(procedure['requires'], [document['id']])

    def test_private_output_is_exclusive_and_draft_has_no_mutable_source_aliases(self):
        draft = self.prepare()
        self.source['actors'][0]['tools'].append('changed')
        self.assertNotIn('changed', json.dumps(draft))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'review.json'
            write_draft(path, draft)
            self.assertEqual(json.loads(path.read_bytes()), draft)
            with self.assertRaises(FileExistsError):
                write_draft(path, draft)
            with self.assertRaises(ValueError):
                write_draft('relative.json', draft)


class DerivedResourceTests(ProjectionFixture):
    def test_denied_dependency_prevents_derived_payload_reads_and_counts(self):
        ident = self.add('Derived board finding', 'finding')
        self.catalog['resources'][-1]['requires'] = [self.hidden]
        view = self.backend.state(self.headers)
        self.assertNotIn(ident, self.loaded)
        self.assertNotIn('finding', view['counts'])
        self.assertNotIn('Derived board', json.dumps(view))

    def test_dependency_cycles_and_missing_sources_are_rejected(self):
        row = self.catalog['resources'][0]
        for required in ([row['id']], ['f' * 64]):
            row['requires'] = required
            with self.assertRaises(ValueError):
                ProjectionCatalog(self.catalog)

    def test_adapter_draft_can_only_reach_backend_after_explicit_operator_classification(self):
        draft = prepare(snapshot(), HumanDirectory(self.org))
        rows = []
        for candidate in draft['resources']:
            row = {key: value for key, value in candidate.items() if key != 'provenance'}
            row.update(category='category-1', scope={'kind': 'organization', 'id': 'example'}, project=None, secret=False)
            rows.append(row)
        self.catalog = {'schema_version': 1, 'organization': 'example', 'status': 'approved',
                        'authority_revision': draft['authority_revision'], 'resources': rows}
        raw = {record['id']: encode(record) for record in draft['records']}
        backend = ScopedBackend(self.gate, lambda: self.catalog, raw.get)
        view = backend.state(self.headers)
        self.assertEqual(view['counts']['procedure'], 1)
        self.assertEqual(view['counts']['finding'], 1)
        persona = next(row for row in rows if row['kind'] == 'persona')
        persona['secret'] = True
        view = backend.state(self.headers)
        self.assertNotIn('procedure', view['counts'])
        self.assertNotIn('finding', view['counts'])


if __name__ == '__main__':
    unittest.main()
