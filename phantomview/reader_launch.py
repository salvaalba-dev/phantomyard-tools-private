"""Explicit Linux reader host; no installation, discovery or policy generation."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import sys
import threading
from urllib.parse import urlsplit

from authority_publication import PublishedAuthority
from handoff_client import DaemonReaderPolicy, _destination
from identified_reader import PublishedReader, signed_access
from organization_authority import _parse, _read
from projection_review import PublishedProjection
from session_audit import Ledger
from trusted_handoff import DaemonPeerPolicy


PATHS = {'authority_directory', 'index_path', 'source_path', 'projection_root',
         'audit_path', 'socket_path'}
FIELDS = PATHS | {'schema_version', 'organization', 'actor', 'identities', 'origin',
                  'port', 'reader_uid', 'issuer_uid', 'socket_group',
                  'conversation_socket', 'authority_max_age', 'session_seconds'}


def validate(value):
    """Validate a fixed operator document, never a browser-supplied request."""
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('Use exactly the fields in reader-launch.example.json')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Reader launch schema_version must be 1')
    for field in ('organization', 'actor'):
        if not isinstance(value[field], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value[field]):
            raise ValueError('Explicit organization and persona identifiers required')
    for field in ('reader_uid', 'issuer_uid', 'socket_group'):
        if type(value[field]) is not int or not 0 < value[field] < 2**32 - 1:
            raise ValueError('Explicit positive Linux account and group IDs required')
    if value['reader_uid'] == value['issuer_uid']:
        raise ValueError('Reader and native daemon accounts must differ')
    for field, lower, upper in (('port', 1024, 65535), ('authority_max_age', 1, 3600),
                                 ('session_seconds', 60, 3600)):
        if type(value[field]) is not int or not lower <= value[field] <= upper:
            raise ValueError('Port, authority lease or session duration is out of range')
    keys = value['identities']
    if (type(keys) is not list or not 1 <= len(keys) <= 64 or
            any(not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key) for key in keys)
            or len(set(keys)) != len(keys)):
        raise ValueError('Configure the reviewed public signer allowlist')
    origin = value['origin']
    try:
        parsed = urlsplit(origin) if isinstance(origin, str) else None
        if (not parsed or parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                or origin != 'https://' + parsed.netloc or any(ord(c) <= 32 or ord(c) == 127 for c in origin)):
            raise ValueError
        _ = parsed.port
    except ValueError:
        raise ValueError('Configure one canonical HTTPS origin without a path or credentials') from None
    selected = PATHS | ({'conversation_socket'} if value['conversation_socket'] is not None else set())
    for field in selected:
        path = value[field]
        if (not isinstance(path, str) or not path.isascii() or not path.startswith('/') or path == '/'
                or path.startswith('//') or PurePosixPath(path).as_posix() != path
                or '..' in PurePosixPath(path).parts or '\\' in path
                or any(ord(c) <= 32 or ord(c) == 127 for c in path)):
            raise ValueError('Use fixed normalized absolute Linux paths')
    if len({value[field] for field in selected}) != len(selected):
        raise ValueError('Reader paths must not alias one another')
    for field in ('socket_path', 'conversation_socket'):
        if value[field] is not None and len(value[field]) > 100:
            raise ValueError('Unix socket paths must be at most 100 bytes')
    return dict(value, identities=list(keys))


def load(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or path.suffix != '.json':
        raise ValueError('Select an absolute protected JSON launch file')
    if os.name == 'posix':
        info, parent = path.lstat(), path.parent.lstat()
        if (info.st_uid not in {0, os.geteuid()} or parent.st_uid not in {0, os.geteuid()}
                or not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022):
            raise ValueError('Launch file and protected parent must be operator-owned')
    return validate(_parse(_read(path), '.json'))


def preflight(config):
    """Read-only check: no socket, audit creation, model call or publication."""
    config = validate(config)
    DaemonPeerPolicy(config['issuer_uid'])
    if os.getuid() != config['reader_uid']:
        raise ValueError('Run as the configured nonroot reader account')
    groups = {os.getgid(), *os.getgroups()}
    if config['socket_group'] not in groups:
        raise ValueError('Reader must already belong to the reviewed handoff group')
    signed_access()
    authority = PublishedAuthority(config['authority_directory'], config['index_path'],
        config['organization'], config['source_path'], max_age=config['authority_max_age'])
    directory = authority()
    projection = PublishedProjection(config['projection_root'], authority.read, authority.snapshot)
    catalog = projection.catalog()
    if (config['actor'] not in directory.scope.policy['personas']
            or catalog['organization'] != config['organization']
            or catalog['authority_revision'] != directory.authority_revision):
        raise ValueError('Current approved projection must authorize the configured issuer')
    for field in ('socket_path', 'audit_path'):
        path = Path(config[field])
        for component in (path.parent, *path.parent.parents):
            if component.is_symlink():
                raise ValueError('Reader paths must not traverse links')
        info = path.parent.stat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.getuid()}
                or info.st_mode & 0o022):
            raise ValueError('Provision protected socket and audit parents before launch')
        if field == 'socket_path' and (path.exists() or path.is_symlink()):
            raise ValueError('Handoff path exists; inspect it without automatic removal')
        if field == 'audit_path' and (path.exists() or path.is_symlink()):
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise ValueError('Existing audit file must be reader-owned and mode 0600')
    if config['conversation_socket'] is not None:
        target = _destination(config['conversation_socket'], DaemonReaderPolicy(config['issuer_uid']))
        info = Path(target).stat()
        if info.st_gid not in groups or stat.S_IMODE(info.st_mode) != 0o660:
            raise ValueError('Native socket must use its reviewed reader group and mode 0660')
    return authority


def build(config, authority):
    """Create the existing assembly only after successful preflight."""
    return PublishedReader(authority=authority, projection_root=config['projection_root'],
        actor=config['actor'], identities=config['identities'], origin=config['origin'], port=config['port'],
        issuer_uid=config['issuer_uid'], socket_path=config['socket_path'], socket_group=config['socket_group'],
        audit=Ledger(config['audit_path']), session_seconds=config['session_seconds'],
        conversation_socket=config['conversation_socket'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--check', action='store_true', help='Read-only preflight; start nothing')
    args = parser.parse_args(argv)
    try:
        config = load(args.config)
        authority = preflight(config)
        if args.check:
            print(json.dumps({'status': 'preflight-passed', 'assistant_enabled': config['conversation_socket'] is not None}))
            return 0
        os.umask(0o077)
        reader = build(config, authority)
        stop = threading.Event()
        previous = {kind: signal.signal(kind, lambda *_: stop.set()) for kind in (signal.SIGTERM, signal.SIGINT)}
        try:
            reader.serve(stop_event=stop)
        finally:
            for kind, handler in previous.items():
                signal.signal(kind, handler)
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Never print raw configuration, identities, source content or exception text.
        print('Reader launch refused. Check account, protected launch file, current authority, approved projection, '
              'socket ownership and the reviewed phantomblog[access] environment; see READER_LAUNCH.md.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
