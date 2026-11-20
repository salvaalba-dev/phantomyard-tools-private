"""Opt-in root Linux integration with the matching PhantomDocs commit protocol.

Set PHANTOMVIEW_POLICY_LINUX=1 only in a disposable root CI process. No installed
paths, real units, identities or documents are used; service control is stubbed.
"""
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import subprocess
import sys
import sysconfig
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from identified_reader import RecipientHandler
import test_authority_publication as fixtures

ENABLED = os.environ.get('PHANTOMVIEW_POLICY_LINUX') == '1'


@unittest.skipUnless(ENABLED, 'explicit disposable privileged Linux integration')
class PolicyLinuxTests(unittest.TestCase):
    def setUp(self):
        import sys
        self.assertEqual(sys.platform, 'linux')
        self.assertEqual(os.geteuid(), 0)
        from phantomdocs import workflow_bridge_policy as publisher
        from phantomdocs.workflow_policy_commit import committed_guard
        self.publisher, self.guard = publisher, committed_guard
        directory = tempfile.TemporaryDirectory(prefix='viewer-policy-', dir='/var/lib')
        self.fixture = fixtures.PublicationTests()
        with patch.object(fixtures.tempfile, 'TemporaryDirectory', return_value=directory):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        # One model accepted by both native PhantomOrg and the viewer scope.
        f.org['organization'].update(name='Example', sector='ngo', languages=['en'], default_language='en')
        f.org['departments'] = [dict(id='operations', name='Operations', parent=None, access_policy='board')]
        for role in f.org['roles']:
            role.update(name=role['id'], department='operations', reports_to=None)
        for actor in f.org['actors']:
            actor.setdefault('tools', [])
        for human in f.org['humans']:
            human.update(name=human['id'], role='executive')
        for level in f.org['policies']['access_levels'].values():
            level['label'] = 'Board'
        for category in f.org['policies']['security_categories'].values():
            category['label'] = 'Synthetic category'
        f.org['escalation_matrix'] = []
        f.org['communication'] = dict(request_id_format='{org_id}-{yyyymmdd}-{seq4}',
                                     message_types=['REQUEST', 'INFORM'], max_hops=3)
        f.source.write_text(json.dumps(f.org), encoding='utf-8')
        f.state = f.observer.refresh()
        self.lock = f.root / 'policy.lock'
        self.lock.touch(mode=0o644)
        self.lock.with_name('policy.lock.publisher').touch(mode=0o600)
        self.bridge, self.docs = f.root / 'bridge.yaml', f.root / 'docs.yaml'
        for path in (self.bridge, self.docs):
            path.write_bytes(f.source.read_bytes())
            path.chmod(0o640)
        self.options = dict(source=str(f.source), destination=[str(self.bridge), str(self.docs)],
            lock_path=str(self.lock), resolver='/synthetic/resolver.js', node='/usr/bin/node',
            unit='synthetic.service', commit_witness=True)
        self.actions = []
        def control(action, unit):
            self.actions.append(action)
            return True
        self.addCleanup(patch.stopall)
        patch.object(publisher, '_systemctl', control).start()
        patch.object(publisher, '_derive_both', lambda a, b, **kw: (a, b)).start()
        self.assertEqual(publisher.refresh(**self.options), 'synchronized')
        f.publication.policy_lock = str(self.lock)
        f.reader.policy_lock = str(self.lock)
        f.publish()

    def reviewed_change(self):
        f = self.fixture
        before = hashlib.sha256(f.source.read_bytes()).hexdigest()
        f.org['humans'][0]['telegram_user_id'] = 201
        candidate = f.root / 'candidate.json'
        candidate.write_text(json.dumps(f.org), encoding='utf-8')
        candidate.chmod(0o600)
        return dict(self.options, candidate=str(candidate), expected_source_sha256=before,
            candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(), organization='example')

    def test_actual_pending_and_old_unexpired_publication_are_denied(self):
        f = self.fixture
        self.assertEqual(f.reader.read(), f.org)
        marker = self.lock.with_name('policy.lock.pending')
        marker.write_text('{}')
        marker.chmod(0o600)
        with self.assertRaises(ValueError):
            f.reader.read()
        marker.unlink()  # synthetic test-owned marker only, never installed state
        self.assertEqual(self.publisher.refresh(**self.reviewed_change()), 'restarted')
        with self.assertRaises(ValueError):
            f.reader.read()  # lease unchanged; receipt already commits revocation
        f.state = f.observer.refresh()
        f.publish()
        self.assertEqual(f.reader.read(), f.org)

    def test_collector_cannot_republish_an_old_observation_as_current(self):
        f = self.fixture
        self.publisher.refresh(**self.reviewed_change())
        with self.assertRaises(ValueError):
            f.publish()  # old observer inputs, even though source now reads new
        with self.assertRaises(ValueError):
            f.reader.read()

    def test_nonroot_owned_or_writable_publication_is_not_trusted(self):
        f = self.fixture
        os.chown(f.publication.path, 65534, 65534)
        with self.assertRaises(ValueError):
            f.reader.read()

    def test_reader_can_verify_current_revision_without_source_access(self):
        self._assert_unprivileged_reader(0o755)

    def test_reader_with_traversal_only_parent_needs_no_listing_permission(self):
        self._assert_unprivileged_reader(0o711)

    def _assert_unprivileged_reader(self, parent_mode):
        f = self.fixture
        # Exercise both the readable synthetic parent and traversal-only access;
        # the original source and copies remain inaccessible in either case.
        f.root.chmod(parent_mode)
        for directory in (f.private, f.index.parent):
            os.chown(directory, 0, 65534)
            directory.chmod(0o750)
        f.publish()
        code = '''
import sys
from pathlib import Path
from authority_publication import PublishedAuthority
from phantomdocs.workflow_policy_commit import committed_guard
private,index,source,lock=sys.argv[1:]
a=PublishedAuthority(private,index,'example',source,max_age=30,clock=lambda:100,policy_lock=lock)
assert a.read()['organization']['id']=='example'
try: Path(source).read_bytes()
except PermissionError: pass
else: raise AssertionError('reader gained source access')
'''
        # CI runner homes can be private. Copy only test code/dependencies to a
        # fresh synthetic runtime instead of changing any runner directory ACL.
        import phantomdocs
        runtime = f.root / 'runtime'
        runtime.mkdir(mode=0o755)
        for module in Path(__file__).parent.glob('*.py'):
            shutil.copyfile(module, runtime / module.name)
        shutil.copytree(Path(phantomdocs.__file__).parent, runtime / 'phantomdocs',
                        ignore=shutil.ignore_patterns('__pycache__'))
        # Preserve the installed dependency closure (jsonschema, signing, YAML)
        # without letting the child traverse the runner's private venv.
        shutil.copytree(sysconfig.get_path('purelib'), runtime / 'site-packages',
                        ignore=shutil.ignore_patterns('__pycache__'))
        result = subprocess.run([sys._base_executable, '-B', '-c', code, str(f.private), str(f.index),
            str(f.source), str(self.lock)], user=65534, group=65534, extra_groups=[],
            cwd=runtime, env={'PYTHONPATH': os.pathsep.join((str(runtime), str(runtime / 'site-packages'))),
                              'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, check=False, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_actual_shared_lock_covers_protected_delivery_and_blocks_writer(self):
        f = self.fixture
        entered, release, started, finished = (threading.Event() for _ in range(4))
        class Slow(RecipientHandler):
            def send(handler, status, body, *args, **kw):
                if status == 200:
                    entered.set()
                    if not release.wait(3):
                        raise OSError('synthetic slow output')
                return super().send(status, body, *args, **kw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Slow)
        server.policy_authority = f.reader
        server.gate = server.scoped_backend = None
        server.token = 'synthetic'
        server.observatory = SimpleNamespace(data=lambda: {'protected': 'current'})
        serve = threading.Thread(target=server.serve_forever, daemon=True)
        serve.start()
        self.addCleanup(server.server_close)
        self.addCleanup(serve.join, 3)
        self.addCleanup(server.shutdown)
        results, errors = [], []
        def fetch():
            client = HTTPConnection('127.0.0.1', server.server_port, timeout=4)
            try:
                client.request('GET', '/api/state', headers={'Authorization': 'Bearer synthetic'})
                response = client.getresponse()
                results.append((response.status, response.read()))
            except Exception as error:
                errors.append(error)
            finally:
                client.close()
        def writer():
            from phantomdocs.workflow_policy_guard import policy_guard
            started.set()
            with policy_guard(str(self.lock), exclusive=True, recovering=True):
                finished.set()
        one, two = threading.Thread(target=fetch), threading.Thread(target=writer)
        one.start()
        try:
            self.assertTrue(entered.wait(2))
            two.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(.05))
        finally:
            release.set()
            one.join(4)
            if two.ident is not None:
                two.join(4)
        self.assertFalse(errors)
        self.assertEqual(results[0][0], 200)
        self.assertTrue(finished.is_set())

    def test_source_copy_interruption_denies_until_matching_recovery(self):
        f = self.fixture
        reviewed = self.reviewed_change()
        sync = self.publisher._synchronize_locked
        def failed(src, dst, **kw):
            if dst == str(self.docs):
                raise OSError('synthetic copy interruption')
            return sync(src, dst, **kw)
        with patch.object(self.publisher, '_synchronize_locked', failed):
            with self.assertRaises(OSError):
                self.publisher.refresh(**reviewed)
        with self.assertRaises(ValueError):
            f.reader.read()
        self.publisher.refresh(**self.options)
        with self.assertRaises(ValueError):
            f.reader.read()  # recovery commits; cached private publication is old
        f.state = f.observer.refresh()
        f.publish()
        self.assertEqual(f.reader.read(), f.org)
