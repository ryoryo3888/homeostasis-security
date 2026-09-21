"""Validate addendum shape and source bindings, never approve physical facts."""
from decimal import Decimal
import re
from jsonschema import Draft202012Validator
from homeostasis_v3.contracts import digest
from homeostasis_v5.persona_generation import ensure
from model_response_json import load_response_object

DECIMAL = re.compile(r'^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')


def _quantity(value):
    amount, unit = value['value'], value['unit']
    ensure((amount is None) == (unit is None), 'QUANTITY_UNIT_PAIR_REQUIRED')
    if amount is not None:
        ensure(isinstance(amount, str) and len(amount) <= 256 and DECIMAL.fullmatch(amount)
               and Decimal(amount).is_finite() and Decimal(amount) >= 0, 'INVALID_PROPOSED_QUANTITY')
        ensure(isinstance(unit, str) and bool(unit.strip()) and len(unit) <= 256, 'QUANTITY_UNIT_REQUIRED')


def validate_addendum(output, request_body):
    """A checked response remains a proposal requiring separate content review.

    Text assertions cannot be proved by schema or numerics. In particular,
    already_in_raw labels and proposed catalogue equivalence remain unchecked
    semantic claims; they never update original holdings or world state.
    """
    schema = request_body['generationConfig']['responseJsonSchema']
    ensure(not any(Draft202012Validator(schema).iter_errors(output)), 'ADDENDUM_SCHEMA_ERROR')
    context = load_response_object(request_body['contents'][0]['parts'][1]['text'])
    original = context['original_nation']
    ensure(output['world_id'] == context['world_id']
           and output['nation_id'] == context['nation_id']
           and output['source_evidence_sha256'] == context['source_evidence_sha256'], 'ADDENDUM_SOURCE_MISMATCH')
    targets = {t['target_id']: t for t in context['review_targets']}
    ensure(len(targets) == len(context['review_targets']), 'DUPLICATE_INPUT_TARGET')
    ids = [i['target_id'] for i in output['items']]
    ensure(len(ids) == len(set(ids)) and set(ids) == set(targets), 'EXACT_TARGET_COVERAGE_REQUIRED')
    holdings = {h['holding_id']: h for h in original['holdings']}
    regions = set(original['geography_ref']['territory_region_ids'])
    catalogue = {s['spec_id'] for s in context['common_asset_specifications']['specifications']}
    components, unmapped = set(), []
    statuses = {s:0 for s in ('already_in_raw', 'new_completion_proposal', 'still_unknown', 'conflict')}
    for item in output['items']:
        refs = item['existing_holding_references']
        ensure(len(refs) == len(set(refs)) and set(refs) <= set(holdings), 'INVALID_HOLDING_REFERENCE')
        status = item['answer_status']; statuses[status] += 1
        proposals = item['completion_proposals']
        if status != 'new_completion_proposal':
            ensure(not proposals, 'NON_PROPOSAL_STATUS_WITH_NEW_DETAILS')
        # No required minimum detail count: uncertainty does not force invention.
        for detail in proposals:
            component = detail['component_id']
            ensure(component not in components, 'DUPLICATE_COMPONENT_ID')
            components.add(component)
            ensure(detail['anchor_target_id'] == item['target_id'], 'COMPONENT_ANCHOR_MISMATCH')
            hid = detail['existing_holding_id']
            ensure(hid is None or hid in holdings, 'UNKNOWN_HOLDING_REFERENCE')
            ensure(set(detail['location_region_ids']) <= regions, 'FOREIGN_REGION_REFERENCE')
            _quantity(detail['quantity'])
            for quantity in detail['capacity_proposals']:
                _quantity(quantity)
            if detail['detail_subject'] == 'existing_holding':
                ensure(hid is not None, 'EXISTING_HOLDING_ID_REQUIRED')
                ensure(detail['quantity']['value'] is None and detail['quantity']['unit'] is None,
                       'EXISTING_QUANTITY_MUTATION_FORBIDDEN')
            # A dependency may link the own holding it supports. Its quantity
            # belongs to that proposed dependency and cannot replace the asset.
            spec = detail['suggested_catalogue_spec_id']
            if spec is not None and spec not in catalogue:
                unmapped.append({'target_id': item['target_id'], 'component_id': component,
                                 'suggested_catalogue_spec_id': spec})
    return {'version': 'v5-nation-addendum-validation-1', 'schema_and_reference_checks_passed': True,
            'checked_targets': len(ids), 'proposed_components': len(components), 'answer_status_counts': statuses,
            'unresolved_catalogue_references': unmapped,
            'source_evidence_sha256': context['source_evidence_sha256'], 'output_sha256': digest(output),
            'requires_semantic_review': True, 'accepted_initial_nation': False,
            'world_physics_approved': False, 'original_values_modified': False,
            'unperformed_checks': ['prose_claims_match_original', 'new_details_do_not_contradict_original',
                                   'catalogue_specification_equivalence', 'acquisition_pricing',
                                   'physical_feasibility', 'initial_world_acceptance'],
            'interpretation': 'Labels and quantities are generated proposals, not recovered facts or adopted capacities.'}
