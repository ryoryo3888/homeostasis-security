"""JSON booleans and numeric types must not substitute for saved evidence."""
from copy import deepcopy
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


class ResumeJsonTypeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / 'synthetic.json'
        self.path = self.output.with_suffix('.json.checkpoint')
        self.params = dict(runs=1, seed=7, turn_count=2, model='test-model', country_ids=('A',))

    def fixture(self):
        # Reading from disk severs aliases between committed and active state.
        return json.loads(json.dumps(fixtures.fixture()))

    def reject(self, data, code):
        self.path.write_text(json.dumps(data)); original = self.path.read_bytes()
        with self.assertRaisesRegex(UnsafeResumeError, code):
            read_resumable_checkpoint(self.path, **self.params)
        self.assertEqual(self.path.read_bytes(), original)

    def test_response_types_must_match_original_decision(self):
        for replacement in (True, 1.0):
            with self.subTest(replacement=replacement):
                data = self.fixture(); data['active_run']['turns'][0]['proposal']['proposal'] = replacement
                self.reject(data, 'RESPONSE_NOT_COMMITTED')

    def test_retry_payload_types_must_not_change(self):
        for replacement in (True, 1.0):
            with self.subTest(replacement=replacement):
                data = self.fixture(); logs = data['active_run']['call_audit']
                failure = deepcopy(logs[0]); failure.update(response_status='provider_error', provider_status_code=503, structured_response=None)
                failure['public_observation_payload']['turn'] = replacement
                failure['observation_digest'] = fixtures.digest(failure['public_observation_payload'])
                logs[0]['attempt'] = 2; logs.insert(0, failure)
                self.reject(data, 'CHANGED_REQUEST')

    def test_runtime_state_types_must_match_committed_state(self):
        for field, committed in (('current_world', 'true_world'), ('country_states', 'country_states'),
                                 ('world_pool', 'world_pool'), ('network_policy', 'network_policy')):
            for replacement in (True, 1.0):
                with self.subTest(field=field, replacement=replacement):
                    data = self.fixture(); active = data['active_run']
                    # Identical, finite fixture-only fields pass before the type change.
                    current_slot = active[field]['A'] if field == 'country_states' else active[field]
                    committed_slot = active['turns'][0]['executed_state'][committed]
                    if field == 'country_states': committed_slot = committed_slot['A']
                    current_slot['synthetic_value'] = 1
                    committed_slot['synthetic_value'] = 1
                    self.path.write_text(json.dumps(data)); read_resumable_checkpoint(self.path, **self.params)
                    current_slot['synthetic_value'] = replacement
                    self.reject(data, 'STATE_MISMATCH')

    def test_damage_type_must_match_committed_damage(self):
        for replacement in (True, 1.0):
            with self.subTest(replacement=replacement):
                data = self.fixture(); data['active_run']['current_damage'] = replacement
                self.reject(data, 'DAMAGE_MISMATCH')

    def test_runner_rejects_changed_response_type_before_credentials_or_dispatch(self):
        original = runner._checkpoint
        def stop(path, data):
            original(path, data)
            if data.get('active_run') and data['active_run']['completed_turn'] == 2:
                raise KeyboardInterrupt('synthetic boundary stop')
        with patch.object(runner, '_checkpoint', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                runner.run_live(fixtures.RunnerResumeIntegrationTests.client(None), self.output, 1, 7)
        data = json.loads(self.path.read_text())
        response = data['active_run']['turns'][0]['country_responses']['MIL']
        self.assertIs(response['action_requires_participation'], True)
        response['action_requires_participation'] = 1
        self.path.write_text(json.dumps(data)); before = self.path.read_bytes()
        client = fixtures.RunnerResumeIntegrationTests.client(None)
        with self.assertRaisesRegex(UnsafeResumeError, 'RESPONSE_NOT_COMMITTED'):
            runner.run_live(client, self.output, 1, 7, True)
        self.assertEqual(client.models.payloads, [])
        args = SimpleNamespace(one_run=True, runs=1, seed=7, execute=True, confirm='YES', output=self.output, resume=True)
        with patch.object(runner, 'parse_args', return_value=args), patch.object(runner, 'getpass') as key, \
                patch.object(runner, 'create_gemini_client') as create, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(UnsafeResumeError, 'RESPONSE_NOT_COMMITTED'): runner.main()
        key.assert_not_called(); create.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before); self.assertFalse(self.output.exists())


if __name__ == '__main__': unittest.main()
