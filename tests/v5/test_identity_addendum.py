"""Offline tests for post-hoc fictional identity addenda.

All source people and provider responses are synthetic fixtures. Socket access
is disabled and no credential file or existing research RAW is read.
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

from homeostasis_v3.contracts import canonical, digest
from homeostasis_v4.evidence import read_record, verify
import homeostasis_v5.identity_addendum as addendum


FAKE_CREDENTIAL = 'offline-addendum-fixture-never-a-real-credential'


def fixture_sources():
    people = []
    for index in range(1, 9):
        persona = {
            'layer1': {
                'person_profile': {
                    'fictional_name': '同名の架空試験人物',
                    'age_years': 52,
                    'life_history': [f'Only-source-person-{index:02d}-marker'],
                    'values_and_beliefs': ['試験用の価値観'],
                    'relationship_style': '試験用の対人傾向',
                    'tensions_and_vulnerabilities': [],
                    'additional_personal_context': None,
                },
                'parameters': {axis: 40 + index for axis in addendum.original.AXES},
            },
            'layer2': {'text': f'これは人物{index}の試験用自己紹介です。'},
            'layer3': [{
                'perceived_condition': '不確実な場合',
                'what_matters': '情報',
                'judgment_tendency': '判断を保留する',
                'deliberation_style': '検討する',
                'exceptions_and_tensions': None,
            }],
        }
        people.append({
            'leader_id': f'leader-{index:02d}', 'persona': persona,
            'persona_sha256': digest(persona), 'evidence_hash': digest({'source': index}),
            'original_generation_id': f'offline-original-generation-{index:02d}',
            'source_relative_directory': f'generation-{index:02d}',
            'response_body_sha256': digest({'original_response': index}),
        })
    return {'source_plan_sha256': digest({'source_plan': 'offline'}), 'people': people}


def response_bytes(identity=None):
    identity = identity if identity is not None else {
        'gender_identity': '特定の分類は用いず、今は明かさない。',
        'sexual_orientation': '複数の表現が重なる。今は決めない。',
    }
    return json.dumps({
        'candidates': [{
            'content': {'role': 'model', 'parts': [{'text': json.dumps(identity, ensure_ascii=False)}]},
            'finishReason': 'STOP',
        }],
        'usageMetadata': {
            'promptTokenCount': 1000, 'candidatesTokenCount': 120, 'totalTokenCount': 1120,
            'serviceTier': 'standard',
        },
        'modelVersion': 'gemini-3.6-flash', 'responseId': 'offline-addendum-response',
    }, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'


class IdentityAddendumTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_REAL_NETWORK'))
        network.start()
        self.addCleanup(network.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / 'original-personas'
        self.source.mkdir(mode=0o700)
        (self.source / 'immutable-fixture.txt').write_text('Original fictional source remains unchanged.')
        self.directory = root / 'addenda'
        self.sources = fixture_sources()
        self.sources_before = copy.deepcopy(self.sources)
        loader = patch.object(addendum, 'load_sources', side_effect=lambda path: copy.deepcopy(self.sources))
        loader.start()
        self.addCleanup(loader.stop)
        self.calls = []

    def prepare(self):
        return addendum.prepare(self.directory, self.source)

    def transport(self, *, raw=None, status=200, timeout=False, count=1000):
        def handle(request):
            self.calls.append((str(request.url), json.loads(request.content)))
            if request.url.path.endswith(':countTokens'):
                return httpx.Response(200, json={'totalTokens': count})
            self.assertTrue(request.url.path.endswith(':generateContent'))
            if timeout:
                raise httpx.ReadTimeout('Offline fixture timeout', request=request)
            return httpx.Response(status, content=response_bytes() if raw is None else raw)
        return httpx.MockTransport(handle)

    def run_one(self, transport):
        return addendum.generate_next(self.directory, transport=transport, credential=FAKE_CREDENTIAL)

    def assert_blocked(self, transport):
        before = len(self.calls)
        with self.assertRaises((ValueError, RuntimeError)):
            self.run_one(transport)
        self.assertEqual(len(self.calls), before, 'A stopped batch must issue no further requests.')

    def test_each_request_contains_only_its_own_person_despite_duplicate_names(self):
        self.prepare()
        plan = read_record(self.directory / 'plan.json')
        for index, request in enumerate(plan['requests'], 1):
            with self.subTest(person=index):
                parts = request['contents'][0]['parts']
                self.assertEqual(len(parts), 2)
                self.assertEqual(parts[1]['text'].split('\n', 1)[1], canonical(self.sources['people'][index - 1]['persona']))
                text = canonical(request)
                for other in range(1, 9):
                    marker = f'Only-source-person-{other:02d}-marker'
                    self.assertEqual(marker in text, other == index)
        self.assertEqual(len(set(plan['request_hashes'])), 8)
        self.assertEqual(self.sources, self.sources_before)

    def test_free_text_identities_and_non_disclosure_are_not_normalized(self):
        values = [
            {'gender_identity': '分類を使わない／定めない', 'sexual_orientation': 'ゲイでもあり、別の表現も自分で用いる。'},
            {'gender_identity': '明かさない', 'sexual_orientation': '明かさない'},
            {'gender_identity': '  自分だけの呼び方\n変化し得る  ', 'sexual_orientation': '未定・複数・流動的'},
        ]
        for value in values:
            with self.subTest(value=value):
                before = copy.deepcopy(value)
                addendum.validate_addendum(value)
                self.assertEqual(value, before)
        self.prepare()
        value = values[-1]
        self.assertEqual(self.run_one(self.transport(raw=response_bytes(value)))['status'], 'success')
        saved = read_record(self.directory / 'generation-01/DERIVED/addendum.json')['report']['identity']
        self.assertEqual(saved, value)

    def test_extra_persona_fields_empty_or_wrong_shape_are_rejected(self):
        invalid = [
            {'gender_identity': '任意', 'sexual_orientation': '任意', 'age_years': 30},
            {'gender_identity': '任意', 'sexual_orientation': '任意', 'layer1': {}},
            {'gender_identity': '任意'},
            {'gender_identity': ['任意'], 'sexual_orientation': '任意'},
            {'gender_identity': '  \n ', 'sexual_orientation': '任意'},
            {'gender_identity': '任意', 'sexual_orientation': 42},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                addendum.validate_addendum(value)

    def test_raw_bytes_parent_pin_original_and_review_gate_are_preserved(self):
        original_files = {p.name: p.read_bytes() for p in self.source.iterdir()}
        self.prepare()
        raw = response_bytes()
        transport = self.transport(raw=raw)
        result = self.run_one(transport)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(self.calls), 2)
        counted = dict(self.calls[0][1]['generateContentRequest'])
        self.assertEqual(counted.pop('model'), 'models/gemini-3.6-flash')
        self.assertEqual(counted, self.calls[1][1])
        run = self.directory / 'generation-01'
        wire = read_record(run / 'RAW/generation.response.json')
        self.assertEqual(base64.b64decode(wire['body_base64']), raw)
        self.assertEqual(wire['body_sha256'], hashlib.sha256(raw).hexdigest())
        pinned = verify(run, expected_evidence_hash=result['evidence_hash'])
        manifest = read_record(run / 'manifest.json')
        parent_pin = self.sources['people'][0]['evidence_hash']
        self.assertEqual(manifest['provenance']['parent_evidence_hash'], parent_pin)
        saved = read_record(run / 'DERIVED/addendum.json')
        self.assertEqual(saved['raw_evidence_hash'], pinned['raw_evidence_hash'])
        self.assertEqual(saved['report']['parent_evidence_hash'], parent_pin)
        self.assertEqual(saved['report']['original_persona_sha256'], self.sources['people'][0]['persona_sha256'])
        self.assertFalse(saved['report']['original_persona_mutation'])
        self.assertFalse(saved['report']['other_agent_access'])
        self.assertEqual(self.sources, self.sources_before)
        self.assertEqual(original_files, {p.name: p.read_bytes() for p in self.source.iterdir()})
        for path in self.directory.rglob('*'):
            if path.is_file():
                self.assertNotIn(FAKE_CREDENTIAL.encode(), path.read_bytes())
        self.assert_blocked(transport)
        addendum.review_last(self.directory, accepted=True, notes='Offline two-field-only review.')
        self.assertEqual(verify(run)['evidence_hash'], pinned['evidence_hash'])
        self.assertEqual(self.run_one(transport)['status'], 'success')
        self.assertEqual(len(self.calls), 4)

    def test_rejected_review_stops_without_replacement(self):
        self.prepare()
        transport = self.transport()
        self.run_one(transport)
        addendum.review_last(self.directory, accepted=False, notes='Offline scope failure.')
        self.assert_blocked(transport)
        self.assertEqual(len(list(self.directory.glob('generation-*'))), 1)

    def test_rehashed_derived_identity_tamper_cannot_be_accepted_as_raw(self):
        self.prepare()
        transport = self.transport()
        result = self.run_one(transport)
        run = self.directory / 'generation-01'
        path = run / 'DERIVED/addendum.json'
        payload = read_record(path)
        payload['report']['identity']['gender_identity'] = '原文にはない改変内容'
        # Deliberately create a self-consistent derived wrapper. The comparison
        # must still reject it because RAW remains the authoritative record.
        path.write_text(canonical({'sha256': digest(payload), 'payload': payload}))
        self.assertEqual(verify(run)['evidence_hash'], result['evidence_hash'])
        with self.assertRaisesRegex(ValueError, 'ADDENDUM_DIFFERS_FROM_RAW'):
            addendum.review_last(self.directory, accepted=True, notes='Offline tamper check.')
        self.assertFalse((run / 'DERIVED/content-review.json').exists())
        self.assert_blocked(transport)

    def test_network_failure_is_retained_without_retry_or_followup(self):
        self.prepare()
        transport = self.transport(timeout=True)
        result = self.run_one(transport)
        self.assertEqual(result['status'], 'failure')
        self.assertEqual(result['error']['code'], 'TRANSPORT_TIMEOUT')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(verify(self.directory / 'generation-01')['status'], 'failure')
        self.assert_blocked(transport)

    def test_schema_failure_retains_raw_and_stops_without_retry(self):
        self.prepare()
        raw = response_bytes({'gender_identity': '任意', 'sexual_orientation': '任意', 'personality_change': 'forbidden'})
        transport = self.transport(raw=raw)
        result = self.run_one(transport)
        self.assertEqual(result['status'], 'failure')
        self.assertEqual(result['error']['code'], 'ADDENDUM_SCHEMA_ERROR')
        self.assertEqual(len(self.calls), 2)
        wire = read_record(self.directory / 'generation-01/RAW/generation.response.json')
        self.assertEqual(base64.b64decode(wire['body_base64']), raw)
        self.assertEqual(verify(self.directory / 'generation-01')['status'], 'failure')
        self.assert_blocked(transport)

    def test_eight_people_complete_within_reservation_and_ninth_is_blocked(self):
        prepared = self.prepare()
        self.assertEqual(Decimal(prepared['reservation_total_usd']), Decimal('0.15744'))
        self.assertLessEqual(Decimal(prepared['reservation_total_usd']), Decimal('0.20'))
        transport = self.transport()
        for index in range(1, 9):
            result = self.run_one(transport)
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['leader_id'], f'leader-{index:02d}')
            review = addendum.review_last(self.directory, accepted=True, notes='Offline two-field-only review.')
            self.assertEqual(review['batch_complete'], index == 8)
        self.assertEqual(len(self.calls), 16)
        self.assertEqual(len(list(self.directory.glob('generation-*'))), 8)
        reserved = sum((Decimal(read_record(p)['usd']) for p in self.directory.glob('reservation-*.json')), Decimal(0))
        self.assertEqual(reserved, Decimal('0.15744'))
        self.assertLessEqual(reserved, addendum.LIMIT)
        self.assert_blocked(transport)
        self.assertEqual(self.sources, self.sources_before)

    def test_changed_source_hash_or_runtime_blocks_before_any_request(self):
        self.prepare()
        transport = self.transport()
        hashes = addendum.source_hashes()
        hashes['homeostasis_v5/identity_addendum.py'] = '0' * 64
        with patch.object(addendum, 'source_hashes', return_value=hashes):
            self.assert_blocked(transport)
        with patch.object(addendum, '_runtime', return_value={'changed': True}):
            self.assert_blocked(transport)
        self.assertEqual(len(self.calls), 0)

    def test_changed_parent_or_generation_configuration_blocks_before_calls(self):
        self.prepare()
        transport = self.transport()
        self.sources['people'][0]['persona']['layer1']['person_profile']['age_years'] = 53
        self.assert_blocked(transport)
        self.sources = copy.deepcopy(self.sources_before)
        approved_build = addendum.build_request
        def changed_build(persona):
            request = approved_build(persona)
            request['generationConfig']['temperature'] = 0.2
            return request
        with patch.object(addendum, 'build_request', side_effect=changed_build):
            self.assert_blocked(transport)
        self.assertEqual(len(self.calls), 0)

    def test_oversize_input_stops_before_generation_and_without_retry(self):
        self.prepare()
        transport = self.transport(count=16001)
        result = self.run_one(transport)
        self.assertEqual(result['status'], 'failure')
        self.assertEqual(result['error']['code'], 'INPUT_OVER_LIMIT_OR_UNKNOWN')
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(list(self.directory.glob('reservation-*.json')))
        self.assert_blocked(transport)

    def test_prepare_is_write_once_and_original_files_unchanged(self):
        self.prepare()
        before = {str(p.relative_to(self.directory)): p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(before, {str(p.relative_to(self.directory)): p.read_bytes() for p in self.directory.rglob('*') if p.is_file()})
        self.assertEqual(self.sources, self.sources_before)


if __name__ == '__main__':
    unittest.main()
