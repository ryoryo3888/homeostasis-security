"""Finish an input-identical observation after an omitted activity description.

Only complete, authenticated-by-local-hash saved exchanges can be reused. This
does not retry a model call, fill in a response, or rewrite the original run.
"""
from copy import deepcopy
from decimal import Decimal
import base64
import hashlib
import json
from pathlib import Path

import httpx
from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.agent_adapter import ExchangeBudget
from homeostasis_v3.choices import check, ensure, TechnicalFailure
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v3.network import load_network
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.turn import TurnRunner
from provider_response import complete_response_text
from v2_autonomous import Journal
from .dialogue import DialogueRunner, parse_reply
from .observation_run import ROOT, BudgetTransport, Exchange, price, profile, request_body


def parent_digest(directory):
    directory = Path(directory)
    ensure(not directory.is_symlink(), 'PARENT_SYMLINK_FORBIDDEN')
    files = sorted(directory.glob('*.json'))
    ensure(bool(files) and all(not p.is_symlink() for p in files), 'PARENT_FILES_REQUIRED')
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def runner_for(settings, source):
    baseline = load_baseline(ROOT / 'scenarios/v3/synthetic_baseline.json')
    network = load_network(ROOT / 'scenarios/v3/synthetic_network.json', baseline)
    return DialogueRunner(TurnRunner(baseline, network, pool_location='MIL',
        context_id='v4-free-dialogue-observation', search_budget=settings['settlement_search_budget']), source=source)


