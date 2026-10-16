"""Synthetic scoped consultation dispatch and delivery boundary tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from assistant_worker import ConsultationHeld
from channel_identity import HumanDirectory
from scoped_assistant import MAX_ENVELOPE_BYTES, ScopedAssistant, encode
from session_audit import Ledger
from test_channel_identity import context
from test_scoped_backend import ProjectionFixture


class ScopedAssistantTests(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.gate.audit = Ledger(Path(self.temp.name) / 'audit.sqlite')
        self.sent = []
        self.persona = self.gate.identified_scope(self.headers)[0].persona
        self.assistant = ScopedAssistant(self.backend, {self.persona: self.execute})

    def execute(self, envelope):
        self.sent.append(envelope)
        return 'The supplied evidence identifies the project partner.'

    def test_only_authorized_evidence_and_authoritative_persona_reach_executor(self):
        result = self.assistant.consult(self.headers, 'What is the River partner?')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(self.sent[0]['persona'], self.persona)
        self.assertEqual([row['id'] for row in self.sent[0]['evidence']], [self.project])
        self.assertNotIn(self.hidden, self.loaded)
        self.assertNotIn(self.other, self.loaded)
        wire = json.dumps(self.sent)
        for value in (self.cookie, 'Private board detail', self.hidden, self.other):
            self.assertNotIn(value, wire)
        self.assertFalse(result['complete_corpus'])
        events = [row for row in self.gate.audit.export() if row['event'].startswith('scoped_assistant_')]
        self.assertEqual([row['metadata']['status'] for row in events], ['queued', 'running', 'complete'])
        self.assertNotIn('River partner', json.dumps(events))

    def test_project_session_has_only_project_evidence(self):
        directory = HumanDirectory(self.org)
        self.gate.recipients[self.gate.digest(self.cookie)] = directory.resolve(
            **context('102', 'administrator'), scope_id='river-project')
        self.assistant.consult(self.headers, 'profile partner assignment', resource_ids=[self.project])
        self.assertEqual([row['id'] for row in self.sent[0]['evidence']], [self.project])
        self.assertEqual(self.sent[0]['scope_id'], 'river-project')

    def test_hidden_and_unknown_focus_ids_cannot_be_used(self):
        for key in (self.hidden, self.other, 'f' * 64):
            with self.subTest(key=key), self.assertRaises(PermissionError):
                self.assistant.consult(self.headers, 'Explain this record', resource_ids=[key])
        self.assertEqual(self.sent, [])

    def test_native_hold_and_provider_failure_release_no_text(self):
        for error, status in ((ConsultationHeld(), 'held'), (RuntimeError('Private provider error'), 'failed')):
            with self.subTest(status=status):
                assistant = ScopedAssistant(self.backend, {self.persona: lambda _: self.raise_error(error)})
                result = assistant.consult(self.headers, 'River')
                self.assertEqual((result['status'], result['text']), (status, ''))

    @staticmethod
    def raise_error(error):
        raise error

    def test_logout_during_execution_discards_response(self):
        def execute(_):
            self.gate.logout(self.headers)
            return 'Never release this answer'

        assistant = ScopedAssistant(self.backend, {self.persona: execute})
        with self.assertRaises(ValueError):
            assistant.consult(self.headers, 'River')

    def test_source_change_during_execution_discards_response(self):
        def execute(_):
            self.replace(self.project, {'title': 'Changed partner'})
            return 'Stale evidence answer'

        with self.assertRaises(ValueError):
            ScopedAssistant(self.backend, {self.persona: execute}).consult(self.headers, 'River')

    def test_policy_change_during_execution_discards_response(self):
        def execute(_):
            self.org['humans'][1]['telegram_user_id'] = 999
            return 'Formerly authorized answer'

        with self.assertRaises(ValueError):
            ScopedAssistant(self.backend, {self.persona: execute}).consult(self.headers, 'River')

    def test_audit_failure_prevents_dispatch_or_response_release(self):
        record = self.gate.audit.record
        for failure in ('scoped_assistant_requested', 'scoped_assistant_dispatched', 'scoped_assistant_finished'):
            def fail(event, *args, **kwargs):
                if event == failure:
                    raise OSError('Audit unavailable')
                return record(event, *args, **kwargs)

            self.sent.clear()
            with self.subTest(event=failure), patch.object(self.gate.audit, 'record', side_effect=fail):
                with self.assertRaises(OSError):
                    self.assistant.consult(self.headers, 'River')
            self.assertEqual(len(self.sent), int(failure == 'scoped_assistant_finished'))

    def test_revocation_after_dispatch_audit_blocks_inference(self):
        record = self.gate.audit_event

        def revoke(headers, event, **kwargs):
            record(headers, event, **kwargs)
            if event == 'scoped_assistant_dispatched':
                self.gate.logout(self.headers)

        with patch.object(self.gate, 'audit_event', side_effect=revoke), self.assertRaises(ValueError):
            self.assistant.consult(self.headers, 'River')
        self.assertEqual(self.sent, [])

    def test_executor_mutation_cannot_change_trusted_basis_or_headers(self):
        def execute(envelope):
            envelope['scope_id'] = 'other-project'
            envelope['evidence'].clear()
            self.headers.clear()
            return 'A bounded response'

        result = ScopedAssistant(self.backend, {self.persona: execute}).consult(self.headers, 'River')
        self.assertEqual(result['scope_id'], 'example')
        self.assertEqual(result['status'], 'complete')

    def test_unicode_envelope_bounds_and_focus_selection_are_explicit(self):
        self.replace(self.project, {'title': 'River ' + '\U0001f30a' * 4000})
        result = self.assistant.consult(self.headers, '\U0001f30a' * 1700, resource_ids=[self.project])
        self.assertLessEqual(len(encode(self.sent[0])), MAX_ENVELOPE_BYTES)
        self.assertTrue(result['evidence_limited'])
        self.assertTrue(self.sent[0]['evidence'][0]['excerpt_only'])

    def test_no_executor_or_audit_never_falls_back_to_legacy_worker(self):
        with self.assertRaises(ValueError):
            ScopedAssistant(self.backend, {'unrelated-persona': self.execute}).consult(self.headers, 'River')
        self.gate.audit = None
        with self.assertRaises(ValueError):
            self.assistant.consult(self.headers, 'River')
        with self.assertRaises(ValueError):
            ScopedAssistant(self.backend, {self.persona: self.execute})
        self.assertEqual(self.sent, [])

    def test_replacing_audit_during_execution_discards_response(self):
        def execute(_):
            self.gate.audit = None
            return 'An unaudited answer'

        with self.assertRaises(ValueError):
            ScopedAssistant(self.backend, {self.persona: execute}).consult(self.headers, 'River')

    def test_final_audit_revocation_still_discards_answer(self):
        record = self.gate.audit_event

        def revoke(headers, event, **kwargs):
            record(headers, event, **kwargs)
            if event == 'scoped_assistant_finished':
                self.gate.logout(self.headers)

        with patch.object(self.gate, 'audit_event', side_effect=revoke), self.assertRaises(ValueError):
            self.assistant.consult(self.headers, 'River')

    def test_invalid_or_oversized_answers_are_failed_and_credentials_redacted(self):
        for answer in (None, {'status': 'complete', 'text': 'Untrusted protocol fields'}, 'x' * 64001):
            with self.subTest(answer_type=type(answer)):
                result = ScopedAssistant(self.backend, {self.persona: lambda _: answer}).consult(self.headers, 'River')
                self.assertEqual((result['status'], result['text']), ('failed', ''))
        result = ScopedAssistant(self.backend, {self.persona: lambda _: 'token=example-sensitive-value'}).consult(
            self.headers, 'River')
        self.assertNotIn('example-sensitive-value', result['text'])

    def test_empty_evidence_does_not_claim_a_complete_corpus_search(self):
        result = self.assistant.consult(self.headers, 'Unmatchedterm')
        self.assertEqual(self.sent[0]['evidence'], [])
        self.assertFalse(result['complete_corpus'])


if __name__ == '__main__':
    unittest.main()
