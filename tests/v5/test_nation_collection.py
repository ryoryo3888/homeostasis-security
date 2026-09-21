"""Offline proposal-collection checks; all requests use a synthetic transport."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from homeostasis_v4.evidence import read_record, verify
from homeostasis_v5 import nation_generation as run
import test_nation_generation as fixtures
from test_nation_generation_contract import nation


class NationCollectionTests(unittest.TestCase):
    def setUp(self):
        # Reuse fixture construction without inheriting/rerunning its test suite.
        self.fixture = fixtures.NationGenerationTests(methodName='runTest')
        with patch.object(run, 'VERSION', 'v5-nation-initialization-5-frozen-map-continuation'):
            self.fixture.setUp()
            self.addCleanup(self.fixture.doCleanups)
            self.map_source, _ = self.fixture.continuation()
            self.source = self.fixture.root
            self.requests = []
            first = run.generate_next(self.source, credential='SYNTHETIC_SECRET',
                                      transport=self.transport())
            self.assertEqual(first['status'], 'success')
            run.review_last(self.source, accepted=False,
                            review_notes=['Synthetic unresolved proposal; preserve for collective review'])
        self.root = Path(self.fixture.tmp.name) / 'collection'
        self.requests = []
        run.prepare_collection(self.root, proposal_source=self.source)

    def transport(self, *, mode='unresolved'):
        def handle(request):
            self.requests.append(request)
            body = json.loads(request.content)
            if request.url.path.endswith(':countTokens'):
                return httpx.Response(200, json={'totalTokens': 100})
            context = json.loads(body['contents'][0]['parts'][1]['text'])
            record = nation()
            record['world_id'] = context['world_id']
            record['nation_id'] = context['own_nation_id']
            slot = next(s for s in context['common_geography']['nation_slots']
                        if s['nation_id'] == record['nation_id'])
            record['geography_ref'] = {
                'map_sha256': context['input_references']['map_sha256'],
                'territory_region_ids': slot['territory_region_ids'],
            }
            # A declared asset with no price or quantity must remain unresolved,
            # and the arithmetic mismatch is a separate, preserved model claim.
            record['reported_retained_points'] = '500'
            if mode == 'unresolved':
                record['holdings'] = [{
                    'holding_id': 'h1', 'source_id': 's1', 'name': 'unpriced synthetic asset',
                    'spec_id': None, 'asset_kind': 'novel',
                    'quantity': {'value': None, 'unit': None},
                    'region_ids': slot['territory_region_ids'], 'state_description': 'unknown',
                    'capability_claim': 'unresolved capability', 'dependencies': [], 'proposal_id': 'p1',
                }]
                record['free_asset_proposals'] = [{
                    'proposal_id': 'p1', 'original_text': 'PRESERVE_UNKNOWN_PROPOSAL',
                    'specification_claim': 'unpriced capability',
                    'quantity': {'value': None, 'unit': None}, 'related_holding_ids': ['h1'],
                    'unresolved_fields': ['quantity', 'price'],
                }]
            if mode.startswith('duplicate_source'):
                record['holdings'] = [{
                    'holding_id': f'h{number}', 'source_id': 'shared_catalog_name',
                    'name': f'distinct synthetic asset {number}', 'spec_id': 'synthetic-stock',
                    'asset_kind': 'inventory', 'quantity': {'value': str(number), 'unit': 'test_unit'},
                    'region_ids': slot['territory_region_ids'], 'state_description': 'record only',
                    'capability_claim': 'unaccepted claim', 'dependencies': [], 'proposal_id': None,
                } for number in (1, 2)]
            if mode == 'duplicate_source_unknown_region':
                record['holdings'][1]['region_ids'] = ['unavailable-region']
            if mode == 'duplicate_source_unknown_nation':
                record['external_relation_claims'] = [{'nation_ids': ['nation-unavailable'], 'claim_text': 'unverified relation'}]
            if mode == 'duplicate_source_wrong_identity':
                record['nation_id'] = 'nation-unexpected'
            if mode == 'wrong_reference':
                record['geography_ref']['map_sha256'] = '0' * 64
            if mode == 'invalid_schema':
                del record['population']
            return httpx.Response(200, json={
                'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(record)}]}}],
                'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 200, 'totalTokenCount': 300},
            })
        return httpx.MockTransport(handle)

    def invoke(self, **kwargs):
        return run.generate_next(self.root, credential='SYNTHETIC_SECRET', transport=self.transport(**kwargs))

    def test_imports_one_then_collects_eleven_without_acceptance_or_assignment(self):
        immutable_before = {str(p): p.read_bytes() for base in (self.map_source, self.source)
                            for p in base.rglob('*') if p.is_file()}
        plan = read_record(self.root / 'plan.json')
        source_plan = read_record(self.source / 'plan.json')
        self.assertEqual(plan['max_generation_calls'], 11)
        self.assertEqual(plan['max_count_calls'], 11)
        self.assertEqual(plan['maximum_reserved_usd'], '1.20384')
        self.assertEqual(plan['assignment'], source_plan['assignment'])
        self.assertEqual(plan['world_id'], source_plan['world_id'])
        self.assertEqual(plan['catalog_sha256'], source_plan['catalog_sha256'])
        for index in range(3, 14):
            mode = 'balance_mismatch' if index % 2 else 'unresolved'
            result = self.invoke(mode=mode)
            self.assertEqual((result['status'], result['stage'], result['index']), ('success', 'nation', index))
            attempt = self.root / f'attempt-{index:02d}'
            validation = read_record(attempt / 'DERIVED/structural-validation.json')['report']
            self.assertFalse(validation['accepted_initial_nation'])
            self.assertIsNone(validation['accepted_retained_points'])
            self.assertFalse((attempt / 'DERIVED/content-review.json').exists())
            self.assertEqual(verify(attempt)['status'], 'success')
            counted = json.loads(self.requests[-2].content)['generateContentRequest']
            counted.pop('model')
            self.assertEqual(run.wire_bytes(counted), self.requests[-1].content)
            context = json.loads(json.loads(self.requests[-1].content)['contents'][0]['parts'][1]['text'])
            self.assertEqual(context['own_nation_id'], run.IDS[index - 2])
            self.assertNotIn('previous_nations', context)
            self.assertNotIn('leader_references', context)
            self.assertNotIn('PRESERVE_UNKNOWN_PROPOSAL', json.dumps(context))
        self.assertEqual(len(self.requests), 22)
        self.assertFalse((self.root / 'attempt-01').exists())
        self.assertFalse((self.root / 'attempt-02').exists())
        self.assertFalse((self.root / 'assignment.json').exists())
        self.assertFalse(list(self.root.glob('blocked-*.json')))
        with self.assertRaisesRegex(run.GenerationError, 'BATCH_COMPLETE'):
            self.invoke()
        self.assertEqual(len(self.requests), 22)
        self.assertEqual(immutable_before, {str(p): p.read_bytes() for base in (self.map_source, self.source)
                                           for p in base.rglob('*') if p.is_file()})
        original_review = read_record(self.source / 'attempt-02/DERIVED/content-review.json')['report']
        self.assertFalse(original_review['accepted'])
        self.assertFalse((self.source / 'assignment.json').exists())

    def test_collection_cannot_use_acceptance_gate_to_assign_leaders(self):
        self.invoke(mode='balance_mismatch')
        with self.assertRaises(run.GenerationError):
            run.review_last(self.root, accepted=True, review_notes=['Cannot turn collection into approval'])
        self.assertFalse((self.root / 'attempt-03/DERIVED/content-review.json').exists())
        self.assertFalse((self.root / 'assignment.json').exists())
        self.assertEqual(len(self.requests), 2)

    def test_duplicate_source_remains_unaccepted_but_does_not_block_collection(self):
        first = self.invoke(mode='duplicate_source')
        self.assertEqual(first['status'], 'success')
        raw = run._output(self.root / 'attempt-03')
        self.assertEqual([h['source_id'] for h in raw['holdings']], ['shared_catalog_name'] * 2)
        report = read_record(self.root / 'attempt-03/DERIVED/structural-validation.json')['report']
        self.assertEqual(report['asset_contract_issue'], 'DUPLICATE_SOURCE_CLAIM')
        self.assertFalse(report['accepted_initial_nation'])
        self.assertIsNone(report['accepted_retained_points'])
        accounting = read_record(self.root / 'attempt-03/DERIVED/accounting-review.json')['report']
        self.assertFalse(accounting['accepted_initial_accounting'])
        self.assertIsNone(accounting['exact_retained_points'])
        second = self.invoke(mode='balance_mismatch')
        self.assertEqual((second['status'], second['index']), ('success', 4))
        self.assertEqual(len(self.requests), 4)
        self.assertFalse((self.root / 'assignment.json').exists())

    def test_duplicate_source_never_hides_wrong_nation_identity(self):
        result = self.invoke(mode='duplicate_source_wrong_identity')
        self.assertEqual(result['error']['code'], 'NATION_IDENTITY_MISMATCH')
        with self.assertRaisesRegex(run.GenerationError, 'BATCH_BLOCKED'):
            self.invoke()
        self.assertEqual(len(self.requests), 2)

    def test_duplicate_source_never_hides_unknown_asset_region(self):
        result = self.invoke(mode='duplicate_source_unknown_region')
        self.assertEqual(result['error']['code'], 'UNKNOWN_REGION_REFERENCE')
        with self.assertRaisesRegex(run.GenerationError, 'BATCH_BLOCKED'):
            self.invoke()
        self.assertEqual(len(self.requests), 2)

    def test_duplicate_source_never_hides_unknown_external_nation(self):
        result = self.invoke(mode='duplicate_source_unknown_nation')
        self.assertEqual(result['error']['code'], 'UNKNOWN_NATION_REFERENCE')
        with self.assertRaisesRegex(run.GenerationError, 'BATCH_BLOCKED'):
            self.invoke()
        self.assertEqual(len(self.requests), 2)

    def test_stopped_collection_imports_three_proposals_without_retrying_failed_raw(self):
        old = Path(self.fixture.tmp.name) / 'old-collection-v6'
        # Recreate the old validator behavior with immutable synthetic evidence.
        with patch.object(run, 'VERSION', 'v5-nation-initialization-6-proposal-collection'), \
             patch.object(run, 'inspect_collection_output', side_effect=run.inspect_nation_output):
            run.prepare_collection(old, proposal_source=self.source)
            result = run.generate_next(old, credential='SYNTHETIC_SECRET',
                                       transport=self.transport(mode='balance_mismatch'))
            self.assertEqual(result['status'], 'success')
            result = run.generate_next(old, credential='SYNTHETIC_SECRET',
                                       transport=self.transport(mode='duplicate_source'))
            self.assertEqual(result['error']['code'], 'DUPLICATE_SOURCE_CLAIM')
            self.assertEqual(result['index'], 4)
        immutable_before = {str(p): p.read_bytes() for p in old.rglob('*') if p.is_file()}
        self.assertEqual(verify(old / 'attempt-04')['status'], 'failure')
        target = Path(self.fixture.tmp.name) / 'extended-collection'
        prepared = run.prepare_collection(target, proposal_source=old)
        self.assertEqual(prepared['imported_proposals'], 3)
        self.assertEqual(prepared['new_proposals'], 9)
        self.assertEqual(prepared['map_generation_calls'], 0)
        plan = read_record(target / 'plan.json')
        self.assertEqual(plan['max_generation_calls'], 9)
        self.assertEqual(plan['max_count_calls'], 9)
        self.assertEqual(run._first_index(plan), 5)
        self.assertEqual([p['nation_id'] for p in plan['collection_source']['collected_proposals']], run.IDS[:3])
        self.assertEqual(plan['collection_source']['collected_proposals'][-1]['original_status'], 'failure')
        self.requests = []
        result = run.generate_next(target, credential='SYNTHETIC_SECRET',
                                   transport=self.transport(mode='balance_mismatch'))
        self.assertEqual((result['status'], result['index']), ('success', 5))
        self.assertEqual(len(self.requests), 2)
        context = json.loads(json.loads(self.requests[-1].content)['contents'][0]['parts'][1]['text'])
        self.assertEqual(context['own_nation_id'], 'nation-004')
        self.assertEqual(immutable_before, {str(p): p.read_bytes() for p in old.rglob('*') if p.is_file()})
        self.assertEqual(verify(old / 'attempt-04')['status'], 'failure')
        self.assertFalse((target / 'assignment.json').exists())

    def test_reference_failure_blocks_without_retry_or_reroll(self):
        result = self.invoke(mode='wrong_reference')
        self.assertEqual(result['error']['code'], 'MAP_REFERENCE_MISMATCH')
        self.assertEqual(result['index'], 3)
        self.assertTrue((self.root / 'attempt-03/RAW/generation.response.json').exists())
        with self.assertRaisesRegex(run.GenerationError, 'BATCH_BLOCKED'):
            self.invoke()
        self.assertEqual(len(self.requests), 2)
        self.assertFalse((self.root / 'assignment.json').exists())

    def test_schema_failure_blocks_with_raw_intact(self):
        result = self.invoke(mode='invalid_schema')
        self.assertEqual(result['error']['code'], 'NATION_SCHEMA_ERROR')
        self.assertEqual(verify(self.root / 'attempt-03')['status'], 'failure')
        with self.assertRaisesRegex(run.GenerationError, 'BATCH_BLOCKED'):
            self.invoke()
        self.assertEqual(len(self.requests), 2)

    def test_source_change_is_detected_before_any_request(self):
        source = deepcopy(run._collection_source(self.source))
        source['changed_pin_sentinel'] = True
        with patch.object(run, '_collection_source', return_value=source):
            with self.assertRaises(run.GenerationError):
                self.invoke()
        self.assertEqual(self.requests, [])

    def test_cost_gate_includes_prior_usage_before_preparing_new_calls(self):
        source = deepcopy(run._collection_source(self.source))
        source['charged_usd'] = '0.40'
        with patch.object(run, '_collection_source', return_value=source):
            with self.assertRaisesRegex(run.GenerationError, 'BUDGET_NOT_SUFFICIENT'):
                run.prepare_collection(Path(self.fixture.tmp.name) / 'over-budget', proposal_source=self.source)
        self.assertEqual(self.requests, [])
        self.assertFalse((Path(self.fixture.tmp.name) / 'over-budget').exists())


if __name__ == '__main__':
    unittest.main()
