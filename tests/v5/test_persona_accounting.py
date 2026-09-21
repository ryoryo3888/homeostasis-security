"""Offline accounting regression tests; fixtures never call a real provider."""
import base64
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_persona_generation import FAKE_CREDENTIAL, fixture_response, leaves

from homeostasis_v4.evidence import read_record, verify
import homeostasis_v5.persona_generation as generation
from homeostasis_v5.persona_generation import account_usage, generate_next, prepare_batch, review_last
from v2_autonomous import Journal


OBSERVED_USAGE_SHAPE = {
    'promptTokenCount': 704,
    'candidatesTokenCount': 1108,
    'totalTokenCount': 1812,
}


class PersonaAccountingTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_REAL_NETWORK'))
        network.start()
        self.addCleanup(network.stop)

    def test_absent_thought_count_uses_reported_total_and_is_not_fabricated(self):
        usage = dict(OBSERVED_USAGE_SHAPE)
        before = copy.deepcopy(usage)
        result = account_usage(usage)
        self.assertEqual(result['input_tokens'], 704)
        self.assertEqual(result['generated_tokens_including_thoughts'], 1108)
        self.assertIsNone(result['thoughts_token_count'])
        self.assertEqual(result['basis'], 'reported_total_minus_prompt')
        self.assertEqual(Decimal(str(result['estimated_cost_usd'])), Decimal('0.004683'))
        self.assertEqual(usage, before)
        self.assertNotIn('thoughtsTokenCount', usage)

    def test_unitemized_generated_tokens_are_billed_without_inventing_thought_count(self):
        usage = dict(OBSERVED_USAGE_SHAPE, totalTokenCount=2000)
        result = account_usage(usage)
        self.assertEqual(result['generated_tokens_including_thoughts'], 1296)
        self.assertIsNone(result['thoughts_token_count'])
        self.assertEqual(Decimal(str(result['estimated_cost_usd'])), Decimal('0.005388'))

    def test_explicit_thought_count_must_reconcile_with_reported_total(self):
        usage = fixture_response()['usageMetadata']
        result = account_usage(usage)
        self.assertEqual(result['input_tokens'], 1000)
        self.assertEqual(result['generated_tokens_including_thoughts'], 1050)
        self.assertEqual(result['thoughts_token_count'], 50)
        self.assertEqual(Decimal(str(result['estimated_cost_usd'])), Decimal('0.0046875'))
        self.assertEqual(account_usage(dict(OBSERVED_USAGE_SHAPE, thoughtsTokenCount=0))['thoughts_token_count'], 0)

    def test_missing_invalid_or_inconsistent_counts_remain_errors(self):
        invalid = []
        for key in OBSERVED_USAGE_SHAPE:
            missing = dict(OBSERVED_USAGE_SHAPE)
            missing.pop(key)
            invalid.append((f'missing-{key}', missing))
            for bad in (-1, True, 1.0, '1', None):
                invalid.append((f'{key}-{bad!r}', dict(OBSERVED_USAGE_SHAPE, **{key: bad})))
        invalid.extend([
            ('total-smaller-than-components', dict(OBSERVED_USAGE_SHAPE, totalTokenCount=1811)),
            ('explicit-thoughts-inconsistent', dict(OBSERVED_USAGE_SHAPE, thoughtsTokenCount=1)),
            ('tools-unapproved', dict(OBSERVED_USAGE_SHAPE, toolUsePromptTokenCount=1)),
            ('priority-unapproved', dict(OBSERVED_USAGE_SHAPE, serviceTier='PRIORITY')),
        ])
        for bad in (-1, True, 1.0, '1', None):
            invalid.append((f'invalid-thoughts-{bad!r}', dict(OBSERVED_USAGE_SHAPE, thoughtsTokenCount=bad)))
        for label, usage in invalid:
            with self.subTest(label=label):
                before = copy.deepcopy(usage)
                with self.assertRaises((ValueError, RuntimeError)):
                    account_usage(usage)
                self.assertEqual(usage, before)

    def _offline_generation(self, directory, usage):
        prepare_batch(directory)
        response = fixture_response()
        response['usageMetadata'] = usage
        raw_bytes = json.dumps(response, ensure_ascii=False).encode()
        calls = []

        def handle(request):
            calls.append(str(request.url))
            if request.url.path.endswith(':countTokens'):
                return httpx.Response(200, json={'totalTokens': 704})
            return httpx.Response(200, content=raw_bytes)

        transport = httpx.MockTransport(handle)
        result = generate_next(directory, transport=transport, credential=FAKE_CREDENTIAL)
        return result, calls, raw_bytes, transport

    def test_http_response_without_optional_thought_count_succeeds_and_keeps_raw(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'batch'
            result, calls, raw_bytes, _ = self._offline_generation(directory, dict(OBSERVED_USAGE_SHAPE))
            self.assertEqual(result['status'], 'success')
            self.assertEqual(Decimal(str(result['estimated_cost_usd'])), Decimal('0.004683'))
            self.assertEqual(len(calls), 2)
            run = directory / 'generation-01'
            self.assertEqual(verify(run)['status'], 'success')
            raw = read_record(run / 'RAW/generation.response.json')
            self.assertIn(base64.b64encode(raw_bytes).decode(), list(leaves(raw)))
            self.assertIn(hashlib.sha256(raw_bytes).hexdigest(), list(leaves(raw)))
            original = json.loads(raw_bytes)
            self.assertNotIn('thoughtsTokenCount', original['usageMetadata'])

    def test_http_bad_total_preserves_raw_and_stops_followup(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'batch'
            usage = dict(OBSERVED_USAGE_SHAPE, totalTokenCount=1811)
            result, calls, raw_bytes, transport = self._offline_generation(directory, usage)
            self.assertEqual(result['status'], 'failure')
            self.assertEqual(len(calls), 2)
            run = directory / 'generation-01'
            self.assertEqual(verify(run)['status'], 'failure')
            raw = read_record(run / 'RAW/generation.response.json')
            self.assertIn(base64.b64encode(raw_bytes).decode(), list(leaves(raw)))
            with self.assertRaises((ValueError, RuntimeError)):
                generate_next(directory, transport=transport, credential=FAKE_CREDENTIAL)
            self.assertEqual(len(calls), 2)

    def _original_omission_failure(self, parent, *, code='USAGE_UNKNOWN', review_accepted=True):
        with patch.object(generation, 'account_usage', side_effect=generation.GenerationError(code)):
            result, calls, raw_bytes, transport = self._offline_generation(parent, dict(OBSERVED_USAGE_SHAPE))
        self.assertEqual(result['status'], 'failure')
        if review_accepted is not None:
            source = verify(parent / 'generation-01')
            Journal(parent / 'generation-01/DERIVED').write('recovery-content-review.json', {
                'raw_evidence_hash': source['raw_evidence_hash'],
                'report': {'accepted': review_accepted, 'evidence_hash': source['evidence_hash'],
                           'notes': 'Offline synthetic fixture content review only.'},
            })
        return result, calls, raw_bytes, transport

    def test_missing_or_rejected_original_content_review_blocks_continuation(self):
        for accepted in (None, False):
            with self.subTest(accepted=accepted), tempfile.TemporaryDirectory() as temporary:
                parent = Path(temporary) / 'original'
                child = Path(temporary) / 'continuation'
                _, calls, _, _ = self._original_omission_failure(parent, review_accepted=accepted)
                pin = verify(parent / 'generation-01')['evidence_hash']
                with self.assertRaises((ValueError, RuntimeError)):
                    prepare_batch(child, continuation_from=parent, expected_parent_evidence_hash=pin)
                self.assertEqual(len(calls), 2)
                self.assertFalse(child.exists())
                self.assertFalse((parent / 'continuation-claim.json').exists())

    def test_continuation_preserves_original_and_generates_only_remaining_seven(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / 'original'
            child = Path(temporary) / 'continuation'
            _, calls, _, transport = self._original_omission_failure(parent)
            original_run = parent / 'generation-01'
            pin = verify(original_run)['evidence_hash']
            original_bytes = {str(p.relative_to(original_run)): p.read_bytes()
                              for p in original_run.rglob('*') if p.is_file()}
            prepared = prepare_batch(child, continuation_from=parent, expected_parent_evidence_hash=pin)
            self.assertEqual(prepared['additional_generations'], 7)
            self.assertEqual(len(calls), 2, 'Offline recovery must not regenerate person one.')
            recovered = read_record(child / 'recovered-leader-01.json')
            self.assertEqual(recovered['persona'], json.loads(fixture_response()['candidates'][0]['content']['parts'][0]['text']))
            self.assertEqual(recovered['parent_evidence_hash'], pin)
            self.assertEqual(recovered['parent_terminal_status'], 'failure')
            self.assertEqual(recovered['regeneration_calls'], 0)
            self.assertEqual(Decimal(str(recovered['accounting']['estimated_cost_usd'])), Decimal('0.004683'))
            self.assertFalse((child / 'generation-01').exists())

            for index in range(2, 9):
                result = generate_next(child, transport=transport, credential=FAKE_CREDENTIAL)
                self.assertEqual(result['status'], 'success')
                before_review_calls = len(calls)
                with self.assertRaises((ValueError, RuntimeError)):
                    generate_next(child, transport=transport, credential=FAKE_CREDENTIAL)
                self.assertEqual(len(calls), before_review_calls)
                reviewed = review_last(child, accepted=True, notes='Offline fixture review only.')
                self.assertEqual(reviewed['completed_personas'], index)
                self.assertEqual(reviewed['batch_complete'], index == 8)

            self.assertEqual(len(calls), 16, 'One prior request pair plus seven new pairs only.')
            self.assertEqual({p.parent.name for p in child.glob('*/terminal.json')},
                             {f'generation-{i:02d}' for i in range(2, 9)})
            with self.assertRaises((ValueError, RuntimeError)):
                generate_next(child, transport=transport, credential=FAKE_CREDENTIAL)
            self.assertEqual(len(calls), 16)
            total_reserved = Decimal(read_record(parent / 'reservation-01.json')['usd'])
            total_reserved += sum((Decimal(read_record(p)['usd']) for p in child.glob('reservation-*.json')), Decimal(0))
            self.assertEqual(total_reserved, Decimal('0.34176'))
            self.assertLessEqual(total_reserved, Decimal('0.40'))
            self.assertEqual({str(p.relative_to(original_run)): p.read_bytes()
                              for p in original_run.rglob('*') if p.is_file()}, original_bytes)
            self.assertEqual(verify(original_run, expected_evidence_hash=pin)['status'], 'failure')
            with self.assertRaises((ValueError, RuntimeError)):
                prepare_batch(Path(temporary) / 'second-child', continuation_from=parent,
                              expected_parent_evidence_hash=pin)
            self.assertFalse((Path(temporary) / 'second-child').exists())

    def test_continuation_rejects_wrong_pin_changed_input_and_other_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / 'original'
            _, calls, _, _ = self._original_omission_failure(parent)
            pin = verify(parent / 'generation-01')['evidence_hash']
            with self.assertRaises((ValueError, RuntimeError)):
                prepare_batch(Path(temporary) / 'bad-pin', continuation_from=parent,
                              expected_parent_evidence_hash='0' * 64)
            changed = generation.build_request()
            changed['generationConfig']['temperature'] = 0.25
            with patch.object(generation, 'build_request', return_value=changed):
                with self.assertRaises((ValueError, RuntimeError)):
                    prepare_batch(Path(temporary) / 'bad-input', continuation_from=parent,
                                  expected_parent_evidence_hash=pin)
            self.assertEqual(len(calls), 2)
            self.assertFalse((parent / 'continuation-claim.json').exists())

            other = Path(temporary) / 'different-failure'
            _, other_calls, _, _ = self._original_omission_failure(other, code='USAGE_INCONSISTENT')
            other_pin = verify(other / 'generation-01')['evidence_hash']
            with self.assertRaises((ValueError, RuntimeError)):
                prepare_batch(Path(temporary) / 'bad-failure', continuation_from=other,
                              expected_parent_evidence_hash=other_pin)
            self.assertEqual(len(other_calls), 2)
            self.assertFalse((other / 'continuation-claim.json').exists())


if __name__ == '__main__':
    unittest.main()
