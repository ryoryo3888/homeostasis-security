"""Phase-two deterministic physical accounting, not an experiment/Agent runner.

Consumption draws on opening stock after explicit loss. Production becomes
available at closing, hence cannot fund consumption earlier in the same step.
No transfers, routes, recovery effects or policy allocation are executed here.
"""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from .contracts import (ID, TEXT, UINT, POS, HASH, SCHEMA, obj, arr, enum,
                        validate_world, require, indexed, digest)

PROFILE = obj({'capacity_id': ID, 'resource_id': {'anyOf': [ID, {'type': 'null'}]},
               'current_capacity': UINT, 'maximum_capacity': UINT,
               'utilization_ppm': {'type': 'integer', 'minimum': 0, 'maximum': 1000000}})
ORIGIN = obj({'path': TEXT, 'kind': enum('existing_asset', 'synthetic_assumption', 'derived'),
              'explanation': TEXT, 'source': TEXT})
BASELINE = obj({'kind': enum('synthetic_baseline_world'), 'contract_version': enum('v3'),
    'physical_schema_version': enum(1), 'world': SCHEMA, 'capacity_profiles': arr(PROFILE),
    'provenance': arr(ORIGIN), 'production_availability': enum('closing_stock'),
    'interpretation': TEXT})


def numeric_paths(value, path=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from numeric_paths(child, path+'/'+key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from numeric_paths(child, path+'/'+str(index))
    elif type(value) is int:
        yield path


def pointer(value, path):
    for key in path.strip('/').split('/'):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def validate_baseline(data):
    Draft202012Validator(BASELINE).validate(data)
    world = data['world']; validate_world(world)
    require(not world['dependencies'] and not world['routes'], 'Phase two does not execute networks')
    require(bool(world['countries']) and bool(world['resources']), 'Empty physical world')
    require(all(not a['in_transit'] and a['location'] == a['owner'] for a in world['accounts']),
            'Phase-two inventory must be domestic, not transit')
    capacities = indexed(world['capacities'], 'capacity_id')
    profiles = indexed(data['capacity_profiles'], 'capacity_id')
    require(set(capacities) == set(profiles), 'Missing capacity profile')
    resources = indexed(world['resources'], 'resource_id')
    accounts = {}
    for account in world['accounts']:
        key = (account['owner'], account['resource_id'])
        require(key not in accounts, 'Duplicate domestic resource account')
        accounts[key] = account
    production = {}
    for cid, cap in capacities.items():
        profile = profiles[cid]
        require(profile['current_capacity'] <= profile['maximum_capacity'], 'Current capacity exceeds maximum')
        actual = profile['current_capacity'] * profile['utilization_ppm'] // 1000000
        require(cap['available'] == actual and cap['reserved'] == 0, 'Capacity operating value mismatch')
        if cap['category'] == 'production':
            resource = profile['resource_id']
            require(resource in resources, 'Unknown production resource')
            require(cap['unit_id'] == resources[resource]['unit_id'] + '_per_turn', 'Production unit mismatch')
            key = (cap['owner'], resource)
            require(key not in production, 'Duplicate production profile')
            production[key] = cap
        else:
            require(profile['resource_id'] is None, 'Service capability is not a resource stock')
            require(cap['unit_id'] == cap['category'] + '_unit_per_turn', 'Service unit mismatch')
    demands = {}
    for country in world['countries']:
        cid = country['state_id']
        for demand in country['demands']:
            key = (cid, demand['resource_id'])
            require(key not in demands, 'Duplicate essential demand')
            demands[key] = demand
        for resource in resources:
            key = (cid, resource)
            require(key in accounts and key in demands and key in production, 'Incomplete country/resource state')
        for category in ('transport', 'recovery'):
            require(sum(c['owner'] == cid and c['category'] == category for c in capacities.values()) == 1,
                    'Missing or duplicate service capacity')
    origins = indexed(data['provenance'], 'path')
    expected = set(numeric_paths(world, '/world')) | set(numeric_paths(data['capacity_profiles'], '/capacity_profiles'))
    require(set(origins) == expected, 'Every numeric initial value requires exact provenance')
    for path in origins:
        require(type(pointer(data, path)) is int, 'Provenance does not identify an initial numeric value')
    return data


def load_baseline(path):
    return validate_baseline(json.loads(Path(path).read_text(encoding='utf-8')))


def distribution(world):
    """Separate stock geography from totals; no welfare or self-reliance score."""
    validate_world(world)
    by_country = {c['state_id']: {r['resource_id']: 0 for r in world['resources']} for c in world['countries']}
    transit = {r['resource_id']: 0 for r in world['resources']}
    for account in world['accounts']:
        if account['in_transit']:
            transit[account['resource_id']] += account['balance']
        else:
            by_country[account['owner']][account['resource_id']] += account['balance']
    domestic = {r: sum(v[r] for v in by_country.values()) for r in transit}
    return {'by_country': by_country, 'domestic_total': domestic, 'in_transit_total': transit,
            'total': {r: domestic[r]+transit[r] for r in transit}}


def self_reliance_components(data):
    """Inputs only; reserve-only coverage excludes production and external supply."""
    validate_baseline(data)
    world = data['world']
    profiles = {p['capacity_id']: p for p in data['capacity_profiles']}
    out = {}
    for country in world['countries']:
        cid = country['state_id']; out[cid] = {}
        for demand in country['demands']:
            rid = demand['resource_id']
            account = next(a for a in world['accounts'] if a['owner'] == cid and a['resource_id'] == rid)
            cap = next(c for c in world['capacities'] if c['owner'] == cid and c['category'] == 'production'
                       and profiles[c['capacity_id']]['resource_id'] == rid)
            q = demand['quantity']
            out[cid][rid] = {'domestic_stock': account['balance'], 'essential_demand': q,
                'production_per_turn': cap['available'],
                'reserve_only_full_turns': account['balance']//q if q else None,
                'reserve_coverage_basis': 'no production, no external supply, constant demand',
                'zero_demand': q == 0}
    return out


def physical_step(data, *, losses=None):
    """One pure accounting unit test operation. No simulation loop or research run."""
    validate_baseline(data)
    losses = {} if losses is None else deepcopy(losses)
    accounts = indexed(data['world']['accounts'], 'account_id')
    require(type(losses) is dict and set(losses) <= set(accounts), 'Unknown loss account')
    for aid, event in losses.items():
        Draft202012Validator(obj({'quantity': UINT, 'evidence_id': ID})).validate(event)
        require(event['quantity'] <= accounts[aid]['balance'], 'Loss exceeds opening stock')
    profiles = indexed(data['capacity_profiles'], 'capacity_id')
    world = data['world']; rows = []
    for country in sorted(world['countries'], key=lambda c: c['state_id']):
        cid = country['state_id']
        for demand in sorted(country['demands'], key=lambda d: d['resource_id']):
            rid = demand['resource_id']; q = demand['quantity']
            account = next(a for a in accounts.values() if a['owner'] == cid and a['resource_id'] == rid)
            cap = next(c for c in world['capacities'] if c['owner'] == cid and c['category'] == 'production'
                       and profiles[c['capacity_id']]['resource_id'] == rid)
            aid = account['account_id']; loss = losses.get(aid, {}).get('quantity', 0)
            consumption = min(q, account['balance']-loss)
            production = cap['available']
            row = {'state_id': cid, 'resource_id': rid, 'unit_id': account['unit_id'], 'account_id': aid,
                'opening_stock': account['balance'], 'production': production, 'consumption': consumption,
                'loss': loss, 'incoming': 0, 'outgoing': 0, 'in_transit': 0,
                'closing_stock': account['balance']+production-consumption-loss,
                'required_demand': q, 'fulfilled_demand': consumption, 'unmet_demand': q-consumption,
                'fulfillment_rate': consumption/q if q else None,
                'evidence': {'opening_world_hash': digest(world), 'production_capacity_id': cap['capacity_id'],
                    'production_rule': 'floor(current_capacity * utilization_ppm / 1000000); available at closing',
                    'production_source': 'synthetic exogenous production capacity; upstream inputs not modeled',
                    'demand_function_id': demand['function_id'], 'loss_evidence_id': losses.get(aid, {}).get('evidence_id')}}
            rows.append(row)
    closing = deepcopy(world)
    balances = {r['account_id']: r['closing_stock'] for r in rows}
    for account in closing['accounts']: account['balance'] = balances[account['account_id']]
    validate_world(closing)
    result = {'kind': 'offline_physical_check', 'contract_version': 'v3', 'input_hash': digest(data),
              'ledger': rows, 'closing_world': closing, 'distribution': distribution(closing)}
    check_balance(result)
    return result


def check_balance(result):
    """Arithmetic invariant check; validate_step also binds production and demand to input."""
    indexed(result['ledger'], 'account_id')
    for r in result['ledger']:
        for name in ('opening_stock','production','consumption','loss','incoming','outgoing',
                     'in_transit','closing_stock','required_demand','fulfilled_demand','unmet_demand'):
            require(type(r[name]) is int and r[name] >= 0, 'Invalid ledger quantity')
        require(r['opening_stock']+r['production']+r['incoming']-r['consumption']-r['outgoing']-r['loss']
                == r['closing_stock'], 'Unbalanced resource ledger')
        require(r['consumption'] == r['fulfilled_demand'] and
                r['fulfilled_demand']+r['unmet_demand'] == r['required_demand'], 'Invalid shortage')


def validate_step(data, result, *, losses=None):
    """Reject tampered balanced records as well as arithmetic inconsistencies."""
    require(result == physical_step(data, losses=losses), 'Physical evidence differs from declared input')
