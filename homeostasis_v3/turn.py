"""Offline single-TURN law executor. No agents, event stories or experiment loop.

Callbacks are trusted host adapters, not a sandbox for executable model code.
They receive immutable JSON snapshots, never the authority or mutable core.
"""
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
import json
from math import lcm

from .contracts import canonical, digest, ID, UINT, TEXT, obj, enum
from .choices import Authority, TechnicalFailure, ensure, check, materialize_choice, TEMPLATE
from .physical import validate_baseline
from .network import validate_network
from .settlement import SettlementEngine, Policy

PHASES = ('TURN_OPEN', 'ARRIVAL', 'SHOCK', 'OBSERVATION_FREEZE', 'COORDINATOR_INPUT',
          'CHOICE_COLLECTION', 'CHOICE_VALIDATION', 'FEASIBILITY', 'JOINT_SETTLEMENT',
          'ATOMIC_APPLY', 'TRANSIT_UPDATE', 'CONSUMPTION', 'PRODUCTION', 'RECOVERY',
          'CONSERVATION', 'TURN_CLOSE', 'EVALUATION_SNAPSHOT', 'NEXT_EVENT_INPUT',
          'AUDIT', 'CHECKPOINT')
SHOCK = obj({'event_id': ID, 'kind': enum('resource_loss', 'capacity_loss', 'route_stop', 'demand_change'),
             'target': ID, 'resource': {'anyOf': [ID, {'type': 'null'}]},
             'amount': UINT, 'evidence': TEXT})
PROPOSAL = obj({'proposal_id': ID, 'public_reason': TEXT})
RULES = {'version': 'v3-turn-1', 'consumption': 'before production; min(stock, essential demand)',
         'production': 'shared-input proportional scale; whole batches; frozen inputs; delayed outputs',
         'recovery': 'no effect until an explicit recovery law is approved',
         'capacity': 'per-turn throughput; dispatch reserves capacity, not future route occupancy'}


@dataclass(frozen=True)
class Snapshot:
    payload: str

    @classmethod
    def of(cls, data):
        return cls(canonical(data))

    @property
    def hash(self):
        return digest(self.read())

    def read(self):
        return json.loads(self.payload)  # A private copy for each reader.


@dataclass(frozen=True)
class CountryInput:
    choose: object  # (Snapshot, proposal Snapshot) -> selections; [] is abstention
    consent: object  # (Snapshot, choices Snapshot) -> {choice_id: bool}


def refresh(world, source):
    """Runtime provenance; never edits the synthetic initial-world file."""
    b, n = world['physical'], world['network']
    for p in b['provenance']:
        p.update(kind='derived', source=source, explanation='Runtime state derived by declared TURN laws')
    n['baseline_hash'] = digest(b)
    validate_network(n, b)


def totals(world):
    result = {r['resource_id']: 0 for r in world['physical']['world']['resources']}
    for a in world['physical']['world']['accounts']:
        result[a['resource_id']] += a['balance']
    for r, q in world['pool'].items():
        result[r] += q
    for s in world['shipments']:
        if s['arrival_turn'] is None:
            result[s['resource']] += s['dispatched_amount']
    for p in world['production_pending']:
        result[p['resource']] += p['quantity']
    return result


def seal(record):
    result = deepcopy(record)
    result['output_digest'] = digest(result['world_state'])
    result['checkpoint_digest'] = digest(result)
    return result


