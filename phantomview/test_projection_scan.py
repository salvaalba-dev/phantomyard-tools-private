"""Request-local projection scans retain revocation and concurrent-change checks."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import projection_review
from projection_review import PrivateRecordStore
from scoped_backend import ScopedBackend
import test_projection_review as publication_fixture
import test_scoped_backend as access_fixture


class ProjectionScanTests(unittest.TestCase):
    def setUp(self):
        self.fixture = publication_fixture.ProjectionReviewTests()
        self.fixture.setUp()
        self.auth = access_fixture.ProjectionFixture()
        self.auth.setUp()
        self.addCleanup(self.auth.doCleanups)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root.chmod(0o700)
        self.publisher = self.fixture.publisher(self.root)
        self.bundle = self.fixture.approval()
        self.publisher.publish(self.bundle, self.fixture.draft, expected_revision=None)
        self.backend = ScopedBackend(self.auth.gate, self.publisher.catalog, self.publisher.record,
                                     projection_scan=self.publisher.scan)

    def test_two_source_validations_per_request_and_identical_authorized_results(self):
        legacy = ScopedBackend(self.auth.gate, self.publisher.catalog, self.publisher.record)
        expected = legacy.state(self.auth.headers)
        with patch('projection_review.prepare_like', wraps=projection_review.prepare_like) as reads:
            self.assertEqual(self.backend.state(self.auth.headers), expected)
            self.assertEqual(reads.call_count, 2)
            self.assertEqual(self.backend.state(self.auth.headers), expected)
            self.assertEqual(reads.call_count, 4)

    def test_source_change_during_record_loading_rejects_the_entire_response(self):
        original = PrivateRecordStore.__call__
        changed = False

        def load(store, ident):
            nonlocal changed
            raw = original(store, ident)
            if not changed:
                self.fixture.source['actors'][0]['name'] = 'Changed during scan'
                changed = True
            return raw

        with patch.object(PrivateRecordStore, '__call__', load), self.assertRaises(ValueError):
            self.backend.state(self.auth.headers)

    def test_changed_record_bytes_are_still_read_twice_and_rejected(self):
        original = PrivateRecordStore.__call__
        changed = False

        def load(store, ident):
            nonlocal changed
            raw = original(store, ident)
            if raw and not changed:
                path = store.root / (ident + '.json')
                path.write_bytes(raw + b' ')
                changed = True
            return raw

        with patch.object(PrivateRecordStore, '__call__', load), self.assertRaises(ValueError):
            self.backend.state(self.auth.headers)

    def test_denied_session_never_opens_a_scan(self):
        with patch.object(self.publisher, 'active', side_effect=AssertionError('Must not open sources')):
            with self.assertRaises(ValueError):
                self.backend.state({})

    def test_logout_during_the_scan_still_prevents_release(self):
        original = PrivateRecordStore.__call__
        revoked = False

        def load(store, ident):
            nonlocal revoked
            raw = original(store, ident)
            if not revoked:
                self.auth.gate.logout(self.auth.headers)
                revoked = True
            return raw

        with patch.object(PrivateRecordStore, '__call__', load), self.assertRaises(ValueError):
            self.backend.state(self.auth.headers)

    def test_pointer_change_after_payload_checks_prevents_release(self):
        @contextmanager
        def changed_pointer():
            with self.publisher.scan() as loaders:
                yield loaders
                (self.root / 'active.json').write_text(json.dumps({'revision': 'f' * 64}), encoding='utf-8')
        self.backend.projection_scan = changed_pointer
        with self.assertRaises((OSError, ValueError)):
            self.backend.state(self.auth.headers)

    def test_no_closed_scan_is_reused_after_a_later_source_change(self):
        self.backend.state(self.auth.headers)
        self.fixture.source['actors'][0]['name'] = 'Changed between requests'
        with self.assertRaises(ValueError):
            self.backend.state(self.auth.headers)


if __name__ == '__main__':
    unittest.main()
