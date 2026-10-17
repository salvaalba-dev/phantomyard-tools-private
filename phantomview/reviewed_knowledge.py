"""Optional full-note reader over existing reviews and identified sessions.

No classification database, filesystem discovery, model calls or native-memory
changes. The application supplies protected loaders from its existing refresh.
"""
import json

from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from resource_review import MAX_REVISION_BYTES, _current, _validate, reviewed_catalog, revision
from scoped_knowledge import HEX, MAX_SCAN_BYTES, normalize


class _ScanLimit(ValueError):
    """Discard the complete result rather than returning a partial corpus."""


class ReviewedKnowledge:
    def __init__(self, gate, review_loader, organization_loader, snapshot_loader, note_loader):
        if not isinstance(gate, IdentifiedGate) or not all(callable(loader) for loader in (
                review_loader, organization_loader, snapshot_loader, note_loader)):
            raise ValueError('The identified gate and protected current knowledge loaders are required')
        self.gate = gate
        self.review_loader, self.organization_loader = review_loader, organization_loader
        self.snapshot_loader, self.note_loader = snapshot_loader, note_loader

    def _scan(self, headers, *, ident=None):
        """One current authority/review snapshot, with no denied body reads."""
        recipient, directory = self.gate.identified_scope(headers)
        raw_org = json.dumps(self.organization_loader(), allow_nan=False).encode()
        if len(raw_org) > MAX_REVISION_BYTES:
            raise ValueError('Selected organization exceeds knowledge reader bounds')
        org = json.loads(raw_org)
        if HumanDirectory(org).revision != directory.revision:
            raise ValueError('Knowledge source and identified session use different authority')
        bundle = _validate(self.review_loader())
        catalog = reviewed_catalog(bundle, org)
        if catalog['organization'] != recipient.organization:
            raise ValueError('Knowledge review belongs to another organization')
        notes, selected, used = [], [], 0

        def bounded_load(key):
            nonlocal used
            raw = self.note_loader(key)
            if isinstance(raw, bytes):
                used += len(raw)
                if used > MAX_SCAN_BYTES:
                    raise _ScanLimit('Knowledge read exceeds the bounded scan; no partial result is released')
            return raw

        for row in sorted(catalog['resources'], key=lambda row: row['id']):
            if ident is not None and row['id'] != ident:
                continue
            if not directory.permits(recipient, row | {'organization': recipient.organization}):
                continue
            try:
                note = _current(row, recipient.organization, self.snapshot_loader(), bounded_load)
            except _ScanLimit:
                raise
            except (ValueError, UnicodeError):
                continue
            selected.append((row, note))
        # Recheck every selected note after the complete scan, so a later read
        # cannot leave an earlier excluded/changed note in titles or counters.
        for row, note in selected:
            try:
                if _current(row, recipient.organization, self.snapshot_loader(), bounded_load) != note:
                    raise ValueError('Knowledge changed while preparing the view')
            except _ScanLimit:
                raise
            except (ValueError, UnicodeError):
                if ident is not None:
                    return []
                raise ValueError('Selected knowledge changed; refresh the complete view') from None
            notes.append({'id': row['id'], 'actor': row['actor'], 'title': note['title'], 'content': note['content'],
                          'category': row['category'], 'scope': dict(row['scope']), 'project': row['project'],
                          'trust': 'untrusted', 'format': 'markdown', 'excerpt_only': False,
                          'review_revision': bundle['revision'], 'payload_sha256': row['payload_sha256']})
        if (revision(self.organization_loader()) != revision(org)
                or _validate(self.review_loader()) != bundle):
            raise ValueError('Knowledge authority or review changed during the read')
        current, _ = self.gate.identified_scope(headers)
        if current != recipient:
            raise ValueError('Identified session changed during the knowledge read')
        return notes

    def detail(self, headers, ident):
        """Return complete untrusted Markdown, never executable HTML or instructions."""
        if not isinstance(ident, str) or not HEX.fullmatch(ident):
            self.gate.identified_scope(headers)
            return None
        return next(iter(self._scan(headers, ident=ident)), None)

    def records(self, headers, query=None):
        """Visible metadata only; optional global text search includes approved bodies."""
        if query is not None and (not isinstance(query, str) or not 1 <= len(query.strip()) <= 200):
            raise ValueError('Expected a knowledge query of 1 to 200 characters')
        terms = normalize(query).split()[:12] if query is not None else []
        records = []
        for note in self._scan(headers):
            if terms and not all(term in normalize(note['title'] + ' ' + note['actor'] + ' ' + note['content']) for term in terms):
                continue
            # No global review revision, paths, bodies or hidden-corpus totals.
            records.append({'id': note['id'], 'kind': 'knowledge', 'data': {
                'title': note['title'], 'actor': note['actor'], 'source': 'reviewed-knowledge',
                'trust': 'untrusted', 'payload_sha256': note['payload_sha256']}})
        return records
