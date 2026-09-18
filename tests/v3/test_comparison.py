"""No real credentials or remote requests. Test paired evidence and cost stops."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import httpx

from homeostasis_v3.comparison import deterministic, run_arm, compare
from homeostasis_v3.comparison_transport import PilotExchange
from homeostasis_v3.contracts import canonical
from homeostasis_v3.live_probe import prepare
from homeostasis_v3.choices import TechnicalFailure

ROOT = Path(__file__).resolve().parents[2]


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT/'scenarios/v3', self.root/'scenarios/v3')
        shutil.copytree(ROOT/'homeostasis_v3', self.root/'homeostasis_v3', ignore=shutil.ignore_patterns('__pycache__'))
        self.raw = canonical(prepare(self.root)['request'])
        self.calls = []

    def exchange(self, *, tokens=100, fail=False, unknown_usage=False):
        def handler(wire):
            self.calls.append(wire)
            self.assertEqual(wire.url.host, 'generativelanguage.googleapis.com')
            if wire.url.path.endswith(':countTokens'):
                body = json.loads(wire.content)['generateContentRequest']
                self.assertIn('systemInstruction', body)
                self.assertIn('responseJsonSchema', body['generationConfig'])
                return httpx.Response(200, json={'totalTokens': tokens})
            if fail: return httpx.Response(503, json={'error': 'fixture'})
            body = json.loads(wire.content)
            answer = deterministic(body['contents'][0]['parts'][0]['text'])
            result = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': answer}]}}]}
            if not unknown_usage: result['usageMetadata'] = {'promptTokenCount': 100, 'candidatesTokenCount': 40}
            return httpx.Response(200, json=result)
        exchange = PilotExchange(self.root, 'test-dummy', transport=httpx.MockTransport(handler))
        exchange.seed = 17; self.addCleanup(exchange.close)
        return exchange

    def test_exact_count_then_generation_and_duplicate_stop(self):
        x = self.exchange(); x(self.raw)
        self.assertEqual(len(self.calls), 2)
        with self.assertRaises(TechnicalFailure): x(self.raw)
        self.assertEqual(len(self.calls), 2)

    def test_input_budget_blocks_generation(self):
        x = self.exchange(tokens=48001)
        with self.assertRaises(TechnicalFailure): x(self.raw)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(x.journal.records()[0]['usage']['generation_attempted'])

    def test_server_failure_no_retry_or_restart(self):
        x = self.exchange(fail=True)
        with self.assertRaises(TechnicalFailure): x(self.raw)
        with self.assertRaises(TechnicalFailure): x(self.raw)
        self.assertEqual(len(self.calls), 2)

    def test_unknown_usage_stops(self):
        x = self.exchange(unknown_usage=True)
        with self.assertRaises(TechnicalFailure): x(self.raw)
        self.assertEqual(x.journal.records()[0]['status'], 'failed')

    def test_paired_three_turn_evidence_and_replay(self):
        control = run_arm(self.root, self.root/'control', seed=17, arm='deterministic', exchange=deterministic)
        x = self.exchange()
        mock = run_arm(self.root, self.root/'mock', seed=17, arm='mock', exchange=x)
        self.assertEqual(mock['completed_turns'], 3)
        self.assertEqual(control['initial_world_digest'], mock['initial_world_digest'])
        for a,b in zip(control['rows'], mock['rows']): self.assertEqual(a['transactions'],b['transactions'])
        with self.assertRaises(TechnicalFailure): compare(control, mock)
        self.assertFalse(mock['research_eligible'])
        self.assertEqual(len(list((self.root/'mock').glob('exchanges-*.json'))), 3)
