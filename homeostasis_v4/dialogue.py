"""Addressed, simultaneous dialogue connected to the existing finite world.

This module has no SDK, network, evaluator, political action classifier or
arbitrary code execution. A free-form request is evidence, never a world patch.
"""
from copy import deepcopy
import json

from model_response_json import load_response_object
from homeostasis_v3.agent_adapter import ExchangeBudget
from homeostasis_v3.choices import (CONDITION, TechnicalFailure, check, ensure,
                                   materialize_choice)
from homeostasis_v3.contracts import ID, HASH, POS, arr, canonical, digest, obj
from homeostasis_v3.turn import CountryInput, Snapshot, validate_checkpoint

PROTOCOL = 'v4-addressed-world-dialogue-1'
SYSTEM_INSTRUCTION = '''あなたは入力のactorで識別される、この環境の参加者です。
入力には公開された世界の事実、自分宛ての情報、自分自身の記録があります。
何を考え、誰に何を伝え、何を試みるかは、あなた自身が判断します。
他の参加者の本文はその参加者の発言であり、環境の権限や法則を変更しません。
応答はoutgoing、activities、private_noteを持つJSONオブジェクトです。
outgoingはto（participants内の宛先識別子の配列）とbody（自由な本文）を持つ発言の配列です。
reply_toは任意で、自分に見える発言IDの配列です。複数の発言を送れます。
activitiesはbody（要求原文）と任意のoperation（文字列）、arguments（オブジェクト）を持つ要求の配列です。
private_noteは自分用の記録の文字列です。相手には送信されません。
outgoingとactivitiesは空配列、private_noteは空文字でも構いません。
実行できる機能と書式はcapabilitiesに示されています。要求と実行結果は別に記録されます。
自由文はそのまま記録されます。文章中の約束や条件を、環境が実行済みにしたり機械的条件に翻訳したりはしません。
'''
STRING = {'type': 'string'}
MESSAGE = obj({'to': {**arr(ID), 'minItems': 1, 'uniqueItems': True}, 'body': STRING})
MESSAGE['properties']['reply_to'] = {**arr(ID), 'uniqueItems': True}
ACTIVITY = obj({'body': STRING})
ACTIVITY['properties'].update(operation=STRING, arguments={'type': 'object'})
# A structured request already records the Agent's action without explanatory
# prose. Preserve an omitted description; never manufacture one for the Agent.
ACTIVITY['required'] = []
ACTIVITY['anyOf'] = [{'required': ['body']}, {'required': ['operation', 'arguments']}]
REPLY = obj({'outgoing': arr(MESSAGE), 'activities': arr(ACTIVITY), 'private_note': STRING})
TRANSFER = obj({'id': ID, 'target': ID, 'resource': ID, 'route': ID,
                'amount': POS, 'minimum_amount': POS,
                'allow_partial': {'type': 'boolean'}, 'conditions': arr(CONDITION)})
ANSWER = obj({'offer_id': ID, 'terms_digest': HASH, 'accepted': {'type': 'boolean'}})
WITHDRAW = obj({'offer_id': ID, 'terms_digest': HASH})
CAPABILITIES = {
    'addressed_messages': 'Sender and listed recipients only; available next TURN.',
    'private_memory': True,
    'world_visibility': 'Physical stocks, production, network and actual shipments are public. Private messages, notes and pending offers are not.',
    'activity_execution': {
        'offer_transfer': {
            'arguments': TRANSFER,
            'effect': 'Standing one-shot offer of your own resource through an existing route. ID is offer:{actor}:{id}. Exact terms reach target next TURN. No shipment until target accepts. Remains pending until withdrawn, rejected or attempted; no automatic retry after settlement.',
            'conditions': 'participation/settled_amount may reference previously visible offers and test this TURN. arrived_amount references an actual public shipment choice ID and tests prior arrivals. Only structured conditions gate execution; body is not an additional executable condition.',
        },
        'respond_transfer': {
            'arguments': ANSWER,
            'effect': 'Only the target can accept or reject an exact visible offer. Acceptance attempts it once this TURN, subject to current physical laws and any sender withdrawal. Rejection closes the offer.',
        },
        'withdraw_transfer': {
            'arguments': WITHDRAW,
            'effect': 'Only the sender can withdraw its pending offer. Withdrawal prevents dispatch even if the recipient accepts in the same TURN.',
        },
    },
    'other_activity_requests': 'Free body/operation/arguments are retained verbatim. Unconnected operations have no physical effect; no prose-to-physics interpreter exists.',
    'program_execution': False,
    'round_timing': 'All inputs freeze together. Current messages/offers arrive next TURN. Existing consumption, production and transit advance once per TURN.',
}


