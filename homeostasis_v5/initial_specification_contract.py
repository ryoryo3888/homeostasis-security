"""Check proposed specifications and their provenance without adopting a world.

RAW source pointers are JSON pointers relative to ``original_nation`` (the
explicit /original_nation prefix is also accepted). Catalogue pointers may be
relative to the named specification, or include the catalogue/specifications
prefix and an index or specification ID. JSON-encoded objects inside catalogue
text fields are traversable for references, without changing their source text.
All reference values are checked; prose equivalence still needs separate review.
"""
from decimal import Decimal, InvalidOperation
import json
import re
from jsonschema import Draft202012Validator
from homeostasis_v3.contracts import digest
from homeostasis_v5.persona_generation import ensure
from model_response_json import load_response_object

_DECIMAL = re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')
_BASES = ('new_generated_initial_assumption', 'unchanged_raw_reference',
          'reference_catalogue_value', 'unresolved', 'not_applicable')
_STATUSES = ('new_initial_specification_proposed', 'unresolved',
             'shared_world_decision_required', 'conflict')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _tokens(pointer):
    ensure(_text(pointer), 'SPECIFICATION_REFERENCE_POINTER_REQUIRED')
    if pointer.startswith('#'):
        pointer = pointer[1:]
    ensure(pointer.startswith('/'), 'SPECIFICATION_INVALID_JSON_POINTER')
    tokens = pointer[1:].split('/')
    ensure(all(not re.search(r'~(?![01])', token) for token in tokens),
           'SPECIFICATION_INVALID_JSON_POINTER')
    return [token.replace('~1', '/').replace('~0', '~') for token in tokens]


def _decoded(value):
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return value
        if isinstance(decoded, (dict, list)):
            return decoded
    return value


def _resolve(root, tokens, *, encoded=False):
    value, parent, last = root, None, None
    for token in tokens:
        if encoded:
            value = _decoded(value)
        parent, last = value, token
        if isinstance(value, dict):
            ensure(token in value, 'SPECIFICATION_REFERENCE_NOT_FOUND')
            value = value[token]
        elif isinstance(value, list):
            ensure(token.isdigit() and str(int(token)) == token and int(token) < len(value),
                   'SPECIFICATION_REFERENCE_NOT_FOUND')
            value = value[int(token)]
        else:
            ensure(False, 'SPECIFICATION_REFERENCE_NOT_FOUND')
    return value, parent, last


def _raw_reference(original, pointer):
    tokens = _tokens(pointer)
    if tokens[0] == 'original_nation':
        tokens = tokens[1:]
    return _resolve(original, tokens)


def _catalogue_reference(specs, spec_id, pointer):
    ensure(spec_id in specs, 'SPECIFICATION_UNKNOWN_CATALOGUE_SPEC')
    tokens = _tokens(pointer)
    if tokens[0] == 'common_asset_specifications':
        tokens = tokens[1:]
    if tokens and tokens[0] == 'specifications':
        ensure(len(tokens) > 1, 'SPECIFICATION_REFERENCE_NOT_FOUND')
        selector, tokens = tokens[1], tokens[2:]
        ordered_ids = list(specs)
        selected = (ordered_ids[int(selector)] if selector.isdigit()
                    and str(int(selector)) == selector and int(selector) < len(ordered_ids)
                    else selector)
        ensure(selected == spec_id, 'SPECIFICATION_CATALOGUE_POINTER_MISMATCH')
    elif tokens and tokens[0] == spec_id:
        tokens = tokens[1:]
    return _resolve(specs[spec_id], tokens, encoded=True)


def _same_value(proposed, observed):
    """Permit decimal presentation changes, never a changed physical quantity."""
    if isinstance(observed, str) and proposed == observed:
        return True
    if isinstance(observed, bool):
        return proposed == ('true' if observed else 'false')
    if isinstance(observed, (str, int, float)) and _text(proposed):
        left, right = str(proposed), str(observed)
        if _DECIMAL.fullmatch(left) and _DECIMAL.fullmatch(right):
            try:
                return Decimal(left) == Decimal(right)
            except InvalidOperation:
                return False
    return False


