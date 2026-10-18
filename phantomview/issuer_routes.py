"""Protected host routes; never accept routing claims from a browser or frame."""
import json
from pathlib import PurePosixPath
import re


FIELDS = {'actor', 'identities', 'issuer_uid', 'socket_path', 'socket_group', 'conversation_socket'}


def validate_routes(primary, additional=None, *, reader_uid=None, occupied=()):
    if additional is None:
        additional = []
    if not isinstance(additional, list) or len(additional) > 15:
        raise ValueError('At most sixteen explicit issuer routes are supported')
    actors, identities, paths = set(), set(), set(occupied)
    rows = [primary, *additional]
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError('Use exactly the protected issuer route fields')
        actor = row['actor']
        if (not isinstance(actor, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', actor)
                or actor in actors):
            raise ValueError('Issuer personas must be explicit and unique')
        actors.add(actor)
        for field in ('issuer_uid', 'socket_group'):
            if type(row[field]) is not int or not 0 < row[field] < 2**32 - 1:
                raise ValueError('Explicit positive issuer account and socket group required')
        if row['issuer_uid'] == reader_uid:
            raise ValueError('Reader and issuer accounts must differ')
        keys = row['identities']
        if (not isinstance(keys, (list, tuple)) or not 1 <= len(keys) <= 64
                or any(not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key) for key in keys)
                or len(set(keys)) != len(keys) or identities.intersection(keys)):
            raise ValueError('Each issuer requires a nonempty disjoint public signer allowlist')
        identities.update(keys)
        for field in ('socket_path', 'conversation_socket'):
            path = row[field]
            if path is None and field == 'conversation_socket':
                continue
            if (not isinstance(path, str) or not path.isascii() or not path.startswith('/')
                    or path.startswith('//') or path == '/' or len(path) > 100
                    or PurePosixPath(path).as_posix() != path or '..' in PurePosixPath(path).parts
                    or '\\' in path or any(ord(c) <= 32 or ord(c) == 127 for c in path)
                    or path in paths):
                raise ValueError('Every issuer socket needs a distinct normalized absolute path')
            paths.add(path)
    return json.loads(json.dumps(rows))
