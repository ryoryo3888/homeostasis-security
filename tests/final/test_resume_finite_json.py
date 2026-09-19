"""Non-finite checkpoint values must stop before another model call or publish."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import final_experiment_runner as runner
from homeostasis_core.resume_guard import read_resumable_checkpoint, UnsafeResumeError
from tests.final import test_no_regeneration_resume as fixtures


class ResumeFiniteJsonTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / 'synthetic.json'
        self.path = self.output.with_suffix('.json.checkpoint')
        self.params = dict(runs=1, seed=7, turn_count=2, model='test-model', country_ids=('A',))

    def test_all_nonfinite_tokens_are_rejected_in_completed_and_active_records(self):
        for completed in (False, True):
            data = fixtures.fixture(2, completed=completed)
            record = data['completed_runs'][0] if completed else data['active_run']
            record['turns'][0]['research_metrics'] = {'global_homeostasis': 'NUMERIC_MARKER'}
            for token in ('NaN', 'Infinity', '-Infinity', '1e9999', '-1e9999'):
                with self.subTest(completed=completed, token=token):
                    self.path.write_text(json.dumps(data).replace('"NUMERIC_MARKER"', token))
                    original = self.path.read_bytes()
                    with self.assertRaisesRegex(UnsafeResumeError, 'NONFINITE_JSON_NUMBER'):
                        read_resumable_checkpoint(self.path, **self.params)
                    self.assertEqual(self.path.read_bytes(), original)

    def test_finite_numbers_and_words_are_preserved_without_normalization(self):
        data = fixtures.fixture()
        data['additional_fixture'] = [1, 1.5, -0.0, 1e-10, 1e300, 'NaN', 'Infinity']
        self.path.write_text(json.dumps(data)); original = self.path.read_bytes()
        loaded = read_resumable_checkpoint(self.path, **self.params)
        self.assertEqual(json.dumps(loaded), json.dumps(data))
        self.assertEqual(self.path.read_bytes(), original)

    def test_runner_stops_before_dispatch_and_cli_before_credentials(self):
        original = runner._checkpoint
        def stop(path, data):
            original(path, data)
            if data.get('active_run') and data['active_run']['completed_turn'] == 2:
                raise KeyboardInterrupt('synthetic boundary stop')
        with patch.object(runner, '_checkpoint', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                runner.run_live(fixtures.RunnerResumeIntegrationTests.client(None), self.output, 1, 7)
        data = json.loads(self.path.read_text())
        data['active_run']['turns'][0]['research_metrics']['global_homeostasis'] = float('nan')
        self.path.write_text(json.dumps(data)); before = self.path.read_bytes()
        client = fixtures.RunnerResumeIntegrationTests.client(None)
        with self.assertRaisesRegex(UnsafeResumeError, 'NONFINITE_JSON_NUMBER'):
            runner.run_live(client, self.output, 1, 7, True)
        self.assertEqual(client.models.payloads, [])
        args = SimpleNamespace(one_run=True, runs=1, seed=7, execute=True, confirm='YES', output=self.output, resume=True)
        with patch.object(runner, 'parse_args', return_value=args), patch.object(runner, 'getpass') as key, \
                patch.object(runner, 'create_gemini_client') as create, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(UnsafeResumeError, 'NONFINITE_JSON_NUMBER'): runner.main()
        key.assert_not_called(); create.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before); self.assertFalse(self.output.exists())


if __name__ == '__main__': unittest.main()