def _check_reference_value(field, resolved):
    observed, parent, last = resolved
    # A pointer to a quantity object is unambiguous as well as /quantity/value.
    if isinstance(observed, dict) and 'value' in observed:
        if 'unit' in observed:
            ensure(field['unit'] == observed['unit'], 'SPECIFICATION_REFERENCE_UNIT_MISMATCH')
        observed = observed['value']
    elif last == 'value' and isinstance(parent, dict) and 'unit' in parent:
        ensure(field['unit'] == parent['unit'], 'SPECIFICATION_REFERENCE_UNIT_MISMATCH')
    ensure(_same_value(field['value'], observed), 'SPECIFICATION_REFERENCE_VALUE_MISMATCH')


def _field(field, original, specs):
    ensure(_text(field['field_name']) and _text(field['meaning']), 'SPECIFICATION_FIELD_MEANING_REQUIRED')
    for key in ('value', 'unit', 'source_pointer', 'unresolved_reason', 'reference_spec_id', 'reference_pointer'):
        ensure(field[key] is None or _text(field[key]), 'SPECIFICATION_EMPTY_FIELD')
    basis = field['basis']
    source = field['source_pointer']
    ref_id, ref_pointer = field['reference_spec_id'], field['reference_pointer']
    if basis in ('unresolved', 'not_applicable'):
        ensure(field['value'] is None and source is None and ref_id is None and ref_pointer is None,
               'SPECIFICATION_UNRESOLVED_VALUE_OR_REFERENCE')
        # A unit may still be known while its magnitude is unresolved.
        ensure(_text(field['unresolved_reason']) or (basis == 'not_applicable' and _text(field['meaning'])),
               'SPECIFICATION_UNRESOLVED_REASON_REQUIRED')
    elif basis == 'new_generated_initial_assumption':
        ensure(_text(field['value']), 'SPECIFICATION_PROPOSED_VALUE_REQUIRED')
        ensure(source is None and ref_id is None and ref_pointer is None,
               'SPECIFICATION_NEW_VALUE_WITH_SOURCE_CLAIM')
    elif basis == 'unchanged_raw_reference':
        ensure(_text(field['value']) and _text(source), 'SPECIFICATION_RAW_REFERENCE_REQUIRED')
        ensure(ref_id is None and ref_pointer is None, 'SPECIFICATION_MIXED_PROVENANCE')
        _check_reference_value(field, _raw_reference(original, source))
    elif basis == 'reference_catalogue_value':
        ensure(_text(field['value']) and _text(ref_id) and _text(ref_pointer),
               'SPECIFICATION_CATALOGUE_REFERENCE_REQUIRED')
        ensure(source is None, 'SPECIFICATION_MIXED_PROVENANCE')
        _check_reference_value(field, _catalogue_reference(specs, ref_id, ref_pointer))


