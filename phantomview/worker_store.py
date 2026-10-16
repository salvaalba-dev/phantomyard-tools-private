"""Read one protected model-only credential document; never open persona vaults."""
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys

from worker_environment import model_credentials

MAX_BYTES = 65536
UNAVAILABLE = 'Protected model credential store unavailable'


def _binding(persona, worker_uid):
    if (not isinstance(persona, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', persona)
            or type(worker_uid) is not int or worker_uid <= 0):
        raise ValueError(UNAVAILABLE)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(UNAVAILABLE)
        result[key] = value
    return result


def encode_credentials(*, persona, worker_uid, credentials):
    """Return private provisioning bytes from an explicitly selected key map.

    Never print these bytes, place them in argv or publish them as a manifest.
    Provisioning/ownership changes are deliberately outside this module.
    """
    try:
        _binding(persona, worker_uid)
        selected = model_credentials(credentials)
        if not selected:
            raise ValueError(UNAVAILABLE)
        result = json.dumps({'schema_version': 1, 'persona': persona, 'worker_uid': worker_uid,
                             'credentials': selected}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(result) > MAX_BYTES:
            raise ValueError(UNAVAILABLE)
        return result
    except (TypeError, ValueError, UnicodeError):
        raise ValueError(UNAVAILABLE) from None


def decode_credentials(raw, *, persona, worker_uid):
    """Validate bytes only; parsing alone does not authenticate their origin."""
    try:
        _binding(persona, worker_uid)
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
            raise ValueError(UNAVAILABLE)
        document = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
        if (not isinstance(document, dict)
                or set(document) != {'schema_version', 'persona', 'worker_uid', 'credentials'}
                or type(document['schema_version']) is not int or document['schema_version'] != 1
                or type(document['worker_uid']) is not int or document['worker_uid'] != worker_uid
                or document['persona'] != persona):
            raise ValueError(UNAVAILABLE)
        selected = model_credentials(document['credentials'])
        if not selected:
            raise ValueError(UNAVAILABLE)
        return selected
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError(UNAVAILABLE) from None


def load_credentials(path, *, persona, worker_uid):
    """Linux worker only; walk protected parents with openat and no symlinks.

    Root owns every parent and the mode-0640 regular file. Its group is the
    worker's effective group. Other accounts must not belong to that group.
    Existing descriptors keep each validated parent pinned during the walk.
    """
    descriptors = []
    try:
        _binding(persona, worker_uid)
        if (sys.platform != 'linux' or os.getuid() != worker_uid or os.geteuid() != worker_uid
                or os.getegid() <= 0 or 0 in os.getgroups()
                or not isinstance(path, str) or not path.startswith('/') or path.startswith('//')
                or '\0' in path or '\\' in path or len(path.encode('utf-8')) > 4096
                or any(part in {'', '.', '..'} for part in path[1:].split('/'))):
            raise ValueError(UNAVAILABLE)
        parts = PurePosixPath(path).parts[1:]
        if not 1 <= len(parts) <= 32:
            raise ValueError(UNAVAILABLE)
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        directory_flags = os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
        directory = os.open('/', directory_flags)
        descriptors.append(directory)
        for part in (*parts[:-1], None):
            info = os.fstat(directory)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError(UNAVAILABLE)
            if part is not None:
                directory = os.open(part, directory_flags, dir_fd=directory)
                descriptors.append(directory)
        descriptor = os.open(parts[-1], flags | os.O_NONBLOCK, dir_fd=directory)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_gid != os.getegid()
                or stat.S_IMODE(before.st_mode) != 0o640 or before.st_nlink != 1
                or not 0 < before.st_size <= MAX_BYTES):
            raise ValueError(UNAVAILABLE)
        chunks, remaining = [], MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 8192))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_nlink) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_nlink):
            raise ValueError(UNAVAILABLE)
        return decode_credentials(b''.join(chunks), persona=persona, worker_uid=worker_uid)
    except (OSError, TypeError, ValueError, UnicodeError, AttributeError):
        raise ValueError(UNAVAILABLE) from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
