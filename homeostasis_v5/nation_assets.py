"""Pure point accounting, without an adopted asset catalog or physical rules.

The caller supplies a versioned price table with explicit capability specification
IDs and units. Names are descriptive only. Each holding is an atomic purchase;
groups reference those holdings for display and never add purchases. A source_id
identifies the physical stock/equipment/capacity being charged: reusing it in two
holdings is rejected. This cannot detect the same real capacity falsely declared
under different source IDs; the world/initialization validator must check that.

No population, terrain, prices, capabilities, or economic assumptions are built
in. An unknown specification/price stays unresolved. ``within_budget`` describes
only arithmetic; it does not accept a nation, unused-point policy, or physical
feasibility. All inputs are left unchanged. There is no I/O or provider access.

To bound decimal memory use, supported input representations have at most 256
coefficient digits and an exponent between -1024 and 1024 (decimal strings at
most 1024 characters). This is a calculator limitation, not an adopted limit on
national capabilities. Unsupported values are rejected, never rounded or reset.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, Inexact, MAX_EMAX, MIN_EMIN, Rounded, localcontext
from typing import Literal


_MAX_DIGITS = 256
_MAX_EXPONENT = 1024
_MAX_INPUT_CHARACTERS = 1024


@dataclass(frozen=True)
class Issue:
    path: str
    code: str


@dataclass(frozen=True)
class PricedHolding:
    holding_id: str
    source_id: str
    spec_id: str
    unit: str
    quantity: Decimal
    points_per_unit: Decimal
    points: Decimal


@dataclass(frozen=True)
class AssetEstimate:
    status: Literal['invalid', 'unpriced', 'within_budget', 'over_budget']
    price_table_version: str | None
    budget_points: Decimal | None
    known_subtotal_points: Decimal | None
    total_points: Decimal | None
    unused_points: Decimal | None
    overage_points: Decimal | None
    priced_holdings: tuple[PricedHolding, ...]
    errors: tuple[Issue, ...]
    unresolved: tuple[Issue, ...]


def _number(value: object, path: str, errors: list[Issue], *, positive=False):
    # Floats have already lost their decimal provenance; bool is not a quantity.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        errors.append(Issue(path, 'invalid_decimal'))
        return None
    # Refuse pathological inputs before parsing or allocating decimal precision.
    if ((isinstance(value, str) and len(value) > _MAX_INPUT_CHARACTERS)
            or (isinstance(value, int) and value.bit_length() > 852)):
        errors.append(Issue(path, 'numeric_range_unsupported'))
        return None
    try:
        number = Decimal(value)
    except (ValueError, ArithmeticError):
        errors.append(Issue(path, 'invalid_decimal'))
        return None
    if not number.is_finite() or number < 0 or (positive and number == 0):
        errors.append(Issue(path, 'invalid_decimal'))
        return None
    parts = number.as_tuple()
    if len(parts.digits) > _MAX_DIGITS or abs(parts.exponent) > _MAX_EXPONENT:
        errors.append(Issue(path, 'numeric_range_unsupported'))
        return None
    return number


def _record(value, required, optional, path, errors):
    if not isinstance(value, Mapping):
        errors.append(Issue(path, 'expected_object'))
        return False
    if not required <= value.keys() or value.keys() - required - optional:
        errors.append(Issue(path, 'unexpected_or_missing_fields'))
        return False
    return True


def _text(value, path, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(Issue(path, 'expected_nonempty_string'))
        return False
    return True


def _list(value, path, errors):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        errors.append(Issue(path, 'expected_sequence'))
        return ()
    return value


def _multiply(left: Decimal, right: Decimal) -> Decimal:
    # Decimal's ambient (normally 28-digit) precision must not hide an overrun.
    with localcontext() as context:
        context.prec = max(1, len(left.as_tuple().digits) + len(right.as_tuple().digits))
        context.Emax, context.Emin = MAX_EMAX, MIN_EMIN
        context.traps[Inexact] = context.traps[Rounded] = True
        return left * right


def _sum(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal(0)
    with localcontext() as context:
        context.prec = max(1, max(value.adjusted() for value in values)
                           - min(value.as_tuple().exponent for value in values)
                           + len(str(len(values))) + 2)
        context.Emax, context.Emin = MAX_EMAX, MIN_EMIN
        context.traps[Inexact] = context.traps[Rounded] = True
        return sum(values, Decimal(0))


def estimate_assets(holdings, price_table, *, groups=(), budget_points='1000') -> AssetEstimate:
    """Quote atomic holdings using caller-supplied specifications and prices.

    price_table = {version: str, entries: [{spec_id, unit, points_per_unit}]}
    holding = {holding_id, source_id, spec_id, unit, quantity, name?: str}
    group = {group_id, holding_ids: [holding_id, ...], name?: str}

    Decimal fields accept Decimal, integer, or decimal string, never float.
    A price of None explicitly means unresolved; zero/negative prices are invalid
    (no free-asset rule is defined). Missing specs are unresolved, unit mismatches
    are invalid, and no unit conversion is guessed. Distinct spec IDs must fully
    describe capability, period, and any physical conditions; this helper cannot
    check whether an external specification document is scientifically adequate.

    Invalid structure takes precedence over unresolved prices. With unresolved
    items only a known subtotal is returned, never a total or remaining budget.
    Exact decimal arithmetic is independent of the process decimal context.
    """
    errors: list[Issue] = []
    unresolved: list[Issue] = []
    lines: list[PricedHolding] = []
    budget = _number(budget_points, 'budget_points', errors)
    version = None
    prices = {}
    if _record(price_table, {'version', 'entries'}, set(), 'price_table', errors):
        if _text(price_table['version'], 'price_table.version', errors):
            version = price_table['version']
        for index, entry in enumerate(_list(price_table['entries'], 'price_table.entries', errors)):
            path = f'price_table.entries[{index}]'
            if not _record(entry, {'spec_id', 'unit', 'points_per_unit'}, set(), path, errors):
                continue
            if not all([_text(entry[key], f'{path}.{key}', errors) for key in ('spec_id', 'unit')]):
                continue
            spec = entry['spec_id']
            if spec in prices:
                errors.append(Issue(path, 'duplicate_spec_id'))
                continue
            rate = None if entry['points_per_unit'] is None else _number(
                entry['points_per_unit'], f'{path}.points_per_unit', errors, positive=True)
            prices[spec] = (entry['unit'], rate)

    holding_ids, source_ids = set(), set()
    for index, holding in enumerate(_list(holdings, 'holdings', errors)):
        path = f'holdings[{index}]'
        if not _record(holding, {'holding_id', 'source_id', 'spec_id', 'unit', 'quantity'}, {'name'}, path, errors):
            continue
        keys = ('holding_id', 'source_id', 'spec_id', 'unit') + (('name',) if 'name' in holding else ())
        if not all([_text(holding[key], f'{path}.{key}', errors) for key in keys]):
            continue
        hid, source, spec = holding['holding_id'], holding['source_id'], holding['spec_id']
        if hid in holding_ids:
            errors.append(Issue(path, 'duplicate_holding_id'))
        if source in source_ids:
            errors.append(Issue(path, 'duplicate_source_claim'))
        holding_ids.add(hid)
        source_ids.add(source)
        quantity = _number(holding['quantity'], f'{path}.quantity', errors)
        if spec not in prices:
            unresolved.append(Issue(path, 'unknown_spec_id'))
            continue
        unit, rate = prices[spec]
        if holding['unit'] != unit:
            errors.append(Issue(path, 'unit_mismatch'))
        elif rate is None:
            unresolved.append(Issue(path, 'unpriced_spec'))
        elif quantity is not None:
            try:
                points = _multiply(quantity, rate)
            except ArithmeticError:
                errors.append(Issue(path, 'numeric_range_unsupported'))
            else:
                lines.append(PricedHolding(hid, source, spec, unit, quantity, rate, points))

    group_ids = set()
    for index, group in enumerate(_list(groups, 'groups', errors)):
        path = f'groups[{index}]'
        if not _record(group, {'group_id', 'holding_ids'}, {'name'}, path, errors):
            continue
        if not _text(group['group_id'], f'{path}.group_id', errors):
            continue
        if 'name' in group:
            _text(group['name'], f'{path}.name', errors)
        if group['group_id'] in group_ids or group['group_id'] in holding_ids:
            errors.append(Issue(path, 'duplicate_group_id'))
        group_ids.add(group['group_id'])
        seen = set()
        for ref in _list(group['holding_ids'], f'{path}.holding_ids', errors):
            if not _text(ref, f'{path}.holding_ids', errors):
                continue
            if ref not in holding_ids:
                errors.append(Issue(path, 'unknown_holding_reference'))
            if ref in seen:
                errors.append(Issue(path, 'duplicate_holding_reference'))
            seen.add(ref)

    if errors:
        return AssetEstimate('invalid', version, budget, None, None, None, None, (), tuple(errors), tuple(unresolved))
    try:
        subtotal = _sum([line.points for line in lines])
        difference = _sum((budget, subtotal.copy_negate())) if not unresolved else None
    except ArithmeticError:
        errors.append(Issue('holdings', 'numeric_range_unsupported'))
        return AssetEstimate('invalid', version, budget, None, None, None, None, (), tuple(errors), tuple(unresolved))
    if unresolved:
        return AssetEstimate('unpriced', version, budget, subtotal, None, None, None, tuple(lines), (), tuple(unresolved))
    return AssetEstimate(
        'within_budget' if difference >= 0 else 'over_budget', version, budget, subtotal, subtotal,
        difference if difference >= 0 else Decimal(0),
        difference.copy_negate() if difference < 0 else Decimal(0), tuple(lines), (), (),
    )
