"""Bounded MP4 verification and authenticated single-range original delivery."""
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import os
import re
import stat
import threading

MAX_VIDEO_BYTES = 8 * 1024 ** 3
CHUNK_BYTES = 256 * 1024
MAX_VERIFIED_FILES = 32


def fingerprint(stream):
    value = os.fstat(stream.fileno())
    if (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1
            or not 0 < value.st_size <= MAX_VIDEO_BYTES
            or os.name == 'posix' and value.st_mode & 0o022):
        raise ValueError('A protected complete regular video is required')
    return tuple(getattr(value, key) for key in (
        'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns',
        'st_mode', 'st_uid', 'st_gid', 'st_nlink'))


def verify(stream, expected_hash, expected_size):
    """Hash the entire file in bounded blocks; never trust a partial range hash."""
    before = fingerprint(stream)
    if before[2] != expected_size:
        raise ValueError('Video size differs from its current native descriptor')
    stream.seek(0)
    head = stream.read(16)
    if len(head) != 16 or head[4:8] != b'ftyp' or not 16 <= int.from_bytes(head[:4], 'big') <= 1024:
        raise ValueError('A reviewed MP4 file-type box is required')
    # Check complete top-level boxes without loading media payloads or decoding.
    position, boxes, kinds = 0, 0, set()
    while position < expected_size:
        if boxes >= 10000 or expected_size - position < 8:
            raise ValueError('Invalid or excessive MP4 boxes')
        stream.seek(position)
        header = stream.read(16)
        length = int.from_bytes(header[:4], 'big')
        header_size = 8
        if length == 1:
            if len(header) < 16:
                raise ValueError('Truncated extended MP4 box')
            length, header_size = int.from_bytes(header[8:16], 'big'), 16
        elif length == 0:
            length = expected_size - position
        if length < header_size or length > expected_size - position:
            raise ValueError('Truncated MP4 container')
        kinds.add(header[4:8])
        position += length
        boxes += 1
    if not {b'ftyp', b'moov', b'mdat'} <= kinds:
        raise ValueError('MP4 metadata and media boxes are required')
    stream.seek(0)
    digest = hashlib.sha256()
    total = 0
    while block := stream.read(CHUNK_BYTES):
        total += len(block)
        if total > expected_size:
            raise ValueError('Video grew during verification')
        digest.update(block)
    if (total != expected_size or digest.hexdigest() != expected_hash
            or fingerprint(stream) != before):
        raise ValueError('Video changed; review its current native version')
    stream.seek(0)
    return before


def byte_range(value, size):
    """Accept exactly one bounded HTTP byte range, including suffix ranges."""
    if value is None:
        return 0, size - 1, 200
    if not isinstance(value, str) or len(value) > 100:
        raise ValueError('Invalid video range')
    match = re.fullmatch(r'bytes=([0-9]{0,20})-([0-9]{0,20})', value)
    if not match or not any(match.groups()):
        raise ValueError('A single video byte range is required')
    first, last = match.groups()
    if not first:
        count = int(last)
        if count == 0:
            raise ValueError('Empty suffix range')
        return max(0, size - count), size - 1, 206
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError('Unsatisfiable video range')
    return start, end, 206


def descriptor(stream, node, display):
    """Publish only reviewed labels; keep media bytes out of the projection."""
    from original_documents import display_metadata, validate_descriptor
    reviewed = display_metadata(display)
    metadata = node.get('meta', {})
    if not isinstance(metadata, dict):
        raise ValueError('Structured native video metadata required')
    for key in ('code', 'version'):
        if key in metadata and metadata[key] != reviewed.get(key):
            raise ValueError('Native and reviewed video metadata disagree')
    size, digest = node.get('size'), node.get('contentHash')
    if (type(size) is not int or not 0 < size <= MAX_VIDEO_BYTES
            or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)):
        raise ValueError('Exact native video size and fingerprint required')
    verify(stream, digest, size)
    return validate_descriptor({**reviewed, 'sha256': digest, 'size_bytes': size,
                                'media_type': 'video/mp4', 'filename': digest + '.mp4'})


class VerifiedVideos:
    """Cache hash verdicts only for unchanged protected POSIX file identities."""
    def __init__(self):
        self._verified = OrderedDict()
        self._lock = threading.Lock()

    @contextmanager
    def open(self, root, value):
        if (not root.is_absolute() or not root.is_dir()
                or any(path.is_symlink() for path in (root, *root.parents))
                or os.name == 'posix' and root.stat().st_mode & 0o022):
            raise ValueError('A protected original-file store is required')
        path = root / value['sha256']
        if path.is_symlink():
            raise ValueError('Video files cannot be symlinks')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            before = fingerprint(stream)
            if before[2] != value['size_bytes']:
                raise ValueError('Video size differs from its reviewed descriptor')
            key = (str(root), value['sha256'], before)
            with self._lock:
                if os.name != 'posix' or key not in self._verified:
                    verify(stream, value['sha256'], value['size_bytes'])
                if os.name == 'posix':
                    self._verified[key] = True
                    self._verified.move_to_end(key)
                    while len(self._verified) > MAX_VERIFIED_FILES:
                        self._verified.popitem(last=False)
            if fingerprint(stream) != before:
                raise ValueError('Verified video changed before delivery')
            yield stream, before


def serve_video(handler, backend, store, ident, row, recipient, value):
    """Recheck authorization and file stability before every bounded write."""
    def authorized():
        if (backend.detail(handler.headers, ident) != row
                or backend.gate.identified_scope(handler.headers)[0] != recipient):
            raise ValueError('Session or video authorization changed')

    try:
        ranges = handler.headers.get_all('Range') if hasattr(handler.headers, 'get_all') else None
        if ranges is not None and len(ranges) != 1:
            raise ValueError('Duplicate ranges are not supported')
        # No public validator is emitted: If-Range cannot establish a match.
        requested = None if handler.headers.get('If-Range') is not None else handler.headers.get('Range')
        start, end, status = byte_range(requested, value['size_bytes'])
    except ValueError:
        authorized()
        handler.send_response(416)
        handler.send_header('Content-Range', 'bytes */' + str(value['size_bytes']))
        handler.send_header('Content-Length', '0')
        handler.send_header('Cache-Control', 'no-store, private')
        handler.end_headers()
        return
    with store.videos.open(store.root, value) as (stream, before):
        authorized()
        handler.send_response(status)
        for name, text in {
            'Content-Type': 'video/mp4', 'Content-Length': str(end - start + 1),
            'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store, private',
            'Content-Disposition': 'inline; filename="' + value['filename'] + '"',
            'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
            'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'none'; media-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        }.items():
            handler.send_header(name, text)
        if status == 206:
            handler.send_header('Content-Range', f'bytes {start}-{end}/{value["size_bytes"]}')
        handler.end_headers()
        stream.seek(start)
        remaining = end - start + 1
        try:
            while remaining:
                block = stream.read(min(CHUNK_BYTES, remaining))
                if not block or fingerprint(stream) != before:
                    raise ValueError('Video changed during delivery')
                authorized()
                handler.wfile.write(block)
                remaining -= len(block)
            if fingerprint(stream) != before:
                raise ValueError('Video changed during delivery')
        except (ValueError, TypeError, RecursionError, KeyError, PermissionError, OSError):
            # Headers are already committed: close, never append a second response.
            handler.close_connection = True
