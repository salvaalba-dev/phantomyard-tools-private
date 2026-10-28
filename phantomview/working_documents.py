"""Explicit, fingerprinted text and original documents from a selected store."""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat

from profile_documents import SECRET

MAX_DOCUMENTS = 512
MAX_BYTES = 128 * 1024
MAX_HTML_ORIGINAL_BYTES = 1024 * 1024


class _Text(HTMLParser):
    """Extract inert body text without rendering, fetching assets or running scripts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {'head', 'script', 'style', 'template', 'noscript'}:
            self.hidden += 1
        elif not self.hidden and tag in {'p', 'div', 'section', 'br', 'h1', 'h2', 'h3', 'li', 'tr'}:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'head', 'script', 'style', 'template', 'noscript'}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in {'p', 'div', 'section', 'h1', 'h2', 'h3', 'li', 'tr'}:
            self.parts.append('\n')
        elif not self.hidden and tag in {'td', 'th'}:
            self.parts.append(' | ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def text_content(content, format):
    if format != 'html-text':
        return content, format
    parser = _Text()
    parser.feed(content)
    parser.close()
    lines = [re.sub(r'\s+', ' ', line).strip(' |') for line in ''.join(parser.parts).splitlines()]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip(), 'text/plain'


def recipients(value):
    """Explicit document associations never imply viewer access grants."""
    primary = value.get('actor')
    extra = value.get('related_actors', [])
    if (not isinstance(primary, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', primary)
            or not isinstance(extra, list) or len(extra) > 7
            or 'related_actors' in value and not extra
            or any(not isinstance(actor, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', actor) for actor in extra)
            or len(set([primary, *extra])) != len(extra) + 1):
        raise ValueError('Unique explicit document personas required')
    return [primary, *extra]


def bindings(value):
    if not isinstance(value, list) or len(value) > MAX_DOCUMENTS:
        raise ValueError(f'At most {MAX_DOCUMENTS} explicit working document bindings are supported')
    seen = set()
    for row in value:
        if (not isinstance(row, dict) or not {'urn', 'actor', 'sha256', 'format'} <= set(row) or set(row) - {'urn', 'actor', 'sha256', 'format', 'original', 'display', 'document_group', 'related_actors', 'original_only'}
                or any(not isinstance(row[key], str) or not row[key] for key in ('urn', 'actor', 'sha256', 'format'))
                or 'original' in row and row['original'] is not True
                or not row['urn'].startswith('urn:') or len(row['urn']) > 512
                or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', row['actor'])
                or not re.fullmatch(r'[a-f0-9]{64}', row['sha256'])
                or row['format'] not in {'markdown', 'text/plain', 'html-text', 'application/pdf', 'image/png', 'image/jpeg'} or row['urn'] in seen):
            raise ValueError('A unique document, persona, reviewed fingerprint and text format are required')
        recipients(row)
        from original_documents import BINARY_MEDIA, display_metadata
        if 'original_only' in row and (row['original_only'] is not True or row.get('original') is not True):
            raise ValueError('Metadata-only delivery requires an explicit reviewed original')
        if row['format'] in BINARY_MEDIA or row.get('original_only') is True:
            if row.get('original') is not True:
                raise ValueError('Binary documents require explicit original-file delivery')
            display_metadata(row.get('display'))
        elif 'display' in row:
            raise ValueError('Text document labels come from the selected source')
        if 'document_group' in row:
            from document_groups import validated as validate_group
            if row.get('original') is not True:
                raise ValueError('Logical document formats require original-file delivery')
            validate_group(row['document_group'])
        seen.add(row['urn'])
    return value


def validated(value):
    if (not isinstance(value, dict) or not {'content', 'format', 'folder', 'sha256', 'source_sha256', 'actor'} <= set(value)
            or set(value) - {'content', 'format', 'folder', 'sha256', 'source_sha256', 'actor', 'original', 'document_group', 'related_actors'}
            or not isinstance(value['content'], str) or not value['content'].strip()
            or len(value['content'].encode()) > MAX_BYTES or '\x00' in value['content']
            or SECRET.search(value['content']) or not isinstance(value['format'], str)
            or value['format'] not in {'markdown', 'text/plain', 'application/pdf', 'image/png', 'image/jpeg'}
            or not isinstance(value['folder'], str) or len(value['folder']) > 512
            or not value['folder'] or len(value['folder'].split('/')) > 8
            or any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}', part)
                   or part in {'.', '..'} for part in value['folder'].split('/'))
            or not isinstance(value['actor'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value['actor'])
            or not isinstance(value['source_sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', value['source_sha256'])
            or hashlib.sha256(value['content'].encode()).hexdigest() != value['sha256']
            or len(json.dumps(value, ensure_ascii=True).encode()) > 32768):
        raise ValueError('Invalid reviewed working document text')
    recipients(value)
    if 'original' in value:
        from original_documents import validate_descriptor
        original = validate_descriptor(value['original'])
        if original['sha256'] != value['source_sha256']:
            raise ValueError('Original must match the reviewed source fingerprint')
    from original_documents import BINARY_MEDIA
    if value['format'] in BINARY_MEDIA and ('original' not in value or value['original']['media_type'] != value['format']):
        raise ValueError('Binary publications must bind their reviewed original media type')
    if 'document_group' in value:
        from document_groups import validated as validate_group
        if 'original' not in value:
            raise ValueError('Logical document formats require a reviewed original')
        validate_group(value['document_group'], value['original'])
    return dict(value)


def current_nodes(manifest):
    """Resolve a structural lineage; native identity verification remains in PhantomDocs."""
    nodes = manifest.get('nodes', [])
    heads = manifest.get('currentVersions', {})
    if (not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes)
            or not isinstance(heads, dict)):
        raise ValueError('Document nodes and current version references must be structured')
    groups = {}
    for node in nodes:
        if node.get('kind') == 'doc':
            urn = node.get('urn')
            if not isinstance(urn, str) or not urn:
                raise ValueError('Document versions require an explicit URN')
            groups.setdefault(urn, []).append(node)
    resolved = {}
    hex64 = lambda value: isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) is not None
    for urn, versions in groups.items():
        if len(versions) == 1:
            tip = versions[0]
            if tip.get('previous') is not None:
                raise ValueError('Document history is incomplete')
        else:
            if len(versions) > 1024:
                raise ValueError('Document history exceeds the review bound')
            by_mac, successors = {}, {}
            roots = []
            for node in versions:
                mac, previous = node.get('mac'), node.get('previous')
                parent, slug, content_hash = node.get('parentMac'), node.get('slug'), node.get('contentHash')
                if (not hex64(mac) or not hex64(parent) or not hex64(content_hash)
                        or not isinstance(slug, str) or not slug or mac in by_mac
                        or previous is not None and not hex64(previous)):
                    raise ValueError('Document revision identity is invalid or duplicated')
                by_mac[mac] = node
                if previous is None:
                    roots.append(node)
                elif previous in successors:
                    raise ValueError('Document history branches')
                else:
                    successors[previous] = node
            if len(roots) != 1 or any(key not in by_mac for key in successors):
                raise ValueError('Document history is disconnected or circular')
            tip, visited = roots[0], set()
            parent, slug = tip['parentMac'], tip['slug']
            while True:
                if tip['mac'] in visited or tip['parentMac'] != parent or tip['slug'] != slug:
                    raise ValueError('Document history changes identity or is circular')
                visited.add(tip['mac'])
                if tip['mac'] not in successors:
                    break
                tip = successors[tip['mac']]
            if len(visited) != len(versions):
                raise ValueError('Document history is incomplete')
        if urn in heads and heads[urn] != tip.get('mac'):
            raise ValueError('Current document reference must identify the lineage tip')
        resolved[urn] = tip
    result, seen = [], set()
    for node in nodes:
        if node.get('kind') != 'doc':
            result.append(node)
        elif node['urn'] not in seen:
            result.append(resolved[node['urn']])
            seen.add(node['urn'])
    return result


def cache_directory(value):
    """A local read-only cache is optional; it never downloads or changes native records."""
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError('An explicit protected cache directory is required')
    root = Path(value)
    if (not root.is_absolute() or '..' in root.parts or not root.is_dir()
            or any(parent.is_symlink() for parent in (root, *root.parents))
            or os.name == 'posix' and (root.stat().st_mode & 0o022
                or root.stat().st_uid not in {0, os.geteuid()})):
        raise ValueError('The document cache must be protected')
    return root


def collect(manifest, source, selected, actors, permitted, cache=None):
    """Read selected local blobs or explicitly configured verified Drive copies; ownership is a link, never an ACL grant."""
    selected = bindings(selected)
    if not selected:
        return {}
    nodes = current_nodes(manifest)
    root = Path(source).parent / 'blobs'
    oid = manifest['manifest']['org']
    result = {}
    for binding in selected:
        matches = [node for node in nodes if node.get('urn') == binding['urn']]
        if not matches:
            continue  # The binding may belong to another selected manifest.
        personas = []
        for ident in recipients(binding):
            matching = [actor for actor in actors if actor.get('id') == ident and actor.get('org') == oid]
            if len(matching) != 1:
                raise ValueError('Working document persona is ambiguous or outside the organization')
            personas.append(matching[0])
        if len(matches) != 1:
            raise ValueError('Working document source is ambiguous')
        node = matches[0]
        owners = node.get('owners')
        if (node.get('kind') != 'doc' or not isinstance(owners, list)
                or any(not isinstance(owner, str) for owner in owners)
                or any(persona.get('role') not in owners or persona.get('searchable') is not True for persona in personas)
                or not permitted(node)
                or node.get('secret') is True or node.get('confidential') is True
                or node.get('visibility') in {'private', 'secret', 'restricted', 'confidential'}
                or not isinstance(node.get('category'), str)):
            raise ValueError('Selected working document must have a declared owner and classification')
        locations = node.get('locations', [])
        if not isinstance(locations, list) or len(locations) != 1 or not isinstance(locations[0], dict):
            raise ValueError('A single explicit document source is required')
        location = locations[0]
        cached = location.get('backend') == 'gdrive'
        if cached:
            if (cache is None or not isinstance(location.get('ref'), str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', location['ref'])
                    or node.get('contentHash') != binding['sha256']):
                raise ValueError('A verified cache and current native Drive reference are required')
            cache_root = cache_directory(cache)
            path = cache_root / binding['sha256']
        elif location.get('backend') == 'local' and isinstance(location.get('path'), str):
            path = Path(location['path'])
            if not path.is_absolute() or '..' in path.parts:
                raise ValueError('Working documents require an absolute local blob path')
            if not path.is_relative_to(root):
                # Match native restored-store semantics only for an absent,
                # canonical hash-addressed local location. Never read outside
                # the selected store or hide a present source's corruption.
                expected = ('blobs', binding['sha256'][:2], binding['sha256'])
                if tuple(path.parts[-3:]) != expected or node.get('contentHash') != binding['sha256']:
                    raise ValueError('Relocated document location must match its native content hash')
                if any(part.is_symlink() for part in (path, *path.parents)):
                    raise ValueError('Relocated document paths cannot contain symlinks')
                try:
                    path.lstat()
                except FileNotFoundError:
                    path = root / binding['sha256'][:2] / binding['sha256']
                else:
                    raise ValueError('A present external document location cannot be redirected')
        else:
            raise ValueError('Unsupported document source')
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError('Document source paths cannot contain symlinks')
        from original_documents import BINARY_MEDIA, MAX_ORIGINAL_BYTES
        binary = binding['format'] in BINARY_MEDIA
        metadata_only = binding.get('original_only') is True
        limit = (MAX_ORIGINAL_BYTES if binary or metadata_only else MAX_HTML_ORIGINAL_BYTES
                 if binding['format'] == 'html-text' and binding.get('original') is True else MAX_BYTES)
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                               | getattr(os, 'O_NONBLOCK', 0)), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit
                    or cached and os.name == 'posix' and (before.st_mode & 0o022
                        or before.st_uid not in {0, os.geteuid()})):
                raise ValueError('A bounded complete regular document is required')
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if ((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                or hashlib.sha256(raw).hexdigest() != binding['sha256']):
            raise ValueError('Document changed; review the current source before publication')
        parts, visited = [], set()
        parent_mac = node.get('parentMac')
        while parent_mac and parent_mac != manifest['manifest'].get('rootMac'):
            parents = [parent for parent in nodes if parent.get('mac') == parent_mac]
            if len(parents) != 1 or parent_mac in visited or len(parts) >= 8 or parents[0].get('kind') != 'folder':
                raise ValueError('Document folder ancestry is ambiguous or circular')
            visited.add(parent_mac)
            slug = parents[0].get('slug')
            if not isinstance(slug, str):
                raise ValueError('Explicit folder labels are required')
            parts.insert(0, slug)
            parent_mac = parents[0].get('parentMac')
        original = None
        if binary or metadata_only:
            from original_documents import descriptor
            if not binary and (b'\x00' in raw or SECRET.search(raw.decode('utf-8'))):
                raise ValueError('Credential-like or invalid source content is excluded')
            original = descriptor(raw, node, binding['format'], binding['display'])
            content = ' '.join(original[key] for key in ('title', 'code', 'version') if key in original)
            format = 'text/plain' if binding['format'] == 'html-text' else binding['format']
        else:
            source_text = raw.decode('utf-8')
            if SECRET.search(source_text):
                raise ValueError('Credential-like source content is excluded from document publication')
            content, format = text_content(source_text, binding['format'])
        value = {'content': content, 'format': format, 'folder': '/'.join(parts),
                 'source_sha256': binding['sha256'], 'sha256': hashlib.sha256(content.encode()).hexdigest(),
                 'actor': binding['actor']}
        if 'related_actors' in binding:
            value['related_actors'] = list(binding['related_actors'])
        if binding.get('original') is True:
            from original_documents import descriptor
            value['original'] = original if binary or metadata_only else descriptor(raw, node, binding['format'])
        if 'document_group' in binding:
            from document_groups import validated as validate_group
            value['document_group'] = validate_group(binding['document_group'], value['original'], oid)
        result[binding['urn']] = validated(value)
    from document_groups import check_members
    check_members(result.values())
    return result
