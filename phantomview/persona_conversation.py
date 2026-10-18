"""Existing-persona conversation through a fixed local native daemon socket."""
import hashlib
import json
from pathlib import Path
import re
import socket
import struct
import time

from handoff_client import DaemonReaderPolicy, _destination
from scoped_assistant import ConsultationCancelled, MAX_EVIDENCE, ScopedAssistant, encode
from trusted_handoff import _unique


class NativePersonaClient:
    def __init__(self, path, daemon_uid, persona):
        target = Path(path)
        if (not target.is_absolute() or '..' in target.parts or len(str(target).encode()) > 100
                or type(daemon_uid) is not int or daemon_uid <= 0 or not isinstance(persona, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', persona)):
            raise ValueError('A fixed native persona, account and local socket are required')
        self.path, self.daemon_uid, self.persona = path, daemon_uid, persona

    def __call__(self, _payload):
        raise ValueError('Existing-persona conversations require cancellable dispatch')

    def run(self, payload, *, cancelled):
        policy = DaemonReaderPolicy(self.daemon_uid)
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        if len(raw) > 16384:
            raise ValueError('Native conversation request exceeds bounds')
        deadline = time.monotonic() + 120
        def receive(connection, size):
            result = bytearray()
            while len(result) < size:
                if cancelled.is_set() or time.monotonic() >= deadline:
                    raise ConsultationCancelled()
                try:
                    part = connection.recv(size - len(result))
                except TimeoutError:
                    continue
                if not part:
                    raise ValueError('Native conversation response unavailable')
                result.extend(part)
            return bytes(result)
        if cancelled.is_set():
            raise ConsultationCancelled()
        destination = _destination(self.path, policy)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(.1)
            connection.connect(destination)
            policy.verify(connection)  # Verify native account before any question bytes.
            if cancelled.is_set():
                raise ConsultationCancelled()
            connection.sendall(struct.pack('!I', len(raw)) + raw)
            size = struct.unpack('!I', receive(connection, 4))[0]
            if not 0 < size <= 64000:
                raise ValueError('Native conversation response exceeds bounds')
            value = json.loads(receive(connection, size), object_pairs_hook=_unique)
        if (not isinstance(value, dict) or set(value) != {'schema_version', 'request_id', 'persona', 'status', 'text'}
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or value['request_id'] != payload['request_id'] or value['persona'] != self.persona
                or value['status'] not in {'complete', 'held', 'failed'}
                or not isinstance(value['text'], str) or len(value['text'].encode()) > 48000
                or value['status'] != 'complete' and value['text']):
            raise ValueError('Invalid native conversation completion')
        return value


class PersonaAssistant(ScopedAssistant):
    """Reuse session/queue lifecycle, without replacing native persona knowledge."""
    mode = 'persona-conversation'

    def available(self, headers):
        recipient, directory = self.gate.identified_scope(headers)
        # Native collaborative memory/tools do not enforce a human-only limit.
        return (recipient.persona in self.executors
                and recipient.human not in directory.scope.policy.get('human_category_limits', {}))

    def _current(self, headers, recipient, view_revision):
        super()._current(headers, recipient, view_revision)
        if not self.available(headers):
            raise PermissionError('Native conversation cannot enforce this human category limit')

    def consult(self, headers, question, *, resource_ids=(), cancelled=None, request_id=None):
        from scoped_consultations import identifier
        if (not isinstance(question, str) or not question.strip() or len(question) > 1800
                or cancelled is None or cancelled.is_set()):
            raise ValueError('A bounded cancellable native question is required')
        request_id = identifier(request_id)
        headers = {'Cookie': headers.get('Cookie', '')}
        recipient = self.gate.identified_scope(headers)[0]
        if not self.available(headers):
            raise PermissionError('Native conversation cannot enforce this human category limit')
        owner, _ = self.gate.session_scope(headers)
        executor = self.executors.get(recipient.persona)
        if executor is None or not callable(getattr(executor, 'run', None)):
            raise ValueError('The issuing persona has no native conversation route')
        if not isinstance(resource_ids, (list, tuple)) or len(resource_ids) > MAX_EVIDENCE:
            raise ValueError('Bounded selected viewer evidence required')
        view = self.backend.state(headers)
        records = {row['id']: row for row in view['resources'] + view['relations']}
        if any(not isinstance(key, str) or key not in records for key in resource_ids):
            raise PermissionError('Selected viewer evidence is unavailable')
        # Thread identity is server-owned and separate from phone/channel history.
        conversation = hashlib.sha256(encode([owner, recipient.organization, recipient.persona, recipient.scope_id])).hexdigest()
        payload = {'schema_version': 1, 'request_id': request_id, 'conversation': 'phantomview:' + conversation,
                   'question': question, 'evidence': [
                       {'id': key, 'kind': records[key]['kind'], 'trust': 'untrusted',
                        'excerpt': encode(records[key]['data']).decode()[:1000]} for key in resource_ids]}
        if len(encode(payload)) > 16384:
            raise ValueError('Selected evidence exceeds native transport bounds')
        def audit(event, status):
            self.gate.audit_event(headers, event, request_id=request_id, status=status, mode=self.mode)
        audit('scoped_assistant_requested', 'queued')
        self._current(headers, recipient, view['view_revision'])
        audit('scoped_assistant_dispatched', 'running')
        self._current(headers, recipient, view['view_revision'])
        if cancelled.is_set():
            raise ConsultationCancelled()
        status, text = 'failed', ''
        try:
            result = executor.run(payload, cancelled=cancelled)
            # The production client verifies correlation, persona and completion shape.
            if result['persona'] != recipient.persona or result['request_id'] != request_id:
                raise ValueError('Native completion route changed')
            status = result['status']
            if status not in {'complete', 'held', 'failed'}:
                raise ValueError('Unsupported native completion')
            if status == 'complete':
                from assistant_worker import redact
                if not isinstance(result['text'], str) or len(result['text'].encode()) > 48000:
                    raise ValueError('Native response exceeds bounds')
                text = redact(result['text'])[:20000]
        except ConsultationCancelled:
            status = 'cancelled'
        except Exception:
            status, text = 'failed', ''
        self._current(headers, recipient, view['view_revision'])
        if cancelled.is_set():
            status, text = 'cancelled', ''
        audit('scoped_assistant_finished', status)
        self._current(headers, recipient, view['view_revision'])
        return {'request_id': request_id, 'status': status, 'text': text, 'mode': self.mode,
                'persona': recipient.persona, 'scope_id': recipient.scope_id,
                'view_revision': view['view_revision'], 'complete_corpus': False,
                'native_context': 'existing-persona', 'evidence_limited': True}
