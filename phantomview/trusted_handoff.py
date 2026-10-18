"""Opt-in Linux IPC with explicit whole-daemon or historical isolated trust.

No import starts a listener. The operator selects the policy in trusted host
configuration; channel context never chooses its own trust boundary.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import time

MAX_FRAME = 16384
REQUEST_SECONDS = 3.0


@dataclass(frozen=True)
class PeerPolicy:
    issuer_uid: int
    model_uids: frozenset[int]

    def __post_init__(self):
        if sys.platform != 'linux' or not hasattr(socket, 'SO_PEERCRED'):
            raise ValueError('Verified handoff requires Linux SO_PEERCRED; no network fallback')
        if (type(self.issuer_uid) is not int or self.issuer_uid <= 0
                or not isinstance(self.model_uids, frozenset) or not self.model_uids
                or any(type(uid) is not int or uid <= 0 for uid in self.model_uids)
                or self.issuer_uid in self.model_uids or os.getuid() in self.model_uids
                or self.issuer_uid == os.getuid()):
            raise ValueError('Channel issuer, reader and every model account must be isolated')

    def verify(self, connection):
        """Authenticate the connected process account before reading request bytes."""
        if connection.family != socket.AF_UNIX:
            raise ValueError('A private Unix-domain connection is required')
        size = struct.calcsize('3i')
        pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size))
        if pid <= 0 or uid != self.issuer_uid or uid in self.model_uids:
            raise ValueError('Untrusted channel-service peer')


@dataclass(frozen=True)
class DaemonPeerPolicy(PeerPolicy):
    """Explicit whole-daemon trust, including code with its account privileges.

    Kernel credentials authenticate an account, not a particular PID, channel
    message or safe model output. The reader still uses a separate account.
    """
    model_uids: frozenset[int] = frozenset()

    def __post_init__(self):
        if sys.platform != 'linux' or not hasattr(socket, 'SO_PEERCRED'):
            raise ValueError('Daemon handoff requires Linux kernel peer credentials')
        if (type(self.issuer_uid) is not int or self.issuer_uid <= 0
                or self.issuer_uid == os.getuid() or os.getuid() == 0
                or self.model_uids != frozenset() or not isinstance(self.model_uids, frozenset)):
            raise ValueError('Explicit nonroot daemon and separate reader accounts required')


def bind_listener(path, group_id):
    """Bind a new operator-selected Unix socket; never remove an existing path.

    Its private parent must be owned by the reader or root and not writable by
    group/others. Provision traversal and group membership outside this module.
    """
    if sys.platform != 'linux' or not hasattr(socket, 'SO_PEERCRED'):
        raise ValueError('Verified handoff requires Linux SO_PEERCRED')
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink() or not path.parent.is_dir()
            or any(parent.is_symlink() for parent in path.parents)
            or type(group_id) is not int or group_id < 0):
        raise ValueError('An absolute private socket path and explicit group are required')
    parent = path.parent.stat()
    if parent.st_uid not in {0, os.getuid()} or stat.S_IMODE(parent.st_mode) & 0o022:
        raise ValueError('Handoff directory must be protected from other writers')
    if path.exists():
        raise ValueError('Handoff socket path already exists; inspect it before restarting')
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        # The parent directory is already protected during bind/chmod/chown.
        listener.bind(str(path))
        os.chmod(path, 0o660)
        os.chown(path, -1, group_id)
        listener.listen(16)
        listener.settimeout(1.0)
        return listener
    except (OSError, ValueError):
        listener.close()
        raise


def _read(connection, length, deadline):
    output = bytearray()
    while len(output) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Handoff deadline exceeded')
        connection.settimeout(remaining)
        part = connection.recv(length - len(output))
        if not part:
            raise ValueError('Incomplete handoff frame')
        output.extend(part)
    return bytes(output)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate handoff field')
        result[key] = value
    return result


def _request(connection, deadline):
    length = struct.unpack('!I', _read(connection, 4, deadline))[0]
    if not 0 < length <= MAX_FRAME:
        raise ValueError('Handoff frame exceeds bounds')
    document = json.loads(_read(connection, length, deadline), object_pairs_hook=_unique)
    return validate_request(document)


def validate_request(document):
    """Shared version-one frame shape; identity still depends on the native peer."""
    fields = {'schema_version', 'authorization', 'channel', 'sender', 'direct',
              'principal_authenticated', 'scope_id'}
    if (not isinstance(document, dict) or set(document) != fields
            or type(document['schema_version']) is not int or document['schema_version'] != 1
            or not isinstance(document['authorization'], str)
            or not document['authorization'].startswith('Nostr ')
            or document['channel'] not in ('telegram', 'phantomchat')
            or not isinstance(document['sender'], str) or len(document['sender']) > 128
            or document['direct'] is not True or document['principal_authenticated'] is not True
            or not isinstance(document['scope_id'], str) or not document['scope_id']):
        raise ValueError('An explicit authenticated direct-message context and scope are required')
    return document


def serve_connection(connection, gate, policy, *, actor=None):
    """Process one authenticated peer connection and close it on every path.

    `gate` is an IdentifiedGate held by the reader. The signing event uses the
    unchanged NIP-98 payload/tags; persona and public origin come from this gate.
    Errors never echo credentials, identities, URLs or exception text. The caller
    must not log frames or returned grants. No model inference occurs here.
    """
    with connection:
        try:
            policy.verify(connection)
        except (OSError, ValueError, struct.error):
            return False  # Reject before reading or replying to an unknown account.
        deadline = time.monotonic() + REQUEST_SECONDS
        try:
            request = _request(connection, deadline)
            context = {key: request[key] for key in ('channel', 'sender', 'direct',
                                                     'principal_authenticated', 'scope_id')}
            link = gate.issue_identified(request['authorization'], gate.origin,
                                         persona=gate.policy['actor'] if actor is None else actor, **context)
            response = {'schema_version': 1, 'link': link}
            success = True
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            response = {'schema_version': 1, 'error': 'Verified access handoff denied'}
            success = False
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            raw = json.dumps(response, separators=(',', ':')).encode()
            if len(raw) > MAX_FRAME:
                return False
            connection.settimeout(remaining)
            connection.sendall(struct.pack('!I', len(raw)) + raw)
        except OSError:
            return False
        return success
