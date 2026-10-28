"""Observe document-matrix changes in the existing collection cycle; never publish."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

import yaml

from authority_publication import private_directory
from document_refresh import fingerprint, prepare
from organization_authority import MAX_BYTES, _parse, _read, _stamp


def native_writers(value):
    """Normalize an explicit bounded owner allowlist; never infer owners from disk."""
    names = (value,) if isinstance(value, str) else value
    if (not isinstance(names, (list, tuple)) or not 1 <= len(names) <= 16
            or any(not isinstance(name, str) or not name or name.strip() != name for name in names)
            or len(set(names)) != len(names)):
        raise ValueError('One to sixteen distinct explicit native writers required')
    return tuple(names)


def native_read(path, writer, group):
    """Observe an explicitly trusted native writer; this read never authorizes publication."""
    if os.name != 'posix':
        raise ValueError('Native writer trust requires POSIX identity checks')
    import grp
    import pwd
    uids = {pwd.getpwnam(name).pw_uid for name in native_writers(writer)}
    gid = grp.getgrnam(group).gr_gid
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError('Linked native manifest')
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES
            or before.st_uid not in uids or before.st_gid != gid or before.st_mode & 0o002):
        raise ValueError('Unexpected native manifest writer or permissions')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        if _stamp(os.fstat(stream.fileno())) != _stamp(before):
            raise ValueError('Native manifest changed while opening')
        raw = stream.read(MAX_BYTES + 1)
        if (_stamp(os.fstat(stream.fileno())) != _stamp(before)
                or _stamp(path.lstat()) != _stamp(before) or len(raw) != before.st_size):
            raise ValueError('Native manifest changed while reading')
    return raw


def source(path, reader=_read):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or path.suffix.lower() not in {'.json', '.yaml', '.yml'}:
        raise ValueError('Explicit protected structured source required')
    raw = reader(path)
    return path, raw, _parse(raw, path.suffix.lower()), reader


def replace(path, value):
    private_directory(path.parent)
    if path.exists() or path.is_symlink():
        _read(path)
        if os.name == 'posix' and (path.stat().st_uid != os.geteuid() or path.stat().st_mode & 0o077):
            raise ValueError('Producer-only report required')
    raw = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError('Document observation exceeds the report limit')
    fd, temporary = tempfile.mkstemp(prefix='.document-watch-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if os.name == 'posix':
                os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def observe(manifest_path, matrix_path, snapshot_path, config_path, directory, organization, *,
            clock=time.time, native_writer=None, native_group=None):
    """Write a private latest observation, including explicit failure without cached plans."""
    if not isinstance(organization, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}', organization):
        raise ValueError('Explicit organization required')
    directory = Path(directory)
    if not directory.is_absolute() or '..' in directory.parts:
        raise ValueError('Explicit report directory required')
    private_directory(directory)
    target = directory / 'document-watch.json'
    paths = [manifest_path, matrix_path, snapshot_path, config_path]
    if any(Path(path).resolve() == target.resolve() for path in paths):
        raise ValueError('A report must never overwrite an input')
    previous = None
    if target.exists() or target.is_symlink():
        previous = _parse(_read(target), '.json')
        if not isinstance(previous, dict) or previous.get('organization') != organization:
            raise ValueError('Existing report belongs to another producer')
    checked_at = clock()
    report = {'schema_version': 1, 'organization': organization, 'checked_at': checked_at,
              'publication_performed': False, 'status': 'unavailable'}
    try:
        if (native_writer is not None) != (native_group is not None):
            raise ValueError('Native writer and group must be explicitly paired')
        if native_writer is not None:
            native_writer = native_writers(native_writer)
        manifest_reader = (lambda path: native_read(path, native_writer, native_group)) if native_writer is not None else _read
        inputs = [source(manifest_path, manifest_reader), *[source(path) for path in paths[1:]]]
        manifest, matrix, state, config = [item[2] for item in inputs]
        snapshot = state.get('snapshot', state) if isinstance(state, dict) else None
        if (not isinstance(config, dict) or not isinstance(snapshot, dict)
                or not isinstance(snapshot.get('actors'), list)
                or manifest.get('manifest', {}).get('org') != organization
                or matrix.get('organization') != organization
                or not any(Path(path).resolve() == inputs[0][0].resolve() for path in config.get('docs_manifests', []))):
            raise ValueError('Selected collector sources and organization must match')
        from phantomview import search_policy
        plan = prepare(manifest, inputs[0][0], matrix, snapshot['actors'], search_policy,
                       config.get('working_documents', []), cache=config.get('working_document_cache'))
        # Refuse a mixed observation if any structured input changed during the scan.
        if any(reader(path) != raw for path, raw, _, reader in inputs):
            raise ValueError('Document inputs changed during observation')
        comparison = dict(plan)
        comparison['input_revisions'] = plan['input_revisions'] | {
            'actors': fingerprint([{key: actor.get(key) for key in ('id', 'org', 'role', 'searchable')}
                                   for actor in snapshot['actors']])}
        revision = fingerprint(comparison)
        stable = previous is not None and previous.get('status') == 'observed' and previous.get('revision') == revision
        report.update(status='observed', revision=revision, changed=not stable,
                      changed_at=previous['changed_at'] if stable else checked_at, plan=plan)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, UnicodeError, RecursionError, yaml.YAMLError):
        # Never export source paths, parser excerpts or the previous plan as fresh evidence.
        report['reason'] = 'document-input-unavailable-or-invalid'
    replace(target, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'matrix', 'snapshot', 'config', 'report-dir', 'organization'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--native-writer', action='append',
                        help='Explicit trusted POSIX owner of the native manifest only; repeat for each owner')
    parser.add_argument('--native-group', help='Explicit trusted POSIX group of the native manifest only')
    args = parser.parse_args(argv)
    report = observe(args.manifest, args.matrix, args.snapshot, args.config, args.report_dir, args.organization,
                     native_writer=args.native_writer, native_group=args.native_group)
    print(json.dumps({'status': report['status'], 'publication_performed': False,
                      'changed': report.get('changed')}, sort_keys=True))
    return 0 if report['status'] == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
