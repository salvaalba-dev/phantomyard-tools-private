"""Fail-closed artifact checks and fixed executor dispatch, without a model."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from assistant_worker import ConsultationHeld
from scoped_assistant import ConsultationCancelled
from native_scoped_executor import ScopedNativeExecutor
from native_scoped_patch import patch as patch_source


class NativeExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {'org': 'example', 'persona': 'administrator', 'executable': str(self.root / 'native'),
                       'manifest': str(self.root / 'manifest.json'), 'working_dir': str(self.root)}
        self.envelope = {'kind': 'scoped-consultation', 'trust': 'untrusted', 'organization': 'example',
                         'persona': 'administrator', 'question': 'Explain the supplied evidence', 'evidence': []}

    def executor(self):
        with patch.object(ScopedNativeExecutor, 'verify'):
            return ScopedNativeExecutor(self.config)

    def test_missing_artifact_and_legacy_worker_are_not_accepted(self):
        with self.assertRaises(ValueError):
            ScopedNativeExecutor(self.config)
        (self.root / 'manifest.json').write_text(json.dumps({'restrictions': ['tools-none']}))
        with self.assertRaises(ValueError):
            ScopedNativeExecutor(self.config)

    def test_fixed_dispatch_reuses_existing_bounded_native_process_runner(self):
        executor = self.executor()
        with patch.object(executor, 'verify') as verify, patch.object(executor.jobs, 'execute', return_value='Answer') as run:
            self.assertEqual(executor(self.envelope), 'Answer')
            verify.assert_called_once()
            row = run.call_args.args[0]
            self.assertEqual(json.loads(row['prompt']), self.envelope)
            self.assertEqual(row['status'], 'running')
            self.assertNotIn('Cookie', json.dumps(row))
            self.assertEqual(executor.config['persona'], 'administrator')

    def test_mismatched_organization_persona_kind_and_trust_cannot_route(self):
        executor = self.executor()
        for key, value in (('organization', 'other'), ('persona', 'other'), ('kind', 'question'), ('trust', 'principal')):
            with self.subTest(key=key), patch.object(executor, 'verify'), patch.object(executor.jobs, 'execute') as run:
                with self.assertRaises(ValueError):
                    executor(self.envelope | {key: value})
                run.assert_not_called()

    def test_artifact_change_after_construction_blocks_inference(self):
        executor = self.executor()
        with patch.object(executor.jobs, 'execute') as run, self.assertRaises(ValueError):
            executor(self.envelope)
        run.assert_not_called()

    def test_hold_is_propagated_from_native_metadata_without_conversion(self):
        executor = self.executor()
        with patch.object(executor, 'verify'), patch.object(executor.jobs, 'execute', side_effect=ConsultationHeld):
            with self.assertRaises(ConsultationHeld):
                executor(self.envelope)

    def test_unknown_source_patch_fails_before_writing(self):
        ask = self.root / 'src/cli/ask.ts'
        ask.parent.mkdir(parents=True)
        ask.write_text('Unknown source version', encoding='utf-8')
        with self.assertRaises(ValueError):
            patch_source(self.root)
        self.assertEqual(ask.read_text(), 'Unknown source version')

    def test_cancellation_is_visible_to_the_native_process_poll_loop(self):
        executor, cancelled = self.executor(), threading.Event()

        def run(row):
            self.assertEqual(row['status'], 'running')
            cancelled.set()
            self.assertEqual(row['status'], 'cancelled')
            raise RuntimeError('Native process stopped')

        with patch.object(executor, 'verify'), patch.object(executor.jobs, 'execute', side_effect=run):
            with self.assertRaises(ConsultationCancelled):
                executor.run(self.envelope, cancelled=cancelled)

    def test_already_cancelled_request_never_starts_a_native_process(self):
        executor, cancelled = self.executor(), threading.Event()
        cancelled.set()
        with patch.object(executor, 'verify'), patch.object(executor.jobs, 'execute') as run:
            with self.assertRaises(ConsultationCancelled):
                executor.run(self.envelope, cancelled=cancelled)
            run.assert_not_called()

    @unittest.skipUnless(sys.platform == 'linux', 'Process-group cancellation requires Linux')
    def test_cancellation_terminates_a_real_disposable_process(self):
        import fcntl
        import subprocess

        executor, cancelled = self.executor(), threading.Event()
        self.envelope['question'] = 'x' * 1800
        self.envelope['evidence'] = [{'excerpt': 'x' * 5000}]
        binary = Path(self.config['executable'])
        binary.write_text('#!' + sys.executable + '\nfrom pathlib import Path\nimport time\n'
                          'Path(__file__).with_suffix(".ready").touch()\nwhile True: time.sleep(.1)\n')
        binary.chmod(0o700)
        outcome = []

        def run():
            try:
                executor.run(self.envelope, cancelled=cancelled)
            except Exception as error:
                outcome.append(type(error))

        thread = threading.Thread(target=run, daemon=True)
        original_popen = subprocess.Popen

        def small_pipe(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            fcntl.fcntl(process.stdin.fileno(), fcntl.F_SETPIPE_SZ, 4096)
            return process

        with patch.object(executor, 'verify'), patch('assistant_worker.subprocess.Popen', side_effect=small_pipe):
            thread.start()
            try:
                deadline = time.monotonic() + 3
                while not binary.with_suffix('.ready').exists() and time.monotonic() < deadline:
                    threading.Event().wait(.01)
                self.assertTrue(binary.with_suffix('.ready').exists())
            finally:
                cancelled.set()
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, [ConsultationCancelled])


if __name__ == '__main__':
    unittest.main()
