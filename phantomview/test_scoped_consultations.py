"""Session-owned bounded HTTP consultations and cooperative native cancellation."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import phantomview as pv
from scoped_assistant import ConsultationCancelled, ScopedAssistant
from scoped_consultations import ScopedConsultations, TERMINAL
from session_audit import Ledger
from test_scoped_backend import ProjectionFixture


class Executor:
    def __init__(self):
        self.started, self.release, self.stopped = threading.Event(), threading.Event(), threading.Event()
        self.release.set()
        self.calls = []

    def __call__(self, envelope):
        raise AssertionError('Queued requests must use the cancellable entry')

    def run(self, envelope, *, cancelled):
        self.calls.append(envelope)
        self.started.set()
        try:
            while not self.release.wait(.01):
                if cancelled.is_set():
                    raise ConsultationCancelled()
            return 'Scoped answer'
        finally:
            self.stopped.set()


class QueueFixture(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.gate.audit = Ledger(Path(self.temp.name) / 'audit.sqlite')
        self.executor = Executor()
        self.persona = self.gate.identified_scope(self.headers)[0].persona
        self.assistant = ScopedAssistant(self.backend, {self.persona: self.executor})
        self.service = ScopedConsultations(self.assistant)
        self.addCleanup(self.service.close)

    def body(self):
        return {'request_id': str(uuid.uuid4()), 'question': 'Explain the River partner', 'resource_ids': [self.project]}

    def terminal(self, ident):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            with self.service.lock:
                if self.service.rows[ident]['status'] in TERMINAL:
                    return self.service.rows[ident]
            threading.Event().wait(.01)
        self.fail('Consultation did not finish within the test deadline')


class QueueTests(QueueFixture):
    def test_identical_retry_runs_once_and_conflicting_retry_is_rejected(self):
        body = self.body()
        status, job = self.service.submit(self.headers, body)
        self.assertEqual(status, 202)
        self.terminal(job['id'])
        status, again = self.service.submit(self.headers, body)
        self.assertEqual((status, again['id']), (200, job['id']))
        self.assertEqual(len(self.executor.calls), 1)
        self.assertEqual(self.service.submit(self.headers, body | {'question': 'Another question'})[0], 409)
        status, result = self.service.get(self.headers, job['id'])
        self.assertEqual((status, result['result']['text']), (200, 'Scoped answer'))
        self.assertEqual(result['result']['request_id'], body['request_id'])

    def test_other_session_cannot_read_or_cancel_a_known_job(self):
        _, job = self.service.submit(self.headers, self.body())
        self.terminal(job['id'])
        recipient = self.gate.identified_scope(self.headers)[0]
        cookie = self.gate.create_session()
        self.gate.recipients[self.gate.digest(cookie)] = recipient
        other = {'Cookie': 'phantomview=' + cookie}
        self.assertEqual(self.service.get(other, job['id'])[0], 404)
        self.assertEqual(self.service.cancel(other, job['id'])[0], 404)

    def test_queued_cancel_does_not_start_another_inference(self):
        self.executor.release.clear()
        _, first = self.service.submit(self.headers, self.body())
        self.assertTrue(self.executor.started.wait(2))
        _, second = self.service.submit(self.headers, self.body())
        self.assertEqual(self.service.cancel(self.headers, second['id'])[1]['status'], 'cancelled')
        self.executor.release.set()
        self.terminal(first['id'])
        self.assertEqual(self.terminal(second['id'])['result'], None)
        self.assertEqual(len(self.executor.calls), 1)

    def test_running_cancel_suppresses_late_answer(self):
        self.executor.release.clear()
        _, job = self.service.submit(self.headers, self.body())
        self.assertTrue(self.executor.started.wait(2))
        self.service.cancel(self.headers, job['id'])
        self.assertTrue(self.executor.stopped.wait(2))
        self.executor.release.set()
        self.assertIsNone(self.service.get(self.headers, job['id'])[1]['result'])

    def test_logout_automatically_cancels_running_work_without_polling(self):
        self.executor.release.clear()
        _, job = self.service.submit(self.headers, self.body())
        self.assertTrue(self.executor.started.wait(2))
        self.gate.logout(self.headers)
        self.assertTrue(self.executor.stopped.wait(2))
        self.assertIsNone(self.terminal(job['id'])['result'])
        with self.assertRaises(ValueError):
            self.service.get(self.headers, job['id'])

    def test_completed_response_is_not_released_after_source_change(self):
        body = self.body()
        _, job = self.service.submit(self.headers, body)
        self.terminal(job['id'])
        self.replace(self.project, {'title': 'Changed project'})
        with self.assertRaises(ValueError):
            self.service.get(self.headers, job['id'])
        self.assertIsNone(self.service.rows[job['id']]['result'])
        self.assertEqual(self.service.submit(self.headers, body)[0], 409)

    def test_pending_queue_and_per_session_hourly_limits(self):
        self.executor.release.clear()
        self.service.submit(self.headers, self.body())
        self.assertTrue(self.executor.started.wait(2))
        for _ in range(4):
            self.assertEqual(self.service.submit(self.headers, self.body())[0], 202)
        self.assertEqual(self.service.submit(self.headers, self.body())[0], 429)
        self.executor.release.set()
        for row in list(self.service.rows.values()):
            self.terminal(row['id'])
        for _ in range(5):
            _, job = self.service.submit(self.headers, self.body())
            self.terminal(job['id'])
        self.assertEqual(self.service.submit(self.headers, self.body())[0], 429)

    def test_deadline_watcher_cancels_a_running_executor(self):
        self.executor.release.clear()
        now = [time.monotonic()]
        self.service.clock = lambda: now[0]
        _, job = self.service.submit(self.headers, self.body())
        self.assertTrue(self.executor.started.wait(2))
        now[0] += 121
        self.assertTrue(self.executor.stopped.wait(2))
        self.assertIsNone(self.terminal(job['id'])['result'])

    def test_audit_failure_at_admission_starts_nothing(self):
        with patch.object(self.gate.audit, 'record', side_effect=OSError('Audit unavailable')):
            with self.assertRaises(OSError):
                self.service.submit(self.headers, self.body())
        self.assertEqual(self.executor.calls, [])
        self.assertEqual(self.service.rows, {})

    def test_global_hourly_limit_applies_across_distinct_sessions(self):
        recipient = self.gate.identified_scope(self.headers)[0]
        for _ in range(4):
            cookie = self.gate.create_session()
            self.gate.recipients[self.gate.digest(cookie)] = recipient
            self.headers = {'Cookie': 'phantomview=' + cookie}
            for _ in range(10):
                status, job = self.service.submit(self.headers, self.body())
                self.assertEqual(status, 202)
                self.terminal(job['id'])
        cookie = self.gate.create_session()
        self.gate.recipients[self.gate.digest(cookie)] = recipient
        self.assertEqual(self.service.submit({'Cookie': 'phantomview=' + cookie}, self.body())[0], 429)

    def test_cancel_audit_failure_still_stops_running_work(self):
        self.executor.release.clear()
        _, job = self.service.submit(self.headers, self.body())
        self.assertTrue(self.executor.started.wait(2))
        with patch.object(self.gate.audit, 'record', side_effect=OSError('Audit unavailable')):
            with self.assertRaises(OSError):
                self.service.cancel(self.headers, job['id'])
        self.assertTrue(self.executor.stopped.wait(2))
        self.assertIsNone(self.service.rows[job['id']]['result'])

    def test_cached_answer_delivery_requires_healthy_unchanged_audit(self):
        body = self.body()
        _, job = self.service.submit(self.headers, body)
        self.terminal(job['id'])
        with patch.object(self.gate.audit, 'record', side_effect=OSError('Audit unavailable')):
            with self.assertRaises(OSError):
                self.service.get(self.headers, job['id'])
        self.assertIsNone(self.service.rows[job['id']]['result'])
        self.gate.audit = None
        with self.assertRaises(ValueError):
            self.service.submit(self.headers, body)

    def test_no_actor_overrides_or_denied_focus_and_shutdown_cancels(self):
        with self.assertRaises(ValueError):
            self.service.submit(self.headers, self.body() | {'human': 'owner'})
        with self.assertRaises(PermissionError):
            self.service.submit(self.headers, self.body() | {'resource_ids': [self.hidden]})
        self.executor.release.clear()
        _, job = self.service.submit(self.headers, self.body())
        self.assertTrue(self.executor.started.wait(2))
        self.service.close()
        self.assertIsNone(self.service.rows[job['id']]['result'])
        self.assertTrue(self.executor.stopped.is_set())
        with self.assertRaises(OSError):
            self.service.submit(self.headers, self.body())


class QueueHTTPTests(QueueFixture):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), pv.Handler)
        self.server.gate, self.server.scoped_backend = self.gate, self.backend
        self.server.scoped_consultations = self.service
        self.server.access_errors = (ValueError, self.gate.access.core.Invalid)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, origin=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = self.headers | {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_submit_poll_and_cancel_are_scoped_and_explicit(self):
        base = '/api/scoped-assistant/jobs'
        status, job = self.request('POST', base, self.body())
        self.assertEqual(status, 202)
        self.terminal(job['id'])
        self.assertEqual(self.request('GET', base + '/' + job['id'])[1]['result']['text'], 'Scoped answer')
        self.assertEqual(self.request('DELETE', base + '/' + job['id'])[1]['status'], 'cancelled')
        self.assertEqual(self.request('GET', base + '/' + job['id'])[1]['result'], None)

    def test_origin_identity_query_legacy_and_unconfigured_routes_remain_closed(self):
        base = '/api/scoped-assistant/jobs'
        self.assertEqual(self.request('POST', base, self.body(), origin='https://untrusted.invalid')[0], 403)
        self.assertEqual(self.request('POST', base + '?human=owner', self.body())[0], 400)
        self.assertEqual(self.request('POST', '/api/assistant/jobs', self.body())[0], 403)
        self.server.scoped_consultations = None
        self.assertEqual(self.request('POST', base, self.body())[0], 403)
        self.assertEqual(self.request('DELETE', base + '/' + str(uuid.uuid4()))[0], 403)
        self.server.scoped_consultations = self.service
        self.gate.logout(self.headers)
        self.assertEqual(self.request('POST', base, self.body())[0], 401)
        self.assertEqual(self.executor.calls, [])


if __name__ == '__main__':
    unittest.main()
