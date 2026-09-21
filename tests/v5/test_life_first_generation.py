"""Offline transport/evidence tests. Fixtures never become research personas."""
import base64
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx

from homeostasis_v4.evidence import read_record, verify
from homeostasis_v5.life_first_contract import AXES, PHASES
from homeostasis_v5.life_first_generation import prepare_batch, generate_next, review_last, wire_bytes


def synthetic_outputs():
    return {
        'life': {'life_periods': [{'narrative': 'Offline synthetic life, not research evidence.', 'elapsed_years': 37.5}],
                 'name': 'Offline Person', 'gender_description': 'Unspecified offline fixture.'},
        'person': {'present_person': 'Offline synthetic present person.', 'age_years': 37,
                   'values_and_beliefs': 'Offline values.', 'view_of_state_and_others': 'Offline view.',
                   'tensions_and_vulnerabilities': 'Offline tensions.', 'conditional_principles': []},
        'assessment': {'assessments': {axis: {'value': None, 'status': 'insufficient_evidence',
                                           'supporting_refs': [], 'counterevidence_refs': [],
                                           'rationale': 'Insufficient synthetic fixture evidence.'} for axis in AXES}},
        'presentation': {'self_introduction': '架空の単体検証用自己紹介です。' * 16},
    }


class LifeFirstGenerationTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_REAL_NETWORK'))
        p.start(); self.addCleanup(p.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'batch'
        self.calls = []
        self.outputs = synthetic_outputs()

    def prepare(self, budget='1.30'):
        return prepare_batch(self.directory, budget_usd=budget)

    def transport(self, *, count=500, failure=None, bad_phase=None):
        def handler(request):
            body = json.loads(request.content)
            self.calls.append((request.url.path, body, request.content))
            if request.url.path.endswith(':countTokens'):
                return httpx.Response(200, json={'totalTokens': count})
            if failure == 'timeout':
                raise httpx.ReadTimeout('Offline timeout with private text omitted', request=request)
            if failure == 'http':
                return httpx.Response(400, content=b'{"error":"offline schema rejection"}')
            schema = body['generationConfig']['responseJsonSchema']['properties']
            phase = ('life' if 'life_periods' in schema else 'person' if 'present_person' in schema
                     else 'assessment' if 'assessments' in schema else 'presentation')
            output = deepcopy(self.outputs[phase])
            if phase == bad_phase:
                output['age_years'] = 38
            response = {
                'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(output, ensure_ascii=False)}]}}],
                'usageMetadata': {'promptTokenCount': 500, 'candidatesTokenCount': 100, 'totalTokenCount': 650},
                'modelVersion': 'offline-model-version', 'responseId': 'offline-response-id',
            }
            return httpx.Response(200, content=wire_bytes(response))
        return httpx.MockTransport(handler)

    def next(self, **kwargs):
        return generate_next(self.directory, transport=self.transport(**kwargs), credential='offline-test-key')

    def assert_no_more_calls(self):
        n = len(self.calls)
        with self.assertRaises((ValueError, RuntimeError, FileNotFoundError)):
            self.next()
        self.assertEqual(len(self.calls), n)

    def test_budget_prepare_and_write_once_no_network(self):
        with self.assertRaises(ValueError):
            self.prepare('0.01')
        self.assertFalse(self.directory.exists())
        prepared = self.prepare()
        self.assertEqual(prepared['generation_calls'], 48)
        self.assertEqual(Decimal(prepared['maximum_reserved_usd']), Decimal('1.29024'))
        saved = (self.directory / 'plan.json').read_bytes()
        with self.assertRaises((ValueError, FileExistsError)):
            self.prepare()
        self.assertEqual(saved, (self.directory / 'plan.json').read_bytes())
        self.assertEqual(self.calls, [])

    def test_review_required_and_exact_ordered_wire_is_retained(self):
        self.prepare()
        result = self.next()
        self.assertEqual(result['status'], 'success')
        self.assert_no_more_calls()
        wire = read_record(self.directory / 'phase-01/RAW/generation.wire.json')
        self.assertEqual(base64.b64decode(wire['body_base64']), self.calls[1][2])
        schema = self.calls[1][1]['generationConfig']['responseJsonSchema']['properties']
        self.assertEqual(list(schema), ['life_periods', 'name', 'gender_description'])
        review_last(self.directory, accepted=True)
        self.assertEqual(self.next()['phase'], 'person')
        for path in self.directory.rglob('*.json'):
            self.assertNotIn('offline-test-key', path.read_text())

    def test_provider_failure_is_saved_and_no_retry(self):
        for failure in ['http', 'timeout']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as d:
                self.directory = Path(d) / 'batch'
                self.prepare()
                result = self.next(failure=failure)
                self.assertEqual(result['status'], 'failure')
                self.assertEqual(verify(self.directory / 'phase-01')['status'], 'failure')
                self.assertTrue((self.directory / 'reservation-01.json').exists())
                self.assert_no_more_calls()

    def test_overlarge_input_sends_no_generation(self):
        self.prepare()
        result = self.next(count=8001)
        self.assertEqual(result['status'], 'failure')
        self.assertEqual(len(self.calls), 1)
        self.assertFalse((self.directory / 'reservation-01.json').exists())
        self.assert_no_more_calls()

    def test_age_mismatch_keeps_raw_and_stops_before_measurement(self):
        self.prepare()
        self.next(); review_last(self.directory, accepted=True)
        result = self.next(bad_phase='person')
        self.assertEqual(result['status'], 'failure')
        self.assertEqual(result['error']['code'], 'LIFE_AGE_MISMATCH')
        raw = read_record(self.directory / 'phase-02/RAW/generation.response.json')
        self.assertIn(b'38', base64.b64decode(raw['body_base64']))
        self.assert_no_more_calls()

    def test_rejected_boundary_review_stops_without_replacement(self):
        self.prepare(); self.next()
        review_last(self.directory, accepted=False)
        self.assert_no_more_calls()
        self.assertEqual(len(list(self.directory.glob('phase-*'))), 1)

    def test_twelve_personas_separate_contexts_and_no_49th_request(self):
        self.prepare()
        first_requests = []
        for index in range(48):
            result = self.next()
            self.assertEqual(result['status'], 'success', result)
            self.assertEqual(result['phase'], PHASES[index % 4])
            if index % 4 == 0:
                first_requests.append(self.calls[-1][2])
            review = review_last(self.directory, accepted=True)
            self.assertEqual(review['batch_complete'], index == 47)
        self.assertEqual(len(self.calls), 96)
        self.assertEqual(len(set(first_requests)), 1, 'Same unconditioned first-stage input, separate requests.')
        self.assertEqual(len(list(self.directory.glob('leader-*.freeze.json'))), 12)
        self.assert_no_more_calls()
        total = sum(Decimal(read_record(p)['usd']) for p in self.directory.glob('reservation-*.json'))
        self.assertEqual(total, Decimal('1.29024'))


if __name__ == '__main__':
    unittest.main()
