"""Native authority uses the existing session and backend, never browser grants."""
import json
from unittest.mock import patch

from native_turn_context import NativeTurnContext
from scoped_backend import ScopedBackend
from test_channel_identity import context as channel_context
from test_scoped_backend import ProjectionFixture
from test_viewer_modules import projects


class NativeTurnContextTests(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.report = {'default_persona': {'resolved': 'administrator', 'provenance': 'config',
                                          'exists': True, 'served': True}}
        self.backend = ScopedBackend(self.gate, lambda: self.catalog, self.load,
                                     default_report_loader=lambda: self.report)

    def test_metadata_binds_human_persona_scope_and_revisions_without_credentials(self):
        context = NativeTurnContext(self.backend, self.headers)
        metadata = context.metadata()
        recipient, directory = self.gate.identified_scope(self.headers)
        self.assertEqual(metadata['human'], recipient.human)
        self.assertEqual(metadata['persona'], 'administrator')
        self.assertEqual(metadata['authority_revision'], directory.authority_revision)
        self.assertEqual(metadata['scope_id'], 'example')
        self.assertEqual(metadata['operation'], 'read')
        self.assertFalse(metadata['complete_corpus'])
        self.assertNotIn(self.cookie, json.dumps(metadata))
        self.assertNotIn('Cookie', metadata)
        metadata['persona'] = 'forged'
        self.assertEqual(context.metadata()['persona'], 'administrator')

    def test_hidden_or_unknown_records_are_not_loaded_by_native_reads_or_search(self):
        context = NativeTurnContext(self.backend, self.headers)
        self.loaded.clear()
        self.assertEqual(context.read(self.public)['data']['title'], 'Public profile')
        for key in (self.hidden, self.other, 'f'*64):
            with self.assertRaises(KeyError):
                context.read(key)
        self.assertEqual(context.search('Private board')['results'], [])
        self.assertNotIn(self.hidden, self.loaded)
        self.assertNotIn(self.other, self.loaded)

    def test_project_scope_does_not_expand_to_other_persona_grants(self):
        recipient = self.gate.recipients[self.gate.digest(self.cookie)]
        from dataclasses import replace
        self.gate.recipients[self.gate.digest(self.cookie)] = replace(recipient, scope_id='river-project')
        context = NativeTurnContext(self.backend, self.headers)
        self.assertEqual(context.read(self.project)['id'], self.project)
        with self.assertRaises(KeyError):
            context.read(self.public)
        with self.assertRaises(KeyError):
            context.read(self.other)

    def test_selected_module_does_not_change_core_or_session_identity(self):
        module = projects()
        module['scope_kinds'] = ['organization']
        backend = ScopedBackend(self.gate, lambda: self.catalog, self.load,
            modules=[module], default_report_loader=lambda: self.report)
        context = NativeTurnContext(backend, self.headers, section_id='project-management:partners')
        self.assertEqual(context.metadata()['section_id'], 'project-management:partners')
        self.assertEqual(context.metadata()['persona'], 'administrator')
        self.assertEqual(backend.workspace(self.headers)['navigation']['assistant']['persona'], 'administrator')
        with self.assertRaises(ValueError):
            NativeTurnContext(backend, self.headers, section_id='project-management:missing')

    def test_unavailable_or_unauthorized_assistant_cannot_create_a_native_context(self):
        workspace = self.backend.workspace

        def denied(headers):
            view = workspace(headers)
            view['navigation']['assistant'] = {
                'persona': None, 'eligible': False, 'source': 'session-issuer'}
            return view

        with patch.object(self.backend, 'workspace', side_effect=denied):
            with self.assertRaises(PermissionError):
                NativeTurnContext(self.backend, self.headers)
        with self.assertRaises(ValueError):
            NativeTurnContext(self.backend, {'Cookie': 'phantomview=forged'})

    def test_logout_or_identity_change_prevents_response_delivery(self):
        context = NativeTurnContext(self.backend, self.headers)
        self.gate.logout(self.headers)
        with self.assertRaises(ValueError):
            context.release('Old answer')

    def test_policy_change_after_native_read_prevents_delivery(self):
        context = NativeTurnContext(self.backend, self.headers)
        context.read(self.public)
        self.org['policies']['security_categories']['category-1']['description'] = 'Revised meaning'
        with self.assertRaises(ValueError):
            context.release('Old answer')

    def test_identity_rebinding_during_projection_does_not_reuse_the_old_turn(self):
        context = NativeTurnContext(self.backend, self.headers)
        _, directory = self.gate.identified_scope(self.headers)
        replacement = directory.resolve(**channel_context('101', 'administrator'), scope_id='example')
        original = self.backend.workspace

        def workspace(headers):
            view = original(headers)
            self.gate.recipients[self.gate.digest(self.cookie)] = replacement
            return view

        with patch.object(self.backend, 'workspace', side_effect=workspace):
            with self.assertRaises(ValueError):
                context.release('Old recipient answer')

    def test_host_default_cannot_redirect_turn_but_changed_resource_invalidates_it(self):
        context = NativeTurnContext(self.backend, self.headers)
        self.report['default_persona']['resolved'] = 'coordinator'
        self.assertEqual(context.metadata()['persona'], 'administrator')
        self.report['default_persona']['served'] = False
        self.assertEqual(context.release('Same issuer answer')['persona'], 'administrator')
        self.replace(self.public, {'title': 'Revised public profile'})
        with self.assertRaises(ValueError):
            context.read(self.public)

    def test_revalidation_discards_a_resource_changed_during_native_read(self):
        context = NativeTurnContext(self.backend, self.headers)
        original = context._current
        calls = []

        def current():
            view = original()
            if not calls:
                self.replace(self.public, {'title': 'Changed during access'})
            calls.append(True)
            return view

        with patch.object(context, '_current', side_effect=current):
            with self.assertRaises(ValueError):
                context.read(self.public)

    def test_close_and_oversized_response_cannot_release_output(self):
        context = NativeTurnContext(self.backend, self.headers)
        with self.assertRaises(ValueError):
            context.release('x'*64001)
        self.assertEqual(context.release('Allowed answer')['text'], 'Allowed answer')
        context.close()
        for operation in (context.metadata, lambda: context.read(self.public), lambda: context.release('Old answer')):
            with self.assertRaises(ValueError):
                operation()

    def test_expired_session_prevents_native_context_reads_and_delivery(self):
        context = NativeTurnContext(self.backend, self.headers)
        clock = self.gate.clock
        self.gate.clock = lambda: clock() + self.gate.seconds + 1
        with self.assertRaises(ValueError):
            context.read(self.public)
        with self.assertRaises(ValueError):
            context.release('Expired answer')

    def test_ineligible_module_override_never_falls_back_to_the_core_persona(self):
        module = projects()
        module['scope_kinds'] = ['organization']
        module['assistant'] = {'persona': 'treasurer'}
        backend = ScopedBackend(self.gate, lambda: self.catalog, self.load,
            modules=[module], default_report_loader=lambda: self.report)
        self.assertEqual(NativeTurnContext(backend, self.headers).metadata()['persona'], 'administrator')
        with self.assertRaises(PermissionError):
            NativeTurnContext(backend, self.headers, section_id='project-management:partners')

    def test_category_zero_uses_existing_information_privileges_without_write_grants(self):
        _, directory = self.gate.identified_scope(self.headers)
        recipient = directory.resolve(**channel_context('101', 'coordinator'), scope_id='example')
        self.gate.recipients[self.gate.digest(self.cookie)] = recipient
        self.report['default_persona']['resolved'] = 'coordinator'
        context = NativeTurnContext(self.backend, self.headers)
        self.assertEqual(context.read(self.hidden)['id'], self.hidden)
        self.assertEqual(context.metadata()['operation'], 'read')
        self.assertFalse(directory.allows_action(recipient, 'resource.edit', 'example'))
