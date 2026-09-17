"""Closed structural contracts; open, explicitly registered law/policy identifiers.

Validation does not execute intentions or certify physical feasibility. Hashes
bind records to evidence; they do not authenticate an untrusted producer.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from jsonschema import Draft202012Validator

VERSION = 'v3'
OBSERVATION_AXES = (
    'homeostasis', 'resilience', 'national_autonomy', 'national_self_reliance',
    'resource_shortage', 'resource_distribution', 'supply_network_health',
    'dependency_concentration', 'network_load', 'settlement', 'conflict_load', 'cascade',
)


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def arr(items):
    return {'type': 'array', 'items': items}


def enum(*values):
    return {'enum': list(values)}


ID = {'type': 'string', 'pattern': r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'}
TEXT = {'type': 'string', 'minLength': 1}
UINT = {'type': 'integer', 'minimum': 0}
POS = {'type': 'integer', 'minimum': 1}
HASH = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
NULL_ID = {'anyOf': [ID, {'type': 'null'}]}
IDS = {**arr(ID), 'uniqueItems': True}
REF = obj({'id': ID, 'digest': HASH})
STOCK = obj({'kind': enum('stock'), 'account_id': ID, 'resource_id': ID,
             'owner': ID, 'location': ID, 'unit_id': ID,
             'balance': UINT, 'in_transit': {'type': 'boolean'}})
CAPACITY = obj({'kind': enum('capacity'), 'capacity_id': ID, 'owner': ID,
                'category': enum('production', 'transport', 'recovery'),
                'unit_id': ID, 'available': UINT, 'reserved': UINT})
DEMAND = obj({'resource_id': ID, 'unit_id': ID, 'quantity': UINT, 'function_id': ID})
COUNTRY = obj({'state_id': ID, 'accounts': IDS, 'capacities': IDS,
               'demands': arr(DEMAND), 'essential_functions': IDS, 'dependencies': IDS,
               'decision_state': obj({'observation_hash': HASH, 'intent_ids': IDS}),
               'autonomy': obj({'mandate_ids': IDS, 'decision_authority': enum('self')}),
               'self_reliance': obj({'assumption_set': REF, 'evidence_refs': IDS})})
EDGE = obj({'dependency_id': ID, 'supplier': ID, 'consumer': ID, 'resource_id': ID,
            'route_id': ID, 'capacity_id': ID, 'alternative_routes': IDS,
            'upstream_dependencies': IDS})
RESOURCE = obj({'resource_id': ID, 'unit_id': ID})
ROUTE = obj({'route_id': ID, 'source': ID, 'target': ID})
POLICY = obj({'policy_id': ID, 'definition_hash': HASH})
SCHEMA = obj({'contract_version': enum(VERSION), 'schema_version': enum(1),
              'resources': arr(RESOURCE), 'countries': arr(COUNTRY), 'accounts': arr(STOCK),
              'capacities': arr(CAPACITY), 'routes': arr(ROUTE), 'dependencies': arr(EDGE),
              'policies': arr(POLICY), 'active_policy': ID})


def record(kind, fields):
    return obj({'contract_version': enum(VERSION), 'kind': enum(kind), **fields})


# Parameters describe desired quantities/references, never a writable state patch.
PARAMETER = obj({'name': ID, 'quantity': UINT, 'unit_id': ID})
INTENT = record('intent', {'intent_id': ID, 'state_id': ID, 'snapshot_hash': HASH,
    'law_ref': REF, 'proposal_id': NULL_ID, 'choice_ref': REF,
    'parameters': arr(PARAMETER), 'evidence_refs': IDS})
FEASIBILITY = record('feasibility', {'intent_hash': HASH, 'snapshot_hash': HASH,
    'validator_ref': REF, 'feasible': {'type': 'boolean'}, 'constraint_refs': IDS})
SETTLEMENT = record('settlement', {'intent_hash': HASH, 'feasibility_hash': HASH,
    'snapshot_hash': HASH, 'policy_ref': REF, 'established': {'type': 'boolean'},
    'consent_refs': IDS, 'condition_refs': IDS})
ENTRY = obj({'entry_id': ID, 'resource_id': ID, 'unit_id': ID,
             'source_account': NULL_ID, 'target_account': NULL_ID,
             'quantity': POS, 'category': enum('transfer', 'generation', 'consumption', 'loss'),
             'evidence_ref': ID})
CHANGE = record('state_change', {'producer': enum('settlement_core'),
    'settlement_hash': HASH, 'snapshot_hash': HASH, 'entries': arr(ENTRY)})
COORDINATOR = record('coordinator_message', {'message_id': ID, 'snapshot_hash': HASH,
    'mode': enum('observation', 'proposal', 'coordination_proposal'), 'public_reason': TEXT,
    'proposal_refs': IDS})
EVENT_INPUT = record('event_input', {'world_hash': HASH, 'intent_refs': IDS,
    'balance_hash': HASH, 'unresolved_shortages_hash': HASH, 'network_load_hash': HASH,
    'transaction_history_hash': HASH, 'turn_history_hash': HASH, 'rule_ref': REF})
EXPERIMENT = record('experiment_spec', {'experiment_id': ID, 'research_question': TEXT,
    'secondary_questions': arr(TEXT), 'policy_refs': arr(REF), 'initial_conditions': REF,
    'primary_endpoints': IDS, 'repetitions': POS, 'seed_policy': REF,
    'law_refs': arr(REF), 'observation_axes': IDS})
CONTRACTS = {'world': SCHEMA, 'intent': INTENT, 'feasibility': FEASIBILITY,
             'settlement': SETTLEMENT, 'state_change': CHANGE,
             'coordinator_message': COORDINATOR, 'event_input': EVENT_INPUT,
             'experiment_spec': EXPERIMENT}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    # Round trip disallows non-JSON objects, NaN and infinity; caller objects are not retained.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode('utf-8')).hexdigest()


def validate(kind, value):
    require(kind in CONTRACTS, 'Unknown contract')
    canonical(value)
    Draft202012Validator(CONTRACTS[kind]).validate(value)
    if kind == 'experiment_spec':
        require(bool(value['policy_refs']) and bool(value['law_refs']) and
                bool(value['primary_endpoints']), 'Missing preregistration fields')
        require(set(OBSERVATION_AXES) <= set(value['observation_axes']), 'Missing observation axes')
    return value


def indexed(rows, key):
    result = {r[key]: r for r in rows}
    require(len(result) == len(rows), 'Duplicate identifier')
    return result


def validate_world(world):
    validate('world', world)
    countries = indexed(world['countries'], 'state_id')
    resources = indexed(world['resources'], 'resource_id')
    accounts = indexed(world['accounts'], 'account_id')
    capacities = indexed(world['capacities'], 'capacity_id')
    routes = indexed(world['routes'], 'route_id')
    edges = indexed(world['dependencies'], 'dependency_id')
    policies = indexed(world['policies'], 'policy_id')
    require(world['active_policy'] in policies, 'Unknown policy')
    for account in accounts.values():
        require(account['owner'] in countries and account['resource_id'] in resources, 'Unknown stock reference')
        require(account['unit_id'] == resources[account['resource_id']]['unit_id'], 'Resource unit mismatch')
    for cap in capacities.values():
        require(cap['owner'] in countries and cap['reserved'] <= cap['available'], 'Invalid capacity')
    for route in routes.values():
        require(route['source'] in countries and route['target'] in countries and
                route['source'] != route['target'], 'Invalid route')
    for key, edge in edges.items():
        require(edge['supplier'] in countries and edge['consumer'] in countries and
                edge['supplier'] != edge['consumer'], 'Invalid dependency endpoints')
        require(edge['resource_id'] in resources and edge['capacity_id'] in capacities, 'Unknown dependency reference')
        require(capacities[edge['capacity_id']]['category'] == 'transport', 'Route capacity must be transport')
        for rid in [edge['route_id'], *edge['alternative_routes']]:
            require(rid in routes, 'Unknown route')
            require((routes[rid]['source'], routes[rid]['target']) ==
                    (edge['supplier'], edge['consumer']), 'Route endpoints mismatch')
        require(edge['route_id'] not in edge['alternative_routes'], 'Duplicate primary route')
        for upstream in edge['upstream_dependencies']:
            require(upstream in edges and upstream != key, 'Invalid upstream reference')
            require(edges[upstream]['consumer'] == edge['supplier'], 'Disconnected dependency chain')
    # Legitimate multi-country cycles are allowed: a cycle is not itself invalid.
    for cid, country in countries.items():
        require(set(country['accounts']) == {k for k,v in accounts.items() if v['owner'] == cid}, 'Account ownership mismatch')
        require(set(country['capacities']) == {k for k,v in capacities.items() if v['owner'] == cid}, 'Capacity ownership mismatch')
        require(set(country['dependencies']) == {k for k,v in edges.items() if v['consumer'] == cid}, 'Dependency ownership mismatch')
        for d in country['demands']:
            require(d['resource_id'] in resources and d['unit_id'] == resources[d['resource_id']]['unit_id']
                    and d['function_id'] in country['essential_functions'], 'Invalid demand')
        require(set(country['essential_functions']) <= {d['function_id'] for d in country['demands']}, 'Undefined essential demand')
    return world


def validate_trace(intent, feasibility, settlement, change, *, authorized_producer):
    for kind, value in [('intent', intent), ('feasibility', feasibility),
                        ('settlement', settlement), ('state_change', change)]:
        validate(kind, value)
    require(authorized_producer == 'settlement_core', 'Agent/coordinator cannot submit state changes')
    require(feasibility['intent_hash'] == settlement['intent_hash'] == digest(intent), 'Intent mismatch')
    require(settlement['feasibility_hash'] == digest(feasibility), 'Feasibility mismatch')
    require(change['settlement_hash'] == digest(settlement), 'Settlement mismatch')
    require(all(x['snapshot_hash'] == intent['snapshot_hash'] for x in (feasibility, settlement, change)), 'Snapshot mismatch')
    if settlement['established']:
        require(feasibility['feasible'] and bool(settlement['consent_refs']), 'Unproven establishment')
    else:
        require(not change['entries'], 'Unestablished action changes state')
    indexed(change['entries'], 'entry_id')
    for e in change['entries']:
        source, target = e['source_account'], e['target_account']
        if e['category'] == 'transfer':
            require(source is not None and target is not None and source != target, 'Invalid transfer')
        elif e['category'] == 'generation':
            require(source is None and target is not None, 'Invalid generation')
        else:
            require(source is not None and target is None, 'Invalid consumption/loss')
    # No world update occurs here. Later core must resolve evidence and ledger balances.


@dataclass(frozen=True)
class FrozenExperiment:
    """Immutable canonical specification. A durable caller retains its original digest."""
    canonical_json: str
    sha256: str

    @classmethod
    def freeze(cls, specification):
        validate('experiment_spec', specification)
        payload = canonical(specification)
        return cls(payload, sha256(payload.encode('utf-8')).hexdigest())

    def verify(self, candidate, *, expected_digest):
        require(self.sha256 == expected_digest == digest(json.loads(self.canonical_json)), 'Experiment anchor changed')
        validate('experiment_spec', candidate)
        require(canonical(candidate) == self.canonical_json, 'Experiment conditions changed; use a new experiment')

    def to_dict(self):
        return json.loads(self.canonical_json)


def validate_intent(intent, world, *, laws, choices):
    validate('intent', intent)
    validate_world(world)
    require(intent['state_id'] in {c['state_id'] for c in world['countries']}, 'Unknown actor')
    require(intent['snapshot_hash'] == digest(world), 'Stale intent')
    for field, registry in [('law_ref', laws), ('choice_ref', choices)]:
        ref = intent[field]
        require(registry.get(ref['id']) == ref['digest'], 'Unknown or changed permission reference')
    return intent


def validate_policy_reference(reference, world):
    Draft202012Validator(REF).validate(reference)
    policies = indexed(world['policies'], 'policy_id')
    require(reference['id'] in policies and
            policies[reference['id']]['definition_hash'] == reference['digest'], 'Invalid policy reference')


def validate_change_accounts(change, world):
    """Validate evidence shape and aggregate spending, without applying a settlement."""
    validate('state_change', change)
    validate_world(world)
    accounts = indexed(world['accounts'], 'account_id')
    indexed(change['entries'], 'entry_id')
    spending = {}
    for e in change['entries']:
        for name in ('source_account', 'target_account'):
            aid = e[name]
            if aid is not None:
                require(aid in accounts, 'Unknown ledger account')
                require((accounts[aid]['resource_id'], accounts[aid]['unit_id']) ==
                        (e['resource_id'], e['unit_id']), 'Ledger unit/resource mismatch')
        source = e['source_account']
        if source is not None:
            spending[source] = spending.get(source, 0) + e['quantity']
    require(all(q <= accounts[a]['balance'] for a,q in spending.items()), 'Double spend / insufficient opening balance')


def validate_pipeline(intent, feasibility, settlement, change, world, *, laws, choices, authorized_producer):
    """The complete phase-one structural gate; not a physical execution engine."""
    validate_intent(intent, world, laws=laws, choices=choices)
    validate_trace(intent, feasibility, settlement, change, authorized_producer=authorized_producer)
    validate_policy_reference(settlement['policy_ref'], world)
    validate_change_accounts(change, world)
