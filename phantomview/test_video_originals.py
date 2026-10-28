"""Synthetic MP4 ranges preserve native ACL, fingerprints and bounded memory."""
from contextlib import contextmanager
from email.message import Message
import hashlib
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from original_documents import OriginalStore, serve, validate_descriptor
from test_scoped_backend import ProjectionFixture
from video_originals import CHUNK_BYTES, MAX_VIDEO_BYTES, byte_range, descriptor, verify
from working_documents import bindings, collect, validated


def box(kind, payload=b''):
    return (8 + len(payload)).to_bytes(4, 'big') + kind + payload


def movie(payload=b'fictional meeting bytes'):
    return box(b'ftyp', b'isom\x00\x00\x00\x00isom') + box(b'moov') + box(b'mdat', payload)


def metadata(raw):
    return {'contentHash': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}


class VideoRangeTests(unittest.TestCase):
    def test_whole_open_closed_and_suffix_ranges(self):
        for value, expected in [(None, (0, 99, 200)), ('bytes=4-9', (4, 9, 206)),
                                ('bytes=4-', (4, 99, 206)), ('bytes=-8', (92, 99, 206)),
                                ('bytes=90-200', (90, 99, 206)), ('bytes=-200', (0, 99, 206))]:
            with self.subTest(value=value):
                self.assertEqual(byte_range(value, 100), expected)

    def test_malformed_multi_and_unsatisfiable_ranges(self):
        for value in ('bytes=100-', 'bytes=5-4', 'bytes=-0', 'bytes=-', 'bytes=0-1,4-5',
                      'items=0-1', 'bytes=+1-4', 'bytes= 1-4', 'bytes=1-4\r\nX: y',
                      'bytes=' + '9' * 90 + '-', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                byte_range(value, 100)


class VideoStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.raw = movie(b'x' * (CHUNK_BYTES * 2 + 9))
        self.node = metadata(self.raw)
        self.path = self.root / self.node['contentHash']
        self.path.write_bytes(self.raw)
        self.path.chmod(0o600)
        with self.path.open('rb') as stream:
            self.value = descriptor(stream, self.node, {'title': 'Synthetic meeting'})
        self.store = OriginalStore(self.root)

    def test_descriptor_contains_metadata_without_media_bytes(self):
        self.assertEqual(self.value['media_type'], 'video/mp4')
        self.assertEqual(self.value['size_bytes'], len(self.raw))
        self.assertEqual(self.value['sha256'], self.node['contentHash'])
        self.assertNotIn('content', self.value)

    def test_video_never_uses_the_whole_file_read_api(self):
        with self.assertRaises(ValueError):
            self.store.read(self.value)

    def test_video_bound_does_not_expand_other_original_limits(self):
        for size in (True, 0, MAX_VIDEO_BYTES + 1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_descriptor(self.value | {'size_bytes': size})
        self.assertEqual(validate_descriptor(self.value | {'size_bytes': MAX_VIDEO_BYTES})['size_bytes'], MAX_VIDEO_BYTES)
        with self.assertRaises(ValueError):
            validate_descriptor(self.value | {'size_bytes': 40 * 1024 ** 2, 'media_type': 'application/pdf', 'filename': 'movie.pdf'})

    def test_verification_reads_only_bounded_blocks(self):
        class Bounded:
            def __init__(self, stream):
                self.stream = stream

            def __getattr__(self, key):
                return getattr(self.stream, key)

            def read(self, size=-1):
                if not 0 <= size <= CHUNK_BYTES:
                    raise AssertionError('Unbounded original read')
                return self.stream.read(size)

        with self.path.open('rb') as stream:
            verify(Bounded(stream), self.node['contentHash'], len(self.raw))

    def test_large_video_exceeds_document_cap_without_a_whole_file_buffer(self):
        path = self.root / 'large-video'
        payload_size = 34 * 1024 ** 2
        with path.open('wb') as stream:
            stream.write(box(b'ftyp', b'isom\x00\x00\x00\x00isom') + box(b'moov'))
            stream.write((8 + payload_size).to_bytes(4, 'big') + b'mdat')
            stream.seek(payload_size - 1, 1)
            stream.write(b'\x00')
        path.chmod(0o600)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(CHUNK_BYTES):
                digest.update(block)
        with path.open('rb') as stream:
            value = descriptor(stream, {'contentHash': digest.hexdigest(), 'size': path.stat().st_size},
                               {'title': 'Large synthetic meeting'})
        self.assertGreater(value['size_bytes'], 32 * 1024 ** 2)

    def test_invalid_and_truncated_containers_fail(self):
        for raw in (b'<html>not a video</html>', box(b'ftyp', b'isom' * 3),
                    self.raw[:-1], self.raw[:20] + b'\x00\x00\x00\x01moov'):
            self.path.write_bytes(raw)
            with self.path.open('rb') as stream, self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                descriptor(stream, metadata(raw), {'title': 'Synthetic meeting'})

    def test_wrong_hash_size_and_version_fail(self):
        for node in (self.node | {'contentHash': 'a' * 64}, self.node | {'size': len(self.raw) - 1},
                     self.node | {'meta': {'version': 'v2.0'}}):
            with self.path.open('rb') as stream, self.subTest(node=node), self.assertRaises(ValueError):
                descriptor(stream, node, {'title': 'Synthetic meeting'})

    @unittest.skipUnless(os.name == 'posix', 'Protected POSIX identity cache')
    def test_unchanged_verified_ranges_reuse_the_hash_verdict(self):
        with patch('video_originals.verify', wraps=verify) as checked:
            for _ in range(3):
                with self.store.videos.open(self.root, self.value):
                    pass
        self.assertEqual(checked.call_count, 1)

    def test_changed_file_cannot_reuse_prior_verification(self):
        with self.store.videos.open(self.root, self.value):
            pass
        self.path.write_bytes(movie(b'y' * (CHUNK_BYTES * 2 + 9)))
        with self.assertRaises(ValueError), self.store.videos.open(self.root, self.value):
            pass

    @unittest.skipUnless(os.name == 'posix', 'POSIX write and link modes')
    def test_writable_sources_and_hard_links_are_rejected(self):
        self.path.chmod(0o620)
        with self.assertRaises(ValueError), self.store.videos.open(self.root, self.value):
            pass
        self.path.chmod(0o600)
        os.link(self.path, self.root / 'alias')
        with self.assertRaises(ValueError), self.store.videos.open(self.root, self.value):
            pass


class VideoDeliveryTests(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.raw = movie(b'fictional bytes' * 45000)
        self.path = self.root / metadata(self.raw)['contentHash']
        self.path.write_bytes(self.raw)
        self.path.chmod(0o600)
        with self.path.open('rb') as stream:
            self.original = descriptor(stream, metadata(self.raw), {'title': 'Synthetic meeting'})
        self.store = OriginalStore(self.root)
        self.ident = self.add('Synthetic meeting', 'document')
        self.replace(self.ident, {'source': 'reviewed-working-document', 'original': self.original})
        self.handler = Mock(headers=dict(self.headers), wfile=BytesIO())

    def test_authorized_whole_video_is_exact(self):
        serve(self.handler, self.backend, self.store, self.ident)
        self.assertEqual(self.handler.wfile.getvalue(), self.raw)
        self.handler.send_response.assert_called_once_with(200)
        headers = dict(call.args for call in self.handler.send_header.call_args_list)
        self.assertEqual(headers['Accept-Ranges'], 'bytes')
        self.assertEqual(headers['Content-Type'], 'video/mp4')
        self.assertEqual(headers['Cache-Control'], 'no-store, private')

    def test_seek_and_suffix_responses_are_exact(self):
        for request in ('bytes=19-90', 'bytes=-19', 'bytes=37-'):
            handler = Mock(headers=dict(self.headers) | {'Range': request}, wfile=BytesIO())
            start, end, _ = byte_range(request, len(self.raw))
            serve(handler, self.backend, self.store, self.ident)
            self.assertEqual(handler.wfile.getvalue(), self.raw[start:end + 1])
            handler.send_response.assert_called_once_with(206)
            headers = dict(call.args for call in handler.send_header.call_args_list)
            self.assertEqual(headers['Content-Range'], f'bytes {start}-{end}/{len(self.raw)}')
            self.assertEqual(int(headers['Content-Length']), end - start + 1)

    def test_bad_ranges_do_not_open_the_original(self):
        self.handler.headers['Range'] = 'bytes=0-1,4-5'
        with patch.object(self.store.videos, 'open') as opened:
            serve(self.handler, self.backend, self.store, self.ident)
        opened.assert_not_called()
        self.handler.send_response.assert_called_once_with(416)
        self.assertEqual(self.handler.wfile.getvalue(), b'')

    def test_duplicate_range_headers_are_rejected(self):
        headers = Message()
        for name, value in self.headers.items():
            headers[name] = value
        headers['Range'], headers['Range'] = 'bytes=0-1', 'bytes=4-5'
        self.handler.headers = headers
        serve(self.handler, self.backend, self.store, self.ident)
        self.handler.send_response.assert_called_once_with(416)

    def test_if_range_without_a_matching_validator_returns_the_whole_file(self):
        self.handler.headers.update({'Range': 'bytes=0-9', 'If-Range': '"old-copy"'})
        serve(self.handler, self.backend, self.store, self.ident)
        self.handler.send_response.assert_called_once_with(200)
        self.assertEqual(self.handler.wfile.getvalue(), self.raw)

    def test_real_http_range_and_denial_responses(self):
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        import threading
        import phantomview as pv

        server = ThreadingHTTPServer(('127.0.0.1', 0), pv.Handler)
        server.gate = self.gate
        server.access_errors = (ValueError, self.gate.access.core.Invalid)
        server.scoped_backend = self.backend
        server.original_documents = self.store
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for headers, expected in [
                (dict(self.headers) | {'Range': 'bytes=10-29'}, 206),
                (dict(self.headers) | {'Range': 'bytes=999999999-'}, 416),
                ({'Cookie': 'phantomview=expired', 'Range': 'bytes=10-29'}, 401),
            ]:
                connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                try:
                    connection.request('GET', '/api/document-original/' + self.ident, headers=headers)
                    response = connection.getresponse()
                    payload = response.read()
                    self.assertEqual(response.status, expected)
                    if expected == 206:
                        self.assertEqual(payload, self.raw[10:30])
                        self.assertEqual(response.getheader('Content-Range'), f'bytes 10-29/{len(self.raw)}')
                    elif expected == 416:
                        self.assertEqual(payload, b'')
                finally:
                    connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_denied_and_expired_sessions_never_open_video_bytes(self):
        with patch.object(self.store.videos, 'open') as opened:
            serve(self.handler, self.backend, self.store, self.hidden)
            self.gate.recipients.clear()
            with self.assertRaises(ValueError):
                serve(self.handler, self.backend, self.store, self.ident)
        opened.assert_not_called()

    def test_expiration_after_hashing_releases_no_headers_or_bytes(self):
        real = self.store.videos.open

        @contextmanager
        def revoked(*args):
            with real(*args) as value:
                self.gate.recipients.clear()
                yield value

        with patch.object(self.store.videos, 'open', revoked), self.assertRaises(ValueError):
            serve(self.handler, self.backend, self.store, self.ident)
        self.handler.send_response.assert_not_called()
        self.assertEqual(self.handler.wfile.getvalue(), b'')

    def check_interrupted(self, change):
        target = BytesIO()

        def write(block):
            target.write(block)
            change()

        self.handler.wfile = Mock(write=write)
        serve(self.handler, self.backend, self.store, self.ident)
        self.assertEqual(target.getvalue(), self.raw[:CHUNK_BYTES])
        self.assertIs(self.handler.close_connection, True)
        self.handler.send_response.assert_called_once_with(200)

    def test_expiration_during_playback_stops_the_connection(self):
        self.check_interrupted(lambda: self.gate.recipients.clear())

    def test_session_expiry_during_playback_stops_the_connection(self):
        self.check_interrupted(lambda: self.gate.sessions.clear())

    def test_projection_change_during_playback_stops_the_connection(self):
        self.check_interrupted(lambda: self.replace(self.ident, {'title': 'Changed'}))

    def test_native_policy_change_during_playback_stops_the_connection(self):
        self.check_interrupted(lambda: self.org['policies']['phantomview'].update(
            human_category_limits={'secretary': ['category-3']}))

    def test_file_change_during_playback_stops_the_connection(self):
        self.check_interrupted(lambda: self.path.write_bytes(b'x' * len(self.raw)))

    def test_malformed_policy_during_playback_closes_without_a_second_response(self):
        self.check_interrupted(lambda: setattr(self.backend, 'detail', Mock(side_effect=TypeError('Changed policy'))))

    def test_recursive_policy_during_playback_closes_without_a_second_response(self):
        self.check_interrupted(lambda: setattr(self.backend, 'detail', Mock(side_effect=RecursionError('Changed policy'))))


class VideoCollectionTests(unittest.TestCase):
    def test_current_native_video_collects_only_reviewed_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            (root / 'blobs').mkdir(mode=0o700)
            path = root / 'blobs' / 'video'
            raw = movie()
            path.write_bytes(raw)
            path.chmod(0o600)
            node = {**metadata(raw), 'kind': 'doc', 'urn': 'urn:example:video', 'slug': 'video',
                    'category': 'category-4-project', 'owners': ['lead'], 'parentMac': 'folder',
                    'locations': [{'backend': 'local', 'path': str(path)}]}
            manifest = {'manifest': {'org': 'example'}, 'nodes': [node,
                        {'kind': 'folder', 'mac': 'folder', 'slug': 'Meetings'}]}
            actor = {'id': 'coordinator', 'org': 'example', 'role': 'lead', 'searchable': True}
            binding = {'urn': node['urn'], 'actor': actor['id'], 'sha256': node['contentHash'],
                       'format': 'video/mp4', 'original': True, 'original_only': True,
                       'display': {'title': 'Reviewed meeting'}}
            value = collect(manifest, root / 'manifest.yaml', [binding], [actor], lambda _: True)[node['urn']]
            self.assertEqual(value['content'], 'Reviewed meeting')
            self.assertEqual(value['format'], 'video/mp4')
            self.assertEqual(validated(value), value)
            self.assertNotIn('fictional meeting bytes', str(value))
            with self.assertRaises(ValueError):
                collect(manifest, root / 'manifest.yaml', [binding], [actor], lambda _: False)
            with self.assertRaises(ValueError):
                collect(manifest, root / 'manifest.yaml', [binding | {'sha256': 'a' * 64}], [actor], lambda _: True)
            with self.assertRaises(ValueError):
                bindings([binding | {'original_only': False}])
