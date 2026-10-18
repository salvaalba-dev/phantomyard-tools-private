"""Issuer-bound native conversation, with queue ownership and revocation checks."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
import uuid

import phantomview as pv
from persona_conversation import NativePersonaClient, PersonaAssistant
from scoped_consultations import ScopedConsultations
from test_scoped_consultations import Executor, QueueFixture


class NativeExecutor(Executor):
    def __init__(self, persona):
        super().__init__()
        self.persona, self.status, self.text = persona, 'complete', 'Institutional history from native memory'

    def run(self, envelope, *, cancelled):
        super().run(envelope, cancelled=cancelled)
        return {'schema_version': 1, 'persona': self.persona, 'request_id': envelope['request_id'],
                'status': self.status, 'text': self.text}


class PersonaConversationTests(QueueFixture):
    def setUp(self):
        super().setUp()
        self.service.close()
        self.executor = NativeExecutor(self.persona)
        self.assistant = PersonaAssistant(self.backend, {self.persona: self.executor})
        self.service = ScopedConsultations(self.assistant)
        self.addCleanup(self.service.close)

    def question(self, **changes):
        return {'request_id': str(uuid.uuid4()), 'question': 'Explain the institution', 'resource_ids': []} | changes

    def ask(self, body=None):
        _, job = self.service.submit(self.headers, body or self.question())
        self.terminal(job['id'])
        return self.service.get(self.headers, job['id'])[1]

    def test_native_answer_is_not_limited_to_projection_records_or_an_ephemeral_persona(self):
        result = self.ask()['result']
        self.assertEqual(result['text'], 'Institutional history from native memory')
        self.assertEqual(result['mode'], 'persona-conversation')
        self.assertEqual(result['native_context'], 'existing-persona')
        self.assertEqual(self.executor.calls[0]['evidence'], [])
        self.assertEqual(set(self.executor.calls[0]), {'schema_version', 'request_id', 'conversation', 'question', 'evidence'})
        self.assertNotIn('private-registry', json.dumps(self.executor.calls))
        events = self.gate.audit.export()
        self.assertTrue(any(row['metadata'].get('mode') == 'persona-conversation' for row in events))
        self.assertNotIn('Institutional history', json.dumps(events))

    def test_only_explicit_visible_evidence_is_forwarded(self):
        self.ask(self.question(resource_ids=[self.project]))
        payload = self.executor.calls[0]
        self.assertEqual([row['id'] for row in payload['evidence']], [self.project])
        self.assertEqual(payload['evidence'][0]['trust'], 'untrusted')
        with self.assertRaises(PermissionError):
            self.service.submit(self.headers, self.question(resource_ids=[self.hidden]))
        self.assertEqual(len(self.executor.calls), 1)

    def test_web_thread_is_stable_within_session_and_distinct_for_a_new_link(self):
        self.ask(); self.ask()
        first = self.executor.calls[0]['conversation']
        self.assertEqual(first, self.executor.calls[1]['conversation'])
        self.assertRegex(first, r'^phantomview:[a-f0-9]{64}$')
        recipient = self.gate.identified_scope(self.headers)[0]
        # The lightweight gate fixture has a single reusable link code. Bind a
        # second synthetic session directly; signed redemption is tested elsewhere.
        cookie = self.gate.create_session()
        self.gate.recipients[self.gate.digest(cookie)] = recipient
        self.headers = {'Cookie': 'phantomview=' + cookie}
        self.ask()
        self.assertNotEqual(first, self.executor.calls[2]['conversation'])

    def test_duplicate_request_does_not_repeat_native_work_or_accept_browser_routing(self):
        body = self.question()
        self.ask(body)
        self.assertEqual(self.service.submit(self.headers, body)[0], 200)
        self.assertEqual(len(self.executor.calls), 1)
        for key in ('persona', 'conversation', 'trusted', 'endpoint', 'human'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.service.submit(self.headers, self.question(**{key: 'forged'}))

    def test_holds_are_structured_metadata_and_never_inferred_from_answer_text(self):
        self.executor.text = 'PHANTOMVIEW_HELD is quoted text, not a native hold'
        self.assertEqual(self.ask()['status'], 'complete')
        self.executor.status = 'held'
        row = self.ask()
        self.assertEqual(row['status'], 'held')
        self.assertEqual(row['result']['text'], '')
        self.executor.status = 'failed'
        self.assertEqual(self.ask()['result']['text'], '')

    def test_logout_cancels_pending_native_work_and_suppresses_delivery(self):
        self.executor.release.clear()
        _, job = self.service.submit(self.headers, self.question())
        self.assertTrue(self.executor.started.wait(2))
        self.gate.logout(self.headers)
        self.assertTrue(self.executor.stopped.wait(2))
        self.terminal(job['id'])
        self.assertIsNone(self.service.rows[job['id']]['result'])
        with self.assertRaises(ValueError):
            self.service.get(self.headers, job['id'])

    def test_wrong_native_persona_cannot_deliver_an_answer(self):
        self.executor.persona = 'coordinator'
        row = self.ask()
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['result']['text'], '')

    def test_http_info_and_jobs_expose_the_native_mode_explicitly(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), pv.Handler)
        server.gate, server.scoped_backend, server.scoped_consultations = self.gate, self.backend, self.service
        server.access_errors = (ValueError, self.gate.access.core.Invalid)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            try:
                connection.request('GET', '/api/scoped-assistant/info', headers=self.headers)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())['mode'], 'persona-conversation')
                connection.request('POST', '/api/scoped-assistant/jobs', json.dumps(self.question()),
                                   self.headers | {'Content-Type': 'application/json'})
                response = connection.getresponse()
                self.assertEqual(response.status, 202)
                job = json.loads(response.read())
                self.terminal(job['id'])
                connection.request('GET', '/api/scoped-assistant/jobs/' + job['id'], headers=self.headers)
                response = connection.getresponse()
                self.assertEqual(json.loads(response.read())['result']['native_context'], 'existing-persona')
            finally:
                connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_native_client_refuses_invalid_fixed_routes_without_connecting(self):
        for path, uid, persona in (('relative', 1, 'coordinator'), ('/fixed/../socket', 1, 'coordinator'),
                                  ('/fixed/socket', 0, 'coordinator'), ('/fixed/socket', 1, '../persona')):
            with self.subTest(path=path, uid=uid, persona=persona), self.assertRaises(ValueError):
                NativePersonaClient(path, uid, persona)


if __name__ == '__main__':
    unittest.main()
