"""Opt-in host binding for existing resource reviews and captured KB payloads."""
import os
from pathlib import Path
import stat

from organization_authority import _parse, _read
from resource_review import MAX_REVISION_BYTES, _validate, reviewed_catalog
from scoped_knowledge import HEX, MAX_PAYLOAD_BYTES, PrivateKBStore

FIELDS = {'review_path', 'payload_directory'}


def coordinates(value):
    if (not isinstance(value, dict) or set(value) != FIELDS
            or any(not isinstance(value[key], str) or not value[key] for key in FIELDS)):
        raise ValueError('Reviewed knowledge requires one protected review path and payload directory')
    return dict(value)


def _protected(path, *, directory=False, limit=None):
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reviewed knowledge paths cannot traverse links')
        if os.name == 'posix' and component != path:
            sticky_system_parent = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                    or info.st_mode & 0o022 and not sticky_system_parent):
                raise ValueError('Reviewed knowledge parents must exclude untrusted writers')
    info = path.stat()
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or not directory and (info.st_nlink != 1 or info.st_size > limit)
            or os.name == 'posix' and (info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022)):
        raise ValueError('Reviewed knowledge inputs must remain protected and operator-owned')


class ReaderKnowledgeSource:
    """Read existing operator approvals; never approve, classify or discover files.

    The host supplies the same authority and current snapshot as the projection.
    The selected review can be atomically replaced after independent review;
    each request checks it again. No worker, database or active pointer is added.
    """
    def __init__(self, config, organization_loader, snapshot_loader):
        config = coordinates(config)
        if not callable(organization_loader) or not callable(snapshot_loader):
            raise ValueError('Current trusted organization and snapshot loaders required')
        self.review_path = Path(config['review_path'])
        self.payload_directory = Path(config['payload_directory'])
        if (any(not path.is_absolute() or '..' in path.parts
                for path in (self.review_path, self.payload_directory))
                or self.review_path.suffix != '.json'
                or self.review_path == self.payload_directory):
            raise ValueError('Fixed absolute review JSON and payload directory required')
        self.organization_loader = organization_loader
        organization = organization_loader()['organization']['id']
        _protected(self.payload_directory, directory=True)
        self.store = PrivateKBStore(self.payload_directory, snapshot_loader, organization)
        self.preflight()

    def review(self):
        _protected(self.review_path.parent, directory=True)
        _protected(self.review_path, limit=MAX_REVISION_BYTES)
        document = _validate(_parse(_read(self.review_path), '.json'))
        reviewed_catalog(document, self.organization_loader())
        return document

    def note(self, ident):
        # ReviewedKnowledge authorizes the session before calling this loader.
        _protected(self.payload_directory, directory=True)
        if not isinstance(ident, str) or not HEX.fullmatch(ident):
            return None
        try:
            _protected(self.payload_directory / (ident + '.json'), limit=MAX_PAYLOAD_BYTES)
        except (OSError, ValueError):
            return None
        return self.store(ident)

    def preflight(self):
        """Validate the selected approval without reading note bodies or writing."""
        _protected(self.payload_directory, directory=True)
        self.review()
