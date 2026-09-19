"""A resumed worldline cannot silently cross different execution conditions."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import final_experiment_runner as runner
import homeostasis_core.execution_identity as identity_module
from tests.final import test_no_regeneration_resume as fixtures


class ResumeExecutionIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / 'synthetic.json'
        self.checkpoint = self.output.with_suffix('.json.checkpoint')
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(socket, 'create_connection', side_effect=AssertionError('NO_NETWORK')))
        source = runner.SOURCE_ROOT
        self.sources = self.root / 'source'
        shutil.copytree(source / 'homeostasis_core', self.sources / 'homeostasis_core',
                        ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('final_experiment_runner.py', 'model_response_json.py', 'response_receipts.py',
                     'provider_retry.py', 'provider_response.py'):
            shutil.copyfile(source / name, self.sources / name)
        stack.enter_context(patch.object(runner, 'SOURCE_ROOT', self.sources))
        self.inputs = []
        for name in ('SCENARIO_PATH', 'COUNTRY_CONFIGURATION_PATH', 'RESOURCE_NETWORK_PATH'):
            original = getattr(runner, name)
            copy = self.root / original.name
            shutil.copyfile(original, copy); self.inputs.append(copy)
            stack.enter_context(patch.object(runner, name, copy))

    def client(self):
        return fixtures.RunnerResumeIntegrationTests.client(None)

    def stop(self, *, completed=False):
        original = runner._checkpoint
        def at_boundary(path, data):
            original(path, data)
            active = data.get('active_run')
            if ((completed and data['completed_runs'] and active is None)
                    or (not completed and active and active['completed_turn'] == 2)):
                raise KeyboardInterrupt('synthetic boundary stop')
        with patch.object(runner, '_checkpoint', side_effect=at_boundary):
            with self.assertRaises(KeyboardInterrupt): runner.run_live(self.client(), self.output, 1, 7)

    def assert_refused(self, code='EXECUTION_IDENTITY_MISMATCH', *, runs=1):
        before = self.checkpoint.read_bytes()
        receipts = {path: path.read_bytes() for path in (self.root / '.artifacts').rglob('*.json') if path.is_file()}
        client = self.client()
        with self.assertRaisesRegex(ValueError, code): runner.run_live(client, self.output, runs, 7, True)
        self.assertEqual(client.models.payloads, [])
        args = SimpleNamespace(one_run=False, runs=runs, seed=7, execute=True,
                               confirm='YES', output=self.output, resume=True)
        with patch.object(runner, 'parse_args', return_value=args), \
                patch.object(runner, 'getpass') as key, \
                patch.object(runner, 'create_gemini_client') as create, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, code): runner.main()
        key.assert_not_called(); create.assert_not_called()
        self.assertEqual(self.checkpoint.read_bytes(), before)
        self.assertEqual({path: path.read_bytes() for path in (self.root / '.artifacts').rglob('*.json') if path.is_file()}, receipts)
        self.assertFalse(self.output.exists())

    def test_each_changed_input_stops_before_new_call(self):
        self.stop()
        for path in self.inputs:
            with self.subTest(input=path.name):
                original = path.read_bytes()
                data = json.loads(original)
                if 'links' in data: data['links'][0]['supply_amount'] = 0
                elif 'countries' in data: data['countries']['MIL']['initial_resources']['levels']['food'] = 0
                else: data['event']['synthetic_change'] = True
                path.write_text(json.dumps(data))
                self.assert_refused()
                path.write_bytes(original)

    def test_each_changed_source_stops_before_new_call(self):
        self.stop()
        for name in ('homeostasis_core/gemini_agents.py', 'homeostasis_core/emergent_dynamics.py',
                     'final_experiment_runner.py', 'provider_response.py'):
            with self.subTest(source=name):
                path = self.sources / name; original = path.read_bytes()
                path.write_bytes(original + b'\n# synthetic file change\n')
                self.assert_refused(); path.write_bytes(original)

    def test_runtime_changes_stop_before_new_call(self):
        self.stop()
        for kind in ('python', 'sdk'):
            with self.subTest(runtime=kind):
                changed = identity_module.runtime_identity()
                if kind == 'python': changed['python'] = '0.0.synthetic'
                else: changed['packages']['google-genai'] = '0.0.synthetic'
                with patch.object(identity_module, 'runtime_identity', return_value=changed): self.assert_refused()

    def test_run_count_cannot_change_mid_experiment(self):
        self.stop(); self.assert_refused(runs=2)

    def test_started_legacy_checkpoint_is_not_backfilled(self):
        self.stop()
        saved = json.loads(self.checkpoint.read_text()); del saved['execution_identity']
        self.checkpoint.write_text(json.dumps(saved))
        self.assert_refused('EXECUTION_IDENTITY_MISSING')

    def test_completed_checkpoint_cannot_publish_under_changed_conditions(self):
        self.stop(completed=True)
        self.inputs[2].write_bytes(self.inputs[2].read_bytes() + b' ')
        self.assert_refused()

    def test_matching_resume_preserves_conditions_and_decisions(self):
        self.stop()
        saved = json.loads(self.checkpoint.read_text())
        client = self.client(); resumed = runner.run_live(client, self.output, 1, 7, True)
        self.assertEqual(len(client.models.payloads), 60)
        baseline = runner.run_live(self.client(), self.root / 'baseline.json', 1, 7)
        self.assertEqual(resumed['runs'][0]['turns'], baseline['runs'][0]['turns'])
        self.assertEqual(resumed['metadata']['execution_identity'], saved['execution_identity'])
        self.assertEqual(json.loads(self.output.read_text())['metadata']['execution_identity'], saved['execution_identity'])
        self.assertEqual(client.models.payloads,
                         [call['public_observation_payload'] for call in baseline['runs'][0]['call_audit']][20:])


if __name__ == '__main__': unittest.main()
