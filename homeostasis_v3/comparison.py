"""Paired exploratory pilot. Real responses and deterministic controls stay distinct."""
from copy import deepcopy
import json
from pathlib import Path

from .agent_adapter import ExchangeBudget
from .autonomous import AutonomousRound
from .checkpoint import CheckpointStore
from .choices import ensure
from .contracts import canonical, digest
from .observation import observe, validate_observation
from .physical import load_baseline
from .network import load_network
from .turn import TurnRunner
from .validation_runner import _write

SEEDS = (17, 23, 41)
TURNS = 5
PILOT_DIRECTORY = '.artifacts/v3-paid-expanded-20260919'


def consent_schema(choice_ids=None):
    from .agent_adapter import RESPONSE
    schema = deepcopy(RESPONSE)
    schema['properties']['decisions']['maxItems'] = 0
    if choice_ids is not None:
        schema['properties']['consents'] = {
            'type': 'object', 'properties': {cid: {'type': 'boolean'} for cid in choice_ids},
            'required': list(choice_ids), 'additionalProperties': False}
    return schema


PILOT_INSTRUCTION = '''
Transfer semantics: actor_state_id is the sender: its own inventory decreases on dispatch.
Target is the recipient. Offering a transfer does not acquire resources from the target.
Choose only opportunities owned by state_id; no action is required.
In consent phase decisions MUST be an empty array []. Only consents records acceptance or
refusal of listed choice IDs. Explicitly answer true or false for EVERY listed choice ID.
True is your own consent only, never another country's consent. False means you do not consent.
Do not leave consents empty. Neither acceptance nor refusal is prescribed. Do not repeat an earlier initiative in decisions.
'''


def deterministic(request_json):
    """Offer up to two surplus units to the reachable neighbor with greatest need.

    Keep two TURNs of own essential demand. At most one offer, no fixed partner.
    Accept transfers; never fabricate another state's initiative or consent.
    """
    r = json.loads(request_json)
    answer = {'state_id': r['state_id'], 'request_digest': r['request_digest']}
    if r['phase'] == 'consent':
        return canonical({**answer, 'decisions': [],
                          'consents': {c['choice_id']: True for c in r['payload']['choices']}})
    world = r['observation']['world_state']['physical']['world']
    stocks = {(a['owner'], a['resource_id']): a['balance'] for a in world['accounts']}
    demands = {(c['state_id'], d['resource_id']): d['quantity'] for c in world['countries'] for d in c['demands']}
    candidates = []
    for t in r['payload']['opportunities']:
        if t['actor_state_id'] != r['state_id']: continue
        own, other = (r['state_id'], t['resource']), (t['target'], t['resource'])
        surplus = stocks[own] - 2 * demands[own]
        need = max(0, 2 * demands[other] - stocks[other])
        amount = min(2, surplus, need)
        if amount > 0: candidates.append((-need, t['route_preference'], t['resource'], t['choice_id'], amount))
    intents = []
    if candidates:
        _, _, _, cid, amount = min(candidates)
        intents = [{'opportunity_id': cid, 'requested_amount': amount, 'minimum_amount': amount,
                    'allow_partial': False, 'conditions': [],
                    'public_reason': 'Rule control: preserve two TURNs of demand; offer surplus to greatest reachable shortage.'}]
    return canonical({**answer, 'initiatives': intents, 'extension_requests': []})


def inputs(root):
    b = load_baseline(Path(root)/'scenarios/v3/synthetic_baseline.json')
    return b, load_network(Path(root)/'scenarios/v3/synthetic_network.json', b)


def protocol(root):
    from .gemini_preflight import SYSTEM_INSTRUCTION
    from .autonomous import INITIATIVE_RESPONSE
    from .agent_adapter import RESPONSE
    b, n = inputs(root)
    return {'kind': 'v3_paired_exploratory_pilot', 'seeds': list(SEEDS), 'turns': TURNS,
            'states': sorted(c['state_id'] for c in b['world']['countries']),
            'baseline_digest': digest(b), 'network_digest': digest(n),
            'control': 'surplus_neighbor_v1', 'model': 'gemini-3.5-flash-lite',
            'temperature': 0.3, 'thinking_level': 'minimal', 'maximum_amount': 2, 'max_initiatives': 1,
            'system_instruction': SYSTEM_INSTRUCTION + PILOT_INSTRUCTION, 'schemas': [INITIATIVE_RESPONSE, consent_schema()],
            'max_generation_calls': 240, 'max_count_calls': 240, 'max_output_tokens': 1536,
            'max_counted_input_tokens': 60000, 'input_token_margin': 2048,
            'estimated_budget_usd': '3.00', 'budget_scope': 'additional_expanded_run',
            'consent_schema_policy': 'every_listed_choice_required_boolean', 'pricing_checked': '2026-09-19',
            'input_usd_per_million': '0.30', 'output_usd_per_million': '2.50',
            'retry': 0, 'artifact_class': 'validation_run', 'research_eligible': False,
            'publication_status': 'withheld',
            'source_hashes': {p.name: digest(p.read_text()) for p in sorted((Path(root)/'homeostasis_v3').glob('*.py'))}}