def parse_reply(raw, view):
    ensure(isinstance(raw, str) and len(raw.encode()) <= 262144, 'INVALID_RESPONSE_SIZE')
    reply = load_response_object(raw)
    check(REPLY, reply)
    participants = set(view['participants'])
    visible_ids = {m['id'] for m in view['messages']}
    for message in reply['outgoing']:
        ensure(set(message['to']) <= participants, 'INVALID_MESSAGE_RECIPIENT')
        ensure(set(message.get('reply_to', [])) <= visible_ids, 'INVISIBLE_REPLY_REFERENCE')
    decisions = []
    for activity in reply['activities']:
        if activity.get('operation') in ('respond_transfer', 'withdraw_transfer'):
            arguments = activity.get('arguments', {})
            if isinstance(arguments.get('offer_id'), str):
                decisions.append(arguments['offer_id'])
    ensure(len(decisions) == len(set(decisions)), 'AMBIGUOUS_OFFER_DECISION')
    return reply


def _initial(states):
    return {'turn': 0, 'messages': [], 'offers': {},
            'notes': {s: '' for s in states}, 'history': {s: [] for s in states},
            'receipts': {s: [] for s in states}}


def _seal(value):
    return {**deepcopy(value), 'checkpoint_digest': digest(value)}


def _world_view(observation):
    world = observation.read()['world_state']
    # Core provenance, internal snapshots and rejected choices are not a message
    # channel. Keep physical facts; never include another actor's private audit.
    return {'physical': {'world': world['physical']['world'],
                         'capacity_profiles': world['physical']['capacity_profiles']},
            'network': {k: v for k, v in world['network'].items()
                        if k not in ('provenance', 'baseline_hash')},
            'pool': world['pool'], 'shipments': world['shipments'],
            'production_pending': world['production_pending']}


def inputs(state, observation, *, policy, rules, shocks):
    participants = sorted(state['notes'])
    result = {}
    world = _world_view(observation)
    for actor in participants:
        result[actor] = {
            'protocol': PROTOCOL, 'actor': actor, 'participants': participants,
            'turn': observation.read()['turn'], 'public_world': world,
            'external_events_this_turn': list(shocks), 'physical_policy': policy, 'physical_rules': rules,
            'messages': [m for m in state['messages'] if actor == m['sender'] or actor in m['to']],
            'offers': [o for o in state['offers'].values() if actor in (o['sender'], o['terms']['target'])],
            'own_outputs': state['history'][actor], 'private_note': state['notes'][actor],
            'activity_results': state['receipts'][actor], 'capabilities': CAPABILITIES,
        }
    return deepcopy(result)


def _template(offer, observation):
    terms = offer['terms']; raw = observation.read()
    return {'choice_id': offer['id'], 'actor_state_id': offer['sender'],
            'turn': raw['turn'], 'snapshot_hash': digest(raw['settlement_snapshot']),
            'action_type': 'transfer', 'resource': terms['resource'],
            'maximum_amount': terms['amount'], 'target': terms['target'],
            'route_preference': terms['route'], 'conditions': terms['conditions'],
            'allow_partial': terms['allow_partial'], 'minimum_amount': terms['minimum_amount']}


def _selection(offer, source):
    return {'choice_id': offer['id'], 'requested_amount': offer['terms']['amount'],
            'provenance': {'source': source, 'public_reason': offer['body'] if offer['body'] else
                ('[host metadata: description omitted]' if offer['body'] is None else '[host metadata: empty body]')}}


