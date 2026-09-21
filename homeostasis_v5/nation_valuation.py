"""Exact V-A acquisition accounting; no physical or semantic approval.

Each recorded whole specification receives its full new-equivalent price,
regardless of operating/stopped/construction state. Inputs remain untouched.
Quantity rules are explicit tokens, never interpreted from free prose.
"""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from jsonschema import Draft202012Validator
from homeostasis_v5.nation_generation_contract import record_hash, schema_for

VALUATION_VERSION = 'v5-initial-holdings-fraction-1'
VALUATION_POLICY = 'new_equivalent_full_acquisition_independent_of_operating_state'
QUANTITY_RULES = frozenset(('nonnegative_integer', 'nonnegative_decimal'))


def _fraction(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def _issue(path, code):
    return {'path': path, 'code': code}


def _number(value):
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError('NUMERIC_REPRESENTATION_UNSUPPORTED')
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('INVALID_DECIMAL') from exc
    if not number.is_finite():
        raise ValueError('INVALID_DECIMAL')
    parts = number.as_tuple()
    if len(parts.digits) > 256 or abs(parts.exponent) > 1024:
        raise ValueError('NUMERIC_REPRESENTATION_UNSUPPORTED')
    if number < 0:
        raise ValueError('NEGATIVE_QUANTITY_OR_BALANCE')
    return Fraction(number)


def evaluate_initial_holdings(nation, catalog):
    """Return JSON-safe exact DERIVED accounting, not acceptance of a nation.

    The model's reported balance is a separate claim. Its exact discrepancy is
    never rounded into agreement, and requires manual review before acceptance.
    Unknown specifications/proposals have no total or inferred remaining funds.
    """
    errors, unresolved, lines = [], [], []
    report = {
        'version': VALUATION_VERSION, 'valuation_policy': VALUATION_POLICY,
        'status': 'invalid', 'accepted_initial_accounting': False,
        'world_physics_approved': False, 'manual_spec_review_required': True,
        'requires_manual_balance_review': True,
        'budget_points': _fraction(Fraction(1000)),
        'known_subtotal_points': None, 'total_acquisition_points': None,
        'exact_retained_points': None, 'over_budget_points': None,
        'reported_retained_points': nation.get('reported_retained_points') if isinstance(nation, dict) else None,
        'reported_balance_matches': None, 'reported_minus_exact_points': None,
        'reported_balance_status': 'not_evaluated',
        'nation_sha256': None, 'catalog_sha256': None,
        'priced_holdings': lines, 'errors': errors, 'unresolved': unresolved,
        'nation_uncertainties': [],
        'unperformed_checks': ['catalog_adoption_and_sources', 'capacity_claim_equivalence',
                               'operating_dependencies', 'physical_feasibility', 'prose_content_review'],
    }
    for value, stage in ((nation, 'nation'), (catalog, 'catalog')):
        if any(Draft202012Validator(schema_for(stage)).iter_errors(value)):
            errors.append(_issue(stage, stage.upper() + '_SCHEMA_ERROR'))
    if errors:
        return report
    report['nation_sha256'], report['catalog_sha256'] = record_hash(nation), record_hash(catalog)
    specs = {}
    for index, spec in enumerate(catalog['specifications']):
        if spec['spec_id'] in specs:
            errors.append(_issue(f'catalog.specifications[{index}]', 'DUPLICATE_SPEC_ID'))
        else:
            specs[spec['spec_id']] = spec
    holding_ids, source_ids, proposal_ids = set(), set(), set()
    for index, proposal in enumerate(nation['free_asset_proposals']):
        path = f'free_asset_proposals[{index}]'
        if proposal['proposal_id'] in proposal_ids:
            errors.append(_issue(path, 'DUPLICATE_PROPOSAL_ID'))
        proposal_ids.add(proposal['proposal_id'])
        unresolved.append(_issue(path, 'FREE_PROPOSAL_REQUIRES_REVIEW'))
    # General uncertainty is not automatically an unknown asset price. Preserve
    # it for the required semantic review instead of guessing its meaning.
    report['nation_uncertainties'] = list(nation['unresolved'])
    subtotal = Fraction(0)
    for index, holding in enumerate(nation['holdings']):
        path, valid = f'holdings[{index}]', True
        for key, seen, code in (('holding_id', holding_ids, 'DUPLICATE_HOLDING_ID'),
                                ('source_id', source_ids, 'DUPLICATE_SOURCE_CLAIM')):
            if holding[key] in seen:
                errors.append(_issue(path, code))
                valid = False
            seen.add(holding[key])
        if holding['proposal_id'] is not None:
            if holding['proposal_id'] not in proposal_ids:
                errors.append(_issue(path, 'UNKNOWN_PROPOSAL_REFERENCE'))
                valid = False
            else:
                unresolved.append(_issue(path, 'HOLDING_PROPOSAL_REQUIRES_REVIEW'))
        spec = specs.get(holding['spec_id'])
        if spec is None:
            unresolved.append(_issue(path, 'UNMAPPED_ASSET_SPECIFICATION'))
            continue
        quantity = holding['quantity']
        if quantity['value'] is None or quantity['unit'] is None:
            unresolved.append(_issue(path, 'UNKNOWN_HOLDING_QUANTITY'))
            continue
        if quantity['unit'] != spec['unit']:
            errors.append(_issue(path, 'HOLDING_UNIT_MISMATCH'))
            valid = False
        if spec['quantity_rules'] not in QUANTITY_RULES:
            unresolved.append(_issue(path, 'QUANTITY_RULE_REQUIRES_REVIEW'))
            continue
        try:
            amount = _number(quantity['value'])
        except ValueError as exc:
            errors.append(_issue(path, str(exc)))
            continue
        if spec['quantity_rules'] == 'nonnegative_integer' and amount.denominator != 1:
            errors.append(_issue(path, 'INTEGER_QUANTITY_REQUIRED'))
            valid = False
        if not valid:
            continue
        rate = Fraction(int(spec['points_per_unit']['numerator']), int(spec['points_per_unit']['denominator']))
        points = amount * rate
        subtotal += points
        lines.append({'holding_id': holding['holding_id'], 'source_id': holding['source_id'],
                      'spec_id': spec['spec_id'], 'unit': quantity['unit'],
                      'quantity': _fraction(amount), 'points_per_unit': _fraction(rate),
                      'acquisition_points': _fraction(points),
                      'raw_state_description': holding['state_description'],
                      'state_discount_applied': False, 'operating_status_inferred': False})
    for index, proposal in enumerate(nation['free_asset_proposals']):
        if not set(proposal['related_holding_ids']) <= holding_ids:
            errors.append(_issue(f'free_asset_proposals[{index}]', 'UNKNOWN_HOLDING_REFERENCE'))
    claimed = None
    if nation['reported_retained_points'] is not None:
        try:
            claimed = _number(nation['reported_retained_points'])
        except ValueError as exc:
            errors.append(_issue('reported_retained_points', str(exc)))
    if errors:
        return report
    report['known_subtotal_points'] = _fraction(subtotal)
    if unresolved:
        report['status'] = 'unresolved'
        return report
    remainder = Fraction(1000) - subtotal
    report['total_acquisition_points'] = _fraction(subtotal)
    if remainder < 0:
        report['status'] = 'over_budget'
        report['over_budget_points'] = _fraction(-remainder)
        errors.append(_issue('holdings', 'INITIAL_POINTS_EXCEEDED'))
        return report
    report['status'], report['accepted_initial_accounting'] = 'within_budget', True
    report['exact_retained_points'] = _fraction(remainder)
    if claimed is None:
        report['reported_balance_status'] = 'not_reported'
    else:
        matched = claimed == remainder
        report['reported_balance_matches'] = matched
        report['requires_manual_balance_review'] = not matched
        report['reported_balance_status'] = 'exact_match' if matched else 'mismatch'
        report['reported_minus_exact_points'] = _fraction(claimed - remainder)
    return report