def validate_specification(output, request_body):
    """Return a mechanical provenance report; never mutate either input.

    No numeric detail minimum is imposed. A descriptive proposal can be useful;
    whether it concretely specifies the target is a separate semantic gate.
    Reference checks do not establish catalogue equivalence, acquisition price,
    legal ownership, operating feasibility, or world acceptance.
    """
    schema = request_body['generationConfig']['responseJsonSchema']
    ensure(not any(Draft202012Validator(schema).iter_errors(output)), 'INITIAL_SPECIFICATION_SCHEMA_ERROR')
    context = load_response_object(request_body['contents'][0]['parts'][1]['text'])
    original = context['original_nation']
    ensure(all(output[key] == context[key] for key in ('world_id', 'nation_id', 'source_evidence_sha256')),
           'INITIAL_SPECIFICATION_SOURCE_MISMATCH')
    targets = {t['target_id']: t for t in context['targets']}
    ensure(len(targets) == len(context['targets']), 'DUPLICATE_INPUT_TARGET')
    ids = [item['target_id'] for item in output['items']]
    ensure(len(ids) == len(set(ids)) and set(ids) == set(targets), 'EXACT_TARGET_COVERAGE_REQUIRED')
    holdings = {h['holding_id'] for h in original['holdings']}
    regions = set(original['geography_ref']['territory_region_ids'])
    specs = {s['spec_id']: s for s in context['common_asset_specifications']['specifications']}
    ensure(len(specs) == len(context['common_asset_specifications']['specifications']), 'DUPLICATE_INPUT_CATALOGUE_SPEC')
    components, bases = set(), {basis: 0 for basis in _BASES}
    statuses = {status: 0 for status in _STATUSES}
    remaining_unknown_count = dependency_count = unknown_ownership_count = 0
    for item in output['items']:
        target = targets[item['target_id']]
        ensure(item['source_pointer'] == target['source_pointer'], 'SPECIFICATION_TARGET_POINTER_MISMATCH')
        _raw_reference(original, target['source_pointer'])
        ensure(_text(item['reason']), 'SPECIFICATION_ITEM_REASON_REQUIRED')
        status = item['proposal_status']; statuses[status] += 1
        proposals = item['initial_specification_proposals']
        if status != 'new_initial_specification_proposed':
            ensure(not proposals, 'NON_PROPOSAL_STATUS_WITH_NEW_DETAILS')
        for component in proposals:
            cid = component['component_id']
            ensure(_text(cid) and cid not in components, 'DUPLICATE_OR_EMPTY_COMPONENT_ID')
            components.add(cid)
            ensure(_text(component['description']), 'SPECIFICATION_COMPONENT_DESCRIPTION_REQUIRED')
            ensure(set(component['supporting_original_holding_ids']) <= holdings, 'UNKNOWN_HOLDING_REFERENCE')
            ensure(set(component['location_region_ids']) <= regions, 'FOREIGN_REGION_REFERENCE')
            ensure(component['reference_spec_id'] is None or component['reference_spec_id'] in specs,
                   'SPECIFICATION_UNKNOWN_CATALOGUE_SPEC')
            ownership = component['ownership_or_access_proposal']
            ensure(ownership is None or _text(ownership), 'SPECIFICATION_EMPTY_OWNERSHIP')
            if ownership is None:
                ensure(any(_text(reason) for reason in component['remaining_unknowns']),
                       'SPECIFICATION_UNKNOWN_OWNERSHIP_REASON_REQUIRED')
                unknown_ownership_count += 1
            for field in component['specification_fields']:
                _field(field, original, specs)
                bases[field['basis']] += 1
            remaining_unknown_count += len(component['remaining_unknowns'])
            dependency_count += len(component['operating_dependencies_still_to_resolve'])
    return {
        'version': 'v5-initial-specification-validation-1',
        'schema_and_reference_checks_passed': True,
        'checked_targets': len(ids), 'proposed_components': len(components),
        'proposal_status_counts': statuses, 'field_basis_counts': bases,
        'new_proposed_fields': bases['new_generated_initial_assumption'],
        'unresolved_fields': bases['unresolved'],
        'unresolved_targets': statuses['unresolved'] + statuses['shared_world_decision_required'] + statuses['conflict'],
        'remaining_unknown_statements': remaining_unknown_count,
        'unresolved_operating_dependencies': dependency_count,
        'unknown_ownership_components': unknown_ownership_count,
        'source_evidence_sha256': context['source_evidence_sha256'], 'output_sha256': digest(output),
        'requires_semantic_review': True, 'accepted_initial_nation': False,
        'world_physics_approved': False, 'original_values_modified': False,
        'unperformed_checks': ['descriptive_novelty_and_target_specificity', 'prose_consistency_with_original',
                               'catalogue_equivalence', 'acquisition_pricing', 'legal_ownership',
                               'physical_feasibility', 'initial_world_acceptance'],
        'interpretation': 'New values remain generated initial proposals; reference checks do not adopt them.'}