def validate_checkpoint(cp):
    ensure(type(cp) is dict and cp.get('kind') == 'v3_offline_turn_checkpoint', 'INVALID_CHECKPOINT')
    raw = deepcopy(cp); checksum = raw.pop('checkpoint_digest', None)
    ensure(digest(raw) == checksum, 'CHECKPOINT_DIGEST_MISMATCH')
    ensure(cp['output_digest'] == digest(cp['world_state']), 'OUTPUT_DIGEST_MISMATCH')
    ensure(type(cp['turn']) is int and cp['turn'] >= 0, 'INVALID_TURN')
    w = cp['world_state']; validate_network(w['network'], w['physical'])
    states = {c['state_id'] for c in w['physical']['world']['countries']}
    resources = {r['resource_id'] for r in w['physical']['world']['resources']}
    ensure(set(w['pool']) == resources and all(type(v) is int and v >= 0 for v in w['pool'].values()), 'INVALID_POOL')
    ensure(len(w['seen_choice_ids']) == len(set(w['seen_choice_ids'])), 'CHOICE_ID_COLLISION')
    ids = set()
    for s in w['shipments']:
        ensure(s['shipment_id'] not in ids, 'DUPLICATE_SHIPMENT'); ids.add(s['shipment_id'])
        ensure(s['choice_id'] in w['seen_choice_ids'] and s['owner'] == s['target'], 'INVALID_SHIPMENT_OWNER')
        ensure(s['source'] in states | {'world_pool'} and s['target'] in states | {'world_pool'} and s['resource'] in resources, 'INVALID_SHIPMENT_REFERENCE')
        ensure(type(s['dispatched_amount']) is int and s['dispatched_amount'] > 0, 'INVALID_SHIPMENT_AMOUNT')
        ensure(type(s['dispatch_turn']) is int and 0 < s['dispatch_turn'] <= cp['turn'], 'INVALID_DISPATCH_TURN')
        ensure(type(s['arrival_due_turn']) is int and s['arrival_due_turn'] > s['dispatch_turn'], 'INVALID_ARRIVAL_DUE')
        ensure(s['arrived_amount'] == (0 if s['arrival_turn'] is None else s['dispatched_amount']), 'INVALID_ARRIVAL_AMOUNT')
        ensure((s['arrival_turn'] is None and s['arrival_due_turn'] > cp['turn']) or
               (type(s['arrival_turn']) is int and s['arrival_due_turn'] <= s['arrival_turn'] <= cp['turn']), 'INVALID_ARRIVAL_TURN')
    pids = set()
    for p in w['production_pending']:
        ensure(p['id'] not in pids, 'DUPLICATE_PRODUCTION'); pids.add(p['id'])
        ensure(p['owner'] in states and p['resource'] in resources, 'INVALID_PRODUCTION_REFERENCE')
        ensure(type(p['quantity']) is int and p['quantity'] > 0 and type(p['due_turn']) is int and p['due_turn'] > cp['turn'], 'INVALID_PENDING_PRODUCTION')
    ensure(len(cp['history']) == cp['turn'], 'INVALID_HISTORY_LENGTH')
    if cp['turn']:
        ensure(cp['input_digest'] == digest(cp['input']), 'INPUT_DIGEST_MISMATCH')
        ensure(all(p['evidence_hash'] == digest(cp['audit'][p['phase']]) for p in cp['phases']), 'AUDIT_DIGEST_MISMATCH')
        ensure(cp['evaluation']['world_hash'] == cp['output_digest'] and cp['evaluation']['world_state'] == w, 'EVALUATION_MISMATCH')
        ensure(cp['next_event_input']['world_hash'] == cp['output_digest'] and cp['next_event_input']['world_state'] == w, 'EVENT_INPUT_MISMATCH')
        ensure([p['phase'] for p in cp['phases']] == list(PHASES), 'PHASE_SEQUENCE_MISMATCH')
    return cp


class TurnFailure(TechnicalFailure):
    """Minimal machine-readable failure; excludes arbitrary exception text."""
    def __init__(self, code, *, phase, exception_type, last_valid_checkpoint):
        super().__init__(code)
        self.record = {'kind': 'technical_failure', 'completed': False, 'code': code,
                       'phase': phase, 'exception_type': exception_type,
                       'last_valid_checkpoint': last_valid_checkpoint}
        if phase == 'SETTLEMENT_TRANSACTION':
            self.record['phase_span'] = ['FEASIBILITY', 'JOINT_SETTLEMENT', 'ATOMIC_APPLY']


