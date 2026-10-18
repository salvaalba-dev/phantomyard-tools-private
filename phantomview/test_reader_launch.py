"""Protected launch contract and read-only preflight; no production installation."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import reader_launch as launch


def example():
    return json.loads(Path(__file__).with_name('reader-launch.example.json').read_text(encoding='utf-8'))


class LaunchContractTests(unittest.TestCase):
    def test_example_and_disabled_assistant_are_supported_without_mutation(self):
        config = example()
        self.assertEqual(launch.validate(config), config)
        config['conversation_socket'] = None
        self.assertIsNone(launch.validate(config)['conversation_socket'])
        validated = launch.validate(config)
        validated['identities'].clear()
        self.assertEqual(len(config['identities']), 1)

    def test_unsafe_or_ambiguous_coordinates_are_rejected(self):
        for field, value in [('reader_uid', 0), ('issuer_uid', 12002), ('port', True),
                ('port', 0), ('authority_max_age', 0), ('session_seconds', 3601),
                ('identities', []), ('identities', ['A' * 64]), ('actor', '../coordinator'),
                ('schema_version', True), ('origin', 'https://view.example/'),
                ('origin', 'https://user@view.example'), ('origin', 'http://view.example'),
                ('origin', 'https://view.example:bad'), ('socket_path', '/run/../link.sock'),
                ('socket_path', '/run//link.sock'), ('socket_path', '/run/' + 'x' * 100),
                ('conversation_socket', '/run/example-view/reader/link.sock')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                launch.validate(example() | {field: value})
        for config in [example() | {'token': 'unexpected'}, {k: v for k, v in example().items() if k != 'reader_uid'}]:
            with self.assertRaises(ValueError):
                launch.validate(config)

    def test_load_rejects_duplicate_fields(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            root.chmod(0o700)
            path = root / 'launch.json'
            path.write_text(json.dumps(example()), encoding='utf-8')
            path.chmod(0o600)
            self.assertEqual(launch.load(path), example())
            path.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
            with self.assertRaises(ValueError):
                launch.load(path)

    @unittest.skipUnless(os.name == 'posix', 'POSIX write modes')
    def test_group_writable_config_and_parent_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            root.chmod(0o700)
            path = root / 'launch.json'
            path.write_text(json.dumps(example()), encoding='utf-8')
            path.chmod(0o664)
            with self.assertRaises(ValueError):
                launch.load(path)
            path.chmod(0o600)
            root.chmod(0o770)
            with self.assertRaises(ValueError):
                launch.load(path)
            root.chmod(0o700)

    def test_check_does_not_build_and_prints_no_coordinates(self):
        output = io.StringIO()
        with patch.object(launch, 'load', return_value=example()), \
                patch.object(launch, 'preflight', return_value=object()), \
                patch.object(launch, 'build') as build, redirect_stdout(output):
            self.assertEqual(launch.main(['--config', '/private/launch.json', '--check']), 0)
        build.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {'status': 'preflight-passed', 'assistant_enabled': True})

    def test_failure_does_not_echo_exception_details(self):
        output = io.StringIO()
        with patch.object(launch, 'load', side_effect=ValueError('private-registry-marker')), redirect_stderr(output):
            self.assertEqual(launch.main(['--config', '/private/launch.json', '--check']), 1)
        self.assertNotIn('private-registry-marker', output.getvalue())
        self.assertIn('READER_LAUNCH.md', output.getvalue())

    def test_build_passes_fixed_coordinates_to_existing_reader(self):
        config, authority = example(), object()
        with patch.object(launch, 'Ledger', return_value='ledger') as ledger, \
                patch.object(launch, 'PublishedReader') as reader:
            launch.build(config, authority)
        ledger.assert_called_once_with(config['audit_path'])
        self.assertIs(reader.call_args.kwargs['authority'], authority)
        self.assertEqual(reader.call_args.kwargs['conversation_socket'], config['conversation_socket'])
        self.assertEqual(reader.call_args.kwargs['actor'], 'coordinator')

    def test_build_forwards_only_protected_additional_issuer_configuration(self):
        config = example() | {'additional_issuers': [{'actor': 'project-guide', 'identities': ['b' * 64],
            'issuer_uid': 12004, 'socket_path': '/run/example-view/reader/project.sock',
            'socket_group': 12003, 'conversation_socket': None}]}
        config = launch.validate(config)
        with patch.object(launch, 'Ledger'), patch.object(launch, 'PublishedReader') as reader:
            launch.build(config, object())
        self.assertEqual(reader.call_args.kwargs['additional_issuers'], config['additional_issuers'])

    def test_signal_sets_stop_event_and_original_handlers_are_restored(self):
        reader, handlers = Mock(), []
        def register(kind, handler):
            handlers.append((kind, handler))
            return 'previous'
        def serve(*, stop_event):
            self.assertFalse(stop_event.is_set())
            handlers[0][1](None, None)
            self.assertTrue(stop_event.is_set())
        reader.serve.side_effect = serve
        with patch.object(launch, 'load', return_value=example()), \
                patch.object(launch, 'preflight', return_value=object()), \
                patch.object(launch, 'build', return_value=reader), \
                patch.object(launch.signal, 'signal', side_effect=register), patch.object(launch.os, 'umask'):
            self.assertEqual(launch.main(['--config', '/private/launch.json']), 0)
        self.assertEqual([handler for _, handler in handlers[2:]], ['previous', 'previous'])

    @unittest.skipUnless(os.name == 'posix', 'Linux deployment filesystem checks')
    def test_preflight_reads_authority_and_creates_no_audit_or_socket(self):
        with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
            root = Path(root)
            root.chmod(0o700)
            uid = os.getuid() if hasattr(os, 'getuid') else 29001
            config = example() | {'reader_uid': uid, 'conversation_socket': None,
                'socket_path': str(root / 'link.sock'), 'audit_path': str(root / 'sessions.sqlite')}
            # Linux path syntax is tested separately; these paths are cross-platform fixtures.
            stack.enter_context(patch.object(launch, 'validate', return_value=config))
            stack.enter_context(patch.object(launch.os, 'getuid', return_value=uid, create=True))
            stack.enter_context(patch.object(launch.os, 'getgid', return_value=12001, create=True))
            stack.enter_context(patch.object(launch.os, 'getgroups', return_value=[12001], create=True))
            stack.enter_context(patch.object(launch, 'DaemonPeerPolicy'))
            stack.enter_context(patch.object(launch, 'signed_access'))
            authority = stack.enter_context(patch.object(launch, 'PublishedAuthority')).return_value
            authority.return_value = SimpleNamespace(scope=SimpleNamespace(policy={'personas': ['coordinator']}),
                                                     authority_revision='current')
            projection = stack.enter_context(patch.object(launch, 'PublishedProjection')).return_value
            projection.catalog.return_value = {'organization': 'example', 'authority_revision': 'current'}
            ledger = stack.enter_context(patch.object(launch, 'Ledger'))
            self.assertIs(launch.preflight(config), authority)
            self.assertEqual(list(root.iterdir()), [])
            ledger.assert_not_called()
            config['additional_issuers'] = [{'actor': 'project-guide', 'identities': ['b' * 64],
                'issuer_uid': 12004, 'socket_path': str(root / 'project.sock'),
                'socket_group': 12001, 'conversation_socket': None}]
            with self.assertRaises(ValueError):
                launch.preflight(config)
            authority.return_value.scope.policy['personas'].append('project-guide')
            self.assertIs(launch.preflight(config), authority)
            self.assertEqual(list(root.iterdir()), [])
            (root / 'project.sock').write_text('existing endpoint', encoding='utf-8')
            with self.assertRaises(ValueError):
                launch.preflight(config)
            (root / 'project.sock').unlink()
            projection.catalog.side_effect = ValueError('Changed approval')
            with self.assertRaises(ValueError):
                launch.preflight(config)
