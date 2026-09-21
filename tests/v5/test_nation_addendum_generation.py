"""Offline runner safeguards for twelve frozen addendum requests; no live API."""
from copy import deepcopy
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from homeostasis_v3.contracts import digest
from homeostasis_v4.evidence import read_record, verify
from homeostasis_v5 import nation_addendum_generation as run


class NationAddendumGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'batch'
        self.proposals = Path(self.tmp.name) / 'approved-proposals'
        self.proposals.mkdir(mode=0o700)
        source_references = []
        requests = []
        for i in range(1, 13):
            nid = f'nation-{i:03d}'
            context = {'world_id': 'synthetic-world', 'nation_id': nid,
                       'source_evidence_sha256': 'a' * 64,
                       'original_nation': {'name': 'synthetic', 'nation_id': nid},
                       'review_targets': [{'target_id': 'target-1', 'source_pointer': '$.name',
                                           'source_value': 'synthetic', 'question': 'test only'}]}
            body = {'contents': [{'role': 'user', 'parts': [
                {'text': 'Synthetic addendum request; never a real experiment'},
                {'text': json.dumps(context, ensure_ascii=False, separators=(',', ':'))}]}],
                'generationConfig': {'responseMimeType': 'application/json',
                    'responseJsonSchema': {'type': 'object', 'properties': {'nation_id': {'type': 'string'}}},
                    'temperature': 1.0, 'candidateCount': 1, 'maxOutputTokens': 8192,
                    'thinkingConfig': {'thinkingLevel': 'LOW', 'includeThoughts': False}}}
            directory = str(self.proposals / nid)
            requests.append({'nation_id': nid, 'name': f'Synthetic {i}', 'body': body,
                             'request_sha256': digest(body), 'source_evidence_hash': 'a' * 64,
                             'source_raw_evidence_hash': 'b' * 64, 'source_directory': directory,
                             'original_nation_sha256': 'c' * 64})
            source_references.append({'directory': directory, 'evidence_hash': 'a' * 64, 'nation_id': nid})
        self.source = {'proposal_plan_sha256': 'd' * 64,
                       'proposal_plan_path': str(self.proposals / 'plan.json'),
                       'collection_index_path': str(self.proposals / 'collection-index.json'),
                       'collection_index_file_sha256': 'e' * 64,
                       'source_references': source_references, 'requests': requests,
                       'map_sha256': 'f' * 64, 'catalog_sha256': '0' * 64}
        for name, value in [('_load_approved_proposals', self.source),
                            ('source_hashes', {'synthetic.py': 'a' * 64}),
                            ('_runtime', {'python': 'synthetic'}),
                            ('_verify_originals', None),
                            ('validate_addendum', {'valid': True, 'accepted_initial_nation': False})]:
            mock = (patch.object(run, name, side_effect=lambda _: deepcopy(self.source))
                    if name == '_load_approved_proposals' else patch.object(run, name, return_value=value))
            mock.start()
            self.addCleanup(mock.stop)
        commit = patch.object(run.subprocess, 'check_output', side_effect=lambda *args, **kwargs:
                              '1' * 40 if kwargs.get('text') else b'1' * 40)
        commit.start()
        self.addCleanup(commit.stop)
        run.prepare(self.root, proposal_directory=self.proposals)
        self.requests = []

    def transport(self, *, count=100, mode='success', generation_hook=None):
        def handle(request):
            self.requests.append(request)
            body = json.loads(request.content)
            if request.url.path.endswith(':countTokens'):
                if mode == 'count_http':
                    return httpx.Response(400, json={'error': {'message': 'synthetic count error'}})
                return httpx.Response(200, json={'totalTokens': count})
            if generation_hook:
                generation_hook()
            if mode == 'timeout':
                raise httpx.ReadTimeout('DO_NOT_RECORD_CREDENTIAL', request=request)
            if mode == 'http':
                return httpx.Response(400, json={'error': {'message': 'synthetic provider schema error'}})
            context = json.loads(body['contents'][0]['parts'][1]['text'])
            output = {'world_id': context['world_id'], 'nation_id': context['nation_id'],
                      'source_evidence_sha256': context['source_evidence_sha256'], 'items': []}
            text = '{broken' if mode == 'malformed' else json.dumps(output)
            finish = 'MAX_TOKENS' if mode == 'incomplete' else 'STOP'
            usage = {'promptTokenCount': 100, 'candidatesTokenCount': 200,
                     'thoughtsTokenCount': 50, 'totalTokenCount': 350}
            if mode == 'usage_over_limit':
                usage = {'promptTokenCount': 24001, 'candidatesTokenCount': 200, 'totalTokenCount': 24201}
            return httpx.Response(200, json={
                'candidates': [{'finishReason': finish, 'content': {'parts': [{'text': text}]}}],
                'usageMetadata': usage, 'modelVersion': 'synthetic-model', 'responseId': 'synthetic-response'})
        return httpx.MockTransport(handle)

    def invoke(self, **kwargs):
        return run.generate_next(self.root, credential='SYNTHETIC_SECRET', transport=self.transport(**kwargs))

    def assertBlockedWithoutMoreRequests(self, code="BATCH_BLOCKED"):
        before = len(self.requests)
        with self.assertRaisesRegex(run.GenerationError, code):
            self.invoke()
        self.assertEqual(len(self.requests), before)

    def test_twelve_frozen_bodies_count_and_generation_are_identical_and_stop(self):
        source_before = deepcopy(self.source)
        for index in range(1, 13):
            result = self.invoke()
            self.assertEqual(result['status'], 'success')
            counted = json.loads(self.requests[-2].content)['generateContentRequest']
            model = counted.pop('model')
            self.assertEqual(model, 'models/gemini-3.6-flash')
            body = json.loads(self.requests[-1].content)
            self.assertEqual(counted, body)
            self.assertEqual(body, self.source['requests'][index - 1]['body'])
            self.assertEqual(self.requests[-1].content, run.wire_bytes(self.source['requests'][index - 1]['body']))
            attempt = self.root / f'attempt-{index:02d}'
            wire = read_record(attempt / 'RAW/generation.wire.json')
            self.assertEqual(base64.b64decode(wire['body_base64']), self.requests[-1].content)
            self.assertEqual(verify(attempt)['status'], 'success')
        self.assertEqual(len(self.requests), 24)
        self.assertEqual(self.source, source_before)
        self.assertBlockedWithoutMoreRequests('BATCH_COMPLETE')
        self.assertFalse((self.root / 'assignment.json').exists())
        self.assertNotIn('SYNTHETIC_SECRET', ''.join(p.read_text() for p in self.root.rglob('*.json')))

    def test_input_cap_stops_after_count_and_before_generation(self):
        result = self.invoke(count=24001)
        self.assertEqual(result['status'], 'failure')
        self.assertFalse(result['error']['generation_attempted'])
        self.assertEqual(len(self.requests), 1)
        self.assertTrue((self.root / 'attempt-01/RAW/count.response.json').exists())
        self.assertFalse((self.root / 'attempt-01/RAW/generation.response.json').exists())
        self.assertFalse(list(self.root.glob('reservation-*.json')))
        self.assertBlockedWithoutMoreRequests()

    def test_count_http_failure_is_preserved_without_generation(self):
        result = self.invoke(mode='count_http')
        self.assertEqual(result['status'], 'failure')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(read_record(self.root / 'attempt-01/RAW/count.response.json')['status'], 400)
        self.assertBlockedWithoutMoreRequests()

    def test_generation_timeout_retains_reservation_and_never_retries(self):
        result = self.invoke(mode='timeout')
        self.assertEqual(result['status'], 'failure')
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(list(self.root.glob('reservation-*.json')))
        self.assertEqual(verify(self.root / 'attempt-01')['status'], 'failure')
        self.assertNotIn('DO_NOT_RECORD_CREDENTIAL', ''.join(p.read_text() for p in self.root.rglob('*.json')))
        self.assertBlockedWithoutMoreRequests()

    def test_provider_schema_error_is_not_repaired_or_retried(self):
        result = self.invoke(mode='http')
        self.assertEqual(result['status'], 'failure')
        self.assertEqual(read_record(self.root / 'attempt-01/RAW/generation.response.json')['status'], 400)
        self.assertEqual(len(self.requests), 2)
        self.assertBlockedWithoutMoreRequests()

    def test_malformed_response_preserved_then_batch_stops(self):
        result = self.invoke(mode='malformed')
        self.assertEqual(result['status'], 'failure')
        self.assertTrue((self.root / 'attempt-01/RAW/generation.response.json').exists())
        self.assertTrue((self.root / 'attempt-01/RAW/receipt.json').exists())
        self.assertEqual(verify(self.root / 'attempt-01')['status'], 'failure')
        self.assertBlockedWithoutMoreRequests()

    def test_incomplete_response_preserved_then_batch_stops(self):
        result = self.invoke(mode='incomplete')
        self.assertEqual(result['status'], 'failure')
        self.assertTrue((self.root / 'attempt-01/RAW/generation.response.json').exists())
        self.assertBlockedWithoutMoreRequests()

    def test_reported_usage_above_reserved_cap_stops(self):
        result = self.invoke(mode='usage_over_limit')
        self.assertEqual(result['status'], 'failure')
        self.assertTrue((self.root / 'attempt-01/RAW/receipt.json').exists())
        self.assertBlockedWithoutMoreRequests()

    def test_changed_original_is_detected_before_transport(self):
        with patch.object(run, '_verify_originals', side_effect=ValueError('SYNTHETIC_SOURCE_CHANGED')):
            with self.assertRaises(Exception):
                self.invoke()
        self.assertEqual(self.requests, [])

    def test_original_change_after_count_stops_before_paid_generation(self):
        def verify_during_send(_):
            if self.requests:
                raise run.GenerationError('SYNTHETIC_SOURCE_CHANGED')
        with patch.object(run, '_verify_originals', side_effect=verify_during_send):
            result = self.invoke()
        self.assertEqual(result['status'], 'failure')
        self.assertFalse(result['error']['generation_attempted'])
        self.assertEqual(len(self.requests), 1)
        self.assertTrue((self.root / 'attempt-01/RAW/count.response.json').exists())
        self.assertFalse(list(self.root.glob('reservation-*.json')))
        self.assertBlockedWithoutMoreRequests()

    def test_changed_source_code_is_detected_before_transport(self):
        with patch.object(run, 'source_hashes', return_value={'synthetic.py': 'b' * 64}):
            with self.assertRaises(Exception):
                self.invoke()
        self.assertEqual(self.requests, [])

    def test_changed_frozen_request_is_detected_before_transport(self):
        path = self.root / 'request-01.json'
        wrapped = json.loads(path.read_text())
        record = wrapped['payload']
        record['body']['generationConfig']['temperature'] = 0.0
        record['request_sha256'] = digest(record['body'])
        wrapped['sha256'] = digest(record)
        path.write_text(json.dumps(wrapped))
        with self.assertRaises(Exception):
            self.invoke()
        self.assertEqual(self.requests, [])


if __name__ == '__main__':
    unittest.main()
