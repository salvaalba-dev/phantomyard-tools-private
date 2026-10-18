"""Denied records and graph endpoints cannot influence the returned projection."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from scoped_backend import PrivateRecordStore, ProjectionCatalog, ScopedBackend
from test_access_gate import ACCESS
from test_channel_identity import context
from test_view_permissions import scoped_organization


class ProjectionFixture(unittest.TestCase):
    def setUp(self):
        self.org = scoped_organization()
        self.gate = IdentifiedGate(ACCESS, {'identities': ['a' * 64], 'actor': 'administrator'},
                                  'https://view.example', 8789,
                                  directory_loader=lambda: HumanDirectory(self.org))
        link = self.gate.issue_identified('Nostr test-signed-event', self.gate.origin,
                                          **context('102', 'administrator'), scope_id='example')
        self.cookie = self.gate.redeem(link.split('#c=')[1])
        self.headers = {'Cookie': 'phantomview=' + self.cookie}
        self.catalog = {'schema_version': 1, 'organization': 'example', 'status': 'approved', 'resources': []}
        self.catalog['authority_revision'] = HumanDirectory(self.org).authority_revision
        self.payloads, self.loaded = {}, []
        self.public = self.add('Public profile', 'persona')
        self.hidden = self.add('Private board detail', 'document', category='category-3')
        self.project = self.add('River partner', 'partner', scope='river-project')
        self.other = self.add('Other partner', 'partner', scope='other-project')
        self.edge = self.add_edge('Visible assignment', self.public, self.project)
        self.hidden_edge = self.add_edge('Hidden assignment', self.public, self.hidden)
        self.backend = ScopedBackend(self.gate, lambda: self.catalog, self.load)

    def add(self, title, kind, category='category-1', scope='example', secret=False):
        ident = hashlib.sha256(title.encode()).hexdigest()
        record = {'id': ident, 'kind': kind, 'data': {'title': title}}
        raw = json.dumps(record).encode()
        self.payloads[ident] = raw
        scope_kind = self.org['policies']['phantomview']['scope_definitions'][scope]['kind']
        self.catalog['resources'].append({'id': ident, 'kind': kind, 'category': category,
                                          'scope': {'kind': scope_kind, 'id': scope},
                                          'project': scope if scope_kind == 'project' else None,
                                          'secret': secret, 'payload_sha256': hashlib.sha256(raw).hexdigest()})
        return ident

    def add_edge(self, title, source, target):
        ident = self.add(title, 'relationship')
        self.catalog['resources'][-1]['endpoints'] = [source, target]
        self.replace(ident, {'source': source, 'target': target, 'type': 'assignment', 'label': title})
        return ident

    def replace(self, ident, data):
        record = json.loads(self.payloads[ident])
        record['data'] = data
        self.payloads[ident] = json.dumps(record).encode()
        next(row for row in self.catalog['resources'] if row['id'] == ident)['payload_sha256'] = hashlib.sha256(self.payloads[ident]).hexdigest()

    def load(self, ident):
        self.loaded.append(ident)
        return self.payloads.get(ident)


class ScopedBackendTests(ProjectionFixture):
    def test_human_category_limit_filters_search_counts_details_and_incident_edges(self):
        self.org['policies']['phantomview']['human_category_limits'] = {'secretary': ['category-3']}
        self.org['actors'][1]['actor_exceptions'] = ['category-3']
        directory = HumanDirectory(self.org)
        self.gate.recipients[self.gate.digest(self.cookie)] = directory.resolve(
            **context('102', 'administrator'), scope_id='example')
        self.catalog['authority_revision'] = directory.authority_revision
        view = self.backend.state(self.headers)
        self.assertEqual([row['id'] for row in view['resources']], [self.hidden])
        self.assertEqual(view['relations'], [])
        self.assertEqual(view['counts'], {'document': 1, 'relationship': 0})
        self.assertEqual(self.backend.search(self.headers, 'River')['results'], [])
        self.assertIsNone(self.backend.detail(self.headers, self.public))
        self.assertNotIn(self.public, self.loaded)

    def test_workspace_menus_use_filtered_records_and_bind_issuer_without_observation(self):
        view = self.backend.workspace(self.headers)
        navigation = view.pop('navigation')
        self.assertEqual(view, self.backend.state(self.headers))
        self.assertEqual({row['kind'] for row in navigation['core']}, {'persona', 'partner'})
        self.assertTrue(navigation['assistant']['eligible'])
        self.assertEqual(navigation['assistant']['source'], 'session-issuer')
        self.assertNotIn(self.hidden, json.dumps(navigation))

    def test_workspace_installed_module_is_scope_bound_and_refreshes_visible_counts(self):
        from test_viewer_modules import projects
        module = projects()
        module['scope_kinds'] = ['organization']
        report = {'default_persona': {'resolved': 'administrator', 'exists': True,
                                     'served': True, 'provenance': 'config'}}
        backend = ScopedBackend(self.gate, lambda: self.catalog, self.load,
                                modules=[module], default_report_loader=lambda: report)
        view = backend.workspace(self.headers)
        self.assertTrue(view['navigation']['assistant']['eligible'])
        self.assertEqual(view['navigation']['modules'][0]['sections'][0]['count'], 1)
        self.payloads.pop(self.project)
        self.assertEqual(backend.workspace(self.headers)['navigation']['modules'], [])

    def test_workspace_rechecks_identity_after_runtime_default_read(self):
        def changed():
            self.gate.recipients.clear()
            return {}
        backend = ScopedBackend(self.gate, lambda: self.catalog, self.load, default_report_loader=changed)
        with self.assertRaises(ValueError):
            backend.workspace(self.headers)

    def test_runtime_observation_failure_does_not_hide_authorized_records(self):
        def unavailable():
            raise OSError('Runtime unavailable')
        backend = ScopedBackend(self.gate, lambda: self.catalog, self.load, default_report_loader=unavailable)
        view = backend.workspace(self.headers)
        self.assertTrue(view['resources'])
        self.assertTrue(view['navigation']['assistant']['eligible'])
        self.assertEqual(view['navigation']['assistant']['persona'], 'administrator')

    def test_state_authorizes_before_reads_and_counts_only_visible_nodes(self):
        view = self.backend.state(self.headers)
        self.assertEqual(view['counts'], {'persona': 1, 'partner': 1, 'relationship': 1})
        self.assertEqual({row['id'] for row in view['resources']}, {self.public, self.project})
        self.assertEqual({row['id'] for row in view['relations']}, {self.edge})
        self.assertTrue(set(self.loaded) <= {self.public, self.project, self.edge})
        self.assertNotIn('Private board detail', json.dumps(view))
        self.assertNotIn(self.hidden, json.dumps(view))
        self.assertFalse(view['complete_corpus'])

    def test_denied_additions_do_not_change_visible_revision_counts_or_results(self):
        before = self.backend.state(self.headers)
        self.add('Undisclosed finding', 'finding', category='category-3')
        self.assertEqual(self.backend.state(self.headers), before)
        self.assertEqual(self.backend.search(self.headers, 'Undisclosed')['results'], [])

    def test_no_snapshot_configuration_history_or_global_source_metadata_is_returned(self):
        self.assertEqual(set(self.backend.state(self.headers)), {
            'schema_version', 'organization', 'scope_id', 'policy_revision', 'view_revision',
            'resources', 'relations', 'counts', 'complete_corpus'})

    def test_source_change_hides_node_and_incident_edges_before_loading_edges(self):
        self.payloads[self.project] += b' '
        view = self.backend.state(self.headers)
        self.assertEqual(view['relations'], [])
        self.assertNotIn(self.edge, self.loaded)
        self.assertEqual(view['counts'], {'persona': 1, 'relationship': 0})

    def test_missing_source_hides_incident_edges_and_unknown_details(self):
        self.payloads.pop(self.project)
        self.assertIsNone(self.backend.detail(self.headers, self.project))
        self.assertIsNone(self.backend.detail(self.headers, self.hidden))
        self.assertIsNone(self.backend.detail(self.headers, 'f' * 64))
        self.assertNotIn(self.hidden, self.loaded)

    def test_resource_scope_and_category_cannot_be_granted_by_payload_claims(self):
        self.replace(self.hidden, {'title': 'Private board detail', 'category': 'category-1',
                                   'scope': 'example', 'human': 'owner'})
        self.assertIsNone(self.backend.detail(self.headers, self.hidden))
        self.assertNotIn(self.hidden, self.loaded)

    def test_explicit_secret_exclusions_apply_to_absolute_human(self):
        directory = HumanDirectory(self.org)
        self.gate.recipients[self.gate.digest(self.cookie)] = directory.resolve(
            **context('101', 'administrator'), scope_id='example')
        row = next(row for row in self.catalog['resources'] if row['id'] == self.hidden)
        row['secret'] = True
        self.assertIsNone(self.backend.detail(self.headers, self.hidden))
        self.assertNotIn(self.hidden, self.loaded)

    def test_project_session_cannot_expand_to_organization_or_other_project(self):
        directory = HumanDirectory(self.org)
        self.gate.recipients[self.gate.digest(self.cookie)] = directory.resolve(
            **context('102', 'administrator'), scope_id='river-project')
        view = self.backend.state(self.headers)
        self.assertEqual([row['id'] for row in view['resources']], [self.project])
        self.assertEqual(view['relations'], [])
        self.assertEqual(set(self.loaded), {self.project})

    def test_unidentified_expired_or_logged_out_sessions_never_load_data(self):
        self.gate.recipients.clear()
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)
        self.assertEqual(self.loaded, [])
        self.gate.logout(self.headers)
        with self.assertRaises(ValueError):
            self.backend.search(self.headers, 'partner')
        self.assertEqual(self.loaded, [])

    def test_policy_change_during_final_payload_check_discards_response(self):
        calls = {}

        def load(ident):
            calls[ident] = calls.get(ident, 0) + 1
            if calls[ident] == 2:
                self.org['humans'][1]['telegram_user_id'] = 999
            return self.payloads.get(ident)

        self.backend.record_loader = load
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)

    def test_catalog_or_source_change_during_request_discards_response(self):
        def load(ident):
            self.catalog['resources'][0]['secret'] = True
            return self.payloads.get(ident)

        self.backend.record_loader = load
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)

    def test_search_uses_all_permitted_kinds_and_no_cross_session_cache(self):
        result = self.backend.search(self.headers, 'river')
        self.assertEqual([row['id'] for row in result['results']], [self.project])
        self.assertEqual(self.backend.search(self.headers, 'private')['results'], [])
        self.catalog['resources'][2]['secret'] = True
        self.assertEqual(self.backend.search(self.headers, 'river')['results'], [])

    def test_draft_duplicate_zero_and_foreign_catalogs_fail_closed(self):
        for mutate in (lambda doc: doc.update(status='draft'),
                       lambda doc: doc['resources'].append(copy.deepcopy(doc['resources'][0])),
                       lambda doc: doc['resources'][0].update(category='category-0'),
                       lambda doc: doc.update(organization='foreign')):
            original = copy.deepcopy(self.catalog)
            mutate(self.catalog)
            with self.assertRaises(ValueError):
                self.backend.state(self.headers)
            self.catalog = original
        self.assertEqual(self.loaded, [])

    def test_category_meaning_changes_invalidate_session_and_catalog(self):
        self.org['policies']['security_categories']['category-1']['description'] = 'Revised meaning'
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)
        directory = HumanDirectory(self.org)
        self.gate.recipients[self.gate.digest(self.cookie)] = directory.resolve(
            **context('102', 'administrator'), scope_id='example')
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)
        self.assertEqual(self.loaded, [])

    def test_forged_relationship_endpoints_never_reach_projection(self):
        self.replace(self.edge, {'source': self.public, 'target': self.hidden,
                                 'type': 'assignment', 'label': 'Forged'})
        self.assertEqual(self.backend.state(self.headers)['relations'], [])

    def test_relation_catalog_rejects_undeclared_or_relationship_endpoints(self):
        row = next(row for row in self.catalog['resources'] if row['id'] == self.edge)
        for endpoints in ([self.public, 'f' * 64], [self.public, self.hidden_edge]):
            row['endpoints'] = endpoints
            with self.assertRaises(ValueError):
                ProjectionCatalog(self.catalog)

    def test_changed_resource_during_final_check_discards_all_records(self):
        reads = {}

        def load(ident):
            reads[ident] = reads.get(ident, 0) + 1
            return None if reads[ident] == 2 else self.payloads.get(ident)

        self.backend.record_loader = load
        with self.assertRaises(ValueError):
            self.backend.state(self.headers)


class PrivateRecordStoreTests(unittest.TestCase):
    def test_manifest_exclusions_removed_and_duplicate_entries_override_cached_files(self):
        ident = 'a' * 64
        manifest = {'organization': 'example', 'resources': [{'id': ident, 'available': True, 'searchable': True}]}
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / (ident + '.json')).write_bytes(b'cached')
            store = PrivateRecordStore(root, lambda: manifest, 'example')
            self.assertEqual(store(ident), b'cached')
            manifest['resources'][0]['searchable'] = False
            self.assertIsNone(store(ident))
            manifest['resources'][0]['searchable'] = True
            manifest['resources'] *= 2
            self.assertIsNone(store(ident))
            manifest['resources'] = []
            self.assertIsNone(store(ident))
            with self.assertRaises(ValueError):
                store('../source')


if __name__ == '__main__':
    unittest.main()
