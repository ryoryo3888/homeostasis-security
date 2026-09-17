"""Phase-three possibility graph and explicit offline transit checks only.

No Agent, optimizer, trade agreement, automatic rerouting or cascade runner.
Route reachability is not a claim that a transaction can or will occur.
"""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from .contracts import ID, TEXT, UINT, POS, HASH, IDS, obj, arr, enum, require, indexed, digest
from .physical import validate_baseline, self_reliance_components

PROVENANCE = obj({'kind': enum('existing_asset', 'synthetic_assumption', 'derived'),
                  'source': TEXT, 'reason': TEXT})
COST = obj({'resource_id': ID, 'stock_unit': ID, 'transport_units_per_stock_unit': POS})
GROUP = obj({'group_id': ID, 'capacity': UINT, 'unit': enum('transport_unit_per_turn'),
             'provenance': PROVENANCE})
ROUTE = obj({'route_id': ID, 'source': ID, 'destination': ID, 'resource_types': IDS,
             'capacity': UINT, 'delay': POS, 'availability': {'type': 'boolean'},
             'shared_capacity_group': ID, 'provenance': PROVENANCE})
PRODUCTION_DEPENDENCY = obj({'dependency_id': ID, 'producer_state': ID,
    'production_capacity_id': ID, 'output_resource': ID, 'input_resource': ID,
    'input_unit': ID, 'output_unit': ID, 'required_input': POS, 'output_batch': POS,
    'relationship': enum('required_input_per_output_batch'),
    'output_delay': POS, 'provenance': PROVENANCE})
NETWORK = obj({'contract_version': enum('v3'), 'network_schema_version': enum(1),
    'kind': enum('synthetic_baseline_network'), 'baseline_hash': HASH,
    'transport_costs': arr(COST), 'shared_capacities': arr(GROUP), 'routes': arr(ROUTE),
    'production_dependencies': arr(PRODUCTION_DEPENDENCY), 'provenance': PROVENANCE})


def validate_network(network, baseline):
    Draft202012Validator(NETWORK).validate(network)
    validate_baseline(baseline)
    require(network['baseline_hash'] == digest(baseline), 'Network/baseline version mismatch')
    world = baseline['world']
    countries = indexed(world['countries'], 'state_id')
    resources = indexed(world['resources'], 'resource_id')
    capacities = indexed(world['capacities'], 'capacity_id')
    profiles = indexed(baseline['capacity_profiles'], 'capacity_id')
    groups = indexed(network['shared_capacities'], 'group_id')
    costs = indexed(network['transport_costs'], 'resource_id')
    require(set(costs) == set(resources), 'Every resource needs an explicit transport conversion')
    for rid, cost in costs.items():
        require(cost['stock_unit'] == resources[rid]['unit_id'], 'Transport stock unit mismatch')
    indexed(network['routes'], 'route_id')
    for route in network['routes']:
        require(route['source'] in countries and route['destination'] in countries, 'Unknown route endpoint')
        require(route['source'] != route['destination'], 'Self route forbidden')
        require(bool(route['resource_types']) and set(route['resource_types']) <= set(resources), 'Invalid route resource')
        require(route['shared_capacity_group'] in groups, 'Unknown shared capacity')
        # No reverse edge or automatic capacity is inferred.
    indexed(network['production_dependencies'], 'dependency_id')
    dependency_pairs = set()
    for dep in network['production_dependencies']:
        require(dep['producer_state'] in countries, 'Unknown producer')
        require(dep['input_resource'] in resources and dep['output_resource'] in resources, 'Unknown production resource')
        require(dep['input_resource'] != dep['output_resource'], 'Direct self production dependency forbidden')
        require(dep['production_capacity_id'] in capacities, 'Unknown production capacity')
        cap = capacities[dep['production_capacity_id']]
        profile = profiles[dep['production_capacity_id']]
        require(cap['category'] == 'production' and cap['owner'] == dep['producer_state'] and
                profile['resource_id'] == dep['output_resource'], 'Production capability mismatch')
        require(dep['input_unit'] == resources[dep['input_resource']]['unit_id'] and
                dep['output_unit'] == resources[dep['output_resource']]['unit_id'], 'Production units mismatch')
        key = (dep['production_capacity_id'], dep['input_resource'])
        require(key not in dependency_pairs, 'Duplicate production input dependency')
        dependency_pairs.add(key)
    # Longer dependency cycles are permitted as structure; nothing is produced here.
    return network


