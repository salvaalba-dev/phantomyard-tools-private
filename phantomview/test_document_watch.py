"""Periodic observation detects changes without mutating bindings or publications."""
import copy
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import document_watch
import test_document_refresh as fixtures


class DocumentWatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DocumentRefreshTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.report = self.root / 'reports'
        self.report.mkdir(mode=0o700)
        self.report.chmod(0o700)
        self.manifest = self.root / 'manifest.json'
        self.matrix = self.root / 'matrix.json'
        self.snapshot = self.root / 'snapshot.json'
        self.config = self.root / 'config.json'
        self.write(self.manifest, self.fixture.manifest)
        self.write(self.matrix, self.fixture.matrix)
        self.write(self.snapshot, {'snapshot': {'actors': [self.fixture.actor]}})
        self.write(self.config, {'docs_manifests': [str(self.manifest)], 'working_documents': []})

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')
        path.chmod(0o600)

    def observe(self, at=100):
        return document_watch.observe(self.manifest, self.matrix, self.snapshot, self.config,
                                      self.report, 'example', clock=lambda: at)

    def test_first_and_repeated_cycles_preserve_inputs_and_stable_change_identity(self):
        paths = [self.manifest, self.matrix, self.snapshot, self.config, self.fixture.path]
        before = {path: path.read_bytes() for path in paths}
        first, second = self.observe(), self.observe(200)
        self.assertTrue(first['changed'])
        self.assertFalse(second['changed'])
        self.assertEqual(first['revision'], second['revision'])
        self.assertEqual(second['changed_at'], 100)
        self.assertEqual(second['checked_at'], 200)
        self.assertFalse(second['publication_performed'])
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        self.assertNotIn(str(self.root), json.dumps(second))
        self.assertNotIn('Act with integrity', json.dumps(second))

    def test_native_changes_and_removed_matrix_entries_are_detected(self):
        binding = self.fixture.plan()['prepared'][0]['binding']
        self.write(self.config, {'docs_manifests': [str(self.manifest)], 'working_documents': [binding]})
        first = self.observe()
        manifest = copy.deepcopy(self.fixture.manifest)
        manifest['nodes'][1]['category'] = 'category-3'
        self.write(self.manifest, manifest)
        changed = self.observe(200)
        self.assertTrue(changed['changed'])
        self.assertNotEqual(first['revision'], changed['revision'])
        self.assertEqual(changed['plan']['pending'][0]['reason'], 'classification-changed')
        self.assertEqual(changed['plan']['excluded_bindings'], [binding['urn']])
        self.write(self.matrix, self.fixture.matrix | {'documents': []})
        removed = self.observe(300)
        self.assertEqual(removed['plan']['removed_bindings'], [binding['urn']])

    def test_incidental_persona_observation_clocks_do_not_create_document_changes(self):
        first = self.observe()
        self.write(self.snapshot, {'actors': [self.fixture.actor | {'checked_at': 999}]})
        second = self.observe(200)
        self.assertFalse(second['changed'])
        self.assertEqual(first['revision'], second['revision'])
        self.assertNotEqual(first['plan']['input_revisions'], second['plan']['input_revisions'])

    def test_invalid_yaml_or_missing_source_replaces_success_without_cached_plan(self):
        self.observe()
        self.matrix.write_bytes(b'{ invalid json')
        failed = self.observe(200)
        self.assertEqual(failed['status'], 'unavailable')
        self.assertNotIn('plan', failed)
        self.assertNotIn('revision', failed)
        self.assertNotIn('invalid json', json.dumps(failed))
        self.matrix.unlink()
        self.assertEqual(self.observe(300)['status'], 'unavailable')

    def test_selected_collector_manifest_and_organization_must_match(self):
        self.write(self.config, {'docs_manifests': [], 'working_documents': []})
        self.assertEqual(self.observe()['status'], 'unavailable')
        self.write(self.config, {'docs_manifests': [str(self.manifest)]})
        self.write(self.matrix, self.fixture.matrix | {'organization': 'other'})
        self.assertEqual(self.observe()['status'], 'unavailable')

    def test_input_change_during_scan_invalidates_observation(self):
        original = document_watch.prepare

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            self.write(self.snapshot, {'actors': []})
            return result

        with patch.object(document_watch, 'prepare', changed):
            report = self.observe()
        self.assertEqual(report['status'], 'unavailable')
        self.assertNotIn('plan', report)

    def test_existing_report_cannot_belong_to_another_organization(self):
        self.write(self.report / 'document-watch.json', {'organization': 'other'})
        with self.assertRaises(ValueError):
            self.observe()

    def test_command_returns_observation_status_without_exporting_the_private_plan(self):
        args = ['--manifest', str(self.manifest), '--matrix', str(self.matrix), '--snapshot', str(self.snapshot),
                '--config', str(self.config), '--report-dir', str(self.report), '--organization', 'example']
        output = io.StringIO()
        with patch('sys.stdout', output):
            self.assertEqual(document_watch.main(args), 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'observed')
        self.assertNotIn('urn:', output.getvalue())
        self.matrix.unlink()
        output = io.StringIO()
        with patch('sys.stdout', output):
            self.assertEqual(document_watch.main(args), 1)
        self.assertEqual(json.loads(output.getvalue())['status'], 'unavailable')

    @unittest.skipUnless(os.name == 'posix', 'POSIX source and report protections')
    def test_group_writable_sources_and_nonprivate_report_are_rejected(self):
        self.matrix.chmod(0o664)
        self.assertEqual(self.observe()['status'], 'unavailable')
        target = self.report / 'document-watch.json'
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        target.chmod(0o644)
        with self.assertRaises(ValueError):
            self.observe()

    @unittest.skipUnless(os.name == 'posix', 'Explicit POSIX native writer identity')
    def test_native_manifest_accepts_only_explicit_owner_and_group_without_weakening_other_inputs(self):
        import grp
        import pwd
        writer, group = pwd.getpwuid(os.geteuid()).pw_name, grp.getgrgid(self.manifest.stat().st_gid).gr_name
        self.manifest.chmod(0o664)
        self.assertEqual(self.observe()['status'], 'unavailable')
        args = (self.manifest, self.matrix, self.snapshot, self.config, self.report, 'example')
        report = document_watch.observe(*args, native_writer=writer, native_group=group)
        self.assertEqual(report['status'], 'observed')
        self.manifest.chmod(0o666)
        self.assertEqual(document_watch.observe(*args, native_writer=writer, native_group=group)['status'], 'unavailable')
        self.manifest.chmod(0o664)
        self.matrix.chmod(0o664)
        self.assertEqual(document_watch.observe(*args, native_writer=writer, native_group=group)['status'], 'unavailable')
        self.matrix.chmod(0o600)
        with patch('pwd.getpwnam') as account:
            account.return_value.pw_uid = os.geteuid() + 1
            self.assertEqual(document_watch.observe(*args, native_writer=writer, native_group=group)['status'], 'unavailable')
        with patch('grp.getgrnam') as selected:
            selected.return_value.gr_gid = self.manifest.stat().st_gid + 1
            self.assertEqual(document_watch.observe(*args, native_writer=writer, native_group=group)['status'], 'unavailable')


    def test_explicit_writer_list_is_bounded_and_preserves_single_writer_api(self):
        self.assertEqual(document_watch.native_writers('registry-user'), ('registry-user',))
        self.assertEqual(document_watch.native_writers(['registry-user', 'ingestion-user']),
                         ('registry-user', 'ingestion-user'))
        self.assertEqual(len(document_watch.native_writers([f'writer-{n}' for n in range(16)])), 16)
        for value in (None, [], '', [''], [' registry-user'], ['registry-user '],
                      ['registry-user', 'registry-user'], ['registry-user', 1],
                      [f'writer-{n}' for n in range(17)], {'registry-user'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                document_watch.native_writers(value)

    def test_empty_or_unpaired_writer_configuration_never_falls_back_to_private_reads(self):
        args = (self.manifest, self.matrix, self.snapshot, self.config, self.report, 'example')
        for writer, group in (([], 'registry-group'), ('', 'registry-group'),
                              (['registry-user'], None), (None, 'registry-group')):
            with self.subTest(writer=writer, group=group):
                with patch.object(document_watch, 'prepare') as prepare:
                    result = document_watch.observe(*args, native_writer=writer, native_group=group)
                self.assertEqual(result['status'], 'unavailable')
                prepare.assert_not_called()

    def test_repeated_cli_writers_are_forwarded_and_revalidated_for_both_manifest_reads(self):
        args = ['--manifest', str(self.manifest), '--matrix', str(self.matrix),
                '--snapshot', str(self.snapshot), '--config', str(self.config),
                '--report-dir', str(self.report), '--organization', 'example',
                '--native-writer', 'registry-user', '--native-writer', 'ingestion-user',
                '--native-group', 'registry-group']
        output = io.StringIO()
        with patch.object(document_watch, 'native_read', return_value=self.manifest.read_bytes()) as read:
            with patch('sys.stdout', output):
                self.assertEqual(document_watch.main(args), 0)
        self.assertEqual(read.call_count, 2)
        for call in read.call_args_list:
            self.assertEqual(call.args, (self.manifest, ('registry-user', 'ingestion-user'), 'registry-group'))
        self.assertEqual(json.loads(output.getvalue())['status'], 'observed')

    def test_native_writer_recheck_failure_discards_the_prepared_plan(self):
        args = (self.manifest, self.matrix, self.snapshot, self.config, self.report, 'example')
        with patch.object(document_watch, 'native_read',
                          side_effect=[self.manifest.read_bytes(), ValueError('Owner changed')]):
            result = document_watch.observe(*args, native_writer=['registry-user', 'ingestion-user'],
                                            native_group='registry-group')
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('plan', result)

    @unittest.skipUnless(os.name == 'posix', 'Explicit POSIX native writer identity')
    def test_native_reader_accepts_each_declared_writer_but_not_other_group_members(self):
        import grp
        from types import SimpleNamespace
        uid = self.manifest.stat().st_uid
        group = grp.getgrgid(self.manifest.stat().st_gid).gr_name
        self.manifest.chmod(0o664)
        for matching in ('registry-user', 'ingestion-user'):
            with self.subTest(matching=matching):
                def account(name):
                    return SimpleNamespace(pw_uid=uid if name == matching else uid + 1)
                with patch('pwd.getpwnam', side_effect=account):
                    self.assertEqual(document_watch.native_read(
                        self.manifest, ['registry-user', 'ingestion-user'], group), self.manifest.read_bytes())
        with patch('pwd.getpwnam', return_value=SimpleNamespace(pw_uid=uid + 1)):
            with self.assertRaises(ValueError):
                document_watch.native_read(self.manifest, ['registry-user', 'ingestion-user'], group)

    @unittest.skipUnless(os.name == 'posix', 'Explicit POSIX native writer identity')
    def test_unknown_writer_invalidates_allowlist_even_when_another_writer_matches(self):
        import grp
        from types import SimpleNamespace
        group = grp.getgrgid(self.manifest.stat().st_gid).gr_name
        def account(name):
            if name == 'missing-user':
                raise KeyError(name)
            return SimpleNamespace(pw_uid=self.manifest.stat().st_uid)
        with patch('pwd.getpwnam', side_effect=account), self.assertRaises(KeyError):
            document_watch.native_read(self.manifest, ['registry-user', 'missing-user'], group)

    @unittest.skipUnless(os.name == 'posix', 'Explicit POSIX native writer identity')
    def test_multiple_writers_keep_group_world_write_and_link_checks(self):
        import grp
        import pwd
        writer = pwd.getpwuid(self.manifest.stat().st_uid).pw_name
        group = grp.getgrgid(self.manifest.stat().st_gid).gr_name
        with patch('pwd.getpwnam', return_value=pwd.getpwnam(writer)):
            for mode in (0o666, 0o602):
                self.manifest.chmod(mode)
                with self.assertRaises(ValueError):
                    document_watch.native_read(self.manifest, [writer, 'ingestion-user'], group)
            self.manifest.chmod(0o664)
            with patch('grp.getgrnam') as selected:
                selected.return_value.gr_gid = self.manifest.stat().st_gid + 1
                with self.assertRaises(ValueError):
                    document_watch.native_read(self.manifest, [writer, 'ingestion-user'], group)
            linked = self.root / 'manifest-link.json'
            linked.symlink_to(self.manifest)
            with self.assertRaises(ValueError):
                document_watch.native_read(linked, [writer, 'ingestion-user'], group)
            linked.unlink()
            os.link(self.manifest, linked)
            with self.assertRaises(ValueError):
                document_watch.native_read(self.manifest, [writer, 'ingestion-user'], group)


if __name__ == '__main__':
    unittest.main()
