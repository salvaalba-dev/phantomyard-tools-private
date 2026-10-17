"""Default selection uses fresh existing observations, never native credentials."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from runtime_default import RuntimeDefault
from scoped_backend import ScopedBackend
from test_scoped_backend import ProjectionFixture


class RuntimeDefaultTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'default.json'
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.report = {'org': 'example', 'persona': 'administrator', 'provenance': 'config',
                       'exists': True, 'served': True, 'checked_at': self.now.isoformat(),
                       'vault': 'PRIVATE_SENTINEL', 'extra_diagnostic': {'token': 'PRIVATE_SENTINEL'}}
        self.write()
        self.reader = RuntimeDefault(str(self.path), organization='example', clock=lambda: self.now)

    def write(self):
        self.path.write_text(json.dumps(self.report), encoding='utf-8')
        self.path.chmod(0o600)

    def test_existing_observation_shape_is_normalized_without_exposing_extra_fields(self):
        self.assertEqual(self.reader(), {'default_persona': {'resolved': 'administrator',
                          'provenance': 'config', 'exists': True, 'served': True}})
        self.assertNotIn('PRIVATE_SENTINEL', str(self.reader()))

    def test_file_is_read_again_after_existing_refresh_replaces_it(self):
        self.assertEqual(self.reader()['default_persona']['resolved'], 'administrator')
        self.report['persona'] = 'project-guide'
        self.write()
        self.assertEqual(self.reader()['default_persona']['resolved'], 'project-guide')

    def test_stale_future_naive_and_missing_timestamps_are_rejected(self):
        for value in ((self.now-timedelta(seconds=1801)).isoformat(),
                      (self.now+timedelta(seconds=1)).isoformat(), '2026-01-01T00:00:00', None):
            self.report['checked_at'] = value
            self.write()
            with self.assertRaises(ValueError):
                self.reader()

    def test_foreign_unknown_unserved_or_missing_personas_are_not_guessed(self):
        for changes in ({'org': 'foreign'}, {'persona': '../other'}, {'provenance': 'guess'},
                        {'exists': False}, {'served': False}):
            original = self.report.copy()
            self.report.update(changes)
            self.write()
            with self.assertRaises(ValueError):
                self.reader()
            self.report = original

    def test_duplicate_malformed_and_oversized_input_is_rejected(self):
        for raw in ('{"org":"example","org":"foreign"}', '{', 'x'*16385):
            self.path.write_text(raw, encoding='utf-8')
            with self.assertRaises(ValueError):
                self.reader()

    def test_operator_configuration_requires_explicit_absolute_path_and_freshness(self):
        for changes in ({'path': 'relative.json'}, {'max_age': True}, {'max_age': 86401}, {'organization': '../other'}):
            options = {'path': str(self.path), 'organization': 'example'} | changes
            with self.assertRaises(ValueError):
                RuntimeDefault(**options)

    @unittest.skipIf(os.name == 'nt', 'POSIX ownership modes and symlinks')
    def test_linked_or_shared_writable_observation_is_rejected(self):
        self.path.chmod(0o666)
        with self.assertRaises(ValueError):
            self.reader()
        self.path.chmod(0o600)
        link = self.path.with_name('link.json')
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            RuntimeDefault(str(link), organization='example')()


class RuntimeDefaultIntegrationTests(ProjectionFixture):
    def test_observation_expiry_cannot_disable_identified_issuer_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'default.json'
            now = datetime.now(timezone.utc)
            path.write_text(json.dumps({'org': 'example', 'persona': 'administrator',
                'provenance': 'config', 'exists': True, 'served': True, 'checked_at': now.isoformat()}))
            path.chmod(0o600)
            reader = RuntimeDefault(str(path), organization='example', clock=lambda: now)
            backend = ScopedBackend(self.gate, lambda: self.catalog, self.load, default_report_loader=reader)
            first = backend.workspace(self.headers)
            self.assertTrue(first['navigation']['assistant']['eligible'])
            reader.clock = lambda: now + timedelta(seconds=1801)
            second = backend.workspace(self.headers)
            self.assertTrue(second['navigation']['assistant']['eligible'])
            self.assertEqual(first['navigation']['assistant'], second['navigation']['assistant'])
            self.assertEqual(second['navigation']['assistant']['source'], 'session-issuer')
            self.assertEqual(first['resources'], second['resources'])
            self.assertEqual(first['view_revision'], second['view_revision'])


if __name__ == '__main__':
    unittest.main()
