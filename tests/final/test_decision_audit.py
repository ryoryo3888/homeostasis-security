import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from homeostasis_core.api_budget import BoundedClient
from homeostasis_core.decision_audit import AuditPersistenceError, validate_choice_trace
from homeostasis_core.gemini_agents import GeminiGateway
from homeostasis_core.action_choices import materialize_choice
from research_workflow import probe
from final_experiment_runner import _checkpoint


class SelectionModels:
    def __init__(self, invalid=False):
        self.calls = 0
        self.answer = None
        self.invalid = invalid

    def generate_content(self, **kwargs):
        self.calls += 1
        payload = json.loads(kwargs['contents'])
        chosen = next(c for c in payload['action_choices'] if c['action_id'] == 'SUPPORT_LOGISTICS')
        self.answer = {'choice_id': 'UNKNOWN' if self.invalid else chosen['choice_id'],
                       'amount': chosen['maximum_amount'], 'reason': 'Public action justification.'}
        return SimpleNamespace(text=json.dumps(self.answer), usage_metadata=None,
                               thoughts='DO NOT STORE INTERNAL REASONING')


class DecisionAuditTests(unittest.TestCase):
    def test_probe_selection_and_action_persist_in_one_linked_record(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); models = SelectionModels()
            client = BoundedClient(SimpleNamespace(models=models), 1, root/'transport.audit.json')
            def save(calls): _checkpoint(root/'decision.audit.json', {'calls': calls})
            result = probe(client, audit_hook=save)
            saved = json.loads((root/'decision.audit.json').read_text())['calls'][0]
            self.assertEqual(saved, result['call_audit'][0])
            self.assertEqual(saved['model_response'], models.answer)
            self.assertEqual(saved['choice_response'], models.answer)
            self.assertEqual(saved['materialized_action'], result['action'])
            self.assertTrue(validate_choice_trace(saved))
            transport = json.loads((root/'transport.audit.json').read_text())['attempts'][0]
            for key in ('run_id', 'run', 'turn', 'agent_id', 'attempt', 'call_id'):
                self.assertEqual(saved[key], transport[key])
            self.assertNotIn('DO NOT STORE INTERNAL REASONING', (root/'decision.audit.json').read_text())
            self.assertEqual(models.calls, 1)

    def test_invalid_choice_is_saved_without_inventing_an_action(self):
        models = SelectionModels(invalid=True); records = []
        with self.assertRaises(RuntimeError):
            probe(SimpleNamespace(models=models), audit_hook=lambda calls: records.append(copy.deepcopy(calls)))
        saved = records[-1][0]
        self.assertEqual(saved['model_response'], models.answer)
        self.assertEqual(saved['choice_response']['choice_id'], 'UNKNOWN')
        self.assertIsNone(saved['materialized_action'])
        self.assertEqual(saved['validation_status'], 'FAIL')
        self.assertEqual(saved['validation_error'], 'unknown action_choice_id')
        self.assertEqual(models.calls, 1)

    def test_audit_failure_before_dispatch_makes_zero_calls(self):
        models = SelectionModels()
        with self.assertRaises(AuditPersistenceError):
            probe(SimpleNamespace(models=models), audit_hook=lambda _: (_ for _ in ()).throw(OSError('disk full')))
        self.assertEqual(models.calls, 0)

    def test_audit_failure_after_response_does_not_retry(self):
        models = SelectionModels(); writes = []
        def save(calls):
            writes.append(1)
            if len(writes) == 2: raise OSError('disk full')
        gateway = GeminiGateway(SimpleNamespace(models=models), retry_limit=3, audit_hook=save)
        payload = {'action_choices': [{'choice_id': 'A001', 'action_id': 'SUPPORT_LOGISTICS',
                   'maximum_amount': 1, 'recipient_type': 'country', 'target_country': 'B', 'resource': 'logistics'}]}
        with self.assertRaises(AuditPersistenceError):
            gateway.call('A', 1, 1, payload, lambda text: {})
        self.assertEqual(models.calls, 1)

    def test_final_audit_write_failure_prevents_success_return(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'decision.audit.json'; models = SelectionModels(); writes = []
            def save(calls):
                writes.append(1)
                if len(writes) == 3: raise OSError('disk full')
                _checkpoint(path, {'calls': calls})
            with self.assertRaises(AuditPersistenceError):
                probe(SimpleNamespace(models=models), audit_hook=save)
            self.assertEqual(models.calls, 1)
            record = json.loads(path.read_text())['calls'][0]
            self.assertEqual(record['validation_status'], 'PENDING')
            with self.assertRaises(ValueError): validate_choice_trace(record)

    def test_transport_persistence_failure_never_retries(self):
        with tempfile.TemporaryDirectory() as d:
            models = SelectionModels()
            client = BoundedClient(SimpleNamespace(models=models), 1, Path(d)/'transport.json')
            with patch('final_experiment_runner._checkpoint', side_effect=OSError('disk full')):
                with self.assertRaises(AuditPersistenceError): probe(client)
            self.assertEqual(models.calls, 0)

    def test_trace_rejects_missing_original_or_altered_materialization(self):
        result = probe(SimpleNamespace(models=SelectionModels()))
        row = result['call_audit'][0]
        for mutate in (lambda r: r.pop('model_response'),
                       lambda r: r['choice_response'].update(choice_id='OTHER'),
                       lambda r: r['materialized_action']['parameters'].update(amount=99),
                       lambda r: r.update(validation_status='FAIL'),
                       lambda r: r.pop('run_id')):
            damaged = copy.deepcopy(row); mutate(damaged)
            with self.assertRaises((ValueError, KeyError)): validate_choice_trace(damaged)

    def test_secrets_and_thoughts_are_not_saved_and_protected_answer_stops(self):
        secret = 'synthetic-test-credential-never-real'
        records = []
        model = SimpleNamespace(generate_content=lambda **_: SimpleNamespace(
            text=json.dumps({'choice_id': 'A001', 'amount': 0, 'reason': secret}), usage_metadata=None))
        choices = [{'choice_id': 'A001', 'action_id': 'NO_ACTION', 'recipient_type': 'none',
                    'target_country': None, 'resource': None, 'maximum_amount': 0}]
        def parse(text):
            a = json.loads(text)
            return materialize_choice('A', a['choice_id'], a['amount'], a['reason'], choices, choices)
        with patch.dict(os.environ, {'GEMINI_API_KEY': secret}):
            gateway = GeminiGateway(SimpleNamespace(models=model), audit_hook=lambda calls: records.append(copy.deepcopy(calls)))
            with self.assertRaises(RuntimeError):
                gateway.call('A', 1, 1, {'action_choices': choices, 'api_key': secret,
                    'thoughts': 'private hidden reasoning', 'GEMINI_API_KEY': 'another-hidden-value'}, parse)
        serialized = json.dumps(records)
        self.assertNotIn(secret, serialized)
        self.assertNotIn('another-hidden-value', serialized)
        self.assertNotIn('private hidden reasoning', serialized)
        self.assertEqual(records[-1][0]['validation_status'], 'FAIL')

    def test_non_json_failure_does_not_archive_arbitrary_raw_text(self):
        records = []
        models = SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text='unstructured sensitive content', usage_metadata=None))
        gateway = GeminiGateway(SimpleNamespace(models=models), audit_hook=lambda calls: records.append(copy.deepcopy(calls)))
        with self.assertRaises(RuntimeError): gateway.call('A', 1, 1, {}, json.loads)
        self.assertNotIn('unstructured sensitive content', json.dumps(records))
        self.assertIsNone(records[-1][0]['model_response'])