def inspect_parent(directory, expected_digest):
    from google.genai import types
    directory = Path(directory)
    ensure(parent_digest(directory) == expected_digest, 'PARENT_CHANGED')
    journal = Journal(directory)
    # Verify every saved wrapper, including pre-counts for unqueried countries.
    for path in directory.glob('*.json'):
        journal.read(path.name)
    ensure(not (directory / 'result.json').exists(), 'PARENT_ALREADY_COMPLETE')
    prior = journal.read('protocol.json'); stopped = journal.read('stopped.json')
    ensure(stopped['status'] == 'technical_stop' and stopped['code'] == 'SCHEMA_ERROR'
           and stopped['automatic_retry'] is False, 'NOT_DESCRIPTION_STOP')
    settings = profile(); old = prior['protocol']
    ensure(prior['digest'] == digest(old), 'PARENT_PROTOCOL_MISMATCH')
    ensure({k:v for k,v in old.items() if k != 'source_hashes'} ==
           {k:v for k,v in settings.items() if k != 'source_hashes'}, 'OBSERVATION_CONDITIONS_CHANGED')
    allowed = {'homeostasis_v4/dialogue.py', 'homeostasis_v4/observation_run.py',
               'homeostasis_v4/observation_continue.py'}
    changed = {k for k in old['source_hashes'].keys() | settings['source_hashes'].keys()
               if old['source_hashes'].get(k) != settings['source_hashes'].get(k)}
    ensure(changed <= allowed, 'UNRELATED_SOURCE_CHANGED')
    runner = runner_for(settings, prior['dialogue_configuration']['source'])
    old_config = deepcopy(prior['dialogue_configuration']); old_schema = old_config.pop('reply_schema')
    new_config = deepcopy(runner.config); new_config.pop('reply_schema')
    ensure(old_config == new_config, 'AGENT_OR_WORLD_CONFIGURATION_CHANGED')
    calls = stopped['api_calls']; width = settings['participants']
    completed = stopped['completed_turns']
    ensure(type(calls) is int and completed * width < calls <= (completed + 1) * width
           and calls < settings['max_calls'], 'INVALID_PARTIAL_ROUND')
    ensure(len(stopped['usage']) == calls, 'UNRESOLVED_PAID_USAGE')
    ensure(len(list(directory.glob('paid-*.reservation.json'))) == calls and
           len(list(directory.glob('paid-*.wire.json'))) == calls and
           len(list(directory.glob('agent-*.sdk.json'))) == calls, 'UNRESOLVED_PAID_ATTEMPT')
    upper = price(settings, settings['max_input_tokens'], settings['max_output_tokens_including_thoughts'])
    ensure(Decimal(stopped['reserved_usd']) == calls * upper, 'RESERVATION_MISMATCH')
    cache = {}; omissions = []
    for index in range(calls):
        request = journal.read(f'agent-{index:03d}.request.json')
        sdk = journal.read(f'agent-{index:03d}.sdk.json')
        reservation = journal.read(f'paid-{index:03d}.reservation.json')
        wire = journal.read(f'paid-{index:03d}.wire.json')
        usage = journal.read(f'paid-{index:03d}.usage.json')
        ensure(wire['status'] == 200 and wire['reservation_digest'] == digest(reservation)
               and sdk['request_digest'] == digest(request), 'SAVED_RESPONSE_MISMATCH')
        ensure(reservation['body'] == request_body(canonical(request), old), 'SAVED_REQUEST_MISMATCH')
        raw_wire = json.loads(base64.b64decode(wire['body_base64']))
        response = types.GenerateContentResponse.model_validate(sdk['response'])
        raw = complete_response_text(response)
        candidate = raw_wire['candidates'][0]
        ensure(candidate['finishReason'] == 'STOP' and raw == ''.join(
            p.get('text', '') for p in candidate['content']['parts'] if not p.get('thought')), 'INCOMPLETE_SAVED_REPLY')
        ensure(usage == stopped['usage'][index] and usage['within_limits'] is True and
               usage['usage'] == raw_wire['usageMetadata'], 'UNVERIFIED_SAVED_USAGE')
        u = usage['usage']; actual = price(settings, u['promptTokenCount'],
                                          u['candidatesTokenCount'] + u['thoughtsTokenCount'])
        ensure(Decimal(usage['estimated_usd']) == actual and actual <= upper, 'SAVED_PRICE_MISMATCH')
        actor = runner.states[index % width]; turn = index // width + 1
        ensure(request['view']['actor'] == actor and request['view']['turn'] == turn, 'SAVED_SEQUENCE_MISMATCH')
        reply = parse_reply(raw, request['view'])
        try:
            check(old_schema, reply)
        except TechnicalFailure:
            # The only accepted old-schema difference is absent prose on an
            # otherwise structured activity. Validate that exact difference.
            repaired_for_validation = deepcopy(reply)
            missing = [a for a in repaired_for_validation['activities'] if 'body' not in a]
            ensure(bool(missing), 'NOT_DESCRIPTION_STOP')
            for activity in missing:
                activity['body'] = ''
            check(old_schema, repaired_for_validation)
            omissions.append(index)
        cache[turn, actor] = {'request': request, 'raw': raw, 'sequence': index}
    ensure(omissions == [calls - 1], 'NOT_DESCRIPTION_STOP')
    ensure(parent_digest(directory) == expected_digest, 'PARENT_CHANGED')
    return prior, stopped, settings, runner, cache


class SavedThenLive:
    def __init__(self, cache, live, journal, directory, pin):
        self.cache = cache; self.live = live; self.journal = journal
        self.directory = directory; self.pin = pin

    def prepare_round(self, raws):
        ensure(parent_digest(self.directory) == self.pin, 'PARENT_CHANGED')
        pending = []
        for raw in raws:
            value = json.loads(raw); key = value['view']['turn'], value['view']['actor']
            if key in self.cache:
                ensure(value['view'] == self.cache[key]['request']['view'], 'SAVED_AGENT_INPUT_CHANGED')
            else:
                pending.append(raw)
        if pending:
            self.live.transport.prepare_round(pending, expected_count=len(pending))

    def __call__(self, raw):
        request = json.loads(raw); key = request['view']['turn'], request['view']['actor']
        if key not in self.cache:
            return self.live(raw)
        saved = self.cache[key]
        ensure(request['view'] == saved['request']['view'], 'SAVED_AGENT_INPUT_CHANGED')
        self.journal.write(f'reused-{saved["sequence"]:03d}.json', {
            'parent_request_digest': digest(saved['request']), 'new_request': request,
            'raw_reply': saved['raw'], 'prose_added': False,
            'metadata_migration': 'opening/config hashes only; Agent view is identical'})
        return saved['raw']


