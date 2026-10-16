"""Inactive ordinary text forwarding; no access issuance or transport delivery API.

Only a protected native host may supply Route. It is not authentication when
constructed from browser input or model output. Worker lifecycle remains external.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import struct
import sys
import threading
import time
import uuid

from trusted_handoff import _unique

MAX_FRAME = 65536
MAX_TEXT = 32768
MAX_SECONDS = 120
FAILURE = 'Ordinary conversation forwarding unavailable'


@dataclass(frozen=True)
class AccountPolicy:
    issuer_uid: int
    worker_uid: int
    reader_uid: int
    model_uids: frozenset[int]

    def check(self, role):
        values = (self.issuer_uid, self.worker_uid, self.reader_uid)
        if (sys.platform != 'linux' or not hasattr(socket, 'SO_PEERCRED')
                or any(type(uid) is not int or uid <= 0 for uid in values)
                or len(set(values)) != 3 or not isinstance(self.model_uids, frozenset)
                or self.worker_uid not in self.model_uids
                or any(type(uid) is not int or uid <= 0 for uid in self.model_uids)
                or self.issuer_uid in self.model_uids or self.reader_uid in self.model_uids
                or role not in {'issuer', 'worker'}
                or os.getuid() != (self.issuer_uid if role == 'issuer' else self.worker_uid)):
            raise ValueError(FAILURE)

    def verify(self, connection, role):
        self.check(role)
        if connection.family != socket.AF_UNIX:
            raise ValueError(FAILURE)
        pid, uid, _ = struct.unpack('3i', connection.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
        expected = self.worker_uid if role == 'issuer' else self.issuer_uid
        if pid <= 0 or uid != expected:
            raise ValueError(FAILURE)


@dataclass(frozen=True, repr=False)
class Route:
    channel: str
    sender: str
    conversation: str
    tier: str
    audience: str

    def validate(self):
        pattern = r'[1-9][0-9]{0,15}' if self.channel == 'telegram' else r'[a-f0-9]{64}'
        if (self.channel not in {'telegram', 'phantomchat'}
                or not isinstance(self.sender, str) or not re.fullmatch(pattern, self.sender)
                or (self.channel == 'telegram' and int(self.sender) > 2**53 - 1)
                or self.conversation != self.sender or self.tier not in {'principal', 'relay', 'open'}
                or self.audience != ('private' if self.tier == 'principal' else 'shared')):
            raise ValueError(FAILURE)


@dataclass(frozen=True, repr=False)
class BoundReply:
    route: Route
    text: str


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > MAX_TEXT:
        raise ValueError(FAILURE)
    return value


def _reserved(text):
    return re.match(r'^\s*/phantomview(?:\s|@|$)', text, re.IGNORECASE)


def _read(connection, size, deadline, cancelled=None):
    result = bytearray()
    while len(result) < size:
        if (cancelled is not None and cancelled.is_set()) or time.monotonic() >= deadline:
            raise ValueError(FAILURE)
        connection.settimeout(min(0.1, deadline - time.monotonic()))
        try:
            part = connection.recv(size - len(result))
        except socket.timeout:
            continue
        if not part:
            raise ValueError(FAILURE)
        result.extend(part)
    return bytes(result)


def _receive(connection, deadline, cancelled=None):
    size = struct.unpack('!I', _read(connection, 4, deadline, cancelled))[0]
    if not 0 < size <= MAX_FRAME:
        raise ValueError(FAILURE)
    return json.loads(_read(connection, size, deadline, cancelled), object_pairs_hook=_unique)


def _send(connection, document, deadline):
    raw = json.dumps(document, separators=(',', ':'), allow_nan=False, ensure_ascii=False).encode('utf-8')
    remaining = deadline - time.monotonic()
    if len(raw) > MAX_FRAME or remaining <= 0:
        raise ValueError(FAILURE)
    connection.settimeout(min(3, remaining))
    connection.sendall(struct.pack('!I', len(raw)) + raw)


def _destination(path, policy):
    target = Path(path)
    if not target.is_absolute() or target.is_symlink():
        raise ValueError(FAILURE)
    for parent in target.parents:
        info = parent.stat()
        if (parent.is_symlink() or info.st_uid not in {0, policy.worker_uid}
                or stat.S_IMODE(info.st_mode) & 0o022):
            raise ValueError(FAILURE)
    info = target.stat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != policy.worker_uid
            or stat.S_IMODE(info.st_mode) & 0o007):
        raise ValueError(FAILURE)
    return str(target)


class Forwarder:
    """Long-lived fixed-persona client with bounded active conversations.

    At most one active turn per route and eight overall. The native host must
    implement its normal queue/control behavior above this rejection boundary.
    No retries, model execution, logging or transport sends occur here.
    """
    def __init__(self, *, persona, socket_path, policy):
        if not isinstance(policy, AccountPolicy) or not isinstance(persona, str) or not re.fullmatch(
                r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', persona):
            raise ValueError(FAILURE)
        policy.check('issuer')
        self.persona, self.path, self.policy = persona, socket_path, policy
        self._active, self._lock = set(), threading.Lock()

    def forward(self, route, text, *, seconds=MAX_SECONDS, cancelled=None):
        key = None
        claimed = False
        try:
            self.policy.check('issuer')
            if not isinstance(route, Route) or type(seconds) is not int or not 1 <= seconds <= MAX_SECONDS:
                raise ValueError(FAILURE)
            route.validate()
            _text(text)
            if _reserved(text) or (cancelled is not None and cancelled.is_set()):
                raise ValueError(FAILURE)
            key = (route.channel, route.conversation)
            with self._lock:
                if key in self._active or len(self._active) >= 8:
                    raise ValueError(FAILURE)
                self._active.add(key)
                claimed = True
            job_id = uuid.uuid4().hex
            deadline = time.monotonic() + seconds
            document = {'schema_version': 1, 'kind': 'ordinary-turn', 'job_id': job_id,
                        'persona': self.persona, 'channel': route.channel, 'sender': route.sender,
                        'conversation': route.conversation, 'tier': route.tier, 'audience': route.audience,
                        'text': text, 'expires_at': int(time.time()) + seconds}
            destination = _destination(self.path, self.policy)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(min(3, seconds))
                connection.connect(destination)
                self.policy.verify(connection, 'issuer')  # Before any identity/prompt bytes.
                if cancelled is not None and cancelled.is_set():
                    raise ValueError(FAILURE)
                _send(connection, document, deadline)
                reply = _receive(connection, deadline, cancelled)
                if (not isinstance(reply, dict) or set(reply) != {'schema_version', 'kind', 'job_id', 'text'}
                        or type(reply['schema_version']) is not int or reply['schema_version'] != 1
                        or reply['kind'] != 'ordinary-reply' or reply['job_id'] != job_id
                        or time.monotonic() >= deadline or (cancelled is not None and cancelled.is_set())):
                    raise ValueError(FAILURE)
                return BoundReply(route, _text(reply['text']))  # Route comes only from this caller.
        except (OSError, ValueError, TypeError, KeyError, RecursionError, struct.error):
            raise ValueError(FAILURE) from None
        finally:
            if claimed:
                with self._lock:
                    self._active.discard(key)


@dataclass(frozen=True, repr=False)
class WorkerJob:
    job_id: str
    persona: str
    route: Route
    text: str
    deadline: float


class WorkerInbox:
    """Fixed-persona authenticated frame receiver, not a worker daemon.

    The embedding owns accepted sockets, cancellation, execution and process
    termination. A worker callback cannot extend this protocol's reply deadline.
    """
    def __init__(self, *, persona, policy):
        if not isinstance(policy, AccountPolicy) or not isinstance(persona, str) or not re.fullmatch(
                r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', persona):
            raise ValueError(FAILURE)
        policy.check('worker')
        self.persona, self.policy = persona, policy
        self._seen, self._lock = {}, threading.Lock()

    def receive(self, connection):
        try:
            self.policy.verify(connection, 'worker')  # Before reading attacker-controlled bytes.
            doc = _receive(connection, time.monotonic() + 3)
            fields = {'schema_version', 'kind', 'job_id', 'persona', 'channel', 'sender',
                      'conversation', 'tier', 'audience', 'text', 'expires_at'}
            if (not isinstance(doc, dict) or set(doc) != fields
                    or type(doc['schema_version']) is not int or doc['schema_version'] != 1
                    or doc['kind'] != 'ordinary-turn' or doc['persona'] != self.persona
                    or not isinstance(doc['job_id'], str) or not re.fullmatch(r'[a-f0-9]{32}', doc['job_id'])
                    or type(doc['expires_at']) is not int or not 0 < doc['expires_at'] - time.time() <= MAX_SECONDS):
                raise ValueError(FAILURE)
            route = Route(*(doc[key] for key in ('channel', 'sender', 'conversation', 'tier', 'audience')))
            route.validate()
            text = _text(doc['text'])
            if _reserved(text):
                raise ValueError(FAILURE)
            now = time.monotonic()
            with self._lock:
                self._seen = {key: expiry for key, expiry in self._seen.items() if expiry > now}
                if doc['job_id'] in self._seen or len(self._seen) >= 256:
                    raise ValueError(FAILURE)
                self._seen[doc['job_id']] = now + MAX_SECONDS + 3
            return WorkerJob(doc['job_id'], self.persona, route, text,
                             now + doc['expires_at'] - time.time())
        except (OSError, ValueError, TypeError, KeyError, RecursionError, struct.error):
            raise ValueError(FAILURE) from None

    def reply(self, connection, job, text):
        """Send plain text under the original ID; the issuer rejects expired replies.

        EOF/deadline checks are cooperative observations. They do not kill an
        ignoring model. The future worker runtime must terminate its actual child.
        """
        try:
            self.policy.verify(connection, 'worker')
            if not isinstance(job, WorkerJob) or job.persona != self.persona:
                raise ValueError(FAILURE)
            if select.select([connection], [], [], 0)[0]:
                # A peer must send one frame only; EOF or extra input cancels it.
                raise ValueError(FAILURE)
            _send(connection, {'schema_version': 1, 'kind': 'ordinary-reply',
                               'job_id': job.job_id, 'text': _text(text)}, job.deadline)
        except (OSError, ValueError, TypeError, KeyError, struct.error):
            raise ValueError(FAILURE) from None
