"""Deterministic reference settlement for synthetic/offline choices.

Exact integer allocation, fail-closed search budget, explicit policy only.
No simulation runner, economic objective, Agent, network rerouting, or UI.
"""
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
import hashlib
from threading import RLock

from .contracts import digest
from .choices import TechnicalFailure, ensure, validate_choice, check, TEMPLATE
from .network import validate_network


@dataclass(frozen=True)
class Policy:
    policy_id: str
    reserve_essential: bool = True
    allocation: str = 'leximin_actor_fulfillment'
    tie_seed: str = 'baseline-v1'

    def __post_init__(self):
        ensure(type(self.policy_id) is str and bool(self.policy_id), 'INVALID_POLICY')
        ensure(type(self.reserve_essential) is bool, 'INVALID_POLICY')
        ensure(self.allocation in ('leximin_actor_fulfillment', 'lexicographic_choice_priority'), 'UNKNOWN_ALLOCATION')
        ensure(type(self.tie_seed) is str, 'INVALID_POLICY')

    def record(self):
        return {'policy_id': self.policy_id, 'reserve_essential': self.reserve_essential,
                'allocation': self.allocation, 'tie_seed': self.tie_seed,
                'consent_required': True, 'pool_uses_opening_stock': True}


# Extensible action names map to reviewed physical handlers, never executable model code.
DEFAULT_ACTIONS = {'transfer': 'transfer', 'pool_deposit': 'pool_deposit', 'pool_withdraw': 'pool_withdraw'}


