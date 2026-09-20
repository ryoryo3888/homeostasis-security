"""Observe turns 6–8 of a completed five-turn world without resetting it."""
import base64
from decimal import Decimal
import json
from pathlib import Path

import httpx
from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.agent_adapter import ExchangeBudget
from homeostasis_v3.choices import ensure
from homeostasis_v3.contracts import canonical, digest
from provider_response import complete_response_text
from v2_autonomous import Journal
from .observation_continue import parent_digest, runner_for
from .observation_run import BudgetTransport, Exchange, price, profile, request_body

FIRST_TURN = 6
LAST_TURN = 8


def extension_profile():
    settings = profile()
    settings.update(kind='v4_three_turn_extension', turns=3, max_calls=24,
        usd_reservation_limit='1.31328', yen_planning_allowance='288.92160')
    return settings


def _verify_exchange(journal, sequence, expected, raw, settings):
    from google.genai import types
    request = journal.read(f'agent-{sequence:03d}.request.json')
    sdk = journal.read(f'agent-{sequence:03d}.sdk.json')
    reservation = journal.read(f'paid-{sequence:03d}.reservation.json')
    wire = journal.read(f'paid-{sequence:03d}.wire.json')
    usage = journal.read(f'paid-{sequence:03d}.usage.json')
    ensure(request == expected and sdk['request_digest'] == digest(request), 'PARENT_REQUEST_MISMATCH')
    ensure(wire['status'] == 200 and wire['reservation_digest'] == digest(reservation), 'PARENT_WIRE_MISMATCH')
    ensure(reservation['body'] == request_body(canonical(request), settings), 'PARENT_BODY_MISMATCH')
    payload = json.loads(base64.b64decode(wire['body_base64']))
    candidate = payload['candidates'][0]
    response = types.GenerateContentResponse.model_validate(sdk['response'])
    ensure(complete_response_text(response) == raw and candidate['finishReason'] == 'STOP'
           and raw == ''.join(p.get('text', '') for p in candidate['content']['parts'] if not p.get('thought')),
           'PARENT_RESPONSE_MISMATCH')
    ensure(usage['within_limits'] is True and usage['usage'] == payload['usageMetadata'], 'PARENT_USAGE_MISMATCH')
    u = usage['usage']
    ensure(Decimal(usage['estimated_usd']) == price(settings, u['promptTokenCount'],
           u['candidatesTokenCount'] + u['thoughtsTokenCount']), 'PARENT_PRICE_MISMATCH')
    return usage


def prepare_extension(directory, expected_digest):
    """Validate live provenance and rebuild chronological state before any API."""
    directory = Path(directory)
    ensure(parent_digest(directory) == expected_digest, 'PARENT_CHANGED')
    journal = Journal(directory)
    for p in directory.glob('*.json'):
        journal.read(p.name)
    ensure(not (directory / 'stopped.json').exists(), 'PARENT_NOT_COMPLETE')
    prior = journal.read('protocol.json'); result = journal.read('result.json')
    ensure(result['status'] == 'observation_period_reached' and result['completed_turns'] == 5
           and result['api_calls'] == 40 and result['automatic_retry'] is False, 'PARENT_NOT_FIVE_TURNS')
    ensure(prior['digest'] == digest(prior['protocol']) and
           prior['provider_mode'] == result['provider_mode'], 'PARENT_PROTOCOL_MISMATCH')
    original = profile(); old = prior['protocol']
    ensure({k:v for k,v in original.items() if k != 'source_hashes'} ==
           {k:v for k,v in old.items() if k != 'source_hashes'}, 'OBSERVATION_CONDITIONS_CHANGED')
    changed = {k for k in original['source_hashes'].keys() | old['source_hashes'].keys()
               if original['source_hashes'].get(k) != old['source_hashes'].get(k)}
    ensure(changed <= {'homeostasis_v4/observation_extend.py'}, 'UNRELATED_SOURCE_CHANGED')
    settings = extension_profile()
    runner = runner_for(settings, prior['dialogue_configuration']['source'])
    ensure(runner.config == prior['dialogue_configuration'], 'AGENT_OR_WORLD_CONFIGURATION_CHANGED')
    # A prior formatting-stop continuation may reference its original 14 calls.
    # Their immutable parent is verified separately, never regenerated.
    ancestor = None; ancestor_protocol = None
    pins = {str(directory.resolve()): expected_digest}
    if 'parent_directory' in prior:
        path = Path(prior['parent_directory'])
        ensure(path.resolve() != directory.resolve() and parent_digest(path) == prior['parent_digest'], 'ANCESTOR_CHANGED')
        ancestor = Journal(path); pins[str(path.resolve())] = prior['parent_digest']
        for p in path.glob('*.json'):
            ancestor.read(p.name)
        ancestor_protocol = ancestor.read('protocol.json')
        ensure(ancestor_protocol['digest'] == digest(ancestor_protocol['protocol']) and
               ancestor_protocol['provider_mode'] == prior['provider_mode'], 'ANCESTOR_PROTOCOL_MISMATCH')
    opening = runner.genesis()
    ensure(opening == journal.read('turn-000.json'), 'PARENT_GENESIS_CHANGED')
    ensure(len(result['usage']) == 40, 'PARENT_USAGE_INCOMPLETE')
    reused = 0
    for turn in range(1, 6):
        completed = journal.read(f'turn-{turn:03d}.json')
        # Rebuild from genesis: canonical JSON sorts map keys, while the Agent's
        # historical offer list retains the order in which offers were made.
        opening = runner.replay(opening, completed)
        for offset, actor in enumerate(runner.states):
            sequence = (turn - 1) * 8 + offset
            request = completed['input']['requests'][actor]
            raw = completed['input']['raw_replies'][actor]
            if (directory / f'reused-{sequence:03d}.json').exists():
                ensure(ancestor is not None, 'ANCESTOR_REQUIRED')
                saved = journal.read(f'reused-{sequence:03d}.json')
                old_request = ancestor.read(f'agent-{sequence:03d}.request.json')
                ensure(saved['new_request'] == request and saved['raw_reply'] == raw and
                       saved['parent_request_digest'] == digest(old_request) and
                       old_request['view'] == request['view'], 'REUSED_INPUT_CHANGED')
                usage = _verify_exchange(ancestor, sequence, old_request, raw, ancestor_protocol['protocol'])
                reused += 1
            else:
                usage = _verify_exchange(journal, sequence, request, raw, old)
            ensure(usage == result['usage'][sequence], 'PARENT_USAGE_MISMATCH')
    ensure(opening['checkpoint_digest'] == result['final_checkpoint_digest'], 'PARENT_CHECKPOINT_CHANGED')
    ensure(len(list(directory.glob('paid-*.reservation.json'))) + reused == 40, 'UNRESOLVED_PARENT_ATTEMPT')
    for path, pin in pins.items():
        ensure(parent_digest(path) == pin, 'PARENT_CHANGED')
    plan = {'protocol': settings, 'protocol_digest': digest(settings), 'parent_pins': pins,
        'start_turn': FIRST_TURN, 'end_turn': LAST_TURN, 'prior_calls': 40,
        'prior_estimated_usd': str(sum(Decimal(u['estimated_usd']) for u in result['usage'])),
        'opening_digest': opening['checkpoint_digest'], 'provider_mode': prior['provider_mode'],
        'output_directory': str(directory.with_name(directory.name + '-through-turn-8')),
        'no_parent_regeneration': True, 'formal_research_eligibility': False}
    return plan, runner, opening