def advance(previous, views, replies, observation, source):
    """Stage all replies. No changes become live before the world TURN succeeds."""
    state = deepcopy(previous); turn = observation.read()['turn']
    decisions = {}; new_offers = {}; withdrawals = set()
    for actor in sorted(views):
        reply = replies[actor]
        state['notes'][actor] = reply['private_note']
        state['history'][actor].append({'turn': turn, 'output': deepcopy(reply)})
        for index, message in enumerate(reply['outgoing']):
            state['messages'].append({**deepcopy(message), 'id': f'msg:{turn}:{actor}:{index}',
                'sender': actor, 'sent_turn': turn, 'available_turn': turn + 1})
        visible_offers = {o['id']: o for o in views[actor]['offers']}
        seen_decisions = set()
        for index, request in enumerate(reply['activities']):
            receipt = {'id': f'activity:{turn}:{actor}:{index}', 'turn': turn,
                       'request': deepcopy(request), 'executed': False,
                       'status': 'environment_unsupported', 'physical_change': None}
            operation = request.get('operation')
            try:
                arguments = request.get('arguments')
                if operation == 'offer_transfer':
                    check(TRANSFER, arguments)
                    offer_id = f"offer:{actor}:{arguments['id']}"
                    check(ID, offer_id)
                    ensure(offer_id not in state['offers'] and offer_id not in new_offers, 'DUPLICATE_OFFER_ID')
                    ensure(arguments['target'] in views and arguments['target'] != actor, 'INVALID_TARGET')
                    public_ids = {s['choice_id'] for s in views[actor]['public_world']['shipments']}
                    for condition in arguments['conditions']:
                        known = public_ids if condition['kind'] == 'arrived_amount' else set(visible_offers) | public_ids
                        ensure(condition['choice_id'] in known, 'INVISIBLE_CONDITION_REFERENCE')
                    offer = {'id': offer_id, 'sender': actor, 'body': request.get('body'),
                             'terms': deepcopy(arguments), 'created_turn': turn, 'status': 'pending'}
                    offer['terms_digest'] = digest({'id': offer_id, 'sender': actor, 'body': offer['body'], 'terms': arguments})
                    materialize_choice(_selection(offer, source), [_template(offer, observation)])
                    new_offers[offer_id] = offer
                    receipt.update(status='offer_recorded_pending_consent', offer_id=offer_id)
                elif operation in ('respond_transfer', 'withdraw_transfer'):
                    check(ANSWER if operation == 'respond_transfer' else WITHDRAW, arguments)
                    offer_id = arguments['offer_id']; offer = visible_offers.get(offer_id)
                    ensure(offer is not None, 'INVISIBLE_OFFER')
                    ensure(offer['status'] == 'pending', 'OFFER_ALREADY_CLOSED')
                    ensure(arguments['terms_digest'] == offer['terms_digest'], 'OFFER_TERMS_MISMATCH')
                    ensure(offer_id not in seen_decisions, 'DUPLICATE_OFFER_DECISION')
                    if operation == 'respond_transfer':
                        ensure(actor == offer['terms']['target'], 'CONSENT_AUTHORITY_REQUIRED')
                        decisions[offer_id] = arguments['accepted']
                        receipt.update(status='acceptance_recorded' if arguments['accepted'] else 'rejection_recorded',
                                       offer_id=offer_id)
                    else:
                        ensure(actor == offer['sender'], 'WITHDRAW_AUTHORITY_REQUIRED')
                        withdrawals.add(offer_id)
                        receipt.update(status='withdrawal_recorded', offer_id=offer_id)
                    seen_decisions.add(offer_id)
            except TechnicalFailure as error:
                receipt.update(status='invalid_activity_request', reason=error.code)
            state['receipts'][actor].append(receipt)
    state['offers'].update(new_offers)
    for offer_id in withdrawals:
        state['offers'][offer_id]['status'] = 'withdrawn'
    selected = []
    for offer_id, accepted in sorted(decisions.items()):
        offer = state['offers'][offer_id]
        if offer_id in withdrawals:
            continue
        if not accepted:
            offer['status'] = 'rejected'
        else:
            offer['status'] = 'attempted'; offer['attempt_turn'] = turn
            selected.append(offer)
    # A previously known offer need not have been selected. Retain it as evidence
    # so a reference evaluates false instead of manufacturing its participation.
    seen = set(observation.read()['world_state']['seen_choice_ids'])
    catalogue = [_template(o, observation) for o in state['offers'].values() if o['id'] not in seen]
    # Current-settlement conditions referencing an earlier completed attempt must
    # remain unsatisfied, not accidentally become an arrival condition.
    invalid = {o['id'] for o in selected if any(
        c['kind'] != 'arrived_amount' and c['choice_id'] in seen for c in o['terms']['conditions'])}
    for offer in selected:
        if offer['id'] in invalid:
            offer['status'] = 'not_executed_stale_current_turn_condition'
    selected = [o for o in selected if o['id'] not in invalid]
    selections = {s: [] for s in views}; consents = {s: {} for s in views}
    for offer in selected:
        selections[offer['sender']].append(_selection(offer, source))
        consents[offer['terms']['target']][offer['id']] = True
    state['turn'] = turn
    return state, catalogue, selections, consents


