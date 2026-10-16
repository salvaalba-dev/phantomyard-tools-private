"""Disposable root Linux CI only: real issuer/worker/model peer credentials."""
import hashlib
import os
from pathlib import Path
import select
import socket
import tempfile
import unittest

from conversation_forwarding import AccountPolicy, Forwarder, Route, WorkerInbox, _send
from conversation_execution import ConversationProcess
from test_conversation_forwarding import frame, request
from test_handoff_accounts import ENABLED, ISSUER, MODEL, READER, finish, spawn
from trusted_handoff import bind_listener
from worker_store import encode_credentials, load_credentials

OTHER_MODEL = 29004
POLICY = AccountPolicy(ISSUER, MODEL, READER, frozenset({MODEL, OTHER_MODEL}))


@unittest.skipUnless(ENABLED, 'Explicit ephemeral root Linux account-test job required')
class ConversationAccountTests(unittest.TestCase):
    def setUp(self):
        # All ancestors must be protected; /tmp is deliberately not accepted.
        self.folder = tempfile.TemporaryDirectory(prefix='phantomview-conversation-', dir='/run')
        self.addCleanup(self.folder.cleanup)
        os.chown(self.folder.name, MODEL, ISSUER)
        os.chmod(self.folder.name, 0o750)
        self.path = str(Path(self.folder.name) / 'conversation.sock')
        self.ready_read, self.ready_write = os.pipe()
        self.addCleanup(os.close, self.ready_read)
        self.addCleanup(os.close, self.ready_write)

    def wait_ready(self):
        self.assertTrue(select.select([self.ready_read], [], [], 8)[0], 'Worker did not become ready')
        self.assertEqual(os.read(self.ready_read, 1), b'1')

    def worker(self, *, malicious=False, reject=False):
        inbox = WorkerInbox(persona='guide', policy=POLICY)
        with bind_listener(self.path, ISSUER) as listener:
            os.write(self.ready_write, b'1')
            listener.settimeout(6)
            connection, _ = listener.accept()
            with connection:
                if reject:
                    try:
                        inbox.receive(connection)
                    except ValueError:
                        return {'rejected': True}
                    return {'rejected': False}
                job = inbox.receive(connection)
                if malicious:
                    _send(connection, {'schema_version': 1, 'kind': 'ordinary-reply', 'job_id': job.job_id,
                                       'text': 'Untrusted response', 'sender': '202', 'operation': 'issue-access'},
                          job.deadline)
                else:
                    inbox.reply(connection, job, 'Synthetic project summary')
                return {'received': job.text == 'Question', 'tier': job.route.tier}

    def issuer(self):
        client = Forwarder(persona='guide', socket_path=self.path, policy=POLICY)
        route = Route('telegram', '101', '101', 'principal', 'private')
        try:
            reply = client.forward(route, 'Question', seconds=5)
        except ValueError:
            return {'denied': True}
        return {'denied': False, 'bound': reply.route == route,
                'answer': reply.text == 'Synthetic project summary'}

    def test_real_isolated_issuer_worker_exchange_preserves_reply_binding(self):
        server = spawn(MODEL, self.worker)
        self.wait_ready()
        client_result = finish(spawn(ISSUER, self.issuer))
        server_result = finish(server)
        self.assertTrue(client_result['ok'], client_result)
        self.assertEqual(client_result['value'], {'denied': False, 'bound': True, 'answer': True})
        self.assertTrue(server_result['ok'], server_result)
        self.assertEqual(server_result['value'], {'received': True, 'tier': 'principal'})

    def test_malicious_worker_cannot_add_a_recipient_or_access_operation(self):
        server = spawn(MODEL, lambda: self.worker(malicious=True))
        self.wait_ready()
        client_result = finish(spawn(ISSUER, self.issuer))
        server_result = finish(server)
        self.assertTrue(server_result['ok'], server_result)
        self.assertEqual(client_result, {'ok': True, 'value': {'denied': True}})

    def test_model_bypassing_client_checks_is_rejected_by_kernel_peer_identity(self):
        server = spawn(MODEL, lambda: self.worker(reject=True))
        self.wait_ready()

        def attacker():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(3)
                connection.connect(self.path)
                try:
                    connection.sendall(frame(request()))
                    return connection.recv(16) == b''
                except OSError:
                    return True

        attack_result = finish(spawn(OTHER_MODEL, attacker))
        server_result = finish(server)
        self.assertEqual(attack_result, {'ok': True, 'value': True})
        self.assertEqual(server_result, {'ok': True, 'value': {'rejected': True}})

    def test_wrong_worker_receives_no_prompt_even_if_socket_metadata_matches(self):
        os.chown(self.folder.name, OTHER_MODEL, ISSUER)

        def wrong_worker():
            with bind_listener(self.path, ISSUER) as listener:
                os.write(self.ready_write, b'1')
                listener.settimeout(6)
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(3)
                    return {'no_bytes': connection.recv(16) == b''}

        server = spawn(OTHER_MODEL, wrong_worker)
        self.wait_ready()
        # Metadata alone now names the expected account; kernel peer credentials
        # must still identify the other account that actually bound the listener.
        os.chown(self.folder.name, MODEL, ISSUER)
        os.chown(self.path, MODEL, ISSUER)
        client_result = finish(spawn(ISSUER, self.issuer))
        server_result = finish(server)
        self.assertEqual(client_result, {'ok': True, 'value': {'denied': True}})
        self.assertEqual(server_result, {'ok': True, 'value': {'no_bytes': True}})

    def process_fixture(self, source):
        artifact = tempfile.TemporaryDirectory(prefix='phantomview-executable-', dir='/run')
        self.addCleanup(artifact.cleanup)
        os.chmod(artifact.name, 0o755)
        binary = Path(artifact.name) / 'fixture'
        binary.write_text('#!/usr/bin/python3\n' + source, encoding='utf-8')
        binary.chmod(0o755)
        return str(binary), hashlib.sha256(binary.read_bytes()).hexdigest()

    def execution_worker(self, binary, digest):
        inbox = WorkerInbox(persona='guide', policy=POLICY)
        executor = ConversationProcess(inbox=inbox, executable=binary, sha256=digest,
                                       working_dir=self.folder.name, environment={})
        with bind_listener(self.path, ISSUER) as listener:
            os.write(self.ready_write, b'1')
            listener.settimeout(6)
            connection, _ = listener.accept()
            return executor.serve_connection(connection)

    def credential_fixture(self):
        directory = tempfile.TemporaryDirectory(prefix='phantomview-model-store-', dir='/run')
        self.addCleanup(directory.cleanup)
        os.chown(directory.name, 0, MODEL)
        os.chmod(directory.name, 0o710)
        path = Path(directory.name) / 'model.json'
        path.write_bytes(encode_credentials(persona='guide', worker_uid=MODEL,
                         credentials={'PHANTOMBOT_PI_API_KEY': 'SYNTHETIC_MODEL_ONLY'}))
        os.chown(path, 0, MODEL)
        path.chmod(0o640)
        return path

    def test_protected_model_store_is_readable_only_by_its_worker_and_not_writable(self):
        path = self.credential_fixture()

        def worker():
            values = load_credentials(str(path), persona='guide', worker_uid=MODEL)
            try:
                path.write_bytes(b'changed')
            except PermissionError:
                return {'selected': values == {'PHANTOMBOT_PI_API_KEY': 'SYNTHETIC_MODEL_ONLY'},
                        'write_denied': True}
            return {'write_denied': False}

        self.assertEqual(finish(spawn(MODEL, worker, gid=MODEL)),
                         {'ok': True, 'value': {'selected': True, 'write_denied': True}})

        def denied():
            try:
                path.read_bytes()
            except PermissionError:
                return True
            return False

        for uid in (ISSUER, READER, OTHER_MODEL):
            self.assertEqual(finish(spawn(uid, denied)), {'ok': True, 'value': True})

    def test_model_store_rejects_linked_or_mutable_sources(self):
        path = self.credential_fixture()

        def refused():
            try:
                load_credentials(str(path), persona='guide', worker_uid=MODEL)
            except ValueError:
                return True
            return False

        path.chmod(0o660)
        self.assertEqual(finish(spawn(MODEL, refused, gid=MODEL)), {'ok': True, 'value': True})
        path.chmod(0o640)
        alias = path.with_name('alias.json')
        os.link(path, alias)
        self.assertEqual(finish(spawn(MODEL, refused, gid=MODEL)), {'ok': True, 'value': True})
        alias.unlink()
        path.rename(alias)
        path.symlink_to(alias)
        self.assertEqual(finish(spawn(MODEL, refused, gid=MODEL)), {'ok': True, 'value': True})
        path.unlink()
        alias.rename(path)
        path.rename(alias)
        os.mkfifo(path, 0o640)
        os.chown(path, 0, MODEL)
        self.assertEqual(finish(spawn(MODEL, refused, gid=MODEL)), {'ok': True, 'value': True})
        path.unlink()
        alias.rename(path)
        os.chmod(path.parent, 0o730)
        self.assertEqual(finish(spawn(MODEL, refused, gid=MODEL)), {'ok': True, 'value': True})

    def test_protected_model_store_reaches_only_the_fixed_child_environment(self):
        path = self.credential_fixture()
        binary, digest = self.process_fixture('import json,os,sys\njson.load(sys.stdin)\n'
            'assert os.environ["PHANTOMBOT_PI_API_KEY"] == "SYNTHETIC_MODEL_ONLY"\n'
            'assert "TELEGRAM_BOT_TOKEN" not in os.environ\n'
            'sys.stdout.write("Synthetic project summary")\n')

        def worker():
            inbox = WorkerInbox(persona='guide', policy=POLICY)
            executor = ConversationProcess(inbox=inbox, executable=binary, sha256=digest,
                working_dir=self.folder.name, environment={}, credential_file=str(path))
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(self.path)
                listener.listen(1)
                os.write(self.ready_write, b'1')
                listener.settimeout(6)
                connection, _ = listener.accept()
                return executor.serve_connection(connection)

        server = spawn(MODEL, worker, gid=MODEL)
        self.wait_ready()
        os.chown(self.path, MODEL, ISSUER)
        os.chmod(self.path, 0o660)
        client = finish(spawn(ISSUER, self.issuer))
        self.assertEqual(finish(server), {'ok': True, 'value': 'complete'})
        self.assertEqual(client, {'ok': True, 'value': {'denied': False, 'bound': True, 'answer': True}})

    def test_isolated_worker_process_receives_full_metadata_and_returns_bound_reply(self):
        binary, digest = self.process_fixture('import json,sys\njob=json.load(sys.stdin)\n'
            'assert job["tier"] == "principal" and job["audience"] == "private"\n'
            'assert job["persona"] == "guide" and job["text"] == "Question"\n'
            'print("Synthetic project summary")\n')
        server = spawn(MODEL, lambda: self.execution_worker(binary, digest))
        self.wait_ready()

        def issuer():
            client = Forwarder(persona='guide', socket_path=self.path, policy=POLICY)
            route = Route('telegram', '101', '101', 'principal', 'private')
            result = client.forward(route, 'Question', seconds=5)
            return result.route == route and result.text.strip() == 'Synthetic project summary'

        self.assertEqual(finish(spawn(ISSUER, issuer)), {'ok': True, 'value': True})
        self.assertEqual(finish(server), {'ok': True, 'value': 'complete'})

    def test_disconnect_terminates_real_worker_child_under_its_separate_uid(self):
        binary, digest = self.process_fixture('import json,os,signal,sys,time\njson.load(sys.stdin)\n'
            'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
            'open("running.pid","w").write(str(os.getpid()))\ntime.sleep(20)\n')
        server = spawn(MODEL, lambda: self.execution_worker(binary, digest))
        self.wait_ready()
        ready = Path(self.folder.name) / 'running.pid'

        def issuer():
            class CancelWhenRunning:
                def is_set(self):
                    return ready.exists()

            client = Forwarder(persona='guide', socket_path=self.path, policy=POLICY)
            try:
                client.forward(Route('telegram', '101', '101', 'principal', 'private'),
                               'Question', seconds=5, cancelled=CancelWhenRunning())
            except ValueError:
                return True
            return False

        self.assertEqual(finish(spawn(ISSUER, issuer)), {'ok': True, 'value': True})
        self.assertEqual(finish(server), {'ok': True, 'value': 'unavailable'})
        pid = int(ready.read_text())
        self.assertFalse(Path(f'/proc/{pid}').exists(), 'Direct worker child must be reaped')


if __name__ == '__main__':
    unittest.main()
