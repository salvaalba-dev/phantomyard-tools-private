"""Inactive native-service client; never expose this function as a model tool."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import sys
import time
from urllib.parse import urlsplit

from trusted_handoff import MAX_FRAME, REQUEST_SECONDS, _read, _unique, validate_request


@dataclass(frozen=True)
class ReaderPolicy:
    receiver_uid: int
    model_uids: frozenset[int]

    def __post_init__(self):
        if sys.platform != 'linux' or not hasattr(socket, 'SO_PEERCRED'):
            raise ValueError('Native handoff requires Linux kernel peer credentials')
        if (type(self.receiver_uid) is not int or self.receiver_uid < 0 or os.getuid() == 0
                or self.receiver_uid == os.getuid() or not isinstance(self.model_uids, frozenset)
                or not self.model_uids or any(type(uid) is not int or uid <= 0 for uid in self.model_uids)
                or self.receiver_uid in self.model_uids or os.getuid() in self.model_uids):
            raise ValueError('Native issuer, reader and model accounts must be isolated')

    def verify(self, connection):
        if connection.family != socket.AF_UNIX:
            raise ValueError('A private Unix-domain connection is required')
        pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                              struct.calcsize('3i')))
        if pid <= 0 or uid != self.receiver_uid:
            raise ValueError('Unexpected reader process account')


def _destination(path, policy):
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError('A fixed absolute private socket path is required')
    parent, target = path.parent.stat(), path.stat()
    if (parent.st_uid not in {0, policy.receiver_uid} or stat.S_IMODE(parent.st_mode) & 0o022
            or not stat.S_ISSOCK(target.st_mode) or target.st_uid != policy.receiver_uid
            or stat.S_IMODE(target.st_mode) & 0o007):
        raise ValueError('Private reader socket ownership or permissions are invalid')
    return str(path)


def request_access(path, policy, expected_origin, authorization, context):
    """Return a fragment link only after authenticating the reader process account.

    Trusted native code supplies the proven direct sender, allowlist decision and
    scope. No network fallback, inference, logging, retries or message delivery.
    A lost reply requires a fresh signed event, never replay of the old request.
    """
    try:
        if not isinstance(policy, ReaderPolicy) or not isinstance(expected_origin, str):
            raise ValueError('A fixed reader policy and HTTPS origin are required')
        origin = urlsplit(expected_origin)
        if (any(ord(char) < 33 for char in expected_origin)
                or origin.scheme != 'https' or not origin.hostname or origin.username is not None
                or origin.password is not None or origin.path or origin.query or origin.fragment
                or expected_origin != 'https://' + origin.netloc):
            raise ValueError('A canonical HTTPS reader origin is required')
        # Force port validation without deriving a destination from the response.
        _ = origin.port
        if not isinstance(context, dict) or set(context) != {
                'channel', 'sender', 'direct', 'principal_authenticated', 'scope_id'}:
            raise ValueError('An explicit native channel context is required')
        document = validate_request({'schema_version': 1, 'authorization': authorization} | context)
        raw = json.dumps(document, separators=(',', ':'), allow_nan=False).encode()
        if len(raw) > MAX_FRAME:
            raise ValueError('Handoff request exceeds bounds')
        destination = _destination(path, policy)
        deadline = time.monotonic() + REQUEST_SECONDS
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(REQUEST_SECONDS)
            connection.connect(destination)
            policy.verify(connection)  # No authorization or identity bytes before this check.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError('Handoff deadline exceeded')
            connection.settimeout(remaining)
            connection.sendall(struct.pack('!I', len(raw)) + raw)
            size = struct.unpack('!I', _read(connection, 4, deadline))[0]
            if not 0 < size <= MAX_FRAME:
                raise ValueError('Handoff response exceeds bounds')
            result = json.loads(_read(connection, size, deadline), object_pairs_hook=_unique)
        if (not isinstance(result, dict) or set(result) != {'schema_version', 'link'}
                or type(result['schema_version']) is not int or result['schema_version'] != 1
                or not isinstance(result['link'], str)
                or not re.fullmatch(re.escape(expected_origin) + r'/#c=[A-Za-z0-9_-]{43}', result['link'])):
            raise ValueError('Invalid private handoff response')
        return result['link']
    except (OSError, ValueError, TypeError, KeyError, RecursionError, struct.error):
        raise ValueError('Verified access handoff failed; request a fresh link through the native channel') from None