class SettlementEngine:
    def __init__(self, baseline, network, authority, policies, *, pool_location, pool_balances=None,
                 action_registry=None, search_budget=200000, context_id=None):
        ensure(type(context_id) is str and bool(context_id), 'CONTEXT_ID_REQUIRED')
        self._lock = RLock()
        validate_network(network, baseline)
        self.baseline = deepcopy(baseline)
        self.network = deepcopy(network)
        self.authority = authority
        self.states = {c['state_id'] for c in baseline['world']['countries']}
        self.resources = {r['resource_id'] for r in baseline['world']['resources']}
        ensure(pool_location in self.states, 'INVALID_POOL_LOCATION')
        self.pool_location = pool_location
        self.policies = {p.policy_id: p for p in policies}
        ensure(len(self.policies) == len(policies) and bool(policies), 'DUPLICATE_OR_EMPTY_POLICY')
        self.actions = dict(DEFAULT_ACTIONS if action_registry is None else action_registry)
        ensure(all(type(k) is str and v in DEFAULT_ACTIONS for k,v in self.actions.items()), 'UNSUPPORTED_PHYSICAL_HANDLER')
        ensure(type(search_budget) is int and search_budget > 0, 'INVALID_SEARCH_BUDGET')
        self.search_budget = search_budget
        self.routes = {r['route_id']: r for r in self.network['routes']}
        self.groups = {g['group_id']: g['capacity'] for g in network['shared_capacities']}
        self.costs = {c['resource_id']: c['transport_units_per_stock_unit'] for c in network['transport_costs']}
        self.transport = {c['owner']: c['available'] for c in baseline['world']['capacities'] if c['category'] == 'transport'}
        self.needs = {(c['state_id'],d['resource_id']): d['quantity'] for c in baseline['world']['countries'] for d in c['demands']}
        pool = {r: 0 for r in self.resources}
        if pool_balances is not None:
            ensure(set(pool_balances) == self.resources, 'INVALID_POOL_RESOURCE')
            ensure(all(type(q) is int and q >= 0 for q in pool_balances.values()), 'INVALID_POOL_BALANCE')
            pool = dict(pool_balances)
        stock = {s: {} for s in self.states}
        for a in baseline['world']['accounts']:
            stock[a['owner']][a['resource_id']] = a['balance']
        state = {'kind': 'settlement_state', 'context_id': context_id, 'turn': 0, 'last_settlement_turn': None,
            'baseline_hash': digest(baseline), 'network_hash': digest(network),
            'action_registry_hash': digest(self.actions),
            'policy_registry_hash': digest([self.policies[p].record() for p in sorted(self.policies)]),
            'pool_location': pool_location,
            'stock': stock, 'pool': pool, 'shipments': [], 'audits': [], 'seen_choice_ids': []}
        self._initial_totals = self._totals(state)
        self.initial = authority._sign(state)
        self._head = digest(state)
        self._configuration_hash = self._configuration()

    def _configuration(self):
        return digest({'baseline': self.baseline, 'network': self.network, 'actions': self.actions,
                       'policies': [self.policies[p].record() for p in sorted(self.policies)],
                       'pool_location': self.pool_location})

    def read(self, state):
        return self.authority.verify(state, 'settlement_state')

    def restore_history(self, principal, *, turn, shipments, seen_choice_ids):
        """Trusted TURN host bootstrap, never an Agent input or a state patch.

        Domestic balances/configuration were validated by the constructor. The
        host validates its durable checkpoint before supplying transit history.
        This entry point is usable only on a fresh engine.
        """
        with self._lock:
            s = self._core(principal, self.initial)
            ensure(type(turn) is int and turn > 0, 'INVALID_RESTORE_TURN')
            ensure(len(seen_choice_ids) == len(set(seen_choice_ids)), 'CHOICE_ID_COLLISION')
            result = deepcopy(s)
            result.update(turn=turn, shipments=deepcopy(shipments), seen_choice_ids=list(seen_choice_ids))
            expected = self._totals(result)
            self._validate_state(result, expected_totals=expected)
            sealed = self._commit(s, result)
            self._initial_totals = expected
            return sealed

    def _core(self, principal, state):
        role, _ = self.authority._identity(principal)
        ensure(role == 'core', 'CORE_AUTHORITY_REQUIRED')
        ensure(self._configuration() == self._configuration_hash, 'CONFIGURATION_CHANGED')
        value = self.read(state)
        ensure(digest(value) == self._head, 'STALE_STATE')
        return value

    def _totals(self, s):
        out = {r: sum(q[r] for q in s['stock'].values())+s['pool'][r] for r in self.resources}
        for shipment in s['shipments']:
            if shipment['arrival_turn'] is None:
                out[shipment['resource']] += shipment['dispatched_amount']
        return out

    def _validate_state(self, state, *, expected_totals=None):
        ensure(all(type(q) is int and q >= 0 for a in [*state['stock'].values(), state['pool']] for q in a.values()), 'NEGATIVE_OR_INVALID_STOCK')
        ensure(self._totals(state) == (self._initial_totals if expected_totals is None else expected_totals), 'RESOURCE_CONSERVATION_VIOLATION')
        ids = [s['shipment_id'] for s in state['shipments']]
        ensure(len(ids) == len(set(ids)), 'DUPLICATE_SHIPMENT')
        for s in state['shipments']:
            ensure(s['owner'] == s['target'], 'OWNERSHIP_VIOLATION')
            ensure(s['arrived_amount'] == (0 if s['arrival_turn'] is None else s['dispatched_amount']), 'ARRIVAL_ACCOUNTING_VIOLATION')
            ensure(s['arrival_turn'] is None or s['arrival_turn'] >= s['arrival_due_turn'], 'EARLY_ARRIVAL')

    def _consents(self, choices, envelopes):
        hashes = {digest(c) for c in choices}
        result = {}
        for envelope in envelopes:
            c = self.authority.verify(envelope, 'consent')
            ensure(c['choice_hash'] in hashes, 'STALE_CONSENT')
            key = (c['choice_hash'], c['principal'])
            ensure(key not in result, 'DUPLICATE_CONSENT')
            result[key] = c['accepted']
        return result

    def _prepare(self, state, choice, policy, consents):
        requested = choice['requested_amount']; rid = choice['resource']; actor = choice['actor_state_id']
        result = {'choice_id': choice['choice_id'], 'feasible_amount': 0, 'reason_codes': [],
                  'requested_amount': requested, 'constraints': {}}
        def fail(code):
            result['reason_codes'].append(code)
            return result
        if actor not in self.states: return fail('INVALID_ACTOR')
        if rid not in self.resources: return fail('INVALID_RESOURCE')
        kind = self.actions.get(choice['action_type'])
        ensure(kind is not None, 'UNKNOWN_ACTION_CONTRACT')
        target = choice['target']
        if (kind == 'pool_deposit' and target != 'world_pool') or (kind != 'pool_deposit' and target not in self.states):
            return fail('INVALID_TARGET')
        if kind == 'transfer' and target == actor: return fail('INVALID_TARGET')
        source = 'world_pool' if kind == 'pool_withdraw' else actor
        physical_source = self.pool_location if source == 'world_pool' else source
        destination = self.pool_location if target == 'world_pool' else target
        required = {target}
        if source == 'world_pool':
            required.update(('world_pool', physical_source))
        if consents.get((digest(choice),actor)) is False: return fail('CONSENT_REFUSED')
        required.discard(actor)  # The authenticated owner's choice is their consent.
        for owner in sorted(required):
            granted = consents.get((digest(choice),owner))
            if granted is False: return fail('CONSENT_REFUSED')
            if granted is not True: return fail('MISSING_CONSENT')
        stock = state['pool'][rid] if source == 'world_pool' else state['stock'][source][rid]
        reserve = 0 if source == 'world_pool' or not policy.reserve_essential else min(stock,self.needs[(source,rid)])
        available = stock-reserve
        result['source'] = source;result['target'] = target;result['physical_source'] = physical_source
        result['kind'] = kind;result['delay'] = 1
        limits = {'INSUFFICIENT_STOCK': stock, 'ESSENTIAL_RESERVE_CONFLICT': available}
        route_id = choice['route_preference']
        if physical_source == destination and kind != 'transfer':
            if route_id is not None: return fail('INVALID_TARGET')
            result['route'] = None;result['group'] = None
        else:
            if route_id not in self.routes: return fail('NO_ROUTE')
            route = self.routes[route_id]
            if (route['source'],route['destination']) != (physical_source,destination): return fail('INVALID_TARGET')
            if rid not in route['resource_types']: return fail('ROUTE_RESOURCE_MISMATCH')
            if not route['availability']: return fail('ROUTE_UNAVAILABLE')
            cost = self.costs[rid]
            limits.update({'ROUTE_CAPACITY_EXCEEDED': route['capacity']//cost,
                           'SHARED_CAPACITY_CONFLICT': self.groups[route['shared_capacity_group']]//cost,
                           'TRANSPORT_CAPACITY_EXCEEDED': self.transport[physical_source]//cost})
            result['route'] = route_id;result['group'] = route['shared_capacity_group'];result['delay'] = route['delay']
        maximum = min(requested, *limits.values())
        result['constraints'] = limits
        result['reason_codes'] = [code for code,value in limits.items() if value < requested]
        if maximum < choice['minimum_amount']:
            maximum = 0;result['reason_codes'].append('MINIMUM_AMOUNT_NOT_MET')
        elif maximum < requested and not choice['allow_partial']:
            maximum = 0;result['reason_codes'].append('FULL_AMOUNT_REQUIRED')
        result['feasible_amount'] = maximum
        return result

    def individual_feasibility(self, state, submission, consents, policy_id):
        s = self.read(state)
        ensure(policy_id in self.policies, 'UNKNOWN_POLICY')
        c = self.authority.verify(submission, 'choice')['choice'];validate_choice(c)
        ensure(c['snapshot_hash'] == digest(s) and c['turn'] == s['turn'], 'STALE_CHOICE')
        return self._prepare(s,c,self.policies[policy_id],self._consents([c],consents))

    def _constraints(self, state, choices, prepared, amounts, policy):
        spending = {}; routes = {}; groups = {}; transport = {}; failures = set()
        chosen = {c['choice_id']:q for c,q in zip(choices,amounts)}
        arrivals = {}
        for shipment in state['shipments']:
            if shipment['arrival_turn'] is not None:
                key = shipment['choice_id'];arrivals[key] = arrivals.get(key,0)+shipment['arrived_amount']
        for c,p,q in zip(choices,prepared,amounts):
            if not q: continue
            for condition in c['conditions']:
                reference = condition['choice_id']
                if condition['kind'] == 'participation': ok = chosen.get(reference,0) > 0
                elif condition['kind'] == 'settled_amount': ok = chosen.get(reference,0) >= condition['minimum_amount']
                else: ok = arrivals.get(reference,0) >= condition['minimum_amount']
                if not ok: failures.add('CONDITION_NOT_MET')
            key = (p['source'],c['resource']);spending[key] = spending.get(key,0)+q
            if p['route'] is not None:
                load = q*self.costs[c['resource']]
                for bag,key in [(routes,p['route']),(groups,p['group']),(transport,p['physical_source'])]:
                    bag[key] = bag.get(key,0)+load
        for (source,resource),amount in spending.items():
            stock = state['pool'][resource] if source == 'world_pool' else state['stock'][source][resource]
            reserve = min(stock,self.needs[(source,resource)]) if source != 'world_pool' and policy.reserve_essential else 0
            if amount > stock-reserve: failures.add('POOL_CONFLICT' if source == 'world_pool' else 'DOUBLE_RESERVATION')
        if any(q > self.routes[r]['capacity'] for r,q in routes.items()):failures.add('ROUTE_CAPACITY_EXCEEDED')
        if any(q > self.groups[g] for g,q in groups.items()):failures.add('SHARED_CAPACITY_CONFLICT')
        if any(q > self.transport[s] for s,q in transport.items()):failures.add('TRANSPORT_CAPACITY_EXCEEDED')
        return sorted(failures), {'stock_reservations': [{'owner':s,'resource':r,'amount':q} for (s,r),q in sorted(spending.items())],
                                 'route_load': routes, 'shared_load': groups, 'transport_load': transport}

    def _allocate(self, state, choices, prepared, policy):
        # Separate only genuinely independent constraint/objective components.
        # One actor's choices must stay together: fulfillment averages resources
        # within an actor before comparing actors, including zero-only choices.
        active = [i for i,p in enumerate(prepared) if p['feasible_amount']]
        parent = {i:i for i in active}
        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]];i = parent[i]
            return i
        def join(a,b):
            parent[root(a)] = root(b)
        owners = {}; by_id = {choices[i]['choice_id']:i for i in active}
        for i in active:
            c,p = choices[i],prepared[i]
            keys = [('actor',c['actor_state_id']),('stock',p['source'],c['resource'])]
            if p['route'] is not None:
                keys += [('route',p['route']),('group',p['group']),('transport',p['physical_source'])]
            for key in keys:
                if key in owners:join(i,owners[key])
                else:owners[key] = i
            for condition in c['conditions']:
                # Arrival evidence is frozen history, never a current allocation.
                if condition['kind'] != 'arrived_amount' and condition['choice_id'] in by_id:
                    join(i,by_id[condition['choice_id']])
        components = {}
        for i in active:components.setdefault(root(i),[]).append(i)
        components = sorted(components.values(),key=lambda items:items[0])
        # Bound total enumerations before allocating ranges or publishing any
        # result. An over-budget connected component still fails without fallback.
        search_size = 0
        for component in components:
            size = 1
            for i in component:
                c,p = choices[i],prepared[i]
                size *= p['feasible_amount']-c['minimum_amount']+2 if c['allow_partial'] else 2
                ensure(search_size+size <= self.search_budget, 'SEARCH_BUDGET_EXCEEDED')
            search_size += size
        tie_order = sorted(range(len(choices)), key=lambda i: (hashlib.sha256((policy.tie_seed+':'+choices[i]['choice_id']).encode()).hexdigest(),choices[i]['choice_id']))
        def score(amounts):
            # Aggregate within actor/resource before dimensionless averaging:
            # splitting a request into multiple IDs cannot change its weight.
            groups = {}
            for c,q in zip(choices,amounts):
                key=(c['actor_state_id'],c['resource'])
                total,asked=groups.get(key,(0,0));groups[key]=(total+q,asked+c['requested_amount'])
            ratios = {}
            for (actor,resource),(total,asked) in groups.items():
                ratios.setdefault(actor,[]).append(Fraction(total,asked))
            actor_ratios = tuple(sorted(sum(v,Fraction(0))/len(v) for v in ratios.values()))
            tie = tuple(amounts[i] for i in tie_order)
            return (actor_ratios,tie) if policy.allocation == 'leximin_actor_fulfillment' else (tie,)
        # Actor sets are disjoint between components. Lexicographic comparison
        # of sorted fulfillment ratios is preserved when merging the same fixed
        # other ratios. The global seeded tie order is preserved too. Thus exact
        # component optima compose to the same global optimum as the full product.
        best = (0,)*len(choices)
        from itertools import product
        for component in components:
            domains = []
            for i in component:
                c,p = choices[i],prepared[i]
                domains.append([0,*range(c['minimum_amount'],p['feasible_amount']+1)]
                               if c['allow_partial'] else [0,c['requested_amount']])
            component_best = None;best_score = None
            for quantities in product(*domains):
                candidate = list(best)
                for i,q in zip(component,quantities):candidate[i] = q
                candidate = tuple(candidate)
                failed,_ = self._constraints(state,choices,prepared,candidate,policy)
                if failed:continue
                candidate_score = score(candidate)
                if best_score is None or candidate_score > best_score:
                    component_best,best_score = candidate,candidate_score
            ensure(component_best is not None, 'NO_VALID_ALLOCATION')
            best = component_best
        return best

    def settle(self, principal, state, submissions, consents, *, policy_id, condition_catalogue=()):
        s = self._core(principal,state)
        ensure(s['last_settlement_turn'] != s['turn'], 'TURN_ALREADY_SETTLED')
        ensure(policy_id in self.policies, 'UNKNOWN_POLICY')
        policy = self.policies[policy_id]
        choices = sorted((self.authority.verify(e,'choice')['choice'] for e in submissions),key=lambda c:c['choice_id'])
        ids = [c['choice_id'] for c in choices]
        ensure(len(ids) == len(set(ids)) and not set(ids)&set(s['seen_choice_ids']), 'CHOICE_ID_COLLISION')
        # Trusted host evidence distinguishes a known but unselected opportunity
        # (condition false) from an invented reference (technical failure).
        known=set()
        for template in condition_catalogue:
            check(TEMPLATE,template)
            ensure(template['turn']==s['turn'] and template['snapshot_hash']==digest(s),'STALE_CONDITION_CATALOGUE')
            ensure(template['actor_state_id'] in self.states,'INVALID_CATALOGUE_ACTOR')
            ensure(template['choice_id'] not in known and template['choice_id'] not in s['seen_choice_ids'],'CHOICE_ID_COLLISION')
            known.add(template['choice_id'])
        for c in choices:
            validate_choice(c)
            ensure(c['turn'] == s['turn'] and c['snapshot_hash'] == digest(s), 'STALE_CHOICE')
            for condition in c['conditions']:
                reference = condition['choice_id']
                ensure(reference in (set(ids)|set(s['seen_choice_ids']) if condition['kind']=='arrived_amount' else set(ids)|known), 'UNKNOWN_CONDITION_REFERENCE')
        consent_map = self._consents(choices,consents)
        prepared = [self._prepare(s,c,policy,consent_map) for c in choices]
        amounts = self._allocate(s,choices,prepared,policy)
        failed,reservations = self._constraints(s,choices,prepared,amounts,policy)
        ensure(not failed, 'ALLOCATION_CONSTRAINT_VIOLATION')
        result = deepcopy(s);audit=[]
        for i,(c,p,q) in enumerate(zip(choices,prepared,amounts)):
            codes = []
            if q < c['requested_amount']:
                proposed = list(amounts);proposed[i] = p['feasible_amount']
                failures,_ = self._constraints(s,choices,prepared,proposed,policy)
                codes = sorted(set(p['reason_codes'] + (failures+['POLICY_ALLOCATION_NOT_SELECTED'] if p['feasible_amount'] > q else [])))
            shipment_id = None;due=None
            if q:
                rid=c['resource'];source=p['source'];target=p['target']
                balance=result['pool'] if source=='world_pool' else result['stock'][source]
                balance[rid]-=q
                shipment_id=c['choice_id']+':shipment';due=s['turn']+p['delay']
                result['shipments'].append({'shipment_id':shipment_id,'choice_id':c['choice_id'],
                    'resource':rid,'source':source,'target':target,'owner':target,
                    'ownership_rule':'receiver owns at atomic dispatch; location remains in_transit until arrival',
                    'route':p['route'],'dispatch_turn':s['turn'],'arrival_due_turn':due,
                    'dispatched_amount':q,'arrived_amount':0,'arrival_turn':None})
            audit.append({'trace_id':digest({'context_id':s['context_id'],'choice_id':c['choice_id']}),'context_id':s['context_id'],'choice_id':c['choice_id'],'intent':deepcopy(c),'intent_hash':digest(c),
                'individual':p,'policy':policy.record(),'policy_hash':digest(policy.record()),'established':q>0,'settled_amount':q,
                'dispatched_amount':q,'arrival_due_turn':due,'shipment_id':shipment_id,
                'reason_codes':codes,'consent_evidence':[{'principal':owner,'accepted':accepted} for (h,owner),accepted in sorted(consent_map.items()) if h==digest(c)],
                'state_change':{'stock_debit':q,'transit_credit':q,'destination_stock_credit':0}})
        result['audits'].append({'turn':s['turn'],'opening_hash':digest(s),'policy':policy.record(),
                                 'choices':audit,'joint_reservations':reservations})
        result['seen_choice_ids'].extend(ids);result['last_settlement_turn']=s['turn']
        self._validate_state(result)
        return self._commit(s,result)

    def arrive(self, principal, state, *, turn):
        s=self._core(principal,state)
        ensure(type(turn) is int and turn>s['turn'], 'INVALID_ARRIVAL_TURN')
        result=deepcopy(s);result['turn']=turn
        for shipment in result['shipments']:
            if shipment['arrival_turn'] is None and shipment['arrival_due_turn']<=turn:
                destination=result['pool'] if shipment['target']=='world_pool' else result['stock'][shipment['target']]
                destination[shipment['resource']]+=shipment['dispatched_amount']
                shipment['arrived_amount']=shipment['dispatched_amount'];shipment['arrival_turn']=turn
        self._validate_state(result)
        return self._commit(s,result)

    def _commit(self, previous, result):
        # Compare-and-swap the head under lock: two callers cannot commit from
        # the same opening snapshot even when both passed the initial read.
        with self._lock:
            ensure(self._head == digest(previous), 'STALE_STATE')
            sealed=self.authority._sign(result)
            self._head=digest(result)
            return sealed
