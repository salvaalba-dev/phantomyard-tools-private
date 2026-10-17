"""Read the existing default-persona observation without opening native stores."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat

from assistant import IDENTIFIER, safe_default

MAX_BYTES = 16384


class RuntimeDefault:
    """Server-owned callable for ScopedBackend.default_report_loader.

    Reuse assistant.py's observation file. This does not run a model, read a
    vault, infer a counterpart, or grant conversation access. Refresh remains
    the responsibility of the installation's existing observation mechanism.
    """
    def __init__(self, path, *, organization, max_age=1800, clock=None):
        self.path = Path(path)
        if (not self.path.is_absolute() or not isinstance(organization, str)
                or not IDENTIFIER.fullmatch(organization)
                or type(max_age) is not int or not 1 <= max_age <= 86400
                or clock is not None and not callable(clock)):
            raise ValueError('A fixed organization observation path and bounded freshness are required')
        self.organization, self.max_age = organization, max_age
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def __call__(self):
        path = self.path
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError('Linked runtime observations are not accepted')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError('A bounded regular runtime observation is required')
            # Windows file ACLs are operator-managed; POSIX mode checks do not
            # model their effective access. Never widen permissions here.
            if os.name != 'nt' and info.st_mode & 0o022:
                raise ValueError('Runtime observation must not be writable by other accounts')
            raw = stream.read(MAX_BYTES + 1)
            final = os.fstat(stream.fileno())
            if len(raw) > MAX_BYTES or (info.st_size, info.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
                raise ValueError('Runtime observation changed during reading')

        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError('Duplicate runtime observation field')
                value[key] = item
            return value

        document = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(document, dict) or document.get('org') != self.organization:
            raise ValueError('Runtime observation belongs to another organization')
        checked = document.get('checked_at')
        if not isinstance(checked, str):
            raise ValueError('Runtime observation time is required')
        checked = datetime.fromisoformat(checked)
        now = self.clock()
        if checked.tzinfo is None or now.tzinfo is None or not 0 <= (now - checked).total_seconds() <= self.max_age:
            raise ValueError('Refresh the expired or future runtime observation')
        clean = safe_default({'default_persona': {
            'resolved': document.get('persona'), 'provenance': document.get('provenance'),
            'exists': document.get('exists'), 'served': document.get('served')}})
        return {'default_persona': {'resolved': clean['persona'], 'provenance': clean['provenance'],
                                    'exists': True, 'served': True}}
