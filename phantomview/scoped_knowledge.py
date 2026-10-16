"""Inactive retrieval boundary for reviewed KB resources and identified sessions.

Trusted application code supplies the gate, catalog loader and bounded note
loader. No browser field can supply a human, category, catalog or note path.
This module does not register routes or enable expanded assistant access.
"""
import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path, PurePosixPath

MAX_RESOURCES = 500
MAX_PAYLOAD_BYTES = 262144
MAX_SCAN_BYTES = 16 * 1024 * 1024
MAX_RESULTS = 4
EXCERPT_CHARS = 1600
HEX = re.compile(r'[a-f0-9]{64}')
IDENTIFIER = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Catalog:
    """Snapshot of an explicitly approved, private classification catalog.

    A digest detects changes; it is not a signature or proof of administrator
    approval. The caller must load this catalog from an independently protected
    configuration source that model processes cannot modify.
    """
    def __init__(self, document):
        if (not isinstance(document, dict)
                or set(document) != {'schema_version', 'organization', 'status', 'resources'}
                or type(document['schema_version']) is not int or document['schema_version'] != 1
                or document['status'] != 'approved'
                or not isinstance(document['organization'], str)
                or not IDENTIFIER.fullmatch(document['organization'])
                or not isinstance(document['resources'], list)
                or len(document['resources']) > MAX_RESOURCES):
            raise ValueError('An explicitly approved private resource catalog is required')
        document = json.loads(json.dumps(document))
        seen, paths = set(), set()
        fields = {'id', 'actor', 'path', 'category', 'project', 'secret', 'payload_sha256'}
        for row in document['resources']:
            if not isinstance(row, dict) or not fields <= set(row) or set(row) - fields - {'scope'}:
                raise ValueError('Invalid resource classification')
            if 'scope' in row:
                scope = row['scope']
                if (not isinstance(scope, dict) or set(scope) != {'id', 'kind'}
                        or not isinstance(scope['id'], str) or not IDENTIFIER.fullmatch(scope['id'])
                        or not isinstance(scope['kind'], str)
                        or scope['kind'] not in {'organization', 'department', 'project'}):
                    raise ValueError('Invalid classified resource scope')
            if (not isinstance(row['id'], str) or not HEX.fullmatch(row['id'])
                    or not isinstance(row['payload_sha256'], str) or not HEX.fullmatch(row['payload_sha256'])
                    or not isinstance(row['actor'], str) or not IDENTIFIER.fullmatch(row['actor'])
                    or not isinstance(row['category'], str)
                    or not re.fullmatch(r'category-[1-9][a-z0-9_-]*', row['category'])
                    or type(row['secret']) is not bool):
                raise ValueError('Invalid resource identity or category; category zero classifies no documents')
            if row['project'] is not None and (not isinstance(row['project'], str)
                                                or not IDENTIFIER.fullmatch(row['project'])):
                raise ValueError('Invalid explicit project')
            if not isinstance(row['path'], str):
                raise ValueError('Invalid resource path')
            path = PurePosixPath(row['path'])
            if (str(path) != row['path'] or path.is_absolute() or '..' in path.parts
                    or '\\' in row['path'] or not path.parts or path.parts[0] != 'kb'
                    or path.suffix != '.md' or any(ord(char) < 32 for char in row['path'])):
                raise ValueError('Expected a canonical relative KB Markdown path')
            if row['id'] in seen or (row['actor'], row['path']) in paths:
                raise ValueError('Duplicate classified resource')
            seen.add(row['id'])
            paths.add((row['actor'], row['path']))
        self._document = document
        self.revision = digest(json.dumps(document, sort_keys=True, separators=(',', ':')).encode())

    def resources(self):
        # Do not expose mutable classification state to a caller or note loader.
        return json.loads(json.dumps(self._document))


def normalize(text):
    return ''.join(char for char in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(char))


