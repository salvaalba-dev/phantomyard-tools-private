"""Current raw-source policy must precede signed issuance and every scoped read."""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from identified_access import IdentifiedGate
from organization_authority import OrganizationAuthority
from scoped_backend import ScopedBackend
from test_channel_identity import context
import test_identified_viewer_flow as signed_flow
import test_scoped_backend as projection
from test_view_permissions import scoped_organization


class AuthoritySourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.path = self.root / 'org.json'
        self.org = scoped_organization()
        self.write()
        self.authority = OrganizationAuthority(self.path, 'example')

    def write(self):
        self.path.write_text(json.dumps(self.org), encoding='utf-8')
        self.path.chmod(0o600)

    def test_each_read_reloads_and_returns_an_independent_document(self):
        first = self.authority.read()
        first['humans'].clear()
        self.assertTrue(self.authority.read()['humans'])
        initial = self.authority().revision
        self.org['humans'][1]['telegram_user_id'] = 1002
        self.write()
        self.assertNotEqual(initial, self.authority().revision)

    def test_yaml_and_json_have_the_same_directory_authority(self):
        other = self.root / 'org.yaml'
        other.write_text(yaml.safe_dump(self.org), encoding='utf-8')
        other.chmod(0o600)
        self.assertEqual(self.authority().revision, OrganizationAuthority(other, 'example')().revision)

    def test_missing_corrupt_or_wrong_source_never_uses_last_good_policy(self):
        self.authority()
        for content in ('{private-marker', '{"organization": {"id": "other"}}',
                        '{"snapshot": {}, "config": {}}'):
            self.path.write_text(content, encoding='utf-8')
            with self.subTest(content=content), self.assertRaises(ValueError) as error:
                self.authority()
            self.assertNotIn('private-marker', str(error.exception))
        self.path.unlink()
        with self.assertRaises(ValueError):
            self.authority()

    def test_explicit_absolute_operator_path_is_required(self):
        for path in ('org.json', self.root / 'org.txt', self.root / '..' / 'org.yaml'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                OrganizationAuthority(path, 'example')
        with self.assertRaises(ValueError):
            OrganizationAuthority(self.path, '')

    def test_legacy_organization_without_viewer_scopes_cannot_activate_binding(self):
        del self.org['policies']['phantomview']
        self.write()
        with self.assertRaises(ValueError):
            self.authority()

    def test_duplicate_keys_aliases_and_nonfinite_values_are_rejected(self):
        for name, content in (
                ('org.json', '{"organization": {}, "organization": {}, "value": NaN}'),
                ('org.json', '{"value": NaN}'),
                ('org.yaml', 'organization: {}\norganization: {}\n'),
                ('org.yaml', 'one: &one {}\ntwo: *one\n'),
                ('org.yaml', 'one: ' + '[' * 65 + '0' + ']' * 65)):
            path = self.root / name
            path.write_text(content, encoding='utf-8')
            path.chmod(0o600)
            with self.subTest(content=content), self.assertRaises(ValueError):
                OrganizationAuthority(path, 'example')()

    def test_large_input_and_nonregular_source_are_rejected(self):
        with patch('organization_authority.MAX_BYTES', 10), self.assertRaises(ValueError):
            self.authority()
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaises(ValueError):
            self.authority()

    def test_hard_link_is_rejected(self):
        alias = self.root / 'alias.json'
        try:
            os.link(self.path, alias)
        except OSError:
            self.skipTest('Hard links unavailable on this filesystem')
        with self.assertRaises(ValueError):
            self.authority()

    def test_source_changed_during_read_is_rejected(self):
        original_open = os.fdopen
        path = self.path

        @contextmanager
        def changing_open(*args, **kwargs):
            with original_open(*args, **kwargs) as stream:
                class ChangingRead:
                    def fileno(self):
                        return stream.fileno()

                    def read(self, size):
                        raw = stream.read(size)
                        path.write_text('{"changed": true}', encoding='utf-8')
                        return raw
                yield ChangingRead()

        with patch('organization_authority.os.fdopen', changing_open), self.assertRaises(ValueError):
            self.authority()

    @unittest.skipUnless(os.name == 'posix', 'POSIX link and permission checks')
    def test_symbolic_paths_and_writable_source_are_rejected(self):
        alias = self.root / 'alias.json'
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            OrganizationAuthority(alias, 'example')()
        parent = self.root / 'linked'
        parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            OrganizationAuthority(parent / 'org.json', 'example')()
        self.path.chmod(0o666)
        with self.assertRaises(ValueError):
            self.authority()


@unittest.skipIf(signed_flow.PrivateKey is None, 'Real PhantomBlog signatures required')
class FileBoundSignedTests(projection.ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'org.json'
        self.path.parent.chmod(0o700)
        self.write()
        self.authority = OrganizationAuthority(self.path, 'example')
        self.keys = {'administrator': signed_flow.PrivateKey()}
        identity = self.keys['administrator'].public_key_xonly.format().hex()
        self.gate = IdentifiedGate(signed_flow.access, {'actor': 'administrator', 'identities': [identity]},
                                  'https://view.example:8790', 8790, directory_loader=self.authority)
        self.backend = ScopedBackend(self.gate, lambda: self.catalog, self.load)

    def write(self):
        self.path.write_text(json.dumps(self.org), encoding='utf-8')
        self.path.chmod(0o600)

    def link(self, sender='102'):
        signed = signed_flow.IdentifiedViewerFlowTests.signed(self, self.gate)
        return self.gate.issue_identified(signed, self.gate.origin,
                                         **context(sender, 'administrator'), scope_id='example')

    def login(self):
        value = self.gate.redeem(self.link().split('#c=')[1])
        return {'Cookie': 'phantomview=' + value}

    def test_real_signed_link_binds_file_identity_and_filters_workspace(self):
        headers = self.login()
        recipient, _ = self.gate.identified_scope(headers)
        self.assertEqual((recipient.human, recipient.persona), ('secretary', 'administrator'))
        view = self.backend.workspace(headers)
        self.assertIn(self.public, {row['id'] for row in view['resources']})
        self.assertNotIn(self.hidden, json.dumps(view))
        self.assertEqual(view['navigation']['assistant']['persona'], 'administrator')
        self.gate.logout(headers)
        with self.assertRaises(ValueError):
            self.backend.workspace(headers)

    def test_unknown_sender_and_changed_source_block_redemption(self):
        with self.assertRaises(ValueError):
            self.link('unknown')
        self.assertEqual(self.gate.recipient_links, {})
        code = self.link().split('#c=')[1]
        self.org['humans'][1].pop('counterpart_persona')
        self.write()
        with self.assertRaises(ValueError):
            self.gate.redeem(code)
        self.assertEqual(self.gate.sessions, {})

    def test_policy_change_or_unavailable_file_blocks_before_record_reads(self):
        headers = self.login()
        self.backend.workspace(headers)
        self.loaded.clear()
        self.org['roles'][0]['security_exceptions'] = ['category-3']
        self.write()
        with self.assertRaises(ValueError):
            self.backend.workspace(headers)
        self.assertEqual(self.loaded, [])
        self.path.unlink()
        with self.assertRaises(ValueError):
            self.backend.search(headers, 'River')
        self.assertEqual(self.loaded, [])

    def test_signed_session_uses_fresh_publication_and_denies_expiry_or_changed_policy(self):
        from authority_publication import AuthorityPublication, PublishedAuthority
        import phantomview as pv
        self.org['version'] = 1
        self.write()
        root = self.path.parent
        private = root / 'authority'
        private.mkdir(mode=0o700)
        index = root / 'reader' / 'index.json'
        index.parent.mkdir(mode=0o750)
        observer = pv.Observatory(root / 'config.json')
        observer.config = {'mode': 'existing', 'org_files': [str(self.path)],
                           'personas_dir': '', 'docs_manifests': [], 'auto_procedures': False}
        ticks = [100]
        publication = AuthorityPublication(private, 'example', clock=lambda: ticks[0])

        def refresh():
            observer.export(index, observer.refresh(), authority=publication)

        refresh()
        self.gate.directory_loader = PublishedAuthority(private, index, 'example', str(self.path),
                                                       max_age=30, clock=lambda: ticks[0])
        headers = self.login()
        self.backend.workspace(headers)
        self.loaded.clear()
        ticks[0] = 130
        with self.assertRaises(ValueError):
            self.backend.workspace(headers)
        self.assertEqual(self.loaded, [])
        ticks[0] = 140
        refresh()
        self.backend.workspace(headers)
        self.loaded.clear()
        self.org['roles'][0]['security_exceptions'] = ['category-3']
        self.write()
        refresh()
        with self.assertRaises(ValueError):
            self.backend.workspace(headers)
        self.assertEqual(self.loaded, [])


if __name__ == '__main__':
    unittest.main()
