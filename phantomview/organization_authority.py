"""Opt-in raw-source authority loader; no cache, discovery, write or listener."""
import json
import os
from pathlib import Path
import stat

import yaml

from channel_identity import HumanDirectory


MAX_BYTES = 4 * 1024 * 1024


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate organization mapping key')
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError('Non-finite organization value')


class _UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        return _pairs((self.construct_object(key, deep=deep),
                       self.construct_object(value, deep=deep)) for key, value in node.value)


def _parse(raw, suffix):
    text = raw.decode('utf-8-sig')
    if suffix == '.json':
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
    depth = 0
    for count, event in enumerate(yaml.parse(text), 1):
        if count > 100000 or isinstance(event, yaml.AliasEvent):
            raise ValueError('Unsupported or oversized organization structure')
        if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
            depth += 1
        if depth > 64:
            raise ValueError('Organization nesting exceeds the limit')
        if isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
            depth -= 1
    return yaml.load(text, Loader=_UniqueLoader)


def _stamp(info):
    # Windows path/descriptor APIs can report different cached creation times.
    # POSIX ctime records metadata changes; Windows ctime does not have that meaning.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns if os.name == 'posix' else None)


class OrganizationAuthority:
    """Bind an operator-selected absolute source to exactly one organization.

    Source and parent-directory write permissions must exclude the model/browser.
    Windows ACLs and native account isolation require separate deployment checks.
    """
    def __init__(self, path, organization):
        self.path = Path(path)
        if (not self.path.is_absolute() or '..' in self.path.parts
                or self.path.suffix not in {'.yaml', '.yml', '.json'}
                or not isinstance(organization, str) or not organization):
            raise ValueError('Explicit absolute source and organization required')
        self.organization = organization

    def read(self):
        """Return a fresh validated document; never fall back to an older copy."""
        try:
            for path in (self.path, *self.path.parents):
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('Linked authority path')
            before = self.path.lstat()
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size > MAX_BYTES
                    or os.name == 'posix' and before.st_mode & 0o022):
                raise ValueError('Unprotected organization source')
            fd = os.open(self.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                         | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
            with os.fdopen(fd, 'rb') as stream:
                if _stamp(os.fstat(stream.fileno())) != _stamp(before):
                    raise ValueError('Organization changed while opening')
                raw = stream.read(MAX_BYTES + 1)
                if (_stamp(os.fstat(stream.fileno())) != _stamp(before)
                        or _stamp(self.path.lstat()) != _stamp(before)
                        or len(raw) != before.st_size or len(raw) > MAX_BYTES):
                    raise ValueError('Organization changed while reading')
            org = _parse(raw, self.path.suffix)
            if not isinstance(org, dict) or org.get('organization', {}).get('id') != self.organization:
                raise ValueError('Organization source mismatch')
            if HumanDirectory(org).scope.policy.get('view_access') is None:
                raise ValueError('Explicit viewer scope declarations required')
            return org
        except (OSError, ValueError, TypeError, AttributeError, UnicodeError,
                RecursionError, yaml.YAMLError):
            raise ValueError('Cannot load current organization authority; check source, format and permissions') from None

    def __call__(self):
        return HumanDirectory(self.read())