def run_arm(root, output, *, seed, arm, exchange, turns=None):
    ensure(seed in SEEDS and arm in ('deterministic', 'gemini', 'mock'), 'INVALID_PILOT_ARM')
    b, n = inputs(root)
    path = Path(output); path.mkdir(parents=True, exist_ok=False)
    runner = TurnRunner(b, n, pool_location='MIL', context_id=f'paired-pilot-{seed}')
    opening = reference = runner.genesis()
    store = CheckpointStore(path/'checkpoints'); store.save(opening, expected_digest=None)
    prior = []; sources = {opening['checkpoint_digest']: opening}
    report = {'arm': arm, 'seed': seed, 'completed_turns': 0, 'status': 'running',
              'artifact_class': 'validation_run', 'research_eligible': False,
              'protocol_digest': digest(protocol(root)), 'initial_world_digest': digest(opening['world_state']),
              'rows': [], 'automatic_retry': False}
    _write(path/'report.json', report)
    try:
        for turn in range(1, (TURNS if turns is None else turns) + 1):
            exchanges = []
            def record(raw):
                # Save the exact JSON presented to each country and its unmodified public answer.
                item = {'request': raw, 'answer': None}; exchanges.append(item)
                _write(path/f'exchanges-{turn}.json', exchanges)
                item['answer'] = exchange(raw)
                _write(path/f'exchanges-{turn}.json', exchanges)
                return item['answer']
            round = AutonomousRound(report_states(b), exchange=record, budget=ExchangeBudget(16),
                                    maximum_amount=2, max_initiatives=1, source=arm+' paired pilot')
            candidate = runner.run(opening, catalogue=round.catalogue, countries=round.countries())
            ensure(runner.replay(opening, candidate['input']) == candidate, 'PILOT_REPLAY_MISMATCH')
            measurement = observe(candidate, worldline_id=f'pilot-{arm}-{seed}',
                provisional_reference='paired-agent-pilot', previous=prior, reference=reference,
                artifact_class='validation_run')
            sources[candidate['checkpoint_digest']] = candidate
            validate_observation(measurement, sources)
            store.save(candidate, expected_digest=opening['checkpoint_digest'])
            _write(path/f'observation-{turn}.json', measurement)
            _write(path/f'round-{turn}.json', round.record())
            row = {'turn': turn, 'checkpoint_digest': candidate['checkpoint_digest'],
                   'transactions': measurement['transaction_metrics']['summary']['value'],
                   'shortage': measurement['world_metrics']['homeostasis_components']['essential_fulfillment']}
            report['rows'].append(row)
            report['completed_turns'] = turn
            prior.append(candidate); opening = candidate
            _write(path/'report.json', report)
        report['status'] = 'completed'
    except Exception as error:
        report['failure_code'] = getattr(error, 'code', type(error).__name__)
        report['status'] = 'technical_failure'
        _write(path/'report.json', report)
        raise RuntimeError('Pilot stopped; inspect saved evidence. No automatic retry.') from None
    _write(path/'report.json', report)
    return report


def report_states(baseline):
    return sorted(c['state_id'] for c in baseline['world']['countries'])


def compare(control, treatment):
    ensure(control['arm'] == 'deterministic' and treatment['arm'] == 'gemini', 'REAL_GEMINI_REQUIRED')
    ensure(control['seed'] == treatment['seed'] and
           control['initial_world_digest'] == treatment['initial_world_digest'] and
           control['protocol_digest'] == treatment['protocol_digest'], 'UNPAIRED_INPUTS')
    ensure(control['status'] == treatment['status'] == 'completed', 'INCOMPLETE_PAIR')
    rows = []
    for a, b in zip(control['rows'], treatment['rows']):
        rows.append({'turn': a['turn'], 'control': deepcopy(a), 'gemini': deepcopy(b)})
    return {'seed': control['seed'], 'rows': rows, 'research_eligible': False,
            'interpretation': 'Descriptive pilot only; deterministic repeats are not independent samples. No causal or statistical conclusion.'}
