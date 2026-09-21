"""Offline safeguards for the approved eight-person generation batch.

All people and provider responses below are synthetic test fixtures. No API
credential is loaded, and every HTTP request is handled by MockTransport.
"""
import base64
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx
from jsonschema import ValidationError

from homeostasis_v4.evidence import EvidenceRun, read_record, verify
import homeostasis_v5.persona_generation as generation
from homeostasis_v5.persona_generation import (
    build_request, generate_next, prepare_batch, review_last, validate_persona,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / 'docs/design/v5/LEADER_GENERATION_SCHEMA.proposed.json').read_text())
FAKE_CREDENTIAL = 'offline-fixture-credential-not-a-real-key'


def fixture_persona(name='Synthetic fixture person'):
    """Satisfy shape only; this fixture is not a generated research person."""
    return {
        'layer1': {
            'person_profile': {
                'fictional_name': name,
                'age_years': 40,
                'life_history': ['Offline fixture history.'],
                'values_and_beliefs': ['Offline fixture belief.'],
                'relationship_style': 'Offline fixture style.',
                'tensions_and_vulnerabilities': [],
                'additional_personal_context': None,
            },
            'parameters': {key: 50 for key in SCHEMA['properties']['layer1']['properties']['parameters']['required']},
        },
        'layer2': {'text': 'これは通信しない単体検証専用の文章です。' * 12},
        'layer3': [{
            'perceived_condition': 'Offline perceived condition.',
            'what_matters': 'Offline concern.',
            'judgment_tendency': 'Offline tendency.',
            'deliberation_style': 'Offline deliberation.',
            'exceptions_and_tensions': None,
        }],
    }


def fixture_response(persona=None):
    return {
        'candidates': [{
            'content': {'role': 'model', 'parts': [{'text': json.dumps(persona or fixture_persona(), ensure_ascii=False)}]},
            'finishReason': 'STOP',
        }],
        'usageMetadata': {
            'promptTokenCount': 1000,
            'candidatesTokenCount': 1000,
            'thoughtsTokenCount': 50,
            'totalTokenCount': 2050,
        },
        'modelVersion': 'gemini-3.6-flash',
        'responseId': 'offline-response-id',
    }


