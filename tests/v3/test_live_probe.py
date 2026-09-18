"""Live entry exercised with the real SDK and an in-memory HTTP transport only."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import httpx

from homeostasis_v3.live_probe import prepare, execute, validate_answer
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical

ROOT = Path(__file__).resolve().parents[2]


class LiveProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT/'scenarios/v3', self.root/'scenarios/v3')
        shutil.copytree(ROOT/'homeostasis_v3', self.root/'homeostasis_v3', ignore=shutil.ignore_patterns('__pycache__'))
        self.protocol = prepare(self.root)
        self.calls = []

    def handler(self, request):
        self.calls.append(request)
        req = json.loads(json.loads(request.content)['contents'][0]['parts'][0]['text'])
        answer = {'state_id': req['state_id'], 'request_digest': req['request_digest'],
                  'initiatives': [], 'extension_requests': []}
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP',
            'content': {'role': 'model', 'parts': [{'text': canonical(answer)}]}}],
            'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 20,
                              'thoughtsTokenCount': 0, 'totalTokenCount': 120}})

    def run_probe(self, handler=None, protocol=None, approval=None):
        with patch('httpx.HTTPTransport', return_value=httpx.MockTransport(handler or self.handler)):
            return execute(self.root, protocol or self.protocol,
                           approval or self.protocol['protocol_digest'], 'test-dummy')

    def test_prepare_deterministic_no_credential(self):
        self.assertEqual(self.protocol, prepare(self.root))
        self.assertFalse((self.root/'.artifacts').exists())
        self.assertFalse(self.protocol['research_eligible'])

    def test_one_call_real_sdk_and_restart_blocked(self):
        result = self.run_probe()
        self.assertEqual(result['turns_adopted'], 0)
        self.assertEqual(result['estimated_usd'], '0.000018')
        body = json.loads(self.calls[0].content)
        # SDK 2.20.0 preserves the protobuf snake_case key here.
        self.assertEqual(body['generationConfig']['thinkingConfig']['thinking_budget'], 0)
        self.assertEqual(body['generationConfig']['maxOutputTokens'], 4096)
        self.assertNotIn('tools', body)
        with self.assertRaises(TechnicalFailure): self.run_probe()
        self.assertEqual(len(self.calls), 1)

    def test_changed_protocol_and_wrong_approval_no_dispatch(self):
        altered = deepcopy(self.protocol); altered['max_calls'] = 2
        with self.assertRaises(TechnicalFailure): self.run_probe(protocol=altered)
        with self.assertRaises(TechnicalFailure): self.run_probe(approval='wrong')
        self.assertFalse(self.calls)

    def test_server_error_no_retry_and_restart_blocked(self):
        def failed(req):
            self.calls.append(req)
            return httpx.Response(503, json={'error': {'message': 'fixture'}})
        with self.assertRaises(TechnicalFailure): self.run_probe(handler=failed)
        with self.assertRaises(TechnicalFailure): self.run_probe()
        self.assertEqual(len(self.calls), 1)

    def test_timeout_consumes_attempt(self):
        def failed(req):
            self.calls.append(req)
            raise httpx.ReadTimeout('fixture')
        with self.assertRaises(TechnicalFailure): self.run_probe(handler=failed)
        with self.assertRaises(TechnicalFailure): self.run_probe()
        self.assertEqual(len(self.calls), 1)

    def test_redirect_not_followed(self):
        def redirect(req):
            self.calls.append(req)
            return httpx.Response(307, headers={'Location': 'https://example.invalid/'})
        with self.assertRaises(TechnicalFailure): self.run_probe(handler=redirect)
        self.assertEqual(len(self.calls), 1)

    def test_invalid_answer_consumes_attempt(self):
        def invalid(req):
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP',
                'content': {'parts': [{'text': '{}'}]}}]})
        with self.assertRaises(TechnicalFailure): self.run_probe(handler=invalid)
        with self.assertRaises(TechnicalFailure): self.run_probe()
        self.assertFalse(self.calls)

    def test_cannot_propose_for_another_country(self):
        request = self.protocol['request']
        foreign = next(t for t in request['payload']['opportunities'] if t['actor_state_id'] != 'MIL')
        answer = {'state_id': 'MIL', 'request_digest': request['request_digest'],
                  'extension_requests': [], 'initiatives': [{'opportunity_id': foreign['choice_id'],
                  'requested_amount': 1, 'minimum_amount': 1, 'allow_partial': True,
                  'conditions': [], 'public_reason': 'fixture'}]}
        with self.assertRaises(TechnicalFailure): validate_answer(answer, request)
