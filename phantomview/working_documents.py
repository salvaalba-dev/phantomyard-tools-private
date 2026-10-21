"""Explicit, fingerprinted text and original documents from a selected store."""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import stat

from profile_documents import SECRET

MAX_BYTES = 128 * 1024


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


def bindings(value):
    if not isinstance(value, list) or len(value) > 16:
        raise ValueError('At most sixteen explicit working document bindings are supported')
    seen = set()
    for row in value:
        if (not isinstance(row, dict) or not {'urn', 'actor', 'sha256', 'format'} <= set(row) or set(row) - {'urn', 'actor', 'sha256', 'format', 'original', 'display'}
                or any(not isinstance(row[key], str) or not row[key] for key in ('urn', 'actor', 'sha256', 'format'))
                or 'original' in row and row['original'] is not True
                or not row['urn'].startswith('urn:') or len(row['urn']) > 512
                or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', row['actor'])
                or not re.fullmatch(r'[a-f0-9]{64}', row['sha256'])
                or row['format'] not in {'markdown', 'text/plain', 'html-text', 'application/pdf', 'image/png', 'image/jpeg'} or row['urn'] in seen):
            raise ValueError('A unique document, persona, reviewed fingerprint and text format are required')
        from original_documents import BINARY_MEDIA, display_metadata
        if row['format'] in BINARY_MEDIA:
            if row.get('original') is not True:
                raise ValueError('Binary documents require explicit original-file delivery')
            display_metadata(row.get('display'))
        elif 'display' in row:
            raise ValueError('Text document labels come from the selected source')
        seen.add(row['urn'])
    return value


def validated(value):
    if (not isinstance(value, dict) or not {'content', 'format', 'folder', 'sha256', 'source_sha256', 'actor'} <= set(value)
            or set(value) - {'content', 'format', 'folder', 'sha256', 'source_sha256', 'actor', 'original'}
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
    if 'original' in value:
        from original_documents import validate_descriptor
        original = validate_descriptor(value['original'])
        if original['sha256'] != value['source_sha256']:
            raise ValueError('Original must match the reviewed source fingerprint')
    from original_documents import BINARY_MEDIA
    if value['format'] in BINARY_MEDIA and ('original' not in value or value['original']['media_type'] != value['format']):
        raise ValueError('Binary publications must bind their reviewed original media type')
    return dict(value)


def collect(manifest, source, selected, actors, permitted):
    """Read selected local blobs only; ownership is a link, never an ACL grant."""
    selected = bindings(selected)
    if not selected:
        return {}
    nodes = manifest.get('nodes', [])
    if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
        raise ValueError('Document nodes must be objects')
    root = Path(source).parent / 'blobs'
    oid = manifest['manifest']['org']
    result = {}
    for binding in selected:
        matches = [node for node in nodes if node.get('urn') == binding['urn']]
        if not matches:
            continue  # The binding may belong to another selected manifest.
        personas = [actor for actor in actors if actor.get('id') == binding['actor'] and actor.get('org') == oid]
        if len(matches) != 1 or len(personas) != 1:
            raise ValueError('Working document source or persona is ambiguous')
        node, persona = matches[0], personas[0]
        owners = node.get('owners')
        if (node.get('kind') != 'doc' or not isinstance(owners, list)
                or any(not isinstance(owner, str) for owner in owners) or persona.get('role') not in owners
                or persona.get('searchable') is not True or not permitted(node)
                or node.get('secret') is True or node.get('confidential') is True
                or node.get('visibility') in {'private', 'secret', 'restricted', 'confidential'}
                or not isinstance(node.get('category'), str)):
            raise ValueError('Selected working document must have a declared owner and classification')
        locations = node.get('locations', [])
        if (not isinstance(locations, list) or len(locations) != 1
                or not isinstance(locations[0], dict) or locations[0].get('backend') != 'local'
                or not isinstance(locations[0].get('path'), str)):
            raise ValueError('A single explicit local document source is required')
        path = Path(locations[0].get('path', ''))
        if (not path.is_absolute() or '..' in path.parts or not path.is_relative_to(root)
                or any(parent.is_symlink() for parent in (path, *path.parents))):
            raise ValueError('Working documents must remain inside the selected local blob store')
        from original_documents import BINARY_MEDIA, MAX_ORIGINAL_BYTES
        binary = binding['format'] in BINARY_MEDIA
        limit = MAX_ORIGINAL_BYTES if binary else MAX_BYTES
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                               | getattr(os, 'O_NONBLOCK', 0)), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise ValueError('A bounded complete regular document is required')
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if ((before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns)
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
        if binary:
            from original_documents import descriptor
            original = descriptor(raw, node, binding['format'], binding['display'])
            content = ' '.join(original[key] for key in ('title', 'code', 'version') if key in original)
            format = binding['format']
        else:
            source_text = raw.decode('utf-8')
            if SECRET.search(source_text):
                raise ValueError('Credential-like source content is excluded from document publication')
            content, format = text_content(source_text, binding['format'])
        value = {'content': content, 'format': format, 'folder': '/'.join(parts),
                 'source_sha256': binding['sha256'], 'sha256': hashlib.sha256(content.encode()).hexdigest(),
                 'actor': binding['actor']}
        if binding.get('original') is True:
            from original_documents import descriptor
            value['original'] = original if binary else descriptor(raw, node, binding['format'])
        result[binding['urn']] = validated(value)
    return result