def load_network(path, baseline):
    return validate_network(json.loads(Path(path).read_text(encoding='utf-8')), baseline)


def usable_routes(network, resource):
    groups = indexed(network['shared_capacities'], 'group_id')
    costs = indexed(network['transport_costs'], 'resource_id')
    require(resource in costs, 'Unknown resource')
    cost = costs[resource]['transport_units_per_stock_unit']
    return [r for r in sorted(network['routes'], key=lambda x: x['route_id'])
            if resource in r['resource_types'] and r['availability'] and r['capacity'] >= cost
            and groups[r['shared_capacity_group']]['capacity'] >= cost]


def candidate_paths(network, baseline, source, destination, resource, *, limit=256):
    """All simple structural paths within an explicit enumeration budget; no ranking.

    Does not reserve stock/capacity, certify consent, or predict future availability.
    Overflow fails explicitly rather than silently returning a preferred subset.
    """
    validate_network(network, baseline)
    countries = {c['state_id'] for c in baseline['world']['countries']}
    require(source in countries and destination in countries and source != destination, 'Invalid path endpoints')
    require(type(limit) is int and limit > 0, 'Invalid path budget')
    routes = usable_routes(network, resource); paths = []
    def walk(node, visited, path):
        for route in routes:
            if route['source'] != node or route['destination'] in visited:
                continue
            chain = path + [route['route_id']]
            if route['destination'] == destination:
                paths.append(chain)
                require(len(paths) <= limit, 'Candidate path budget exceeded')
            else:
                walk(route['destination'], visited | {route['destination']}, chain)
    walk(source, {source}, [])
    return paths


def dependency_trace(network, baseline, state_id, resource_id):
    """Static influence edges, not computed shortages or future events."""
    validate_network(network, baseline)
    require(state_id in {c['state_id'] for c in baseline['world']['countries']}, 'Unknown trace state')
    require(resource_id in {r['resource_id'] for r in baseline['world']['resources']}, 'Unknown trace resource')
    edges = []
    for route in network['routes']:
        for resource in route['resource_types']:
            edges.append({'id': route['route_id'], 'kind': 'transport',
                          'source': (route['source'], resource), 'target': (route['destination'], resource)})
    for dep in network['production_dependencies']:
        edges.append({'id': dep['dependency_id'], 'kind': 'production_input',
                      'source': (dep['producer_state'], dep['input_resource']),
                      'target': (dep['producer_state'], dep['output_resource'])})
    reached = {(state_id, resource_id)}; selected = []
    pending = sorted(edges, key=lambda e: (e['kind'], e['id'], e['source']))
    while True:
        next_edges = [e for e in pending if e['source'] in reached]
        if not next_edges:
            break
        selected.extend(next_edges)
        reached.update(e['target'] for e in next_edges)
        pending = [e for e in pending if e not in next_edges]
    return {'interpretation': 'static potential, including currently unavailable routes; not a forecast',
            'nodes': sorted(reached), 'edges': selected}


def network_components(network, baseline):
    """Potential concentration and domestic components, never a goodness score."""
    validate_network(network, baseline)
    domestic = self_reliance_components(baseline)
    out = {}
    for state in sorted(domestic):
        out[state] = {}
        for resource in sorted(domestic[state]):
            incoming = [r for r in network['routes'] if r['destination'] == state and resource in r['resource_types']]
            out[state][resource] = {'domestic': domestic[state][resource],
                'potential_direct_suppliers': sorted({r['source'] for r in incoming}),
                'potential_incoming_routes': sorted(r['route_id'] for r in incoming),
                'shared_capacity_groups': sorted({r['shared_capacity_group'] for r in incoming})}
    return out


def new_transport_check(network, baseline):
    """Isolated test inventory. Never modifies baseline or executes a worldline."""
    validate_network(network, baseline)
    return {'kind': 'offline_transport_check', 'network_hash': digest(network),
            'baseline_hash': digest(baseline), 'clock': 0, 'shipments': []}


