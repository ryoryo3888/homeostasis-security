"""Synthetic offline contract tests, plus a local frozen-request integration check."""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

from homeostasis_v5.initial_specification_contract import validate_specification
from homeostasis_v5.persona_generation import GenerationError


def obj(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def schema():
    text, nullable = {'type': 'string'}, {'type': ['string', 'null']}
    texts = {'type': 'array', 'items': text}
    field = obj({'field_name': text, 'value': nullable, 'unit': nullable, 'meaning': text,
                 'basis': {'type': 'string', 'enum': ['new_generated_initial_assumption',
                    'unchanged_raw_reference', 'unresolved', 'not_applicable', 'reference_catalogue_value']},
                 'source_pointer': nullable, 'unresolved_reason': nullable,
                 'reference_spec_id': nullable, 'reference_pointer': nullable})
    component = obj({'component_id': text, 'description': text,
        'supporting_original_holding_ids': texts, 'ownership_or_access_proposal': nullable,
        'location_region_ids': texts, 'specification_fields': {'type': 'array', 'items': field},
        'included_parts_and_exclusions': texts, 'operating_dependencies_still_to_resolve': texts,
        'reference_spec_id': nullable, 'reference_scope_explanation': text, 'remaining_unknowns': texts})
    item = obj({'target_id': text, 'source_pointer': text, 'proposal_status': {'type': 'string', 'enum': [
        'new_initial_specification_proposed', 'unresolved', 'shared_world_decision_required', 'conflict']},
        'initial_specification_proposals': {'type': 'array', 'items': component}, 'reason': text})
    return obj({'document_type': {'type': 'string', 'enum': ['v5-targeted-initial-specification-proposal-1']},
                'world_id': text, 'nation_id': text, 'source_evidence_sha256': text,
                'items': {'type': 'array', 'items': item}})


def new_field():
    return {'field_name': 'structure', 'value': 'Synthetic detached building', 'unit': None,
            'meaning': 'A newly proposed building structure, not an observed original fact',
            'basis': 'new_generated_initial_assumption', 'source_pointer': None,
            'unresolved_reason': None, 'reference_spec_id': None, 'reference_pointer': None}


def output_for(context):
    return {'document_type': 'v5-targeted-initial-specification-proposal-1',
            'world_id': context['world_id'], 'nation_id': context['nation_id'],
            'source_evidence_sha256': context['source_evidence_sha256'], 'items': [
        {'target_id': target['target_id'], 'source_pointer': target['source_pointer'],
         'proposal_status': 'new_initial_specification_proposed',
         'initial_specification_proposals': [{
            'component_id': 'offline-only-' + str(index),
            'description': 'Synthetic test proposal; not a model output or world asset',
            'supporting_original_holding_ids': [context['original_nation']['holdings'][0]['holding_id']],
            'ownership_or_access_proposal': None,
            'location_region_ids': context['original_nation']['geography_ref']['territory_region_ids'],
            'specification_fields': [new_field()], 'included_parts_and_exclusions': [],
            'operating_dependencies_still_to_resolve': ['Operating inputs are not supplied by this test'],
            'reference_spec_id': None, 'reference_scope_explanation': 'No catalogue equivalence claimed',
            'remaining_unknowns': ['Ownership or access has not been proposed']}],
         'reason': 'Offline synthetic validation exercise only'}
        for index, target in enumerate(context['targets'])]}


def fixture():
    context = {'world_id': 'world-synthetic', 'nation_id': 'nation-synthetic',
        'source_evidence_sha256': 'a' * 64,
        'original_nation': {'holdings': [{'holding_id': 'holding-test',
            'quantity': {'value': '100.0', 'unit': 'metric_tonne'}, 'state_description': 'Stored at a warehouse'}],
            'geography_ref': {'territory_region_ids': ['region-test']},
            'population': {'count': 15}},
        'targets': [{'target_id': 'target-test', 'source_pointer': '/holdings/0/state_description'}],
        'common_asset_specifications': {'specifications': [
            {'spec_id': 'catalog-test', 'name': 'Synthetic specification',
             'definition': json.dumps({'published_specification': {'capacity': {'value': '42', 'unit': 'test_unit'}}})},
            {'spec_id': 'catalog-other', 'name': 'Other specification'}]}}
    body = {'contents': [{'parts': [{'text': 'Offline fixture'}, {'text': json.dumps(context)}]}],
            'generationConfig': {'responseJsonSchema': schema()}}
    return output_for(context), body


class InitialSpecificationContractTests(unittest.TestCase):
    def setUp(self):
        self.output, self.body = fixture()

    def component(self):
        return self.output['items'][0]['initial_specification_proposals'][0]

    def field(self):
        return self.component()['specification_fields'][0]

    def reject(self):
        with self.assertRaises(GenerationError):
            validate_specification(self.output, self.body)

    def raw_field(self):
        self.field().update(basis='unchanged_raw_reference', value='100.0', unit='metric_tonne',
                            source_pointer='/holdings/0/quantity/value')

    def catalogue_field(self, pointer='/definition/published_specification/capacity/value'):
        self.field().update(basis='reference_catalogue_value', value='42', unit='test_unit',
                            reference_spec_id='catalog-test', reference_pointer=pointer)

    def test_pass_does_not_mutate_or_accept_world_and_counts_fields(self):
        before = deepcopy((self.output, self.body))
        report = validate_specification(self.output, self.body)
        self.assertEqual((self.output, self.body), before)
        self.assertEqual(report['new_proposed_fields'], 1)
        self.assertEqual(report['unknown_ownership_components'], 1)
        self.assertTrue(report['requires_semantic_review'])
        self.assertFalse(report['accepted_initial_nation'])
        self.assertFalse(report['world_physics_approved'])

    def test_narrative_and_zero_numeric_values_have_no_numeric_minimum(self):
        for value, unit in [('Synthetic timber structure', None), ('0', 'test_unit')]:
            self.field().update(value=value, unit=unit)
            self.assertEqual(validate_specification(self.output, self.body)['new_proposed_fields'], 1)

    def test_valid_unresolved_item_is_preserved_without_forcing_proposals(self):
        item = self.output['items'][0]
        item.update(proposal_status='unresolved', initial_specification_proposals=[])
        report = validate_specification(self.output, self.body)
        self.assertEqual(report['new_proposed_fields'], 0)
        self.assertEqual(report['unresolved_targets'], 1)

    def test_schema_violation(self):
        self.output['new_world_balance'] = 1000
        self.reject()

    def test_source_identity(self):
        for key in ('world_id', 'nation_id', 'source_evidence_sha256'):
            with self.subTest(key=key):
                self.output, self.body = fixture()
                self.output[key] = 'different'
                self.reject()

    def test_exact_targets(self):
        for mode in ('missing', 'duplicate', 'wrong'):
            with self.subTest(mode=mode):
                self.output, self.body = fixture()
                if mode == 'missing': self.output['items'] = []
                elif mode == 'duplicate': self.output['items'] *= 2
                else: self.output['items'][0]['target_id'] = 'foreign-target'
                self.reject()

    def test_target_source_pointer(self):
        self.output['items'][0]['source_pointer'] = '/population/count'
        self.reject()

    def test_unique_component_ids(self):
        self.output['items'][0]['initial_specification_proposals'].append(deepcopy(self.component()))
        self.reject()

    def test_own_holding_and_region_only(self):
        for key in ('supporting_original_holding_ids', 'location_region_ids'):
            with self.subTest(key=key):
                self.output, self.body = fixture()
                self.component()[key] = ['another-nation']
                self.reject()

    def test_nonproposal_status_with_components(self):
        for status in ('unresolved', 'shared_world_decision_required', 'conflict'):
            with self.subTest(status=status):
                self.output, self.body = fixture()
                self.output['items'][0]['proposal_status'] = status
                self.reject()

    def test_unresolved_ownership_has_reason(self):
        self.component()['remaining_unknowns'] = []
        self.reject()
        self.component()['ownership_or_access_proposal'] = 'Synthetic proposed ownership'
        validate_specification(self.output, self.body)

    def test_blank_values_and_meanings_rejected(self):
        for key in ('value', 'meaning', 'field_name', 'unit'):
            with self.subTest(key=key):
                self.output, self.body = fixture()
                self.field()[key] = '  '
                self.reject()

    def test_new_assumption_is_not_claimed_as_raw_or_catalogue(self):
        for key, value in [('source_pointer', '/population/count'), ('reference_spec_id', 'catalog-test'),
                           ('reference_pointer', '/name')]:
            with self.subTest(key=key):
                self.output, self.body = fixture()
                self.field()[key] = value
                self.reject()

    def test_unresolved_field_has_null_value_reason_and_known_unit_allowed(self):
        self.field().update(basis='unresolved', value=None, unit='metric_tonne', unresolved_reason='Unspecified')
        report = validate_specification(self.output, self.body)
        self.assertEqual(report['unresolved_fields'], 1)
        self.field()['unresolved_reason'] = None
        self.reject()

    def test_unresolved_cannot_claim_value_or_source(self):
        for change in ({'value': '0'}, {'source_pointer': '/population/count'}, {'reference_spec_id': 'catalog-test'}):
            with self.subTest(change=change):
                self.output, self.body = fixture()
                self.field().update(basis='unresolved', value=None, unresolved_reason='Unspecified')
                self.field().update(change)
                self.reject()

    def test_not_applicable_with_explanation(self):
        self.field().update(basis='not_applicable', value=None, meaning='No cooling equipment proposed')
        validate_specification(self.output, self.body)

    def test_raw_reference_scalar_object_and_explicit_original_root(self):
        self.raw_field()
        for pointer in ('/holdings/0/quantity/value', '/holdings/0/quantity', '/original_nation/holdings/0/quantity/value'):
            self.field().update(source_pointer=pointer, value='100')
            validate_specification(self.output, self.body)
        self.field().update(source_pointer='/population/count', value='15', unit=None)
        validate_specification(self.output, self.body)

    def test_raw_changed_value_or_unit_rejected(self):
        for change in ({'value': '101'}, {'unit': 'kilogram'}, {'source_pointer': '/missing'}):
            with self.subTest(change=change):
                self.output, self.body = fixture()
                self.raw_field(); self.field().update(change)
                self.reject()

    def test_mixed_raw_and_catalogue_provenance_rejected(self):
        self.raw_field(); self.field()['reference_spec_id'] = 'catalog-test'
        self.reject()

    def test_catalogue_relative_and_qualified_paths_and_embedded_json(self):
        tail = '/definition/published_specification/capacity/value'
        for prefix in ('', '/catalog-test', '/specifications/0', '/specifications/catalog-test',
                       '/common_asset_specifications/specifications/0'):
            with self.subTest(prefix=prefix):
                self.catalogue_field(prefix + tail)
                validate_specification(self.output, self.body)

    def test_catalogue_id_value_unit_and_pointer_binding(self):
        changes = ({'reference_spec_id': 'unknown'}, {'value': '43'}, {'unit': 'kilogram'},
                   {'reference_pointer': '/specifications/1/name'}, {'reference_pointer': '/missing'})
        for change in changes:
            with self.subTest(change=change):
                self.output, self.body = fixture()
                self.catalogue_field(); self.field().update(change)
                self.reject()

    def test_component_catalogue_claim_must_be_supplied_spec(self):
        self.component()['reference_spec_id'] = 'invented-model'
        self.reject()

    def test_field_empty_strings_are_not_missing_values(self):
        self.field()['unresolved_reason'] = ''
        self.reject()

    def test_frozen_001_request_offline_integration(self):
        default = (Path('/Users/mk/.codex/.chatgpt-projects/g-p-6aaa878f0bb08191b79262fa642e3801') /
                   'homeostasis-security/.artifacts/v5-initial-specification-review-20260922/nation-001-request.proposed.json')
        path = Path(os.environ.get('V5_FROZEN_SPEC_REQUEST', str(default)))
        if not path.exists():
            self.skipTest('Private frozen request is not part of the public test fixture')
        body = json.loads(path.read_text())['body']
        self.assertEqual(body['generationConfig']['responseJsonSchema'], schema())
        context = json.loads(body['contents'][0]['parts'][1]['text'])
        artificial = output_for(context)
        report = validate_specification(artificial, body)
        self.assertEqual(report['checked_targets'], len(context['targets']))
        self.assertFalse(report['accepted_initial_nation'])


if __name__ == '__main__':
    unittest.main()
