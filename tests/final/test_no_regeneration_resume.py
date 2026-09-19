"""Technical synthetic fixtures only; no external API or research outcomes."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
# Load the real read-only gate without constructing any model/client.
spec = importlib.util.spec_from_file_location('resume_gate_under_test', ROOT/'homeostasis_core/resume_guard.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def fixture(n=1, completed=False):
    rows, audit = [], []
    for turn in range(1, n + 1):
        country = {'action': 'synthetic', 'turn': turn}
        proposal, evaluation = {'proposal': turn}, {'assessment': turn}
        state = {'true_world': {'synthetic': turn}, 'country_states': {'A': {'stock': turn}},
                 'world_pool': {}, 'network_policy': {}, 'reconstruction': {'after': 1}}
        rows.append({'turn': turn, 'proposal': proposal, 'country_responses': {'A': country},
                     'evaluator_commentary': evaluation, 'executed_state': state})
        for role, actor, answer in [('coordinator', 'coord', proposal),
                                    ('country', 'A', country), ('evaluator', 'eval', evaluation)]:
            payload = {'turn': turn, 'actor': actor}
            audit.append({'run': 1, 'turn': turn, 'model': 'test-model', 'agent_type': role,
                          'agent_id': actor, 'attempt': 1, 'snapshot_id': f'run-1-turn-{turn}-start',
                          'public_observation_payload': payload, 'observation_digest': digest(payload),
                          'response_status': 'validated', 'structured_response': answer})
    record = {'run': 1, 'seed': 7, 'turns': rows, 'call_audit': audit}
    if completed:
        record['model'] = 'test-model'
        return {'completed_runs': [record], 'active_run': None}
    record.update(completed_turn=n, current_world=state['true_world'],
                  country_states=state['country_states'], world_pool={}, network_policy={},
                  current_damage=1, history_state={}, memories={'A': [{} for _ in range(n)]})
    return {'completed_runs': [], 'active_run': record}


class ResumeGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'result.json.checkpoint'
        self.params = dict(runs=1, seed=7, turn_count=2, model='test-model', country_ids=('A',))
        self.net = patch.object(socket, 'create_connection', side_effect=AssertionError('NO_NETWORK'))
        self.net.start(); self.addCleanup(self.net.stop)

    def read(self, value):
        self.path.write_text(json.dumps(value))
        before = self.path.read_bytes()
        try:
            return gate.read_resumable_checkpoint(self.path, **self.params)
        finally:
            self.assertEqual(self.path.read_bytes(), before)

    def reject(self, value, code):
        with self.assertRaisesRegex(gate.UnsafeResumeError, code):
            self.read(value)

    def test_empty_unstarted_checkpoint(self):
        self.assertEqual(self.read({'completed_runs': []}), {'completed_runs': []})

    def test_clean_turn_boundary_unchanged(self):
        data = fixture(); self.assertEqual(self.read(data), data)

    def test_finished_run_needs_no_reexecution(self):
        data = fixture(2, completed=True); self.assertEqual(self.read(data), data)

    def test_legacy_successful_committed_decisions(self):
        data = fixture()
        for row in data['active_run']['call_audit']: row.pop('response_status')
        self.assertEqual(self.read(data), data)

    def test_partial_next_turn_blocks_even_after_success(self):
        data = fixture(); extra = deepcopy(data['active_run']['call_audit'][0]); extra['turn'] = 2
        data['active_run']['call_audit'].append(extra)
        self.reject(data, 'UNCOMMITTED_DECISION')

    def test_pre_dispatch_journal_also_blocks(self):
        data = fixture(); extra = deepcopy(data['active_run']['call_audit'][0])
        extra.update(turn=2, structured_response=None); extra.pop('response_status')
        data['active_run']['call_audit'].append(extra)
        self.reject(data, 'UNCOMMITTED_DECISION')

    def test_invalid_response_never_counts_as_completed(self):
        data = fixture(); data['active_run']['call_audit'][0]['response_status'] = 'validation_failed'
        self.reject(data, 'RESPONSE_NOT_COMMITTED')

    def test_missing_audit(self):
        data = fixture(); data['active_run'].pop('call_audit')
        self.reject(data, 'MISSING_CALL_AUDIT')

    def test_missing_country_decision(self):
        data = fixture(); data['active_run']['call_audit'].pop(1)
        self.reject(data, 'MISSING_DECISION_EVIDENCE')

    def test_model_mismatch(self):
        data = fixture(); data['active_run']['call_audit'][0]['model'] = 'other'
        self.reject(data, 'AUDIT_IDENTITY_MISMATCH')

    def test_finished_model_mismatch(self):
        data = fixture(2, completed=True); data['completed_runs'][0]['model'] = 'other'
        self.reject(data, 'MODEL_MISMATCH')

    def test_seed_mismatch(self):
        data = fixture(); data['active_run']['seed'] = 8
        self.reject(data, 'SEED_MISMATCH')

    def test_turn_counter_cannot_hide_partial_turn(self):
        data = fixture(); data['active_run']['completed_turn'] = 2
        self.reject(data, 'TURN_COUNT_MISMATCH')

    def test_boolean_is_not_turn_number(self):
        data = fixture(); data['active_run']['completed_turn'] = True
        self.reject(data, 'INVALID_COMPLETED_TURN')

    def test_out_of_order_turns(self):
        data = fixture(2); data['active_run']['turns'].reverse()
        self.reject(data, 'TURN_ORDER_MISMATCH')

    def test_response_must_match_committed_turn(self):
        data = fixture(); data['active_run']['call_audit'][1]['structured_response'] = {'different': True}
        self.reject(data, 'RESPONSE_NOT_COMMITTED')

    def test_snapshot_mismatch(self):
        data = fixture(); data['active_run']['call_audit'][1]['snapshot_id'] = 'wrong'
        self.reject(data, 'SNAPSHOT_MISMATCH')

    def test_request_digest_mismatch(self):
        data = fixture(); data['active_run']['call_audit'][1]['observation_digest'] = 'wrong'
        self.reject(data, 'REQUEST_DIGEST_MISMATCH')

    def test_changed_runtime_state(self):
        data = deepcopy(fixture()); data['active_run']['current_world'] = {'changed': 1}
        self.reject(data, 'STATE_MISMATCH')

    def test_changed_damage(self):
        data = fixture(); data['active_run']['current_damage'] = 99
        self.reject(data, 'DAMAGE_MISMATCH')

    def test_memory_length(self):
        data = fixture(); data['active_run']['memories']['A'] = []
        self.reject(data, 'MEMORY_LENGTH_MISMATCH')

    def test_known_provider_retry_identical_request_allowed(self):
        data = fixture(); logs = data['active_run']['call_audit']
        failure = deepcopy(logs[0]); failure.update(response_status='provider_error', structured_response=None)
        logs[0]['attempt'] = 2; logs.insert(0, failure)
        self.assertEqual(self.read(data), data)

    def test_legacy_ambiguous_retry_is_not_accepted(self):
        data = fixture(); logs = data['active_run']['call_audit']
        failure = deepcopy(logs[0]); failure.update(structured_response=None); failure.pop('response_status')
        logs[0]['attempt'] = 2; logs.insert(0, failure)
        self.reject(data, 'REGENERATED_OR_AMBIGUOUS_RESPONSE')

    def test_retry_with_changed_payload_is_rejected(self):
        data = fixture(); logs = data['active_run']['call_audit']
        failure = deepcopy(logs[0]); failure.update(response_status='provider_error', structured_response=None)
        failure['public_observation_payload'] = {'changed': True}
        failure['observation_digest'] = digest(failure['public_observation_payload'])
        logs[0]['attempt'] = 2; logs.insert(0, failure)
        self.reject(data, 'CHANGED_REQUEST')

    def test_missing_file_is_not_new_experiment(self):
        with self.assertRaisesRegex(gate.UnsafeResumeError, 'CHECKPOINT_NOT_FOUND'):
            gate.read_resumable_checkpoint(self.path, **self.params)
        self.assertFalse(self.path.exists())

    def test_duplicate_keys_are_not_silently_collapsed(self):
        self.path.write_text('{"completed_runs":[],"completed_runs":[{}]}')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(gate.UnsafeResumeError, 'DUPLICATE_JSON_KEY'):
            gate.read_resumable_checkpoint(self.path, **self.params)
        self.assertEqual(self.path.read_bytes(), before)


class RunnerResumeIntegrationTests(unittest.TestCase):
    """Real runner, gateway, parsers and world modules; synthetic provider only."""
    def setUp(self):
        import final_experiment_runner as runner
        self.runner = runner
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)/'synthetic.json'
        self.network = patch.object(socket, 'create_connection', side_effect=AssertionError('NO_NETWORK'))
        self.network.start(); self.addCleanup(self.network.stop)

    def client(self):
        class Models:
            def __init__(self): self.payloads = []
            def generate_content(self, **kw):
                data = json.loads(kw['contents']); self.payloads.append(data)
                if 'observable_world' in data:
                    answer = dict(proposal_id='p', proposal_type='食料援助', reason='synthetic',
                                  predicted_global_effect=60, predicted_sovereignty_burden=5, requested_action='synthetic')
                elif 'executed_true_state' in data:
                    answer = dict(national_sovereignty=80, global_homeostasis=75, resource_stability=70,
                                  resilience=72, conflict_load=20, history_effect=30, assessment='synthetic')
                else:
                    answer = dict(country_id=data['turn_start_observation']['own_country'], proposal_id='p',
                                  response_id='ACCEPT', response_label='受け入れる', reason='synthetic', conditions={},
                                  self_interest=60, sovereignty_burden=5, perceived_global_effect=60,
                                  action_requires_participation=True,
                                  action=dict(action_id='NO_ACTION', description='synthetic',
                                              parameters=dict(recipient_type='none', target_country=None, resource=None, amount=0)))
                return SimpleNamespace(text=json.dumps(answer), usage_metadata=None)
        return SimpleNamespace(models=Models())

    def test_clean_committed_boundary_continues_without_reissuing(self):
        original = self.runner._checkpoint
        first = self.client()
        def stop_at_boundary(path, data):
            original(path, data)
            active = data.get('active_run')
            if active and active['completed_turn'] == 2 and len(active['call_audit']) == 20:
                raise KeyboardInterrupt('synthetic boundary stop')
        with patch.object(self.runner, '_checkpoint', side_effect=stop_at_boundary):
            with self.assertRaises(KeyboardInterrupt):
                self.runner.run_live(first, self.output, 1, 7)
        self.assertEqual(len(first.models.payloads), 20)
        second = self.client()
        resumed = self.runner.run_live(second, self.output, 1, 7, True)
        self.assertEqual(len(second.models.payloads), 60)
        baseline = self.runner.run_live(self.client(), Path(self.tmp.name)/'baseline.json', 1, 7)
        self.assertEqual(resumed['runs'][0]['turns'], baseline['runs'][0]['turns'])
        self.assertEqual(len(resumed['runs'][0]['call_audit']), 80)

    def test_partial_turn_refused_with_zero_new_provider_calls(self):
        original = self.runner._checkpoint
        def stop_in_next_turn(path, data):
            original(path, data)
            active = data.get('active_run')
            if active and active['completed_turn'] == 2 and len(active['call_audit']) == 21:
                raise KeyboardInterrupt('synthetic partial stop')
        with patch.object(self.runner, '_checkpoint', side_effect=stop_in_next_turn):
            with self.assertRaises(KeyboardInterrupt):
                self.runner.run_live(self.client(), self.output, 1, 7)
        cp = self.output.with_suffix('.json.checkpoint'); before = cp.read_bytes()
        second = self.client()
        with self.assertRaisesRegex(ValueError, 'UNCOMMITTED_DECISION'):
            self.runner.run_live(second, self.output, 1, 7, True)
        self.assertEqual(second.models.payloads, [])
        self.assertEqual(cp.read_bytes(), before); self.assertFalse(self.output.exists())

    def test_cli_refuses_missing_checkpoint_before_client_or_key(self):
        args = SimpleNamespace(one_run=True, runs=1, seed=7, execute=True, confirm='YES',
                               output=self.output, resume=True)
        with patch.object(self.runner, 'parse_args', return_value=args), \
             patch.object(self.runner, 'create_gemini_client') as create, \
             patch.object(self.runner, 'getpass') as key:
            with self.assertRaisesRegex(ValueError, 'CHECKPOINT_NOT_FOUND'):
                self.runner.main()
            create.assert_not_called(); key.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_old_protocol_checkpoint_is_not_continued_under_new_semantics(self):
        original = self.runner._checkpoint
        def stop_at_boundary(path, data):
            original(path, data)
            active = data.get('active_run')
            if active and active['completed_turn'] == 1:
                raise KeyboardInterrupt('synthetic boundary stop')
        with patch.object(self.runner, '_checkpoint', side_effect=stop_at_boundary):
            with self.assertRaises(KeyboardInterrupt):
                self.runner.run_live(self.client(), self.output, 1, 7)
        cp = self.output.with_suffix('.json.checkpoint')
        data = json.loads(cp.read_text())
        for entry in data['active_run']['call_audit']:
            entry['schema_version'] = 2
        cp.write_text(json.dumps(data)); before = cp.read_bytes()
        second = self.client()
        with self.assertRaisesRegex(ValueError, 'RESUME_PROTOCOL_MISMATCH'):
            self.runner.run_live(second, self.output, 1, 7, True)
        self.assertEqual(second.models.payloads, [])
        self.assertEqual(cp.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