class PrivateKBStore:
    """Bounded local payload reader retaining the collector's source exclusions.

    The application supplies the fixed private directory and fresh selected
    snapshot. Neither dependency may be selected by a browser or a model.
    Recheck the snapshot per read so cached, removed or nonsearchable notes do
    not become evidence just because their payload files still exist.
    """
    def __init__(self, root, snapshot_loader, organization):
        self.root = Path(root)
        if (not self.root.is_absolute() or self.root.is_symlink() or not self.root.is_dir()
                or any(parent.is_symlink() for parent in self.root.parents)
                or not callable(snapshot_loader) or not IDENTIFIER.fullmatch(organization)):
            raise ValueError('A fixed private KB store and trusted snapshot loader are required')
        self.snapshot_loader, self.organization = snapshot_loader, organization

    def __call__(self, ident):
        if not isinstance(ident, str) or not HEX.fullmatch(ident):
            raise ValueError('Invalid opaque knowledge ID')
        snapshot = self.snapshot_loader()
        matching = [note for actor in snapshot.get('actors', [])
                    if actor.get('org') == self.organization and actor.get('searchable') is True
                    for note in actor.get('knowledge', []) if note.get('id') == ident
                    and note.get('searchable') is True and not note.get('unavailable')]
        if len(matching) != 1:
            return None
        path = self.root / (ident + '.json')
        if path.is_symlink():
            return None
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        try:
            # The fixed parent directory must be protected from model writers.
            fd = os.open(path, flags)
        except OSError:
            return None
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return None
            return stream.read(MAX_PAYLOAD_BYTES + 1)


def prepare_review(proposal, snapshot, note_loader):
    """Fingerprint current candidate notes without approving their contents.

    This removes per-note manual hash work, not the content-review decision.
    Every secret classification stays unset, so changing only the top-level
    status cannot accidentally turn this output into an approved catalog.
    """
    organization = proposal.get('organization')
    if (proposal.get('status') != 'draft' or proposal.get('activation_supported') is not False
            or not isinstance(organization, str) or not IDENTIFIER.fullmatch(organization)):
        raise ValueError('An inert classification review proposal is required')
    rules = {}
    for rule in proposal.get('rules', []):
        key = (rule.get('actor'), rule.get('folder'))
        if key in rules or rule.get('recursive') is not False or rule.get('approved') is not False:
            raise ValueError('Unique unapproved exact-folder rules are required')
        category = rule.get('suggested_category')
        if category is not None and (category == 'category-0' or category not in proposal.get('categories', {})):
            raise ValueError('An existing information category is required')
        rules[key] = rule
    resources = []
    for actor in snapshot.get('actors', []):
        if actor.get('org') != organization or actor.get('searchable') is not True:
            continue
        for note in actor.get('knowledge', []):
            if (not isinstance(note.get('path'), str) or note.get('searchable') is not True
                    or note.get('unavailable') or not isinstance(note.get('id'), str)
                    or not HEX.fullmatch(note['id'])):
                continue
            rule = rules.get((actor.get('id'), str(PurePosixPath(note['path']).parent)))
            if not rule or not rule.get('suggested_category'):
                continue
            raw = note_loader(note['id'])
            if not isinstance(raw, bytes) or len(raw) > MAX_PAYLOAD_BYTES:
                raise ValueError('Current candidate payload is unavailable or exceeds bounds')
            payload = json.loads(raw)
            if (payload.get('id') != note['id'] or payload.get('actor') != f"{organization}:actors:{actor['id']}"
                    or payload.get('path') != note['path'] or payload.get('truncated') is not False):
                raise ValueError('Candidate payload does not match the selected current snapshot')
            resources.append({'id': note['id'], 'actor': actor['id'], 'path': note['path'],
                              'category': rule['suggested_category'], 'project': rule.get('project'),
                              'secret': None, 'payload_sha256': digest(raw)})
    resources.sort(key=lambda row: (row['actor'], row['path']))
    document = {'schema_version': 1, 'organization': organization, 'status': 'draft', 'resources': resources}
    # Validate structural boundaries without turning the returned draft into a grant.
    Catalog(document | {'status': 'approved', 'resources': [row | {'secret': False} for row in resources]})
    return document