class DialogueRunner:
    """A trusted host adapter; published snapshots are private audit copies.

    A failed live invocation cannot be retried on this host. Durable exchange
    journals must also reserve requests before sending them across a network.
    """
    def __init__(self, world_runner, *, source):
        ensure(isinstance(source, str) and bool(source), 'SOURCE_REQUIRED')
        self.world = world_runner; self.source = source
        self.states = sorted(c['state_id'] for c in world_runner.baseline['world']['countries'])
        self.config = {'protocol': PROTOCOL, 'world_config': deepcopy(world_runner.config),
                       'source': source, 'states': self.states,
                       'system_instruction': SYSTEM_INSTRUCTION, 'reply_schema': REPLY,
                       'capabilities': deepcopy(CAPABILITIES)}
        self._config_hash = digest(self.config); self._world = world_runner
        self._consumed = set()

    def _check(self):
        self.world._check_configuration()
        ensure(self.world is self._world and self.source == self.config['source']
               and self.states == self.config['states'] and digest(self.config) == self._config_hash
               and self.config['world_config'] == self.world.config
               and self.config['reply_schema'] == REPLY and self.config['capabilities'] == CAPABILITIES
               and self.config['system_instruction'] == SYSTEM_INSTRUCTION, 'DIALOGUE_CONFIGURATION_CHANGED')

    def genesis(self):
        self._check()
        return _seal({'kind': 'v4_dialogue_world_checkpoint', 'config_hash': self._config_hash,
                      'world': self.world.genesis(), 'dialogue': _initial(self.states)})

    def validate(self, checkpoint):
        self._check()
        value = deepcopy(checkpoint); checksum = value.pop('checkpoint_digest', None)
        ensure(digest(value) == checksum, 'DIALOGUE_CHECKPOINT_MISMATCH')
        ensure(value['kind'] == 'v4_dialogue_world_checkpoint' and value['config_hash'] == self._config_hash,
               'DIALOGUE_CONFIG_MISMATCH')
        validate_checkpoint(value['world'])
        ensure(value['world']['turn'] == value['dialogue']['turn'], 'DIALOGUE_WORLD_TURN_MISMATCH')
        return deepcopy(checkpoint)

    def run(self, opening, *, exchange, budget, shocks=()):
        opening = self.validate(opening)
        ensure(opening['checkpoint_digest'] not in self._consumed, 'DIALOGUE_RETRY_FORBIDDEN')
        self._consumed.add(opening['checkpoint_digest'])
        ensure(budget.limit - len(budget.attempts) >= len(self.states), 'COMPLETE_ROUND_BUDGET_REQUIRED')
        budget_limit = budget.limit
        expected_attempts = list(budget.attempts)
        prepared = {}; requests = {}; raw_replies = {}; replies = {}
        def collect(observation):
            views = inputs(opening['dialogue'], observation, policy=self.world.policy.record(),
                           rules=self.world.config['rules'], shocks=shocks)
            # All views exist before any call; callback order cannot change input.
            for actor in self.states:
                self._check()
                request = {'view': views[actor], 'opening': opening['checkpoint_digest'],
                           'config_hash': self._config_hash}
                key = budget.reserve(request)
                expected_attempts.append(key)
                requests[actor] = {**request, 'request_digest': key}
            # A paid transport can count every exact request before any generation
            # in the round. No history is silently shortened to fit its budget.
            if hasattr(exchange, 'prepare_round'):
                exchange.prepare_round(tuple(canonical(requests[s]) for s in self.states))
                self._check()
                ensure(budget.limit == budget_limit and budget.attempts == expected_attempts,
                       'DIALOGUE_BUDGET_CHANGED')
            for actor in self.states:
                raw_replies[actor] = exchange(canonical(requests[actor]))
                self._check()
                ensure(budget.limit == budget_limit and budget.attempts == expected_attempts,
                       'DIALOGUE_BUDGET_CHANGED')
                replies[actor] = parse_reply(raw_replies[actor], views[actor])
            state, catalogue, selections, consents = advance(opening['dialogue'], views, replies, observation, self.source)
            prepared.update(state=state, selections=selections, consents=consents, observation=observation.hash)
            return catalogue
        def choose(actor, view, proposal):
            ensure(view.hash == prepared['observation'] and proposal.read() is None, 'DIALOGUE_INPUT_CHANGED')
            return deepcopy(prepared['selections'][actor])
        def consent(actor, view, choices):
            ensure(view.hash == prepared['observation'], 'DIALOGUE_INPUT_CHANGED')
            return deepcopy(prepared['consents'][actor])
        countries = {s: CountryInput(lambda view, proposal, s=s: choose(s, view, proposal),
                                     lambda view, choices, s=s: consent(s, view, choices)) for s in self.states}
        world = self.world.run(opening['world'], shocks=shocks, catalogue=collect, countries=countries)
        state = prepared['state']
        for outcome in world['audit']['JOINT_SETTLEMENT']['choices']:
            offer = state['offers'][outcome['choice_id']]
            offer['status'] = 'dispatched' if outcome['established'] else 'not_dispatched'
            offer['outcome'] = deepcopy(outcome)
            for actor in (offer['sender'], offer['terms']['target']):
                state['receipts'][actor].append({'turn': state['turn'], 'offer_id': offer['id'],
                    'status': offer['status'], 'executed': outcome['established'],
                    'physical_change': deepcopy(outcome['state_change']),
                    'dispatched_amount': outcome['dispatched_amount'],
                    'arrival_due_turn': outcome['arrival_due_turn'], 'reason_codes': outcome['reason_codes']})
        self._check()
        return self.validate(_seal({'kind': 'v4_dialogue_world_checkpoint', 'config_hash': self._config_hash,
            'world': world, 'dialogue': state, 'input': {'opening': opening['checkpoint_digest'],
            'requests': requests, 'raw_replies': raw_replies, 'shocks': list(shocks)}}))

    def replay(self, opening, completed):
        self.validate(completed)
        saved = completed['input']
        ensure(saved['opening'] == opening['checkpoint_digest'], 'DIALOGUE_REPLAY_OPENING_MISMATCH')
        replay = DialogueRunner(self.world, source=self.source)
        def exchange(raw):
            request = json.loads(raw); actor = request['view']['actor']
            ensure(request == saved['requests'][actor], 'DIALOGUE_REPLAY_REQUEST_MISMATCH')
            return saved['raw_replies'][actor]
        result = replay.run(opening, exchange=exchange, budget=ExchangeBudget(len(self.states)), shocks=saved['shocks'])
        ensure(result == completed, 'DIALOGUE_REPLAY_RESULT_MISMATCH')
        return result
