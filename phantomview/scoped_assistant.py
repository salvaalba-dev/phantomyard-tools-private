"""Inactive synchronous consultation boundary over authorized projection data.

Executors are protected operator bindings, not browser-selected endpoints. They
must preserve the native untrusted-input screen and isolate persona memory.
No native executor, HTTP route, queue or live activation is installed here.
"""
import json
import re
import uuid

from assistant_worker import ConsultationHeld, redact
from scoped_backend import ScopedBackend
from scoped_knowledge import HEX, normalize
from session_audit import Ledger

MAX_ENVELOPE_BYTES = 12000
MAX_EVIDENCE = 8


class ConsultationCancelled(Exception):
    """Trusted lifecycle cancellation, never generated model output."""


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')


class ScopedAssistant:
    def __init__(self, backend, executors):
        if (not isinstance(backend, ScopedBackend) or not isinstance(backend.gate.audit, Ledger)
                or not isinstance(executors, dict) or not executors
                or any(not isinstance(key, str) or not key or not callable(value)
                       for key, value in executors.items())):
            raise ValueError('A scoped backend, protected audit and explicit persona executors are required')
        self.backend, self.gate, self.executors = backend, backend.gate, dict(executors)
        self.audit = self.gate.audit

    def _current(self, headers, recipient, view_revision):
        if self.gate.audit is not self.audit:
            raise ValueError('The protected consultation audit changed')
        if (self.gate.identified_scope(headers)[0] != recipient
                or self.backend.state(headers)['view_revision'] != view_revision
                or self.gate.identified_scope(headers)[0] != recipient):
            raise ValueError('Session, authority or authorized evidence changed; discard the consultation')

    def consult(self, headers, question, *, resource_ids=(), cancelled=None, request_id=None):
        """A fresh single turn, without tools, history, implicit retries or writes.

        The callable bound to the authenticated persona receives only a detached
        bounded JSON envelope. ConsultationHeld must come from trusted native
        completion metadata, never a field parsed from generated model text.
        """
        if not isinstance(question, str) or not question.strip() or len(question) > 1800:
            raise ValueError('A question of 1 to 1800 characters is required')
        if (not isinstance(resource_ids, (list, tuple)) or len(resource_ids) > MAX_EVIDENCE
                or any(not isinstance(key, str) or not HEX.fullmatch(key) for key in resource_ids)
                or len(set(resource_ids)) != len(resource_ids)):
            raise ValueError('Focus resources must be unique bounded opaque IDs')
        headers = {'Cookie': headers.get('Cookie', '')}
        resource_ids = tuple(resource_ids)
        if self.gate.audit is not self.audit:
            raise ValueError('The protected consultation audit changed')
        recipient = self.gate.identified_scope(headers)[0]
        executor = self.executors.get(recipient.persona)
        if executor is None:
            raise ValueError('No isolated executor is configured for this session persona')
        if cancelled is not None:
            if not callable(getattr(cancelled, 'is_set', None)) or not callable(getattr(executor, 'run', None)):
                raise ValueError('Queued consultations require an explicitly cancellable executor')
            if cancelled.is_set():
                raise ConsultationCancelled()
        view = self.backend.state(headers)
        records = {row['id']: row for row in view['resources'] + view['relations']}
        if any(key not in records for key in resource_ids):
            raise PermissionError('Focus resource unavailable')
        terms = sorted(set(re.findall(r'\w{2,}', normalize(question))))[:32]
        ranked = []
        for row in records.values():
            words = set(re.findall(r'\w{2,}', normalize(encode(row['data']).decode('utf-8'))))
            score = len(set(terms) & words)
            if score and row['id'] not in resource_ids:
                ranked.append((-score, row['id']))
        selected = list(resource_ids) + [key for _, key in sorted(ranked)]
        envelope = {'schema_version': 1, 'kind': 'scoped-consultation', 'trust': 'untrusted',
                    'organization': recipient.organization, 'scope_id': recipient.scope_id,
                    'persona': recipient.persona, 'question': question, 'evidence': [],
                    'complete_corpus': False, 'evidence_limited': False}
        for key in selected[:MAX_EVIDENCE]:
            row = records[key]
            text = encode(row['data']).decode('utf-8')
            evidence = {'id': key, 'kind': row['kind'], 'trust': 'untrusted',
                        'excerpt': text[:1000], 'excerpt_only': len(text) > 1000}
            envelope['evidence'].append(evidence)
            if len(encode(envelope)) > MAX_ENVELOPE_BYTES:
                envelope['evidence'].pop()
                break
        envelope['evidence_limited'] = (len(envelope['evidence']) < len(selected)
                                        or any(row['excerpt_only'] for row in envelope['evidence']))
        if len(encode(envelope)) > MAX_ENVELOPE_BYTES:
            raise ValueError('Consultation envelope exceeds bounds')
        request_id = str(uuid.uuid4()) if request_id is None else request_id
        if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
            raise ValueError('An exact consultation request UUID is required')

        def audit(event, status):
            self.gate.audit_event(headers, event, request_id=request_id, status=status, mode='scoped-consultation')

        audit('scoped_assistant_requested', 'queued')
        self._current(headers, recipient, view['view_revision'])
        audit('scoped_assistant_dispatched', 'running')
        self._current(headers, recipient, view['view_revision'])
        if cancelled is not None and cancelled.is_set():
            raise ConsultationCancelled()
        status, text = 'complete', ''
        try:
            payload = json.loads(encode(envelope))
            answer = executor(payload) if cancelled is None else executor.run(payload, cancelled=cancelled)
            if not isinstance(answer, str) or len(answer.encode('utf-8')) > 64000:
                raise ValueError('Invalid bounded assistant response')
            text = redact(answer)[:20000]
        except ConsultationHeld:
            status = 'held'
        except ConsultationCancelled:
            status = 'cancelled'
        except Exception:
            # No provider errors, filesystem paths or partial output reach humans.
            status = 'failed'
        self._current(headers, recipient, view['view_revision'])
        if cancelled is not None and cancelled.is_set():
            status, text = 'cancelled', ''
        audit('scoped_assistant_finished', status)
        self._current(headers, recipient, view['view_revision'])
        if cancelled is not None and cancelled.is_set():
            status, text = 'cancelled', ''
        return {'request_id': request_id, 'status': status, 'text': text,
                'persona': recipient.persona, 'scope_id': recipient.scope_id,
                'view_revision': view['view_revision'], 'complete_corpus': False,
                'evidence_limited': envelope['evidence_limited']}