class ExtensionExchange(Exchange):
    def __init__(self, *args, pins, **kwargs):
        super().__init__(*args, **kwargs)
        self.pins = pins

    def prepare_round(self, raws):
        for path, pin in self.pins.items():
            ensure(parent_digest(path) == pin, 'PARENT_CHANGED')
        super().prepare_round(raws)


def extend_observation(directory, credential, *, expected_parent_digest, protocol_digest, inner=None):
    from google import genai
    from google.genai import types
    ensure(type(credential) is str and bool(credential) and not any(c.isspace() for c in credential), 'CREDENTIAL_REQUIRED')
    plan, runner, opening = prepare_extension(directory, expected_parent_digest)
    ensure(plan['protocol_digest'] == protocol_digest, 'PREPARED_PROTOCOL_CHANGED')
    live = inner is None
    ensure((plan['provider_mode'] == 'live_gemini') == live, 'PROVIDER_MODE_CHANGED')
    output = Path(plan['output_directory']); settings = plan['protocol']
    with exclusive_execution(output):
        ensure(not output.exists() and not output.is_symlink(), 'EXTENSION_ALREADY_ATTEMPTED')
        output.mkdir(mode=0o700); journal = Journal(output)
        journal.write('protocol.json', {**plan, 'digest': plan['protocol_digest'], 'dialogue_configuration': runner.config})
        journal.write('turn-005.json', opening)
        transport = BudgetTransport(inner or httpx.HTTPTransport(retries=0), journal, settings, credential)
        budget = ExchangeBudget(settings['max_calls']); checkpoint = opening
        try:
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=120) as http:
                with genai.Client(vertexai=False, api_key=credential, http_options=types.HttpOptions(
                        base_url='https://generativelanguage.googleapis.com', api_version='v1beta',
                        httpx_client=http, timeout=120000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    exchange = ExtensionExchange(client, transport, journal, settings, pins=plan['parent_pins'])
                    for turn in range(FIRST_TURN, LAST_TURN + 1):
                        candidate = runner.run(checkpoint, exchange=exchange, budget=budget)
                        runner.replay(checkpoint, candidate)
                        journal.write(f'turn-{turn:03d}.json', candidate); checkpoint = candidate
                        print(f'V4 TURN {turn}/8 saved; additional generation calls {transport.calls}.', flush=True)
            status = 'observation_period_reached'
        except BaseException as error:
            status = 'technical_stop'
            failure = {'exception_type': type(error).__name__, 'code': getattr(error, 'code', None),
                       'not_an_agent_decision': True}
        result = {'status': status, 'provider_mode': plan['provider_mode'],
            'completed_turns': checkpoint['dialogue']['turn'], 'additional_completed_turns': checkpoint['dialogue']['turn'] - 5,
            'additional_api_calls': transport.calls, 'cumulative_api_calls': 40 + transport.calls,
            'api_calls_scope': 'additional_api_calls counts only new generateContent; prior 40 never regenerated',
            'count_token_calls': transport.count_calls, 'reserved_usd': str(transport.reserved), 'usage': transport.usages,
            'prior_estimated_usd': plan['prior_estimated_usd'], 'billing_verified': False,
            'final_checkpoint_digest': checkpoint['checkpoint_digest'], 'parent_pins': plan['parent_pins'],
            'automatic_retry': False, 'formal_research_eligibility': False}
        if status == 'technical_stop': result.update(failure)
        journal.write('result.json' if status == 'observation_period_reached' else 'stopped.json', result)
        return result
