"""Fixed job metadata, response gating and real disconnect cancellation."""
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from conversation_execution import ConversationProcess
from conversation_forwarding import WorkerInbox, WorkerJob
from test_conversation_forwarding import Connection, POLICY, ROUTE
from test_worker_workspace import workspace


class ConversationExecutionTests(unittest.TestCase):
    def setUp(self):
        self.job = WorkerJob('a' * 32, 'guide', ROUTE, 'Question', time.monotonic() + 5)
        with patch.object(POLICY.__class__, 'check'):
            self.inbox = WorkerInbox(persona='guide', policy=POLICY)
        with patch.object(ConversationProcess, 'verify'):
            self.executor = ConversationProcess(inbox=self.inbox, executable='/protected/native',
                                                sha256='a' * 64, working_dir='/protected/work', environment={})

    def serve(self, response=b'Answer', *, during_run=None, shutdown=None, **options):
        def execute(*args, **kwargs):
            if during_run:
                during_run(args, kwargs)
            return response

        with patch.object(self.executor, 'verify'), patch.object(self.inbox, 'receive', return_value=self.job), \
                patch.object(self.inbox, 'reply') as reply, patch('conversation_execution.run', side_effect=execute) as run, \
                patch('conversation_execution.select.select', return_value=([], [], [])):
            outcome = self.executor.serve_connection(Connection(), shutdown=shutdown, **options)
            return outcome, run, reply

    def test_full_job_metadata_crosses_stdin_and_target_stays_fixed(self):
        outcome, run, reply = self.serve()
        self.assertEqual(outcome, 'complete')
        args, kwargs = run.call_args
        self.assertEqual(args[0], ['/protected/native', '__conversation-worker'])
        doc = json.loads(args[1])
        self.assertEqual((doc['persona'], doc['tier'], doc['audience']), ('guide', 'principal', 'private'))
        self.assertEqual(doc['text'], 'Question')
        self.assertNotIn('authorization', doc)
        self.assertEqual(kwargs['environment'], {'PHANTOMVIEW_WORKER_PERSONA': 'guide',
                                                 'PHANTOMVIEW_WORKER_UID': str(POLICY.worker_uid)})
        self.assertIs(reply.call_args.args[1], self.job)

    def test_native_hold_never_releases_model_stdout(self):
        def hold(_args, kwargs):
            kwargs['stderr_sink'](b'\nPHANTOMVIEW_HELD\n')

        outcome, _, reply = self.serve(during_run=hold)
        self.assertEqual(outcome, 'held')
        reply.assert_not_called()

    def test_shutdown_during_execution_discards_late_answer(self):
        shutdown = threading.Event()
        outcome, _, reply = self.serve(shutdown=shutdown, during_run=lambda *_: shutdown.set())
        self.assertEqual(outcome, 'cancelled')
        reply.assert_not_called()

    def test_artifact_change_or_denied_peer_never_reaches_inference(self):
        for target in ('verify', 'receive'):
            owner = self.executor if target == 'verify' else self.inbox
            with patch.object(self.executor, 'verify'), patch.object(owner, target, side_effect=ValueError('private')):
                with patch('conversation_execution.run') as run:
                    self.assertEqual(self.executor.serve_connection(Connection()), 'unavailable')
                    run.assert_not_called()

    def test_artifact_change_before_release_and_invalid_utf8_discard_answer(self):
        with patch.object(self.executor, 'verify', side_effect=[None, ValueError('changed')]), \
                patch.object(self.inbox, 'receive', return_value=self.job), patch.object(self.inbox, 'reply') as reply, \
                patch('conversation_execution.run', return_value=b'Answer'), \
                patch('conversation_execution.select.select', return_value=([], [], [])):
            self.assertEqual(self.executor.serve_connection(Connection()), 'unavailable')
            reply.assert_not_called()
        outcome, _, reply = self.serve(response=b'\xff')
        self.assertEqual(outcome, 'unavailable')
        reply.assert_not_called()

    def test_busy_slot_does_not_start_another_process(self):
        self.executor._slot.acquire()
        try:
            with patch('conversation_execution.run') as run:
                self.assertEqual(self.executor.serve_connection(Connection()), 'unavailable')
                run.assert_not_called()
        finally:
            self.executor._slot.release()

    def test_environment_cannot_override_fixed_persona_or_worker_uid(self):
        for environment in ({'PHANTOMVIEW_WORKER_PERSONA': 'other'}, {'PHANTOMVIEW_WORKER_UID': '1'}):
            with patch.object(ConversationProcess, 'verify'), self.assertRaises(ValueError):
                ConversationProcess(inbox=self.inbox, executable='/protected/native', sha256='a' * 64,
                                    working_dir='/protected/work', environment=environment)

    def test_channel_credentials_and_loader_injection_never_create_an_executor(self):
        for key in ('TELEGRAM_BOT_TOKEN', 'NOSTR_NSEC', 'NODE_OPTIONS', 'LD_PRELOAD'):
            with patch.object(ConversationProcess, 'verify') as verify, self.assertRaises(ValueError):
                ConversationProcess(inbox=self.inbox, executable='/protected/native', sha256='a' * 64,
                                    working_dir='/protected/work', environment={key: 'PRIVATE_SENTINEL'})
            verify.assert_not_called()

    def test_model_store_is_reloaded_per_turn_and_missing_store_never_releases_an_answer(self):
        self.executor.credential_file = '/protected/model.json'
        with patch('conversation_execution.load_credentials', side_effect=[
                {'PHANTOMBOT_PI_API_KEY': 'first'}, {'PHANTOMBOT_PI_API_KEY': 'second'}]) as loader:
            first, run_one, _ = self.serve()
            second, run_two, _ = self.serve()
        self.assertEqual((first, second, loader.call_count), ('complete', 'complete', 2))
        self.assertEqual(run_one.call_args.kwargs['environment']['PHANTOMBOT_PI_API_KEY'], 'first')
        self.assertEqual(run_two.call_args.kwargs['environment']['PHANTOMBOT_PI_API_KEY'], 'second')
        self.assertNotIn('PHANTOMBOT_PI_API_KEY', self.executor.environment)
        with patch('conversation_execution.load_credentials', side_effect=ValueError('unavailable')):
            outcome, run, reply = self.serve()
            self.assertEqual(outcome, 'unavailable')
            run.assert_not_called()
            reply.assert_not_called()

    def test_inline_credentials_cannot_override_a_protected_store(self):
        with patch.object(ConversationProcess, 'verify'), self.assertRaises(ValueError):
            ConversationProcess(inbox=self.inbox, executable='/protected/native', sha256='a' * 64,
                                working_dir='/protected/work', credential_file='/protected/model.json',
                                environment={'PHANTOMBOT_PI_API_KEY': 'INLINE_SENTINEL'})

    def test_fixed_workspace_binds_locations_and_private_child_files(self):
        plan = workspace(worker_uid=POLICY.worker_uid)
        with patch.object(ConversationProcess, 'verify'):
            self.executor = ConversationProcess(inbox=self.inbox, executable='/protected/native', sha256='a' * 64,
                working_dir=plan.home, environment={}, workspace=plan)
        outcome, run, _ = self.serve()
        self.assertEqual(outcome, 'complete')
        self.assertTrue(run.call_args.kwargs['private_files'])
        self.assertEqual(run.call_args.kwargs['environment']['HOME'], plan.home)
        self.assertEqual(run.call_args.kwargs['environment']['PHANTOMBOT_PERSONAS_DIR'], plan.root + '/profiles')

    def test_workspace_mismatch_and_location_overrides_fail_before_verification(self):
        for changes in ({'working_dir': '/other'}, {'environment': {'HOME': '/issuer'}},
                        {'workspace': workspace(persona='other')}, {'workspace': object()}):
            plan = workspace(worker_uid=POLICY.worker_uid)
            args = {'inbox': self.inbox, 'executable': '/protected/native', 'sha256': 'a' * 64,
                    'working_dir': plan.home, 'environment': {}, 'workspace': plan} | changes
            with patch.object(ConversationProcess, 'verify') as verify, self.assertRaises(ValueError):
                ConversationProcess(**args)
            verify.assert_not_called()

    @unittest.skipUnless(sys.platform == 'linux', 'Real Unix disconnect and process groups required')
    def test_real_disconnect_stops_ignoring_native_fixture_and_releases_slot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = root / 'fixture'
            binary.write_text('#!/usr/bin/python3\nimport os,signal,time\n'
                              'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                              'open("ready.pid","w").write(str(os.getpid()))\ntime.sleep(20)\n')
            binary.chmod(0o700)
            self.executor.executable, self.executor.working_dir = str(binary), str(root)
            self.executor.sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()
            connection, peer = socket.socketpair()
            outcome = []
            thread = threading.Thread(target=lambda: outcome.append(self.executor.serve_connection(connection)))
            with patch.object(self.executor, 'verify'), patch.object(self.inbox, 'receive', return_value=self.job):
                thread.start()
                try:
                    end = time.monotonic() + 3
                    while not (root / 'ready.pid').exists() and time.monotonic() < end:
                        threading.Event().wait(.01)
                    self.assertTrue((root / 'ready.pid').exists())
                finally:
                    peer.close()
                    thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(outcome, ['unavailable'])
            self.assertFalse(self.executor._slot.locked())


if __name__ == '__main__':
    unittest.main()
