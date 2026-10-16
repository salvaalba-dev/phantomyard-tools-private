"""Disposable root Linux CI only: real issuer/worker/model peer credentials."""
import os
from pathlib import Path
import select
import socket
import tempfile
import unittest

from conversation_forwarding import AccountPolicy, Forwarder, Route, WorkerInbox, _send
from test_conversation_forwarding import frame, request
from test_handoff_accounts import ENABLED, ISSUER, MODEL, READER, finish, spawn
from trusted_handoff import bind_listener

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


if __name__ == '__main__':
    unittest.main()