def continue_observation(directory, credential, *, expected_parent_digest, protocol_digest, inner=None):
    from google import genai
    from google.genai import types
    ensure(type(credential) is str and bool(credential) and not any(c.isspace() for c in credential), 'CREDENTIAL_REQUIRED')
    prior, stopped, settings, runner, cache = inspect_parent(directory, expected_parent_digest)
    ensure(digest(settings) == protocol_digest, 'PREPARED_PROTOCOL_CHANGED')
    live = inner is None
    ensure((prior['provider_mode'] == 'live_gemini') == live, 'PROVIDER_MODE_CHANGED')
    parent = Journal(Path(directory)); output = Path(directory).with_name(Path(directory).name + '-completion')
    # One fixed child path prevents spending again by selecting a new output name.
    with exclusive_execution(output):
        ensure(not output.exists() and not output.is_symlink(), 'CONTINUATION_ALREADY_ATTEMPTED')
        output.mkdir(mode=0o700); journal = Journal(output)
        journal.write('protocol.json', {'protocol': settings, 'digest': protocol_digest,
            'provider_mode': prior['provider_mode'], 'dialogue_configuration': runner.config,
            'parent_directory': str(Path(directory).resolve()), 'parent_digest': expected_parent_digest,
            'description_omission_preserved': True, 'prior_api_calls': stopped['api_calls']})
        checkpoint = runner.genesis(); journal.write('turn-000.json', checkpoint)
        transport = BudgetTransport(inner or httpx.HTTPTransport(retries=0), journal, settings, credential)
        transport.calls = stopped['api_calls']; transport.reserved = Decimal(stopped['reserved_usd'])
        transport.usages = deepcopy(stopped['usage']); transport.count_calls = stopped['count_token_calls']
        budget = ExchangeBudget(settings['max_calls'])
        try:
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=120) as http:
                with genai.Client(vertexai=False, api_key=credential, http_options=types.HttpOptions(
                        base_url='https://generativelanguage.googleapis.com', api_version='v1beta',
                        httpx_client=http, timeout=120000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    exchange = Exchange(client, transport, journal, settings); exchange.sequence = stopped['api_calls']
                    joined = SavedThenLive(cache, exchange, journal, directory, expected_parent_digest)
                    for turn in range(1, settings['turns'] + 1):
                        candidate = runner.run(checkpoint, exchange=joined, budget=budget)
                        runner.replay(checkpoint, candidate)
                        if turn <= stopped['completed_turns']:
                            original = parent.read(f'turn-{turn:03d}.json')
                            ensure(candidate['world'] == original['world'] and candidate['dialogue'] == original['dialogue'],
                                   'COMPLETED_TURN_CHANGED')
                        journal.write(f'turn-{turn:03d}.json', candidate); checkpoint = candidate
                        print(f'V4 TURN {turn}/{settings["turns"]} saved; total generation calls {transport.calls}.', flush=True)
            status = 'observation_period_reached'
        except BaseException as error:
            status = 'technical_stop'
            failure = {'exception_type': type(error).__name__, 'code': getattr(error, 'code', None),
                       'not_an_agent_decision': True}
        result = {'status': status, 'provider_mode': prior['provider_mode'], 'completed_turns': checkpoint['dialogue']['turn'],
            'api_calls': transport.calls, 'prior_api_calls': stopped['api_calls'],
            'new_api_calls': transport.calls - stopped['api_calls'], 'count_token_calls': transport.count_calls,
            'api_calls_scope': 'generateContent cumulative including parent; saved responses never regenerated',
            'reserved_usd': str(transport.reserved), 'usage': transport.usages, 'billing_verified': False,
            'final_checkpoint_digest': checkpoint['checkpoint_digest'], 'formal_research_eligibility': False,
            'automatic_retry': False, 'parent_digest': expected_parent_digest}
        if status == 'technical_stop': result.update(failure)
        journal.write('result.json' if status == 'observation_period_reached' else 'stopped.json', result)
        return result
