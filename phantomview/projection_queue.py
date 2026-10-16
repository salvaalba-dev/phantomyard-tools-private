"""Operator-selected automatic draft queue; never approves or publishes access."""
import os

from channel_identity import HumanDirectory
from projection_review import read_json, root_path, write_new
from resource_review import revision
from source_adapter import prepare


class ReviewQueue:
    def __init__(self, root, org_loader):
        self.root = root_path(root)
        if not callable(org_loader):
            raise ValueError('A trusted current organization loader is required')
        self.org_loader = org_loader
        self.available = False

    def _save(self, make_state):
        root_path(self.root)
        lock = self.root / 'queue.lock'
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            state = make_state()
            staged = self.root / 'review.next.json'
            write_new(staged, state)
            os.replace(staged, self.root / 'review.json')
            return state
        finally:
            os.close(fd)
            lock.unlink()

    def refresh(self, snapshot):
        """Persist a new immutable draft only when selected source evidence changes."""
        self.available = False
        def stage():
            org = self.org_loader()
            draft = prepare(snapshot, HumanDirectory(org))
            ident = revision(draft)
            target = self.root / (ident + '.draft.json')
            if target.exists() or target.is_symlink():
                if read_json(target) != draft:
                    raise ValueError('Stored draft does not match its revision')
            else:
                write_new(target, draft)
            if revision(self.org_loader()) != revision(org):
                raise ValueError('Organization changed while preparing review queue')
            return {'schema_version': 1, 'status': 'ready', 'draft_revision': ident,
                    'organization_revision': revision(org)}
        state = self._save(stage)
        self.available = True
        return state

    def unavailable(self):
        """Invalidate the current review after collection or preparation fails."""
        self.available = False
        return self._save(lambda: {'schema_version': 1, 'status': 'blocked',
                                  'draft_revision': None, 'organization_revision': None})

    def current(self, snapshot):
        """Operator retrieval requires fresh matching sources, never cached fallback."""
        from scoped_knowledge import HEX
        if not self.available:
            raise ValueError('A successful current collection is required before review retrieval')
        root_path(self.root)
        state = read_json(self.root / 'review.json')
        if (not isinstance(state, dict)
                or set(state) != {'schema_version', 'status', 'draft_revision', 'organization_revision'}
                or type(state['schema_version']) is not int or state['schema_version'] != 1
                or state['status'] != 'ready'
                or any(not isinstance(state[key], str) or not HEX.fullmatch(state[key])
                       for key in ('draft_revision', 'organization_revision'))):
            raise ValueError('No current review is available')
        org = self.org_loader()
        draft = read_json(self.root / (state['draft_revision'] + '.draft.json'))
        if (revision(org) != state['organization_revision'] or revision(draft) != state['draft_revision']
                or prepare(snapshot, HumanDirectory(org)) != draft):
            raise ValueError('Review queue is stale; refresh selected sources')
        if (not self.available or read_json(self.root / 'review.json') != state
                or revision(self.org_loader()) != state['organization_revision']):
            raise ValueError('Review changed during retrieval')
        return draft
