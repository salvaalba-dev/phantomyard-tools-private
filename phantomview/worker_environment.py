"""Closed ordinary-worker environment contract; no ambient or vault imports."""
from pathlib import PurePosixPath
from types import MappingProxyType


MODEL_CREDENTIALS = frozenset({
    'PHANTOMBOT_PI_API_KEY',
    'PHANTOMBOT_JEV_API_KEY',
    'PHANTOMBOT_GEMINI_API_KEY',
    'PHANTOMBOT_OPENAI_COMPATIBLE_API_KEY',
})
LOCATION_KEYS = frozenset({
    'HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME',
    'PHANTOMBOT_CONFIG', 'PHANTOMBOT_PERSONAS_DIR',
})
BINDING_KEYS = frozenset({'PHANTOMVIEW_WORKER_PERSONA', 'PHANTOMVIEW_WORKER_UID'})
ALLOWED_KEYS = MODEL_CREDENTIALS | LOCATION_KEYS | BINDING_KEYS | {'PATH', 'LANG', 'LC_ALL'}
UNAVAILABLE = 'A reviewed model-only worker environment is required'


def _strings(values):
    if (not isinstance(values, dict) or len(values) > len(ALLOWED_KEYS)
            or any(not isinstance(key, str) or not isinstance(value, str)
                   or not key or '\0' in key or '\0' in value
                   for key, value in values.items())):
        raise ValueError(UNAVAILABLE)
    try:
        size = sum(len(key.encode('utf-8')) + len(value.encode('utf-8'))
                   for key, value in values.items())
    except UnicodeError:
        raise ValueError(UNAVAILABLE) from None
    if size > 65536:
        raise ValueError(UNAVAILABLE)


def model_credentials(values):
    """Validate an explicitly selected map, never a complete persona vault.

    Unknown keys reject the selection instead of silently stripping a mixed
    channel/model store. Values are never placed in errors or public metadata.
    This function does not open, decrypt, copy or sanitize any source store.
    """
    _strings(values)
    if (set(values) - MODEL_CREDENTIALS
            or any(not value or value != value.strip() or '\n' in value or '\r' in value
                   for value in values.values())):
        raise ValueError(UNAVAILABLE)
    return dict(values)


def environment(values):
    """Snapshot only reviewed locations, model secrets and fixed role binding.

    This checks the launch contract, not ownership, content or reachability of
    the referenced filesystem. A separate worker store is still mandatory.
    """
    _strings(values)
    if set(values) - ALLOWED_KEYS:
        raise ValueError(UNAVAILABLE)
    model_credentials({key: value for key, value in values.items() if key in MODEL_CREDENTIALS})
    for key in LOCATION_KEYS & values.keys():
        path = PurePosixPath(values[key])
        if (not values[key].startswith('/') or values[key].startswith('//')
                or '..' in path.parts or '\\' in values[key]
                or any(char in values[key] for char in ('\n', '\r'))):
            raise ValueError(UNAVAILABLE)
    if 'PATH' in values:
        entries = values['PATH'].split(':')
        if (not entries or any(not entry.startswith('/') or entry.startswith('//')
                              or '..' in PurePosixPath(entry).parts or '\\' in entry
                              or '\n' in entry or '\r' in entry for entry in entries)):
            raise ValueError(UNAVAILABLE)
    if any(values.get(key, 'C.UTF-8') not in {'C', 'C.UTF-8', 'en_US.UTF-8'}
           for key in ('LANG', 'LC_ALL')):
        raise ValueError(UNAVAILABLE)
    return MappingProxyType(dict(values))
