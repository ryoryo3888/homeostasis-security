import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from homeostasis_core.api_budget import BoundedClient
from homeostasis_core.gemini_agents import GeminiGateway, create_gemini_client
from homeostasis_core.research_validation import validate_research, accepted_research_paths, research_manifest
from final_experiment_runner import run_live
from tests.final.test_phase9_gemini_final import Client, Models, Response
import research_workflow as workflow


class VariedModels(Models):
    def generate_content(self, **kwargs):
        response = super().generate_content(**kwargs)
        payload = json.loads(kwargs['contents'])
        if 'turn_start_observation' in payload and payload['turn_start_observation']['own_country'] == 'MIL':
            value = json.loads(response.text)
            value.update(response_id='REJECT', response_label='拒否する')
            return Response(json.dumps(value))
        return response


class WorkflowSafetyTests(unittest.TestCase):
    def test_zero_budget_and_failed_attempt_are_counted_before_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            client = Client()
            bounded = BoundedClient(client, 0, Path(d)/'zero.json')
            with self.assertRaises(RuntimeError): bounded.models.generate_content(contents='{}')
            self.assertEqual(client.models.payloads, [])
            broken = type('C', (), {'models': type('M', (), {'generate_content': lambda *a, **k: (_ for _ in ()).throw(ValueError('failed'))})()})()
            bounded = BoundedClient(broken, 1, Path(d)/'audit.json')
            with self.assertRaises(ValueError): bounded.models.generate_content(contents='{}')
            with self.assertRaises(RuntimeError): bounded.models.generate_content(contents='{}')
            self.assertEqual(json.loads((Path(d)/'audit.json').read_text())['api_calls'], 1)

    def test_probe_is_one_call_and_schema_failure_never_retries(self):
        with tempfile.TemporaryDirectory() as d:
            bounded = BoundedClient(Client(True), 1, Path(d)/'audit.json')
            with self.assertRaises(RuntimeError): workflow.probe(bounded)
            self.assertEqual(len(bounded.attempts), 1)

    def test_offline_mode_blocks_real_client_and_socket_even_with_key(self):
        with patch.dict(os.environ, {'HOMEOSTASIS_OFFLINE': '1', 'GEMINI_API_KEY': 'fake'}):
            with self.assertRaises(RuntimeError): create_gemini_client('fake')
        # Only attempt a connection if the guard is active; never contact a host.
        if os.environ.get('HOMEOSTASIS_OFFLINE') == '1':
            with socket.socket() as sock:
                with self.assertRaisesRegex(RuntimeError, 'network forbidden'):
                    sock.connect(('127.0.0.1', 9))

    def test_plans_and_unconfirmed_execution_never_construct_client(self):
        with patch('homeostasis_core.gemini_agents.create_gemini_client', side_effect=AssertionError('client')):
            for mode, maximum in [('probe', 1), ('turn', 10), ('experiment', 80)]:
                self.assertEqual(workflow.PLANS[mode]['maximum_api_calls'], maximum)
                workflow.main([mode])
                with self.assertRaises(SystemExit): workflow.main([mode, '--execute'])

    def test_failed_preflight_stops_before_client(self):
        with patch.dict(os.environ, {'HOMEOSTASIS_OFFLINE': '0', 'GEMINI_API_KEY': 'fake'}), \
             patch('research_workflow.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'check')), \
             patch('homeostasis_core.gemini_agents.create_gemini_client', side_effect=AssertionError('client')):
            with self.assertRaises(subprocess.CalledProcessError): workflow.main(['experiment', '--execute', '--confirm', 'YES'])

    def test_one_turn_runs_settlement_evaluator_and_ten_fake_calls(self):
        with tempfile.TemporaryDirectory() as d:
            client = Client()
            result = run_live(client, Path(d)/'result.json', 1, 7, turns=1, max_calls=10, retry_limit=1)
            self.assertEqual(len(client.models.payloads), 10)
            self.assertIn('reconstruction', result['runs'][0]['turns'][0]['executed_state'])
            for payload in client.models.payloads:
                if 'turn_start_observation' in payload:
                    self.assertNotIn('action', payload['response_contract']['required'])
                    self.assertIn('choice_id', payload['response_contract']['required'])
                    self.assertNotIn('feasible_actions', payload)

    def test_default_full_budget_cannot_be_replenished_by_resume(self):
        from tests.final.test_phase9_gemini_final import InterruptingClient
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)/'result.json'
            with self.assertRaises(KeyboardInterrupt): run_live(InterruptingClient(20), output, 1, 7)
            client = Client()
            with self.assertRaisesRegex(RuntimeError, 'API call limit'): run_live(client, output, 1, 7, True)
            self.assertEqual(len(client.models.payloads), 59)
            self.assertFalse(output.exists())

    def test_research_gate_accepts_complete_evidence_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); output = root/'result.json'
            fake = type('C', (), {'models': VariedModels()})()
            bounded = BoundedClient(fake, 80, root/'transport.audit.json')
            run_live(bounded, output, 1, 7, max_calls=80, retry_limit=1)
            result = json.loads(output.read_text()); audit = json.loads((root/'transport.audit.json').read_text())
            self.assertEqual(validate_research(result, audit), [])
            output.with_suffix('.audit.json').write_text(json.dumps(research_manifest(output, [])))
            self.assertEqual(accepted_research_paths(root), (output,))
            for mutate in (
                lambda r: r['runs'][0]['details']['turns'].pop(),
                lambda r: r['runs'][0]['details']['call_audit'].pop(),
                lambda r: r['runs'][0]['details']['turns'][2]['snapshot'].update(event='scripted'),
                lambda r: r['runs'][0]['details']['turns'][3]['executed_state']['reconstruction'].update(after=0),
                lambda r: r['runs'][0]['details']['turns'][0].pop('evaluator_commentary'),
            ):
                changed = copy.deepcopy(result); mutate(changed)
                self.assertTrue(validate_research(changed, audit))
            output.write_text('{}')
            self.assertEqual(accepted_research_paths(root), ())

    def test_preflight_uses_emergent_reconstruction_without_legacy_simulator(self):
        from preflight_emergent import run_preflight
        with patch('simulation_final.run_final_simulation', side_effect=AssertionError('legacy scripted recovery')):
            result = run_preflight()
        self.assertEqual(result['status'], 'PASS')
        for previous, row in zip(result['rows'], result['rows'][1:]):
            self.assertEqual(previous['reconstruction']['after'], row['reconstruction']['before'])
            self.assertEqual(row['event_origin'], 'derived_from_previous_executed_state')
