"""Opt-in private authority publication inside the existing collector lifecycle."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

import yaml

from channel_identity import HumanDirectory
from organization_authority import MAX_BYTES, OrganizationAuthority, _parse, _read


META = '_phantomview_publication'


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _absolute(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Explicit absolute publication paths required')
    return path


def private_directory(path):
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked publication directory')
    info = path.stat()
    if (not stat.S_ISDIR(info.st_mode) or os.name == 'posix' and
            (info.st_uid != os.geteuid() or info.st_mode & 0o027)):
        raise ValueError('Private producer-owned publication directory required')
    return info


class AuthorityPublication:
    """Producer-owned directory, fixed private file; never a static asset directory."""
    def __init__(self, directory, organization, *, clock=time.time):
        if not isinstance(organization, str) or not organization:
            raise ValueError('Explicit publication organization required')
        self.directory = _absolute(directory)
        application = Path(__file__).resolve().parent
        if self.directory == application or application in self.directory.parents:
            raise ValueError('Authority publication must be outside the application directory')
        self.path = self.directory / 'organization.json'
        self.organization, self.clock = organization, clock

    def _replace(self, document):
        parent = private_directory(self.directory)
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                    os.name == 'posix' and (info.st_uid != os.geteuid() or info.st_mode & 0o027)):
                raise ValueError('Unsafe existing authority publication')
            existing = _parse(_read(self.path), '.json')
            marker = existing.get(META, {}) if isinstance(existing, dict) else {}
            if (not isinstance(marker, dict) or marker.get('organization') != self.organization
                    and existing != {'status': 'unavailable', 'organization': self.organization}):
                raise ValueError('Existing file is not owned by this authority publication')
        raw = json.dumps(document, allow_nan=False).encode()
        if len(raw) > MAX_BYTES:
            raise ValueError('Authority publication exceeds size limit')
        fd, temporary = tempfile.mkstemp(prefix='.authority-', dir=self.directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                if os.name == 'posix':
                    os.fchown(stream.fileno(), -1, parent.st_gid)
                    os.fchmod(stream.fileno(), 0o640)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def unavailable(self):
        self._replace({'status': 'unavailable', 'organization': self.organization})

    def publish(self, observer, state):
        """Bind a fresh source reread to the exact input captured during collect()."""
        selected = observer.config.get('org_files', [])
        if any(_absolute(source) == self.path for source in selected):
            raise ValueError('Authority publication must never overwrite its source')
        try:
            snapshot = state.get('snapshot')
            if (state.get('error') or not isinstance(snapshot, dict) or len(selected) != 1
                    or not isinstance(snapshot.get('digest'), str)
                    or not re.fullmatch(r'[a-f0-9]{64}', snapshot['digest'])
                    or snapshot.get('digest') != (observer.snapshot or {}).get('digest')
                    or snapshot.get('collected_at') != (observer.snapshot or {}).get('collected_at')):
                raise ValueError('Current successful single-source collection required')
            source = str(_absolute(selected[0]))
            rows = snapshot.get('organizations', [])
            if len(rows) != 1 or rows[0].get('id') != self.organization or rows[0].get('source') != source:
                raise ValueError('Publication organization/source mismatch')
            org = OrganizationAuthority(source, self.organization).read()
            if META in org or org != observer.organization_inputs.get(source):
                raise ValueError('Source changed after collection')
            timestamp = self.clock()
            if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
                raise ValueError('Invalid publication time')
            document = dict(org)
            document[META] = {'schema_version': 1, 'source': source, 'organization': self.organization,
                              'organization_revision': revision(org), 'snapshot_digest': snapshot['digest'],
                              'published_at': timestamp}
            self._replace(document)
        except (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError, yaml.YAMLError):
            # If invalidation itself fails, propagate failure; the reader's lease
            # still bounds the lifetime of any previously valid publication.
            self.unavailable()
            raise ValueError('Authority publication unavailable; check current source and private target') from None


class PublishedAuthority:
    """Fresh private publication + current index; no direct source access required."""
    def __init__(self, directory, index, organization, source, *, max_age, clock=time.time):
        self.path = _absolute(directory) / 'organization.json'
        self.index, self.source = _absolute(index), str(_absolute(source))
        if type(max_age) is not int or not 1 <= max_age <= 3600:
            raise ValueError('Explicit authority lease between 1 and 3600 seconds required')
        self.organization, self.max_age, self.clock = organization, max_age, clock

    def read(self):
        try:
            org = OrganizationAuthority(self.path, self.organization).read()
            metadata = org.pop(META)
            if (not isinstance(metadata, dict) or set(metadata) != {
                    'schema_version', 'source', 'organization', 'organization_revision',
                    'snapshot_digest', 'published_at'} or type(metadata['schema_version']) is not int
                    or metadata['schema_version'] != 1 or metadata['source'] != self.source
                    or metadata['organization'] != self.organization
                    or not isinstance(metadata['snapshot_digest'], str)
                    or not re.fullmatch(r'[a-f0-9]{64}', metadata['snapshot_digest'])
                    or metadata['organization_revision'] != revision(org)):
                raise ValueError('Publication binding mismatch')
            published = metadata['published_at']
            age = self.clock() - published
            if type(published) not in (int, float) or not math.isfinite(age) or not 0 <= age < self.max_age:
                raise ValueError('Authority publication expired or future-dated')
            index = _parse(_read(self.index), '.json')
            snapshot = index.get('snapshot', {})
            if (index.get('error') or index.get('config', {}).get('org_files') != [self.source]
                    or snapshot.get('digest') != metadata['snapshot_digest']
                    or [(row.get('id'), row.get('source')) for row in snapshot.get('organizations', [])]
                    != [(self.organization, self.source)]):
                raise ValueError('Current index does not match authority publication')
            return org
        except (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError, yaml.YAMLError):
            raise ValueError('Current private organization publication is unavailable') from None

    def __call__(self):
        return HumanDirectory(self.read())
