"""Fail-closed artifact checks and fixed executor dispatch, without a model."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from assistant_worker import ConsultationHeld
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


if __name__ == '__main__':
    unittest.main()
