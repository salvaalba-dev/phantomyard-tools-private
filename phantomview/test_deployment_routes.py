"""Deployment descriptors must agree before offline native preparation."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

import deployment_routes as pairing
from test_reader_launch import example


def host(launch, actor=None):
    target = next(row for row in pairing.reader.issuer_routes(launch)
                  if row['actor'] == (actor or launch['actor']))
    route = {'persona': target['actor'], 'channel': 'telegram', 'scopeId': 'river-project',
             'origin': launch['origin'], 'issuerUid': target['issuer_uid'],
             'readerUid': launch['reader_uid'], 'python': '/usr/bin/python3',
             'clientScript': '/opt/example-view/native_link_client.py',
             'socketPath': target['socket_path']}
    if target['conversation_socket'] is not None:
        route.update(conversationSocketPath=target['conversation_socket'], conversationGroup=12003)
    return {'schema_version': 1, 'routes': [route]}


class DeploymentRouteTests(unittest.TestCase):
    def test_two_channels_share_one_issuer_without_mutating_inputs(self):
        launch = example()
        document = host(launch)
        document['routes'].append(document['routes'][0] | {'channel': 'phantomchat'})
        before = copy.deepcopy((launch, document))
        report = pairing.compare(launch, [document])
        self.assertEqual((launch, document), before)
        self.assertEqual(report['native_listener_count'], 2)
        self.assertEqual(report['issuer_count'], 1)
        self.assertFalse(report['activation_ready'])
        self.assertIn('loaded-public-signing-identities', report['pending'])

    def test_multiple_accounts_and_shared_account_builds(self):
        launch = example()
        launch['additional_issuers'] = [{'actor': 'project-guide', 'identities': ['b' * 64],
            'issuer_uid': 12004, 'socket_group': 12003,
            'socket_path': '/run/example-view/reader/project.sock', 'conversation_socket': None}]
        first, second = host(launch), host(launch, 'project-guide')
        report = pairing.compare(launch, [first, second])
        self.assertEqual((report['issuer_count'], report['native_host_count']), (2, 2))
        launch['additional_issuers'][0]['issuer_uid'] = launch['issuer_uid']
        second = host(launch, 'project-guide')
        with self.assertRaises(ValueError):
            pairing.compare(launch, [first, second])
        first['routes'].extend(second['routes'])
        self.assertEqual(pairing.compare(launch, [first])['issuer_count'], 2)

    def test_endpoint_mismatches_and_missing_native_coverage_are_rejected(self):
        launch = example()
        for field, value in [('persona', 'unknown'), ('origin', 'https://other.example'),
                ('issuerUid', 12004), ('readerUid', 12005),
                ('socketPath', '/run/other/link.sock'),
                ('conversationSocketPath', '/run/other/chat.sock')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                document = host(launch)
                document['routes'][0][field] = value
                pairing.compare(launch, [document])
        launch['additional_issuers'] = [{'actor': 'project-guide', 'identities': ['b' * 64],
            'issuer_uid': 12004, 'socket_group': 12003,
            'socket_path': '/run/example-view/reader/project.sock', 'conversation_socket': None}]
        with self.assertRaises(ValueError):
            pairing.compare(launch, [host(launch)])
        for documents in ([], None, {}, [host(launch)] * 17):
            with self.subTest(documents=type(documents)), self.assertRaises(ValueError):
                pairing.compare(launch, documents)

    def test_conversation_enablement_must_match_on_every_channel(self):
        launch = example()
        document = host(launch)
        link_only = {key: value for key, value in document['routes'][0].items()
                     if key not in pairing.native.CONVERSATION}
        with self.assertRaises(ValueError):
            pairing.compare(launch, [{'schema_version': 1, 'routes': [link_only]}])
        launch['conversation_socket'] = None
        with self.assertRaises(ValueError):
            pairing.compare(launch, [document])
        self.assertEqual(pairing.compare(launch, [host(launch)])['issuer_count'], 1)

    def test_cli_reads_only_and_reports_no_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            launch = example()
            files = {'reader.json': json.dumps(launch), 'native.json': json.dumps(host(launch))}
            for name, content in files.items():
                (root / name).write_text(content, encoding='utf-8')
                (root / name).chmod(0o600)
            out, err = io.StringIO(), io.StringIO()
            args = ['--reader', str(root / 'reader.json'), '--native-host', str(root / 'native.json')]
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(pairing.main(args), 0)
            self.assertFalse(json.loads(out.getvalue())['activation_ready'])
            self.assertNotIn(launch['origin'], out.getvalue())
            self.assertNotIn(launch['identities'][0], out.getvalue())
            self.assertEqual(err.getvalue(), '')
            self.assertEqual(sorted(path.name for path in root.iterdir()), sorted(files))
            for name, content in files.items():
                self.assertEqual((root / name).read_text(encoding='utf-8'), content)
            (root / 'native.json').write_text('{"routes":[],"routes":[]}', encoding='utf-8')
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(pairing.main(args), 1)
            self.assertEqual(out.getvalue(), '')
            self.assertIn('Route pairing refused', err.getvalue())
            self.assertNotIn(str(root), err.getvalue())

    def test_native_loader_preserves_existing_size_and_path_bounds(self):
        with self.assertRaises(ValueError):
            pairing.load_host('relative.json')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            path = root / 'host.json'
            path.write_bytes(b' ' * 65537)
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                pairing.load_host(path)
