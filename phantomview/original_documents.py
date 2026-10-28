"""Reviewed original-file metadata and a fixed, content-addressed private store."""
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import stat
import unicodedata

# Preload media support before isolated readers permanently drop kernel UIDs.
from video_originals import MAX_VIDEO_BYTES, VerifiedVideos, serve_video

MAX_ORIGINAL_BYTES = 32 * 1024 * 1024
MEDIA = {'text/html': 'html', 'text/plain': 'txt', 'text/markdown': 'md',
         'application/pdf': 'pdf', 'image/png': 'png', 'image/jpeg': 'jpg', 'video/mp4': 'mp4'}
BINARY_MEDIA = {'application/pdf', 'image/png', 'image/jpeg'}


def display_metadata(value):
    if (not isinstance(value, dict) or 'title' not in value
            or set(value) - {'title', 'code', 'version'}):
        raise ValueError('Original display metadata needs a reviewed title and optional reference')
    for key, limit in [('title', 240), ('code', 80), ('version', 40)]:
        if key in value and (not isinstance(value[key], str) or not value[key].strip()
                or len(value[key]) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value[key])):
            raise ValueError('Invalid original-file display metadata')
    return dict(value)


def binary_signature(raw, media):
    valid = (media == 'application/pdf' and raw.startswith(b'%PDF-') and b'%%EOF' in raw[-1024:]
             or media == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n') and raw[-8:-4] == b'IEND'
             or media == 'image/jpeg' and raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'))
    if not valid:
        raise ValueError('Original signature or ending does not match its reviewed media type')


class _Metadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.headings, self.references = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            self.handle_data(' ')
            return
        if tag in {'meta', 'link', 'img', 'hr', 'input', 'wbr', 'source'}:
            return
        if len(self.stack) >= 64:
            raise ValueError('Document metadata nesting exceeds bounds')
        classes = dict(attrs).get('class', '').split()
        entry = [tag, [], tag == 'h1', 'doc-code' in classes]
        self.stack.append(entry)

    def handle_data(self, value):
        for entry in self.stack:
            if entry[2] or entry[3]:
                entry[1].append(value)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                for _, parts, heading, reference in self.stack[index:]:
                    value = ' '.join(''.join(parts).split())
                    if heading and value:
                        self.headings.append(value)
                    if reference and value:
                        self.references.append(value)
                del self.stack[index:]
                break


def validate_descriptor(value):
    required = {'title', 'sha256', 'size_bytes', 'media_type', 'filename'}
    if (not isinstance(value, dict) or not required <= set(value)
            or set(value) - required - {'code', 'version'}
            or type(value['size_bytes']) is not int or not 0 < value['size_bytes'] <= (
                MAX_VIDEO_BYTES if value.get('media_type') == 'video/mp4' else MAX_ORIGINAL_BYTES)
            or value['media_type'] not in MEDIA
            or not isinstance(value['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', value['sha256'])
            or not isinstance(value['filename'], str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', value['filename'])
            or not value['filename'].endswith('.' + MEDIA[value['media_type']])):
        raise ValueError('Invalid reviewed original-file metadata')
    for key, limit in [('title', 240), ('code', 80), ('version', 40)]:
        if key in value and (not isinstance(value[key], str) or not value[key].strip()
                or len(value[key]) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value[key])):
            raise ValueError('Invalid original-file display metadata')
    return dict(value)


def descriptor(raw, node, format, display=None):
    """Use the selected current manifest entry; never rank filenames or dates."""
    if node.get('contentHash') != hashlib.sha256(raw).hexdigest() or node.get('size') != len(raw):
        raise ValueError('Original must match the current manifest content hash and size')
    media = format if format in BINARY_MEDIA else {'html-text': 'text/html', 'markdown': 'text/markdown', 'text/plain': 'text/plain'}[format]
    meta = node.get('meta', {})
    title = meta.get('title') if isinstance(meta, dict) else None
    values = {key: meta[key] for key in ('code', 'version') if isinstance(meta, dict) and key in meta}
    if media in BINARY_MEDIA:
        binary_signature(raw, media)
    if media in BINARY_MEDIA or display is not None:
        reviewed = display_metadata(display)
        title = reviewed['title']
        for key in ('code', 'version'):
            if key in reviewed:
                if key in values and values[key] != reviewed[key]:
                    raise ValueError('Manifest and reviewed binary metadata disagree')
                values[key] = reviewed[key]
    if format == 'html-text':
        parser = _Metadata()
        parser.feed(raw.decode('utf-8'))
        parser.close()
        headings = set(parser.headings)
        if len(headings) == 1:
            title = next(iter(headings))
        references = set(parser.references)
        if len(references) == 1:
            reference = next(iter(references))
            codes = set(re.findall(r'\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){1,8}\b', reference))
            versions = set(re.findall(r'\bv\d+(?:\.\d+){1,3}\b', reference))
            for key, candidates in [('code', codes), ('version', versions)]:
                if len(candidates) == 1:
                    found = next(iter(candidates))
                    if key in values and values[key] != found:
                        raise ValueError('Manifest and original document metadata disagree')
                    values[key] = found
    value = {'title': title, 'sha256': node['contentHash'], 'size_bytes': len(raw), 'media_type': media,
             'filename': node['contentHash'] + '.' + MEDIA[media], **values}
    if media in BINARY_MEDIA:
        stem = '-'.join(value[key] for key in ('code', 'version', 'title') if key in value)
        stem = unicodedata.normalize('NFKD', stem).encode('ascii', 'ignore').decode()
        stem = re.sub(r'[^A-Za-z0-9_.-]+', '-', stem).strip('-._')[:110].rstrip('-._')
        value['filename'] = (stem or node['contentHash']) + '.' + MEDIA[media]
    return validate_descriptor(value)


class OriginalStore:
    """Only hash-named reviewed copies; no request-controlled filesystem paths."""
    def __init__(self, root):
        self.root = Path(root)
        self.videos = VerifiedVideos()

    def read(self, value):
        value = validate_descriptor(value)
        if value['media_type'] == 'video/mp4':
            raise ValueError('Video originals require bounded streaming delivery')
        if (not self.root.is_absolute() or not self.root.is_dir()
                or any(p.is_symlink() for p in (self.root, *self.root.parents))
                or os.name == 'posix' and self.root.stat().st_mode & 0o022):
            raise ValueError('A protected original-file store is required')
        path = self.root / value['sha256']
        if path.is_symlink():
            raise ValueError('Original files cannot be symlinks')
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                               | getattr(os, 'O_NONBLOCK', 0)), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size != value['size_bytes']
                    or os.name == 'posix' and before.st_mode & 0o022):
                raise ValueError('Original-file storage does not match the reviewed descriptor')
            raw = stream.read(value['size_bytes'] + 1)
            after = os.fstat(stream.fileno())
        if (len(raw) != value['size_bytes'] or hashlib.sha256(raw).hexdigest() != value['sha256']
                or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('Original file changed; review its current version')
        return raw


def serve(handler, backend, store, ident):
    """Authorize before opening bytes, then recheck session and projection."""
    recipient = backend.gate.identified_scope(handler.headers)[0]
    row = backend.detail(handler.headers, ident)
    if not row or row['kind'] != 'document' or row['data'].get('source') != 'reviewed-working-document':
        handler.send(404, {'error': 'Original unavailable'})
        return
    value = validate_descriptor(row['data'].get('original'))
    if value['media_type'] == 'video/mp4':
        return serve_video(handler, backend, store, ident, row, recipient, value)
    raw = store.read(value)
    if (backend.detail(handler.headers, ident) != row
            or backend.gate.identified_scope(handler.headers)[0] != recipient):
        raise ValueError('Session or original-file authorization changed')
    content_type = value['media_type']
    if content_type.startswith('text/'):
        try:
            raw.decode('utf-8')
        except UnicodeDecodeError:
            # Preserve legacy encoding behavior rather than mislabeling its bytes.
            pass
        else:
            content_type += '; charset=utf-8'
    handler.send_response(200)
    handler.send_header('Content-Type', content_type)
    handler.send_header('Content-Length', str(len(raw)))
    disposition = 'attachment' if value['media_type'] == 'application/pdf' else 'inline'
    handler.send_header('Content-Disposition', disposition + '; filename="' + value['filename'] + '"')
    handler.send_header('Cache-Control', 'no-store, private')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Referrer-Policy', 'no-referrer')
    handler.send_header('X-Frame-Options', 'DENY')
    handler.send_header('Content-Security-Policy', "sandbox; default-src 'none'; style-src 'unsafe-inline'; "
                        "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    handler.end_headers()
    handler.wfile.write(raw)
