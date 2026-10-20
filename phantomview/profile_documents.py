"""Bounded, opt-in profile sources; collection never assigns information access."""
import hashlib
import os
from pathlib import Path
import re
import stat

NAMES = {'IDENTITY.md': 'Identity', 'SOUL.md': 'Persona profile'}
MAX_BYTES = 16384
SECRET = re.compile(r'nsec1[023456789acdefghjklmnpqrstuvwxyz]{20,}|'
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----|'
    r'(?:api[_ -]?key|password|access[_ -]?token|secret[_ -]?key)\s*[:=]\s*[^\s]{8,}', re.I)


def validate_document(value):
    if (not isinstance(value, dict) or set(value) != {'name', 'content', 'sha256'}
            or value['name'] not in NAMES or not isinstance(value['content'], str)
            or not value['content'].strip() or len(value['content'].encode('utf-8')) > MAX_BYTES
            or SECRET.search(value['content'])
            or hashlib.sha256(value['content'].encode('utf-8')).hexdigest() != value['sha256']):
        raise ValueError('A complete, bounded allowlisted profile source is required')
    return dict(value)


def collect(root, permitted):
    """Read two exact regular files only; memory, prompts and credentials stay out."""
    root = Path(root)
    if not root.is_absolute() or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('An explicit persona root without symlinks is required')
    result = []
    for name in sorted(NAMES):
        path = root / name
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or os.name == 'posix' and info.st_mode & 0o022 or info.st_size > MAX_BYTES):
                    continue
                raw = stream.read(MAX_BYTES + 1)
                after = os.fstat(stream.fileno())
                if (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                    continue
            content = raw.decode('utf-8')
            document = validate_document({'name': name, 'content': content,
                                          'sha256': hashlib.sha256(raw).hexdigest()})
            if permitted(content):
                result.append(document)
        except (OSError, UnicodeError, ValueError):
            continue
    return result