def retrieve(gate, headers, catalog_loader, note_loader, question):
    """Return only reviewed, unchanged evidence permitted by the current session.

    Loaders are trusted in-process dependencies, never request JSON. note_loader
    receives only an already-authorized opaque ID and must return bounded bytes
    from the selected organization's private KB store. No denied document is
    opened, searched, counted or mentioned in the result.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > 1800:
        raise ValueError('A question of at most 1800 characters is required')
    terms = sorted(set(re.findall(r'\w{2,}', normalize(question))))[:32]
    if not terms:
        raise ValueError('Provide at least one searchable word')
    recipient, directory = gate.identified_scope(headers)
    catalog = Catalog(catalog_loader())
    document = catalog.resources()
    if document['organization'] != recipient.organization:
        raise ValueError('Knowledge catalog is outside the identified organization')
    matches, scanned = [], 0
    for row in document['resources']:
        resource = {'organization': document['organization'], 'category': row['category'],
                    'project': row['project'], 'secret': row['secret']}
        if 'scope' in row:
            resource['scope'] = row['scope']
        if not directory.permits(recipient, resource):
            continue
        raw = note_loader(row['id'])
        if raw is None:
            continue
        if not isinstance(raw, bytes) or len(raw) > MAX_PAYLOAD_BYTES:
            raise ValueError('Knowledge payload exceeds the bounded loader contract')
        scanned += len(raw)
        if scanned > MAX_SCAN_BYTES:
            raise ValueError('Knowledge scan exceeds bounds; no partial evidence was submitted')
        if digest(raw) != row['payload_sha256']:
            continue  # Changed notes need review; a folder rule cannot approve new content.
        try:
            note = json.loads(raw)
        except (ValueError, UnicodeError):
            continue
        if (not isinstance(note, dict) or note.get('id') != row['id']
                or note.get('actor') != f"{document['organization']}:actors:{row['actor']}"
                or note.get('path') != row['path']
                or note.get('truncated') is not False or not isinstance(note.get('content'), str)
                or not isinstance(note.get('title'), str) or len(note['title']) > 500):
            continue
        content, title = normalize(note['content']), normalize(note['title'])
        score = sum(3 * (term in title) + (term in content) for term in terms)
        if not score:
            continue
        # Excerpts and titles remain untrusted evidence for JEV, never instructions.
        positions = [content.find(term) for term in terms if term in content]
        start = max(0, min(positions, default=0) - 200)
        evidence = {
            'id': row['id'], 'actor': row['actor'], 'title': note['title'],
            'category': row['category'], 'project': row['project'],
            'payload_sha256': row['payload_sha256'], 'trust': 'untrusted',
            'excerpt': note['content'][start:start + EXCERPT_CHARS],
            'excerpt_only': True,
        }
        if 'scope' in row:
            evidence['scope'] = row['scope']
        matches.append((score, row['id'], evidence))
    # Expiry, logout and policy/channel-identity changes during retrieval must
    # discard all collected evidence before it can be handed to a model.
    current, _ = gate.identified_scope(headers)
    if current != recipient or Catalog(catalog_loader()).revision != catalog.revision:
        raise ValueError('Session or classification changed; request fresh evidence')
    matches.sort(key=lambda row: (-row[0], row[1]))
    selected = [row[2] for row in matches[:MAX_RESULTS]]
    for note in selected:
        raw = note_loader(note['id'])
        if (not isinstance(raw, bytes) or len(raw) > MAX_PAYLOAD_BYTES
                or digest(raw) != note['payload_sha256']):
            raise ValueError('Selected knowledge changed or became unavailable; request fresh evidence')
    return {'trust': 'untrusted', 'scope': 'reviewed unchanged resources permitted by this identified session',
            'policy_revision': recipient.policy_revision, 'catalog_revision': catalog.revision,
            'notes': selected,
            'complete_corpus': False}
