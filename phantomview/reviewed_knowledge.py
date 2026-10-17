"""Optional full-note reader over existing reviews and identified sessions.

No classification database, filesystem discovery, model calls or native-memory
changes. The application supplies protected loaders from its existing refresh.
"""
import json

from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from resource_review import MAX_REVISION_BYTES, _current, _validate, reviewed_catalog, revision
from scoped_knowledge import HEX


class ReviewedKnowledge:
    def __init__(self, gate, review_loader, organization_loader, snapshot_loader, note_loader):
        if not isinstance(gate, IdentifiedGate) or not all(callable(loader) for loader in (
                review_loader, organization_loader, snapshot_loader, note_loader)):
            raise ValueError('The identified gate and protected current knowledge loaders are required')
        self.gate = gate
        self.review_loader, self.organization_loader = review_loader, organization_loader
        self.snapshot_loader, self.note_loader = snapshot_loader, note_loader

    def detail(self, headers, ident):
        """Authorize before any body read; unavailable and denied notes return None.

        Raw Markdown is untrusted display content, never HTML or model instructions.
        A review's provenance/hash is consistency evidence, not authentication.
        """
        recipient, directory = self.gate.identified_scope(headers)
        if not isinstance(ident, str) or not HEX.fullmatch(ident):
            return None
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
        row = next((row for row in catalog['resources'] if row['id'] == ident), None)
        if row is None or not directory.permits(recipient, row | {'organization': recipient.organization}):
            return None
        try:
            note = _current(row, recipient.organization, self.snapshot_loader(), self.note_loader)
            # Reuse the same provenance validation after reading. Removed sources,
            # path changes and byte changes discard the complete response.
            if _current(row, recipient.organization, self.snapshot_loader(), self.note_loader) != note:
                return None
        except (ValueError, UnicodeError):
            return None
        if (revision(self.organization_loader()) != revision(org)
                or _validate(self.review_loader()) != bundle):
            raise ValueError('Knowledge authority or review changed during the read')
        current, _ = self.gate.identified_scope(headers)
        if current != recipient:
            raise ValueError('Identified session changed during the knowledge read')
        return {'id': ident, 'actor': row['actor'], 'title': note['title'], 'content': note['content'],
                'category': row['category'], 'scope': dict(row['scope']), 'project': row['project'],
                'trust': 'untrusted', 'format': 'markdown', 'excerpt_only': False,
                'review_revision': bundle['revision'], 'payload_sha256': row['payload_sha256']}
