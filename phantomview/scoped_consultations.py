"""Opt-in bounded consultation queue, tied to one identified session and view."""
from collections import deque
import json
import threading
import time
import uuid

from resource_review import revision
from scoped_assistant import ConsultationCancelled, MAX_EVIDENCE, ScopedAssistant
from scoped_knowledge import HEX

TERMINAL = {'complete', 'held', 'failed', 'cancelled'}


def identifier(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('An exact consultation UUID is required')
    return value


class ScopedConsultations:
    def __init__(self, assistant, *, clock=time.monotonic):
        if (not isinstance(assistant, ScopedAssistant) or assistant.mode not in {'scoped-consultation', 'persona-conversation'}
                or any(not callable(getattr(executor, 'run', None)) for executor in assistant.executors.values())):
            raise ValueError('A scoped assistant with explicitly cancellable executors is required')
        self.assistant, self.backend, self.gate, self.clock = assistant, assistant.backend, assistant.gate, clock
        self.lock = threading.RLock()
        self.rows, self.requests, self.calls = {}, {}, deque()
        self.queue, self.worker, self.closed = deque(), None, False

    def _identity(self, headers):
        recipient = self.gate.identified_scope(headers)[0]
        owner, expiry = self.gate.session_scope(headers)
        return recipient, owner, expiry

    def _prune(self):
        now = self.clock()
        while self.calls and self.calls[0][0] <= now - 3600:
            self.calls.popleft()
        for ident, row in list(self.rows.items()):
            if row['expires'] <= now:
                row['cancelled'].set()
                row['result'] = None
                if row['status'] in TERMINAL:
                    self.rows.pop(ident)
                    self.requests.pop((row['owner'], row['request_id']), None)

    @staticmethod
    def _public(row):
        return {'id': row['id'], 'status': row['status'], 'result': json.loads(json.dumps(row['result']))}

    def submit(self, headers, body):
        headers = {'Cookie': headers.get('Cookie', '')}
        recipient, owner, expiry = self._identity(headers)
        if self.gate.audit is not self.assistant.audit:
            raise ValueError('The protected consultation audit changed')
        if (not isinstance(body, dict) or set(body) != {'request_id', 'question', 'resource_ids'}
                or not isinstance(body['question'], str) or not body['question'].strip() or len(body['question']) > 1800
                or not isinstance(body['resource_ids'], list) or len(body['resource_ids']) > MAX_EVIDENCE
                or any(not isinstance(key, str) or not HEX.fullmatch(key) for key in body['resource_ids'])
                or len(set(body['resource_ids'])) != len(body['resource_ids'])):
            raise ValueError('Invalid bounded consultation request')
        request_id = identifier(body['request_id'])
        body = json.loads(json.dumps(body, allow_nan=False))
        if recipient.persona not in self.assistant.executors:
            raise ValueError('No scoped executor is configured for this persona')
        view = self.backend.state(headers)
        visible = {row['id'] for row in view['resources'] + view['relations']}
        if not set(body['resource_ids']) <= visible:
            raise PermissionError('Focus resource unavailable')
        fingerprint = revision(body)
        with self.lock:
            self._prune()
            if self.closed:
                raise OSError('Consultation queue is closed')
            old = self.rows.get(self.requests.get((owner, request_id)))
            if old is not None:
                if old['fingerprint'] != fingerprint or old['view_revision'] != view['view_revision']:
                    return 409, {'error': 'Request identifier or authorized view changed'}
                return self._delivery(headers, old)
            if (len(self.calls) >= 40 or sum(value == owner for _, value in self.calls) >= 10
                    or sum(self.rows[key]['status'] == 'queued' for key in self.queue if key in self.rows) >= 4
                    or len(self.rows) >= 40):
                return 429, {'error': 'Consultation limit reached; try later'}
            now, ident = self.clock(), str(uuid.uuid4())
            self.gate.audit_event(headers, 'scoped_assistant_queued', request_id=request_id, job_id=ident,
                                  status='queued', mode=self.assistant.mode)
            row = {'id': ident, 'owner': owner, 'recipient': recipient, 'request_id': request_id,
                   'fingerprint': fingerprint, 'view_revision': view['view_revision'], 'body': body,
                   'headers': {'Cookie': headers.get('Cookie', '')}, 'status': 'queued', 'result': None,
                   'cancelled': threading.Event(), 'expires': now + min(1800, max(0, expiry - time.time()))}
            row['deadline'] = min(now + 120, row['expires'])
            self.rows[ident], self.requests[owner, request_id] = row, ident
            self.queue.append(ident)
            self.calls.append((now, owner))
            if self.worker is None:
                self.worker = threading.Thread(target=self._drain, daemon=True)
                self.worker.start()
            return 202, self._public(row)

    def get(self, headers, ident):
        recipient, owner, _ = self._identity(headers)
        ident = identifier(ident)
        with self.lock:
            self._prune()
            row = self.rows.get(ident)
            if row is None or row['owner'] != owner or row['recipient'] != recipient:
                return 404, {'error': 'Consultation unavailable'}
        return self._delivery(headers, row)

    def _delivery(self, headers, row):
        try:
            self.assistant._current(headers, row['recipient'], row['view_revision'])
            with self.lock:
                has_result = row['result'] is not None
            if has_result:
                self.gate.audit_event(headers, 'scoped_assistant_delivered', request_id=row['request_id'],
                    job_id=row['id'], status=row['status'], mode=self.assistant.mode)
            self.assistant._current(headers, row['recipient'], row['view_revision'])
        except (ValueError, OSError):
            with self.lock:
                row['cancelled'].set()
                row['result'] = None
            raise
        with self.lock:
            return 200, self._public(row)

    def cancel(self, headers, ident):
        recipient, owner, _ = self._identity(headers)
        ident = identifier(ident)
        with self.lock:
            row = self.rows.get(ident)
            if row is None or row['owner'] != owner or row['recipient'] != recipient:
                return 404, {'error': 'Consultation unavailable'}
            try:
                if self.gate.audit is not self.assistant.audit:
                    raise OSError('The protected consultation audit changed')
                self.gate.audit_event(headers, 'scoped_assistant_cancelled', request_id=row['request_id'],
                                      job_id=ident, status='cancelled', mode=self.assistant.mode)
            finally:
                row['cancelled'].set()
                row['status'], row['result'] = 'cancelled', None
            return 200, self._public(row)

    def _watch(self, row, done):
        while not done.wait(.1):
            try:
                if (self.gate.audit is not self.assistant.audit or self.clock() >= row['deadline']
                        or self._identity(row['headers'])[0] != row['recipient']):
                    row['cancelled'].set()
                    return
            except (ValueError, OSError):
                row['cancelled'].set()
                return

    def _drain(self):
        while True:
            with self.lock:
                if not self.queue:
                    self.worker = None
                    return
                row = self.rows.get(self.queue.popleft())
                if row is None:
                    continue
                if row['cancelled'].is_set() or self.clock() >= row['deadline']:
                    row['status'], row['body'], row['headers'] = 'cancelled', None, None
                    continue
                row['status'] = 'running'
            done = threading.Event()
            watch = threading.Thread(target=self._watch, args=(row, done), daemon=True)
            watch.start()
            result = None
            try:
                self.assistant._current(row['headers'], row['recipient'], row['view_revision'])
                body = row['body']
                result = self.assistant.consult(row['headers'], body['question'], resource_ids=body['resource_ids'],
                    cancelled=row['cancelled'], request_id=row['request_id'])
                self.assistant._current(row['headers'], row['recipient'], row['view_revision'])
                status = result['status']
            except ConsultationCancelled:
                status = 'cancelled'
            except Exception:
                status, result = 'failed', None
            finally:
                done.set()
                watch.join(timeout=1)
            with self.lock:
                if row['cancelled'].is_set():
                    status, result = 'cancelled', None
                row['status'], row['result'], row['body'], row['headers'] = status, result, None, None

    def close(self):
        with self.lock:
            self.closed = True
            for row in self.rows.values():
                row['cancelled'].set()
                row['status'], row['result'] = 'cancelled', None
            worker = self.worker
        if worker is not None:
            worker.join(timeout=5)