def _materialize(check, network, baseline):
    """Replay a bounded shipment ledger; reject duplicate receipts/spending/capacity."""
    validate_network(network, baseline)
    shipment_schema = obj({'shipment_id': ID, 'route_id': ID, 'resource_id': ID,
        'quantity': POS, 'dispatch_turn': UINT,
        'arrival_turn': {'anyOf': [UINT, {'type': 'null'}]}})
    Draft202012Validator(obj({'kind': enum('offline_transport_check'), 'network_hash': HASH,
        'baseline_hash': HASH, 'clock': UINT, 'shipments': arr(shipment_schema)})).validate(check)
    require(check['network_hash'] == digest(network) and check['baseline_hash'] == digest(baseline), 'Transport snapshot changed')
    routes = indexed(network['routes'], 'route_id')
    groups = indexed(network['shared_capacities'], 'group_id')
    costs = indexed(network['transport_costs'], 'resource_id')
    indexed(check['shipments'], 'shipment_id')
    stock = {(a['owner'], a['resource_id']): a['balance'] for a in baseline['world']['accounts']}
    starting = {r: sum(q for (s,rid),q in stock.items() if rid == r) for r in costs}
    transport = {c['owner']: c['available'] for c in baseline['world']['capacities'] if c['category'] == 'transport'}
    route_use = {}; group_use = {}; state_use = {}; events = []
    for s in check['shipments']:
        require(s['route_id'] in routes, 'Unknown shipment route')
        route = routes[s['route_id']]
        require(route['availability'] and s['resource_id'] in route['resource_types'], 'Unavailable resource route')
        require(s['dispatch_turn'] <= check['clock'], 'Future dispatch')
        if s['arrival_turn'] is not None:
            require(s['dispatch_turn']+route['delay'] <= s['arrival_turn'] <= check['clock'], 'Premature/future arrival')
            events.append((s['arrival_turn'], 0, s['shipment_id'], s))
        events.append((s['dispatch_turn'], 1, s['shipment_id'], s))
    for turn, kind, _, s in sorted(events):
        route = routes[s['route_id']]; resource = s['resource_id']; quantity = s['quantity']
        if kind == 0:
            stock[(route['destination'], resource)] += quantity
            continue
        source = (route['source'], resource)
        require(stock[source] >= quantity, 'Insufficient stock / double spending')
        load = quantity * costs[resource]['transport_units_per_stock_unit']
        for used, key, capacity in (
            (route_use, (turn, route['route_id']), route['capacity']),
            (group_use, (turn, route['shared_capacity_group']), groups[route['shared_capacity_group']]['capacity']),
            (state_use, (turn, route['source']), transport[route['source']]),
        ):
            used[key] = used.get(key, 0) + load
            require(used[key] <= capacity, 'Transport capacity exceeded')
        stock[source] -= quantity
    transit = {r: 0 for r in costs}
    for s in check['shipments']:
        if s['arrival_turn'] is None:
            transit[s['resource_id']] += s['quantity']
    require(all(sum(q for (state,rid),q in stock.items() if rid == r)+transit[r] == starting[r]
                for r in costs), 'Transport conservation failure')
    return {'domestic': {state: {r: stock[(state,r)] for r in costs} for state in sorted(transport)},
            'in_transit': transit, 'total': starting,
            'shipments': deepcopy(check['shipments'])}


def transport_inventory(check, network, baseline):
    return _materialize(check, network, baseline)


def dispatch_for_check(check, network, baseline, *, shipment_id, route_id, resource_id, quantity):
    """Explicit caller-selected test shipment, not consent/settlement feasibility."""
    _materialize(check, network, baseline)
    result = deepcopy(check)
    result['shipments'].append({'shipment_id': shipment_id, 'route_id': route_id,
        'resource_id': resource_id, 'quantity': quantity, 'dispatch_turn': result['clock'], 'arrival_turn': None})
    _materialize(result, network, baseline)
    return result


def arrive_for_check(check, network, baseline, *, shipment_id, turn):
    """Caller-driven receipt. No automatic scheduling or rerouting."""
    _materialize(check, network, baseline)
    require(type(turn) is int and turn >= check['clock'], 'Clock cannot reverse')
    result = deepcopy(check)
    shipment = next((s for s in result['shipments'] if s['shipment_id'] == shipment_id), None)
    require(shipment is not None and shipment['arrival_turn'] is None, 'Unknown or repeated receipt')
    shipment['arrival_turn'] = turn; result['clock'] = turn
    _materialize(result, network, baseline)
    return result
