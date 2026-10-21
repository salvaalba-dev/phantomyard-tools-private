"""Originals use current reviewed fingerprints and the existing session ACL."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from original_documents import OriginalStore, descriptor, serve, validate_descriptor
from test_scoped_backend import ProjectionFixture


SOURCE = b'<html><h1>Code of conduct</h1><div class="doc-code">EX-20260101-001<br>v1.2</div><script>neverRun()</script></html>'


def sample(raw=SOURCE):
    node = {'contentHash': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'meta': {'title': 'conduct'}}
    return descriptor(raw, node, 'html-text')


class OriginalMetadataTests(unittest.TestCase):
    def test_reference_and_real_size_without_rewriting_original(self):
        value = sample()
        self.assertEqual(value['title'], 'Code of conduct')
        self.assertEqual(value['code'], 'EX-20260101-001')
        self.assertEqual(value['version'], 'v1.2')
        self.assertEqual(value['size_bytes'], len(SOURCE))
        self.assertEqual(value['sha256'], hashlib.sha256(SOURCE).hexdigest())

    def test_stale_manifest_and_conflicting_versions_fail_closed(self):
        for node in [{'contentHash': 'a' * 64, 'size': len(SOURCE)},
                     {'contentHash': hashlib.sha256(SOURCE).hexdigest(), 'size': 1},
                     {'contentHash': hashlib.sha256(SOURCE).hexdigest(), 'size': len(SOURCE),
                      'meta': {'title': 'conduct', 'version': 'v9.0'}}]:
            with self.assertRaises(ValueError):
                descriptor(SOURCE, node, 'html-text')

    def test_unknown_template_never_invents_a_version(self):
        value = sample(b'<h1>Guide</h1><p>Version v9.0 is discussed here.</p>')
        self.assertNotIn('version', value)
        self.assertNotIn('code', value)

    def test_untrusted_paths_mime_types_and_sizes_are_rejected(self):
        for patch in [{'filename': '../document.html'}, {'size_bytes': True}, {'size_bytes': 0},
                      {'size_bytes': 33 * 1024 * 1024}, {'media_type': 'application/javascript'},
                      {'sha256': '../../file'}, {'title': 'Title\r\nInjected: true'}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_descriptor(sample() | patch)


class OriginalDeliveryTests(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.original = sample()
        self.path = self.root / self.original['sha256']
        self.path.write_bytes(SOURCE)
        self.path.chmod(0o600)
        self.store = OriginalStore(self.root)
        self.ident = self.add('Conduct', 'document')
        self.replace(self.ident, {'title': 'Conduct', 'source': 'reviewed-working-document', 'original': self.original})
        self.handler = Mock(headers=self.headers, wfile=BytesIO())

    def test_authorized_original_is_exact_and_sandboxed_without_cache(self):
        serve(self.handler, self.backend, self.store, self.ident)
        self.assertEqual(self.handler.wfile.getvalue(), SOURCE)
        self.handler.send_response.assert_called_once_with(200)
        headers = dict(call.args for call in self.handler.send_header.call_args_list)
        self.assertEqual(headers['Cache-Control'], 'no-store, private')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertTrue(headers['Content-Security-Policy'].startswith('sandbox;'))
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertNotIn('allow-scripts', headers['Content-Security-Policy'])
        self.assertNotIn('allow-same-origin', headers['Content-Security-Policy'])

    def test_denied_document_and_unknown_ids_do_not_open_the_store(self):
        store = Mock()
        for ident in (self.hidden, 'f' * 64):
            serve(self.handler, self.backend, store, ident)
        store.read.assert_not_called()
        self.assertNotIn(self.hidden, self.loaded)

    def test_expired_session_never_reads_original_bytes(self):
        self.gate.recipients.clear()
        store = Mock()
        with self.assertRaises(ValueError):
            serve(self.handler, self.backend, store, self.ident)
        store.read.assert_not_called()

    def test_authorization_changes_during_read_release_no_bytes(self):
        store = Mock()
        def read(_):
            self.gate.recipients.clear()
            return SOURCE
        store.read.side_effect = read
        with self.assertRaises(ValueError):
            serve(self.handler, self.backend, store, self.ident)
        self.assertEqual(self.handler.wfile.getvalue(), b'')
        self.handler.send_response.assert_not_called()

    def test_payload_replacement_during_read_releases_no_bytes(self):
        store = Mock()
        def read(_):
            self.replace(self.ident, {'title': 'Changed'})
            return SOURCE
        store.read.side_effect = read
        with self.assertRaises(ValueError):
            serve(self.handler, self.backend, store, self.ident)
        self.handler.send_response.assert_not_called()

    def test_changed_copy_is_not_served(self):
        self.path.write_bytes(b'x' * len(SOURCE))
        with self.assertRaises(ValueError):
            serve(self.handler, self.backend, self.store, self.ident)
        self.handler.send_response.assert_not_called()

    def test_metadata_never_contains_a_host_path_or_original_body(self):
        encoded = json.dumps(self.backend.state(self.headers))
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn('neverRun', encoded)

    def test_non_original_documents_cannot_be_reinterpreted(self):
        self.replace(self.ident, {'title': 'Conduct', 'source': 'reviewed-profile', 'original': self.original})
        store = Mock()
        serve(self.handler, self.backend, store, self.ident)
        store.read.assert_not_called()

    def test_symlinks_are_not_followed(self):
        if not hasattr(Path, 'symlink_to'):
            self.skipTest('Symlinks unavailable')
        target = self.root / 'other'
        target.write_bytes(SOURCE)
        target.chmod(0o600)
        self.path.unlink()
        try:
            self.path.symlink_to(target)
        except OSError:
            self.skipTest('Symlink creation unavailable')
        with self.assertRaises((ValueError, OSError)):
            self.store.read(self.original)
