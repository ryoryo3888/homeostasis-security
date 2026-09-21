"""Synthetic offline tests for addendum boundaries; no provider calls."""
from copy import deepcopy
import json
import unittest

from homeostasis_v5.nation_addendum_contract import validate_addendum
from homeostasis_v5.persona_generation import GenerationError


def obj(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def fixture():
    text = {'type': 'string'}
    texts = {'type': 'array', 'items': text}
    nullable = {'type': ['string', 'null']}
    quantity = obj({'value': nullable, 'unit': nullable, 'meaning': text})
    component = obj({
        'description': nullable, 'ownership_or_access': nullable,
        'location_region_ids': texts, 'quantity': quantity,
        'capacity_proposals': {'type': 'array', 'items': quantity},
        'required_inputs_and_dependencies': texts,
        'suggested_catalogue_spec_id': nullable, 'catalogue_equivalence_reason': nullable,
        'component_id': text, 'anchor_target_id': text,
        'detail_subject': {'enum': ['existing_holding', 'referenced_unlisted_asset',
                                    'dependency', 'activity_or_expertise']},
        'existing_holding_id': nullable,
        'new_information_status': {'enum': ['generated_in_this_addendum_proposal']},
    })
    item = obj({
        'target_id': text, 'classification': text, 'recorded_fact': text,
        'unresolved_fields': texts,
        'answer_status': {'enum': ['already_in_raw', 'new_completion_proposal',
                                   'still_unknown', 'conflict']},
        'existing_holding_references': texts,
        'new_asset_or_access_right_required': {'enum': ['yes', 'no', 'unknown']},
        'affects_acquisition_total': {'enum': ['yes', 'no', 'unknown']},
        'shared_world_dependency': texts, 'reason': text,
        'completion_proposals': {'type': 'array', 'items': component},
    })
    schema = obj({
        'document_type': {'enum': ['nation-initialization-addendum-proposal-1']},
        'world_id': text, 'nation_id': text, 'source_evidence_sha256': text,
        'items': {'type': 'array', 'items': item}, 'remaining_unknowns': texts,
    })
    original = {
        'world_id': 'world-test', 'nation_id': 'nation-test', 'name': 'Synthetic Nation',
        'population': {'count': 10, 'description': 'Synthetic population'},
        'geography_ref': {'territory_region_ids': ['region-test'], 'map_sha256': 'b' * 64},
        'holdings': [{'holding_id': 'stock-one', 'spec_id': 'catalog-known',
                      'quantity': {'value': '100', 'unit': 'test_unit'}}],
        'reported_retained_points': '999',
    }
    context = {
        'world_id': 'world-test', 'nation_id': 'nation-test',
        'source_evidence_sha256': 'a' * 64, 'original_nation': original,
        'common_asset_specifications': {'specifications': [{'spec_id': 'catalog-known'}]},
        'review_targets': [
            {'target_id': 'holding-1', 'source_pointer': '$.holdings[0]',
             'source_value': original['holdings'][0], 'question': 'Synthetic question'},
            {'target_id': 'society-technology', 'source_pointer': '$.society.technology',
             'source_value': 'Synthetic expertise only', 'question': 'Synthetic question'},
        ],
    }
    body = {'contents': [{'role': 'user', 'parts': [
        {'text': 'Synthetic review instructions'}, {'text': json.dumps(context)}]}],
        'generationConfig': {'responseJsonSchema': schema}}
    details = {
        'description': 'New detail proposed here, not a recovered fact',
        'ownership_or_access': None, 'location_region_ids': ['region-test'],
        'quantity': {'value': '1', 'unit': 'test_facility', 'meaning': 'Proposed facility count'},
        'capacity_proposals': [{'value': None, 'unit': None, 'meaning': 'Unknown capacity'}],
        'required_inputs_and_dependencies': ['Unknown operating inputs'],
        'suggested_catalogue_spec_id': None, 'catalogue_equivalence_reason': None,
        'component_id': 'component-one', 'anchor_target_id': 'holding-1',
        'detail_subject': 'referenced_unlisted_asset', 'existing_holding_id': None,
        'new_information_status': 'generated_in_this_addendum_proposal',
    }
    output = {
        'document_type': 'nation-initialization-addendum-proposal-1',
        'world_id': 'world-test', 'nation_id': 'nation-test', 'source_evidence_sha256': 'a' * 64,
        'items': [
            {'target_id': 'holding-1', 'classification': 'explicit_asset_claim',
             'recorded_fact': 'A paraphrase that still requires human review',
             'unresolved_fields': ['capacity'], 'answer_status': 'new_completion_proposal',
             'existing_holding_references': ['stock-one'],
             'new_asset_or_access_right_required': 'unknown', 'affects_acquisition_total': 'unknown',
             'shared_world_dependency': [], 'reason': 'Synthetic pending review',
             'completion_proposals': [details]},
            {'target_id': 'society-technology', 'classification': 'expertise_or_institution',
             'recorded_fact': 'No physical asset inference from expertise',
             'unresolved_fields': [], 'answer_status': 'still_unknown',
             'existing_holding_references': [],
             'new_asset_or_access_right_required': 'unknown', 'affects_acquisition_total': 'unknown',
             'shared_world_dependency': [], 'reason': 'No extra initial asset inferred',
             'completion_proposals': []},
        ],
        'remaining_unknowns': ['Unpriced and not accepted'],
    }
    return output, body


class NationAddendumContractTests(unittest.TestCase):
    def setUp(self):
        self.output, self.body = fixture()

    def component(self):
        return self.output['items'][0]['completion_proposals'][0]

    def reject(self):
        with self.assertRaises(GenerationError):
            validate_addendum(self.output, self.body)

    def test_valid_proposal_is_not_world_acceptance_and_does_not_mutate_inputs(self):
        originals = deepcopy((self.output, self.body))
        report = validate_addendum(self.output, self.body)
        self.assertTrue(report['requires_semantic_review'])
        self.assertFalse(report['accepted_initial_nation'])
        self.assertEqual((self.output, self.body), originals)

    def test_paraphrased_raw_claim_is_left_for_semantic_review(self):
        self.output['items'][0]['answer_status'] = 'already_in_raw'
        self.output['items'][0]['completion_proposals'] = []
        report = validate_addendum(self.output, self.body)
        self.assertTrue(report['requires_semantic_review'])

    def test_schema_violation_is_rejected(self):
        self.output['unexpected_free_asset'] = 'forbidden'
        self.reject()

    def test_world_nation_and_evidence_binding_are_checked_beyond_schema(self):
        for key in ('world_id', 'nation_id', 'source_evidence_sha256'):
            with self.subTest(key=key):
                self.output, self.body = fixture()
                self.output[key] = 'another-source'
                self.reject()

    def test_missing_extra_and_duplicate_targets_are_rejected(self):
        for mutation in ('missing', 'extra', 'duplicate'):
            with self.subTest(mutation=mutation):
                self.output, self.body = fixture()
                if mutation == 'missing':
                    self.output['items'].pop()
                else:
                    item = deepcopy(self.output['items'][1])
                    if mutation == 'extra':
                        item['target_id'] = 'another-target'
                    self.output['items'].append(item)
                self.reject()

    def test_component_ids_must_be_unique_across_targets(self):
        target = self.output['items'][1]
        target['answer_status'] = 'new_completion_proposal'
        duplicate = deepcopy(self.component())
        duplicate['anchor_target_id'] = target['target_id']
        target['completion_proposals'] = [duplicate]
        self.reject()

    def test_component_anchor_must_match_enclosing_item(self):
        self.component()['anchor_target_id'] = 'society-technology'
        self.reject()

    def test_unknown_original_holding_reference_is_rejected(self):
        self.output['items'][0]['existing_holding_references'] = ['other-national-holding']
        self.reject()

    def test_unknown_component_holding_id_is_rejected(self):
        self.component()['existing_holding_id'] = 'other-national-holding'
        self.reject()

    def test_existing_holding_requires_own_id_and_cannot_restate_or_replace_quantity(self):
        for mode in ('missing-id', 'same-quantity', 'changed-quantity'):
            with self.subTest(mode=mode):
                self.output, self.body = fixture()
                component = self.component()
                component['detail_subject'] = 'existing_holding'
                component['existing_holding_id'] = None if mode == 'missing-id' else 'stock-one'
                component['quantity'] = {'value': None, 'unit': None, 'meaning': 'Do not restate'}
                if mode != 'missing-id':
                    component['quantity'].update(value='100' if mode == 'same-quantity' else '200',
                                                 unit='test_unit')
                self.reject()

    def test_existing_holding_detail_with_null_quantity_is_allowed(self):
        component = self.component()
        component.update(detail_subject='existing_holding', existing_holding_id='stock-one')
        component['quantity'] = {'value': None, 'unit': None, 'meaning': 'Original quantity retained'}
        report = validate_addendum(self.output, self.body)
        self.assertFalse(report['accepted_initial_nation'])

    def test_dependency_can_reference_own_equipment_without_replacing_it(self):
        self.component().update(detail_subject='dependency', existing_holding_id='stock-one')
        report = validate_addendum(self.output, self.body)
        self.assertTrue(report['requires_semantic_review'])

    def test_non_new_status_cannot_contain_completion_proposals(self):
        for status in ('already_in_raw', 'still_unknown', 'conflict'):
            with self.subTest(status=status):
                self.output, self.body = fixture()
                self.output['items'][0]['answer_status'] = status
                self.reject()

    def test_quantity_and_unit_are_jointly_null_or_present(self):
        for value, unit in ((None, 'test_unit'), ('1', None)):
            with self.subTest(value=value, unit=unit):
                self.output, self.body = fixture()
                self.component()['quantity'].update(value=value, unit=unit)
                self.reject()

    def test_invalid_quantity_representations_are_rejected(self):
        for value in ('-1', '1e3', 'NaN', 'Infinity', '01', '1.', '.1', '9' * 257):
            with self.subTest(value=value):
                self.output, self.body = fixture()
                self.component()['quantity']['value'] = value
                self.reject()

    def test_valid_zero_decimal_and_unknown_quantity_remain_proposals(self):
        for value, unit in (('0', 'test_unit'), ('0.125', 'test_unit'), (None, None)):
            with self.subTest(value=value):
                self.output, self.body = fixture()
                self.component()['quantity'].update(value=value, unit=unit)
                report = validate_addendum(self.output, self.body)
                self.assertFalse(report['accepted_initial_nation'])

    def test_quantity_meaning_field_is_required_by_frozen_schema(self):
        del self.component()['quantity']['meaning']
        self.reject()

    def test_empty_quantity_unit_is_rejected(self):
        self.component()['quantity']['unit'] = ' '
        self.reject()

    def test_capacity_proposals_use_the_same_quantity_guards(self):
        self.component()['capacity_proposals'] = [{'value': '-2', 'unit': 'test_unit', 'meaning': 'Invalid'}]
        self.reject()

    def test_unknown_catalogue_suggestion_is_preserved_as_warning_not_rejected(self):
        self.component()['suggested_catalogue_spec_id'] = 'new-unverified-spec'
        report = validate_addendum(self.output, self.body)
        self.assertTrue(report['unresolved_catalogue_references'])
        self.assertIn('new-unverified-spec', json.dumps(report['unresolved_catalogue_references']))
        self.assertFalse(report['accepted_initial_nation'])

    def test_known_catalogue_suggestion_is_not_physical_or_price_acceptance(self):
        self.component()['suggested_catalogue_spec_id'] = 'catalog-known'
        report = validate_addendum(self.output, self.body)
        self.assertEqual(report['unresolved_catalogue_references'], [])
        self.assertFalse(report['accepted_initial_nation'])


if __name__ == '__main__':
    unittest.main()
