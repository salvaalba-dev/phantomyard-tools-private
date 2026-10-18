"""Private authority refresh shares collection; stale or mismatched copies deny."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from authority_publication import AuthorityPublication, META, PublishedAuthority
import phantomview as pv
from test_setup_source_compatibility import proposed_organization


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.source = self.root / 'org.json'
        self.org = proposed_organization()
        self.org['humans'][0]['email'] = 'private-registry-marker@example.invalid'
        self.source.write_text(json.dumps(self.org), encoding='utf-8')
        self.source.chmod(0o600)
        self.observer = pv.Observatory(self.root / 'config.json')
        self.observer.config = {'mode': 'existing', 'org_files': [str(self.source)],
            'personas_dir': '', 'persona_paths': {}, 'remote_personas': {},
            'docs_manifests': [], 'auto_procedures': False}
        self.state = self.observer.refresh()
        self.index = self.root / 'reader' / 'index.json'
        self.index.parent.mkdir(mode=0o750)
        self.index.parent.chmod(0o750)
        self.private = self.root / 'private'
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.ticks = [100]
        self.publication = AuthorityPublication(self.private, 'example', clock=lambda: self.ticks[0])
        self.reader = PublishedAuthority(self.private, self.index, 'example', str(self.source),
                                         max_age=30, clock=lambda: self.ticks[0])

    def publish(self, state=None):
        self.observer.export(self.index, state or self.state, authority=self.publication)

    def test_complete_private_document_never_enters_index_or_data(self):
        self.publish()
        self.assertEqual(self.reader.read(), self.org)
        for public in (self.observer.data(), json.loads(self.index.read_text(encoding='utf-8'))):
            self.assertNotIn('private-registry-marker', json.dumps(public))
            self.assertNotIn(META, json.dumps(public))
            self.assertNotIn('organization_inputs', public)
        if os.name == 'posix':
            self.assertEqual(self.publication.path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(self.index.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.private.iterdir()), [self.publication.path])

    def test_default_export_does_not_publish_authority(self):
        self.observer.export(self.index, self.state)
        self.assertFalse(self.publication.path.exists())
        with self.assertRaises(ValueError):
            self.reader()

    def test_reader_does_not_open_the_original_source(self):
        self.publish()
        self.source.unlink()
        self.assertEqual(self.reader.read(), self.org)
        self.ticks[0] = 130
        with self.assertRaises(ValueError):
            self.reader()

    @unittest.skipUnless(os.name == 'nt', 'Windows short-path regression')
    def test_windows_short_source_path_matches_the_collected_resolved_path(self):
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.kernel32.GetShortPathNameW(str(self.source), buffer, len(buffer))
        if not result or str(Path(buffer.value).resolve()) == str(Path(buffer.value)):
            self.skipTest('Filesystem has no distinct short-path alias')
        self.observer.config['org_files'] = [buffer.value]
        self.state = self.observer.refresh()
        self.publish()
        reader = PublishedAuthority(self.private, self.index, 'example', buffer.value,
                                    max_age=30, clock=lambda: self.ticks[0])
        self.assertEqual(reader.read(), self.org)

    def test_clock_expiry_and_future_dates_fail_without_fallback(self):
        self.publish()
        for timestamp in (99, 130, 200):
            self.ticks[0] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.reader()

    def test_refresh_renews_lease_and_policy_change_changes_directory(self):
        self.publish()
        first = self.reader().revision
        self.org['humans'][1]['telegram_user_id'] = 2002
        self.source.write_text(json.dumps(self.org), encoding='utf-8')
        self.ticks[0] = 120
        self.state = self.observer.refresh()
        self.publish()
        self.assertNotEqual(first, self.reader().revision)
        self.ticks[0] = 149
        self.assertEqual(self.reader.read(), self.org)

    def test_failed_collection_invalidates_copy_while_legacy_index_is_preserved(self):
        self.publish()
        previous = self.index.read_bytes()
        self.source.write_text('{private-invalid-input', encoding='utf-8')
        failed = self.observer.refresh()
        self.assertTrue(failed['error'])
        with self.assertRaises(ValueError):
            self.publish(failed)
        self.assertEqual(self.index.read_bytes(), previous)
        self.assertEqual(json.loads(self.publication.path.read_text()),
                         {'status': 'unavailable', 'organization': 'example'})
        with self.assertRaises(ValueError):
            self.reader()

    def test_source_drift_after_collection_invalidates_copy(self):
        self.publish()
        self.org['humans'][1].pop('counterpart_persona')
        self.source.write_text(json.dumps(self.org), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.publish()
        with self.assertRaises(ValueError):
            self.reader()

    def test_failed_index_write_denies_a_new_unpaired_observation(self):
        self.publish()
        self.org['organization']['name'] = 'Changed organization'
        self.source.write_text(json.dumps(self.org), encoding='utf-8')
        self.state = self.observer.refresh()
        with patch.object(pv, 'atomic_json', side_effect=OSError('Index unavailable')):
            with self.assertRaises(OSError):
                self.publish()
        with self.assertRaises(ValueError):
            self.reader()

    def test_wrong_source_index_organization_or_digest_is_denied(self):
        self.publish()
        original = json.loads(self.index.read_text(encoding='utf-8'))
        for change in ('source', 'organization', 'digest', 'error'):
            index = copy.deepcopy(original)
            if change == 'source':
                index['config']['org_files'] = ['/other/org.yaml']
            elif change == 'organization':
                index['snapshot']['organizations'][0]['id'] = 'other'
            elif change == 'digest':
                index['snapshot']['digest'] = '0' * 64
            else:
                index['error'] = 'Unavailable'
            self.index.write_text(json.dumps(index), encoding='utf-8')
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.reader()

    def test_manual_files_and_source_are_never_overwritten(self):
        self.publication.path.write_text('{"manual": true}', encoding='utf-8')
        self.publication.path.chmod(0o640)
        before = self.publication.path.read_bytes()
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.publication.path.read_bytes(), before)
        collision = AuthorityPublication(self.source.parent, 'example')
        collision.path = self.source
        original = self.source.read_bytes()
        with self.assertRaises(ValueError):
            collision.publish(self.observer, self.state)
        self.assertEqual(self.source.read_bytes(), original)

    def test_private_directory_must_exist_and_stay_outside_index_and_kb(self):
        for directory in (self.index.parent, self.index.parent / 'kb', self.root / 'missing'):
            publication = AuthorityPublication(directory, 'example')
            with self.subTest(directory=directory), self.assertRaises((ValueError, OSError)):
                self.observer.export(self.index, self.state, authority=publication)

    def test_explicit_bounded_reader_lease_required(self):
        for age in (0, -1, True, 3601, '30'):
            with self.subTest(age=age), self.assertRaises(ValueError):
                PublishedAuthority(self.private, self.index, 'example', str(self.source), max_age=age)

    def test_failed_atomic_replacement_leaves_old_copy_bounded_by_lease(self):
        self.publish()
        before = self.publication.path.read_bytes()
        self.ticks[0] = 120
        with patch('authority_publication.os.replace', side_effect=OSError('Unavailable')):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(self.publication.path.read_bytes(), before)
        self.assertEqual(list(self.private.iterdir()), [self.publication.path])
        self.ticks[0] = 130
        with self.assertRaises(ValueError):
            self.reader()

    def test_changed_private_payload_is_not_accepted_as_the_published_authority(self):
        self.publish()
        document = json.loads(self.publication.path.read_text(encoding='utf-8'))
        document['humans'][1]['telegram_user_id'] = 999
        self.publication.path.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.reader()

    @unittest.skipUnless(os.name == 'posix', 'POSIX private directory permissions')
    def test_public_or_group_writable_directory_is_refused(self):
        for mode in (0o755, 0o770):
            self.private.chmod(mode)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.publish()
            self.assertFalse(self.publication.path.exists())

    def test_sync_cli_requires_complete_explicit_publication_options(self):
        import contextlib
        import io
        for options in (['--authority-org', 'example'], ['--authority-dir', str(self.private)],
                        ['--authority-org', 'example', '--authority-dir', str(self.private)]):
            with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()):
                with patch('sys.argv', ['phantomview', '--config', str(self.root / 'config.json'), 'sync', *options]):
                    with self.assertRaises(SystemExit) as error:
                        pv.main()
            self.assertEqual(error.exception.code, 2)

    def test_sync_cli_publishes_only_with_explicit_options(self):
        import contextlib
        import io
        self.observer.path.write_text(json.dumps(self.observer.config), encoding='utf-8')
        arguments = ['phantomview', '--config', str(self.observer.path), 'sync',
                     '--export', str(self.index), '--authority-dir', str(self.private),
                     '--authority-org', 'example']
        output = io.StringIO()
        with patch('sys.argv', arguments), contextlib.redirect_stdout(output):
            pv.main()
        reader = PublishedAuthority(self.private, self.index, 'example', str(self.source), max_age=30)
        self.assertEqual(reader.read(), self.org)
        self.assertEqual(output.getvalue().strip(), 'Information updated')


if __name__ == '__main__':
    unittest.main()