def leaves(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from leaves(child)
    else:
        yield value


class PersonaGenerationTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_REAL_NETWORK'))
        network.start()
        self.addCleanup(network.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / 'batch'
        self.calls = []

    def transport(self, *, generation=None, status=200, count=1000, timeout=False):
        def handle(request):
            body = json.loads(request.content)
            self.calls.append((str(request.url), body))
            if request.url.path.endswith(':countTokens'):
                return httpx.Response(200, json={'totalTokens': count})
            self.assertTrue(request.url.path.endswith(':generateContent'))
            if timeout:
                raise httpx.ReadTimeout('offline fixture timeout', request=request)
            content = generation
            if content is None:
                content = json.dumps(fixture_response(), ensure_ascii=False).encode()
            return httpx.Response(status, content=content, headers={'content-type': 'application/json'})
        return httpx.MockTransport(handle)

    def run_one(self, transport):
        return generate_next(self.directory, transport=transport, credential=FAKE_CREDENTIAL)

    def attempt_failure(self, transport):
        # The API may report a recorded provider failure or raise it. In either
        # case, the persisted terminal is the authoritative success boundary.
        try:
            self.run_one(transport)
        except (ValueError, RuntimeError, httpx.HTTPError, ValidationError):
            pass

    def records(self):
        return sorted(self.directory.glob('*/terminal.json'))

    def assert_blocked(self, transport):
        before = len(self.calls)
        self.attempt_failure(transport)
        self.assertEqual(len(self.calls), before, 'A stopped batch must not issue another request.')

    def assert_raw_bytes_preserved(self, raw_bytes):
        values = []
        for path in self.directory.glob('*/RAW/*.json'):
            values.extend(leaves(read_record(path)))
        self.assertIn(base64.b64encode(raw_bytes).decode('ascii'), values)
        self.assertIn(hashlib.sha256(raw_bytes).hexdigest(), values)

    def test_approved_input_exact_and_model_configuration_unchanged(self):
        request = build_request()
        text_parts = [part['text'] for content in request['contents'] for part in content['parts'] if 'text' in part]
        self.assertEqual(text_parts, [(ROOT / 'docs/design/v5/LEADER_GENERATION_PROMPT.txt').read_text()])
        config = request['generationConfig']
        self.assertEqual(config['temperature'], 1.0)
        self.assertEqual(config['candidateCount'], 1)
        self.assertEqual(config['maxOutputTokens'], 8192)
        self.assertEqual(config['thinkingConfig']['thinkingLevel'], 'LOW')
        self.assertEqual(config['responseJsonSchema'], SCHEMA)
        self.assertNotIn('seed', config)
        self.assertNotIn('topK', config)
        self.assertNotIn('topP', config)

    def test_prepare_is_write_once_and_contains_no_secret(self):
        prepare_batch(self.directory)
        before = {str(p.relative_to(self.directory)): p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        try:
            prepare_batch(self.directory)
        except (ValueError, RuntimeError, FileExistsError):
            pass
        after = {str(p.relative_to(self.directory)): p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertTrue((self.directory / 'plan.json').is_file())

    def test_sixteen_independent_axes_are_not_normalized_or_repaired(self):
        persona = fixture_persona()
        persona['layer1']['parameters'] = {key: 100 for key in persona['layer1']['parameters']}
        persona['layer2']['text'] = '私はあまり共感を語らない。'
        original = copy.deepcopy(persona)
        checked = validate_persona(persona)
        self.assertEqual(persona, original)
        self.assertEqual(sum(persona['layer1']['parameters'].values()), 1600)
        self.assertEqual(checked['intro_character_count'], len(persona['layer2']['text']))
        self.assertTrue(checked['warnings'], 'Length outside the guideline is noted, not rewritten or rejected.')

    def test_intro_length_excludes_line_breaks_and_keeps_original(self):
        persona = fixture_persona()
        persona['layer2']['text'] = '私' * 100 + '\n' + 'は' * 125
        before = copy.deepcopy(persona)
        checked = validate_persona(persona)
        self.assertEqual(checked['intro_character_count'], 225)
        self.assertEqual(persona, before)

    def test_invalid_shape_empty_text_or_axis_type_is_rejected(self):
        alterations = [
            lambda p: p['layer1']['parameters'].update(empathy=-1),
            lambda p: p['layer1']['parameters'].update(empathy=101),
            lambda p: p['layer1']['parameters'].update(empathy=True),
            lambda p: p['layer1']['parameters'].pop('empathy'),
            lambda p: p['layer1']['person_profile'].update(relationship_style=' \n\t'),
            lambda p: p['layer1']['person_profile'].update(life_history=['   ']),
            lambda p: p.update(layer3=[]),
            lambda p: p.update(extra_unapproved_field='not allowed'),
        ]
        for alter in alterations:
            with self.subTest(alter=alter):
                persona = fixture_persona()
                alter(persona)
                with self.assertRaises((ValueError, RuntimeError, ValidationError)):
                    validate_persona(persona)

    def test_success_requires_review_and_preserves_verifiable_evidence(self):
        prepare_batch(self.directory)
        transport = self.transport()
        self.run_one(transport)
        self.assertEqual(len(self.calls), 2)
        count_body, generated_body = self.calls[0][1], self.calls[1][1]
        counted_request = dict(count_body['generateContentRequest'])
        self.assertEqual(counted_request.pop('model'), 'models/gemini-3.6-flash')
        self.assertEqual(counted_request, generated_body)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(verify(self.records()[0].parent)['status'], 'success')
        self.assert_blocked(transport)
        review_last(self.directory, accepted=True, notes='Offline fixture review only.')
        self.run_one(transport)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.calls[1][1], self.calls[3][1], 'A prior person must never enter the next generation context.')
        for path in self.directory.rglob('*'):
            if path.is_file():
                self.assertNotIn(FAKE_CREDENTIAL.encode(), path.read_bytes())
        for terminal in self.records():
            self.assertEqual(verify(terminal.parent)['status'], 'success')

    def test_eight_person_limit_and_independent_equal_requests(self):
        prepare_batch(self.directory)
        transport = self.transport()
        for _ in range(8):
            self.run_one(transport)
            review_last(self.directory, accepted=True, notes='Offline fixture review only.')
        self.assertEqual(len(self.records()), 8)
        self.assertEqual(len(self.calls), 16)
        generation_bodies = [body for url, body in self.calls if url.endswith(':generateContent')]
        self.assertEqual(len(generation_bodies), 8)
        self.assertTrue(all(body == generation_bodies[0] for body in generation_bodies))
        reservations = [read_record(path) for path in self.directory.glob('reservation-*.json')]
        self.assertEqual(len(reservations), 8)
        total_reserved = sum((Decimal(item['usd']) for item in reservations), Decimal(0))
        self.assertEqual(total_reserved, Decimal('0.34176'))
        self.assertLessEqual(total_reserved, Decimal('0.40'))
        self.assert_blocked(transport)

    def test_rejected_content_review_does_not_generate_replacement(self):
        prepare_batch(self.directory)
        transport = self.transport()
        self.run_one(transport)
        review_last(self.directory, accepted=False, notes='Synthetic fixture has a forbidden assigned nation reference.')
        self.assert_blocked(transport)
        self.assertEqual(len(self.records()), 1)

    def test_count_limit_stops_before_generation_without_retry(self):
        prepare_batch(self.directory)
        transport = self.transport(count=16001)
        self.attempt_failure(transport)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(verify(self.records()[0].parent)['status'], 'failure')
        self.assert_blocked(transport)

    def test_invalid_provider_responses_are_retained_and_stop_batch(self):
        examples = []
        examples.append(('http', b'{"error":{"message":"offline fixture service error"}}', 503))
        examples.append(('not-json', b'raw offline fixture malformed response', 200))
        examples.append(('duplicate-envelope-key', b'{"candidates":[],"candidates":[]}', 200))
        for label in ('schema', 'usage', 'over-reservation', 'max-tokens', 'multicandidate', 'duplicate-persona-key'):
            response = fixture_response()
            if label == 'schema':
                response['candidates'][0]['content']['parts'][0]['text'] = '{"layer1":{}}'
            elif label == 'usage':
                response.pop('usageMetadata')
            elif label == 'over-reservation':
                response['usageMetadata']['candidatesTokenCount'] = 20000
                response['usageMetadata']['totalTokenCount'] = 21050
            elif label == 'max-tokens':
                response['candidates'][0]['finishReason'] = 'MAX_TOKENS'
            elif label == 'multicandidate':
                response['candidates'].append(copy.deepcopy(response['candidates'][0]))
            elif label == 'duplicate-persona-key':
                original = response['candidates'][0]['content']['parts'][0]['text']
                response['candidates'][0]['content']['parts'][0]['text'] = original[:-1] + ',"layer3":[]}'
            examples.append((label, json.dumps(response, ensure_ascii=False).encode(), 200))
        for label, raw_bytes, status in examples:
            with self.subTest(response=label):
                self.directory = Path(self.temporary.name) / label
                self.calls.clear()
                prepare_batch(self.directory)
                transport = self.transport(generation=raw_bytes, status=status)
                self.attempt_failure(transport)
                self.assertEqual(len(self.calls), 2)
                self.assertEqual(len(self.records()), 1)
                self.assertEqual(verify(self.records()[0].parent)['status'], 'failure')
                self.assert_raw_bytes_preserved(raw_bytes)
                reservations = list(self.directory.glob('reservation-*.json'))
                self.assertEqual(len(reservations), 1)
                self.assertEqual(Decimal(read_record(reservations[0])['usd']), Decimal('0.04272'))
                self.assert_blocked(transport)

    def test_timeout_is_failed_evidence_and_never_retried(self):
        prepare_batch(self.directory)
        transport = self.transport(timeout=True)
        self.attempt_failure(transport)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(verify(self.records()[0].parent)['status'], 'failure')
        reservations = list(self.directory.glob('reservation-*.json'))
        self.assertEqual(len(reservations), 1)
        self.assertEqual(Decimal(read_record(reservations[0])['usd']), Decimal('0.04272'))
        self.assert_blocked(transport)

    def test_source_change_during_response_preserves_raw_then_stops(self):
        prepare_batch(self.directory)
        original_hashes = generation.source_hashes()
        changed = False
        raw_bytes = json.dumps(fixture_response(), ensure_ascii=False).encode()

        def observed_hashes():
            if not changed:
                return original_hashes
            altered = dict(original_hashes)
            altered['homeostasis_v5/persona_generation.py'] = 'f' * 64
            return altered

        def handle(request):
            nonlocal changed
            self.calls.append((str(request.url), json.loads(request.content)))
            if request.url.path.endswith(':countTokens'):
                return httpx.Response(200, json={'totalTokens': 1000})
            changed = True
            return httpx.Response(200, content=raw_bytes)

        transport = httpx.MockTransport(handle)
        with patch.object(generation, 'source_hashes', side_effect=observed_hashes):
            self.attempt_failure(transport)
            self.assertEqual(len(self.calls), 2)
            self.assertEqual(len(self.records()), 1)
            self.assertEqual(verify(self.records()[0].parent)['status'], 'failure')
            self.assert_raw_bytes_preserved(raw_bytes)
            self.assert_blocked(transport)
        # Restoring the source does not authorize repeating the failed request.
        self.assert_blocked(transport)

    def test_request_persistence_failure_prevents_any_api_request(self):
        prepare_batch(self.directory)
        original_write = EvidenceRun.write

        def fail_count_request(run, name, payload):
            if name == 'count.request.json':
                raise OSError('offline fixture write failure')
            return original_write(run, name, payload)

        transport = self.transport()
        with patch.object(EvidenceRun, 'write', new=fail_count_request):
            self.attempt_failure(transport)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(verify(self.records()[0].parent)['status'], 'failure')
        self.assertEqual(list(self.directory.glob('reservation-*.json')), [])
        self.assert_blocked(transport)


if __name__ == '__main__':
    unittest.main()