class TurnRunner:
    def __init__(self, baseline, network, *, pool_location, context_id, policy=None, search_budget=200000):
        validate_network(network, baseline)
        self.baseline, self.network = deepcopy(baseline), deepcopy(network)
        self.policy = policy or Policy('baseline')
        self.pool_location, self.context_id, self.search_budget = pool_location, context_id, search_budget
        ensure(pool_location in {c['state_id'] for c in baseline['world']['countries']}, 'INVALID_POOL_LOCATION')
        check(ID, context_id)
        self.config = deepcopy(self._configuration())
        self.config_hash = digest(self.config)

    def _configuration(self):
        return {'baseline': digest(self.baseline), 'network': digest(self.network), 'policy': self.policy.record(),
                'pool_location': self.pool_location, 'context_id': self.context_id,
                'rules': RULES, 'search_budget': self.search_budget}

    def _check_configuration(self):
        ensure(digest(self.config) == self.config_hash and
               digest(self._configuration()) == self.config_hash, 'TURN_CONFIGURATION_CHANGED')

    def genesis(self):
        self._check_configuration()
        w = {'physical': deepcopy(self.baseline), 'network': deepcopy(self.network),
             'pool': {r['resource_id']: 0 for r in self.baseline['world']['resources']},
             'shipments': [], 'production_pending': [], 'seen_choice_ids': []}
        return seal({'kind': 'v3_offline_turn_checkpoint', 'context_id': self.context_id,
                     'config_hash': self.config_hash, 'turn': 0, 'world_state': w, 'ledger': [],
                     'history': [], 'phases': [], 'audit': {}, 'input_digest': digest(self.config)})

    def run(self, opening, *, shocks=(), catalogue=None, countries=None, coordinator=None, pool_consent=None):
        progress = []
        try:
            return self._run(opening, shocks=shocks, catalogue=catalogue, countries=countries,
                             coordinator=coordinator, pool_consent=pool_consent, progress=progress)
        except Exception as error:
            phase = PHASES[min(len(progress), len(PHASES)-1)]
            if phase == 'FEASIBILITY': phase = 'SETTLEMENT_TRANSACTION'
            raise TurnFailure(getattr(error, 'code', 'RUNTIME_OR_SCHEMA_ERROR'), phase=phase,
                              exception_type=type(error).__name__,
                              last_valid_checkpoint=opening.get('checkpoint_digest') if isinstance(opening, dict) else None) from None

    def replay(self, opening, recorded_input):
        """Rehydrate offline input without invoking the original actor callbacks."""
        self._check_configuration()
        ensure(recorded_input['config'] == self.config, 'REPLAY_CONFIG_MISMATCH')
        ensure(recorded_input['opening'] == opening['checkpoint_digest'], 'REPLAY_OPENING_MISMATCH')
        record = deepcopy(recorded_input)
        countries = {sid: CountryInput(lambda *_args, sid=sid: deepcopy(record['selections'][sid]),
                                      lambda *_args, sid=sid: deepcopy(record['consents'][sid]))
                     for sid in record['selections']}
        result = self.run(opening, shocks=record['shocks'], catalogue=lambda _: deepcopy(record['catalogue']),
                          countries=countries, coordinator=lambda _: deepcopy(record['proposal']),
                          pool_consent=(lambda *_: deepcopy(record['consents']['world_pool'])) if 'world_pool' in record['consents'] else None)
        ensure(result['input_digest'] == digest(record), 'REPLAY_INPUT_MISMATCH')
        return result

    def _run(self, opening, *, shocks, catalogue, countries, coordinator, pool_consent, progress):
        """Produce a candidate only. CheckpointStore is the durable adoption boundary.

        catalogue is a trusted Python factory; countries can select IDs/amounts
        only. Callback exceptions propagate, with no completed checkpoint.
        """
        self._check_configuration()
        validate_checkpoint(opening)
        ensure(opening['config_hash'] == self.config_hash and opening['context_id'] == self.context_id, 'CONFIGURATION_MISMATCH')
        def invoke(callback, *args):
            self._check_configuration()
            result = callback(*args)
            self._check_configuration()
            return result
        w = deepcopy(opening['world_state']); turn = opening['turn'] + 1
        before = totals(w); phases = progress; evidence = {}
        def phase(name, data):
            ensure(name == PHASES[len(phases)], 'PHASE_ORDER_ERROR')
            phases.append({'phase': name, 'evidence_hash': digest(data)})
            evidence[name] = deepcopy(data)
        phase('TURN_OPEN', {'checkpoint': opening['checkpoint_digest']})
        accounts = {(a['owner'], a['resource_id']): a for a in w['physical']['world']['accounts']}
        arrivals = []
        for s in w['shipments']:
            if s['arrival_turn'] is None and s['arrival_due_turn'] <= turn:
                if s['target'] == 'world_pool': w['pool'][s['resource']] += s['dispatched_amount']
                else: accounts[s['target'], s['resource']]['balance'] += s['dispatched_amount']
                s.update(arrival_turn=turn, arrived_amount=s['dispatched_amount']); arrivals.append(deepcopy(s))
        remaining = []
        for p in w['production_pending']:
            if p['due_turn'] <= turn:
                accounts[p['owner'], p['resource']]['balance'] += p['quantity']; arrivals.append(deepcopy(p))
            else: remaining.append(p)
        w['production_pending'] = remaining
        phase('ARRIVAL', arrivals)
        shocks = deepcopy(list(shocks))
        for event in shocks: check(SHOCK, event)
        shocks.sort(key=lambda e: e['event_id'])
        ensure(len({s['event_id'] for s in shocks}) == len(shocks), 'DUPLICATE_EVENT')
        loss = {r: 0 for r in before}
        for event in shocks: self._shock(w, event, loss)
        refresh(w, opening['checkpoint_digest'])
        phase('SHOCK', shocks)
        b, n = w['physical'], w['network']
        ids = sorted(c['state_id'] for c in b['world']['countries'])
        auth = Authority(ids); core = auth.issue('core')
        engine = SettlementEngine(b, n, auth, [self.policy], pool_location=self.pool_location,
                                  context_id=self.context_id, pool_balances=w['pool'], search_budget=self.search_budget)
        state = engine.restore_history(core, turn=turn, shipments=w['shipments'], seen_choice_ids=w['seen_choice_ids'])
        observation = Snapshot.of({'turn': turn, 'world_state': w, 'settlement_snapshot': engine.read(state)})
        phase('OBSERVATION_FREEZE', observation.read())
        proposal = None if coordinator is None else invoke(coordinator, observation)
        if proposal is not None: check(PROPOSAL, proposal)
        proposal = Snapshot.of(proposal)
        phase('COORDINATOR_INPUT', proposal.read())
        templates = [] if catalogue is None else deepcopy(invoke(catalogue, observation))
        ensure(type(templates) is list, 'INVALID_CATALOGUE')
        for template in templates: check(TEMPLATE, template)
        ensure(len({t['choice_id'] for t in templates}) == len(templates), 'CHOICE_ID_COLLISION')
        templates.sort(key=lambda t: t['choice_id'])
        countries = {} if countries is None else dict(countries)
        ensure(set(countries) <= set(ids), 'UNKNOWN_COUNTRY_ADAPTER')
        selections = {}; choices = []; principals = {s: auth.issue('country', s) for s in ids}
        for sid in ids:
            selected = [] if sid not in countries else invoke(countries[sid].choose, observation, proposal)
            ensure(type(selected) is list, 'INVALID_SELECTION_LIST')
            selections[sid] = sorted(deepcopy(selected), key=lambda s: s['choice_id'])
        phase('CHOICE_COLLECTION', selections)
        for sid in ids:
            for selection in selections[sid]:
                choice = materialize_choice(selection, templates)
                ensure(choice['actor_state_id'] == sid, 'ACTOR_AUTHORITY_REQUIRED')
                choices.append(choice)
        choices.sort(key=lambda c: c['choice_id'])
        ensure(len({c['choice_id'] for c in choices}) == len(choices), 'CHOICE_ID_COLLISION')
        choice_view = Snapshot.of(choices); by_id = {c['choice_id']: c for c in choices}; consents = []
        consent_record = {}
        for sid in ids + (['world_pool'] if pool_consent else []):
            callback = pool_consent if sid == 'world_pool' else (countries[sid].consent if sid in countries else None)
            answers = {} if callback is None else invoke(callback, observation, choice_view)
            ensure(type(answers) is dict and set(answers) <= set(by_id), 'INVALID_CONSENT_REFERENCE')
            consent_record[sid] = deepcopy(answers)
            principal = auth.issue('pool') if sid == 'world_pool' else principals[sid]
            for cid, accepted in sorted(answers.items()):
                consents.append(auth.consent(principal, by_id[cid], accepted=accepted))
        submissions = [auth.submit(principals[c['actor_state_id']], c) for c in choices]
        phase('CHOICE_VALIDATION', {'catalogue': templates, 'choices': choices, 'consents': consent_record})
        # Phase-four settle encapsulates feasibility -> joint allocation -> atomic
        # apply. Record its actual evidence only after the complete call succeeds.
        settled = engine.read(engine.settle(core, state, submissions, consents, policy_id=self.policy.policy_id,
                                           condition_catalogue=templates))
        audit = settled['audits'][-1]
        phase('FEASIBILITY', [a['individual'] for a in audit['choices']])
        phase('JOINT_SETTLEMENT', audit)
        phase('ATOMIC_APPLY', {'before': digest(engine.read(state)), 'after': digest(settled)})
        for (sid, rid), a in accounts.items(): a['balance'] = settled['stock'][sid][rid]
        w.update(pool=settled['pool'], shipments=settled['shipments'], seen_choice_ids=settled['seen_choice_ids'])
        phase('TRANSIT_UPDATE', w['shipments'])
        ledger = []; consumed = {r: 0 for r in before}
        for country in sorted(b['world']['countries'], key=lambda c: c['state_id']):
            for d in sorted(country['demands'], key=lambda d: d['resource_id']):
                a = accounts[country['state_id'], d['resource_id']]; amount = min(a['balance'], d['quantity'])
                a['balance'] -= amount; consumed[d['resource_id']] += amount
                ledger.append({'owner': country['state_id'], 'resource': d['resource_id'], 'consumed': amount,
                               'required': d['quantity'], 'shortage': d['quantity'] - amount})
        phase('CONSUMPTION', ledger)
        production, inputs, outputs = self._produce(w, turn)
        phase('PRODUCTION', production)
        phase('RECOVERY', {'status': 'NO_DEFINED_RECOVERY_LAW', 'applied': []})
        refresh(w, digest({'opening': opening['checkpoint_digest'], 'turn': turn, 'shocks': shocks}))
        expected = {r: before[r] - loss[r] - consumed[r] - inputs[r] + outputs[r] for r in before}
        ensure(totals(w) == expected, 'RESOURCE_CONSERVATION_VIOLATION')
        conservation = {'opening': before, 'loss': loss, 'consumed': consumed,
                        'production_inputs': inputs, 'production_outputs': outputs, 'closing': totals(w)}
        phase('CONSERVATION', conservation)
        end_hash = digest(w); phase('TURN_CLOSE', {'world_hash': end_hash})
        evaluation = {'world_hash': end_hash, 'world_state': deepcopy(w)}
        phase('EVALUATION_SNAPSHOT', evaluation)
        history = deepcopy(opening['history']) + [{'turn': turn, 'events': shocks, 'choices': choices,
                                                  'settlement': audit, 'world_hash': end_hash}]
        next_input = {'world_hash': end_hash, 'world_state': deepcopy(w), 'shortages': ledger,
                      'capacity_profiles': deepcopy(b['capacity_profiles']),
                      'network_load': audit['joint_reservations'],
                      'unresolved_conditions': [a for a in audit['choices'] if a['reason_codes']], 'history': history}
        phase('NEXT_EVENT_INPUT', next_input)
        input_record = {'opening': opening['checkpoint_digest'], 'shocks': shocks, 'catalogue': templates,
                        'selections': selections, 'consents': consent_record, 'proposal': proposal.read(), 'config': self.config}
        phase('AUDIT', {'input_digest': digest(input_record), 'output_digest': end_hash})
        phase('CHECKPOINT', {'adoption': 'validated atomic CheckpointStore save required', 'world_hash': end_hash})
        self._check_configuration()
        cp = seal({'kind': 'v3_offline_turn_checkpoint', 'context_id': self.context_id, 'config_hash': self.config_hash,
                   'turn': turn, 'world_state': w, 'ledger': ledger, 'history': history, 'phases': phases,
                   'audit': evidence, 'input': input_record, 'input_digest': digest(input_record),
                   'evaluation': evaluation, 'next_event_input': next_input})
        validate_checkpoint(cp)
        return cp

    @staticmethod
    def _shock(w, event, losses):
        target, resource, amount = event['target'], event['resource'], event['amount']
        ensure(type(amount) is int, 'INTEGER_QUANTITY_REQUIRED')
        b = w['physical']; kind = event['kind']
        if kind == 'resource_loss':
            a = next((a for a in b['world']['accounts'] if a['account_id'] == target), None)
            ensure(a is not None and a['resource_id'] == resource and amount <= a['balance'], 'INVALID_RESOURCE_LOSS')
            a['balance'] -= amount; losses[resource] += amount
        elif kind == 'capacity_loss':
            ensure(resource is None, 'INVALID_CAPACITY_EVENT')
            p = next((p for p in b['capacity_profiles'] if p['capacity_id'] == target), None)
            ensure(p is not None and amount <= p['current_capacity'], 'INVALID_CAPACITY_LOSS')
            p['current_capacity'] -= amount
            cap = next(c for c in b['world']['capacities'] if c['capacity_id'] == target)
            cap['available'] = p['current_capacity'] * p['utilization_ppm'] // 1000000
        elif kind == 'route_stop':
            r = next((r for r in w['network']['routes'] if r['route_id'] == target), None)
            ensure(r is not None and resource is None and amount == 0, 'INVALID_ROUTE_EVENT'); r['availability'] = False
        else:
            c = next((c for c in b['world']['countries'] if c['state_id'] == target), None)
            ensure(c is not None, 'INVALID_DEMAND_OWNER')
            d = next((d for d in c['demands'] if d['resource_id'] == resource), None)
            ensure(d is not None, 'INVALID_DEMAND_RESOURCE'); d['quantity'] = amount

    @staticmethod
    def _produce(w, turn):
        b, n = w['physical'], w['network']
        accounts = {(a['owner'], a['resource_id']): a for a in b['world']['accounts']}
        profiles = {p['capacity_id']: p for p in b['capacity_profiles']}
        deps = n['production_dependencies']; plans = []
        inputs = {r: 0 for r in w['pool']}; outputs = dict(inputs)
        for c in sorted(b['world']['capacities'], key=lambda c: c['capacity_id']):
            if c['category'] != 'production': continue
            needs = [d for d in deps if d['production_capacity_id'] == c['capacity_id']]
            batch = lcm(*(d['output_batch'] for d in needs)) if needs else 1
            plans.append({'capacity_id': c['capacity_id'], 'owner': c['owner'],
                          'resource': profiles[c['capacity_id']]['resource_id'], 'batch': batch,
                          'maximum': c['available'] // batch * batch, 'needs': needs})
        # Consumers of each shared input use an explicit proportional scale.
        # Frozen post-consumption stock prevents production order advantage.
        scales = {}
        required = {}
        for p in plans:
            for d in p['needs']:
                key = p['owner'], d['input_resource']
                required[key] = required.get(key, 0) + p['maximum'] // d['output_batch'] * d['required_input']
        for (owner, resource), amount in required.items():
            ratio = min(Fraction(1), Fraction(accounts[owner, resource]['balance'], amount)) if amount else Fraction(1)
            scales[owner, resource] = ratio
        records = []
        for p in plans:
            scale = min((scales[p['owner'], d['input_resource']] for d in p['needs']), default=Fraction(1))
            q = p['maximum'] * scale // p['batch'] * p['batch']
            debits = []
            for d in p['needs']:
                amount = q // d['output_batch'] * d['required_input']
                accounts[p['owner'], d['input_resource']]['balance'] -= amount
                inputs[d['input_resource']] += amount
                debits.append({'resource': d['input_resource'], 'amount': amount, 'dependency': d['dependency_id']})
            delay = max((d['output_delay'] for d in p['needs']), default=0)
            outputs[p['resource']] += q
            records.append({'capacity_id': p['capacity_id'], 'owner': p['owner'], 'resource': p['resource'],
                            'quantity': q, 'inputs': debits, 'available_turn': turn + delay})
        # Credit only after every input debit; outputs never feed this phase.
        for row in records:
            if row['available_turn'] == turn:
                accounts[row['owner'], row['resource']]['balance'] += row['quantity']
            elif row['quantity']:
                w['production_pending'].append({'id': str(turn)+':'+row['capacity_id'], 'owner': row['owner'],
                    'resource': row['resource'], 'quantity': row['quantity'], 'due_turn': row['available_turn']})
        return records, inputs, outputs
