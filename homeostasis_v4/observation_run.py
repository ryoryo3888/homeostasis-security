"""Bounded V4 exploratory observation with write-once evidence and no retries.

An injected HTTP transport runs the same SDK path without credentials/network
in tests. Live execution requires an exact prepared protocol digest.
"""
from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import httpx

from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.agent_adapter import ExchangeBudget
from homeostasis_v3.choices import ensure, TechnicalFailure
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v3.network import load_network
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.turn import TurnRunner
from model_response_json import load_response_object
from provider_response import complete_response_text
from v2_autonomous import Journal
from .dialogue import DialogueRunner, SYSTEM_INSTRUCTION

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gemini-3.6-flash'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/' + MODEL


def sources():
    paths = list(ROOT.glob('*.py'))
    for package in ('homeostasis_core', 'homeostasis_v3', 'homeostasis_v4'):
        paths.extend((ROOT / package).glob('*.py'))
    paths.extend(ROOT / 'scenarios/v3' / name for name in ('synthetic_baseline.json', 'synthetic_network.json'))
    paths.append(ROOT / 'tools/run_v4_observation.py')
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def profile():
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    return {'kind': 'v4_exploratory_observation', 'model': MODEL, 'turns': 5,
            'participants': 8, 'max_calls': 40, 'max_input_tokens': 32000,
            'settlement_search_budget': 1000000,
            'max_output_tokens_including_thoughts': 8192,
            'max_input_bytes': 1000000, 'input_usd_per_million': '0.75',
            'output_usd_per_million': '3.75', 'usd_reservation_limit': '2.1888',
            'price_source': 'https://ai.google.dev/gemini-api/docs/pricing#gemini-3.6-flash',
            'price_checked_on': '2026-09-20', 'price_valid_through': '2026-12-31',
            'yen_planning_allowance': '481.536',
            'yen_basis': '200 JPY/USD plus 10 percent; planning margin, not a billing or exchange-rate quote',
            'automatic_retries': False, 'model_defaults_preserved': True,
            'observer_feedback': False, 'external_shocks': [],
            'initial_conditions': 'Existing synthetic finite-resource baseline; no new scenario event',
            'formal_research_eligibility': False, 'publication': 'private_saved_observation',
            'sdk_version': importlib.metadata.version('google-genai'),
            'python_version': platform.python_version(), 'source_hashes': sources()}


def price(settings, input_tokens, output_tokens):
    return (Decimal(input_tokens) * Decimal(settings['input_usd_per_million']) +
            Decimal(output_tokens) * Decimal(settings['output_usd_per_million'])) / 1000000


def request_body(raw, settings):
    return {'contents': [{'parts': [{'text': raw}], 'role': 'user'}],
            'systemInstruction': {'parts': [{'text': SYSTEM_INSTRUCTION}], 'role': 'user'},
            'generationConfig': {'responseMimeType': 'application/json',
                'maxOutputTokens': settings['max_output_tokens_including_thoughts']}}


class BudgetTransport(httpx.BaseTransport):
    """Pre-count all requests in a round, reserve before every paid wire call."""
    def __init__(self, inner, journal, settings, credential):
        self.inner = inner; self.journal = journal
        self.settings_json = canonical(settings); self.credential = credential
        self.calls = 0; self.reserved = Decimal(0); self.usages = []
        self.pending = []; self.blocked = None; self.round = 0; self.count_calls = 0

    def _check(self):
        settings = json.loads(self.settings_json)
        ensure(sources() == settings['source_hashes'], 'OBSERVATION_SOURCE_CHANGED')
        ensure(self.blocked is None, 'PREVIOUS_PAID_CALL_UNRESOLVED')
        return settings

    def prepare_round(self, raws):
        settings = self._check()
        ensure(not self.pending and len(raws) == settings['participants'], 'INVALID_ROUND_REQUEST_SET')
        upper = price(settings, settings['max_input_tokens'], settings['max_output_tokens_including_thoughts'])
        ensure(self.calls + len(raws) <= settings['max_calls'] and
               self.reserved + upper * len(raws) <= Decimal(settings['usd_reservation_limit']), 'ROUND_BUDGET_EXHAUSTED')
        bodies = [request_body(raw, settings) for raw in raws]
        ensure(all(len(canonical(body).encode()) <= settings['max_input_bytes'] for body in bodies),
               'INPUT_LIMIT_NO_HISTORY_TRUNCATED')
        self.round += 1; prepared = []
        # No generateContent request is dispatched unless all eight exact inputs fit.
        for index, body in enumerate(bodies):
            sequence = self.calls + index
            count_request = {'generateContentRequest': {'model': 'models/' + MODEL, **body}}
            self.journal.write(f'count-{sequence:03d}.request.json', count_request)
            request = httpx.Request('POST', ENDPOINT + ':countTokens',
                headers={'x-goog-api-key': self.credential, 'content-type': 'application/json'},
                json=count_request, extensions={'timeout': {'connect': 30, 'read': 120, 'write': 30, 'pool': 30}})
            self.blocked = 'INPUT_COUNT_UNRESOLVED'
            self.count_calls += 1
            response = self.inner.handle_request(request)
            try:
                response.read()
                self.journal.write(f'count-{sequence:03d}.wire.json', {
                    'status': response.status_code, 'body_base64': base64.b64encode(response.content).decode()})
                ensure(response.status_code == 200, 'COUNT_FAILED_NO_GENERATION')
                data = load_response_object(response.text)
                tokens = data.get('totalTokens')
                ensure(type(tokens) is int and 0 <= tokens <= settings['max_input_tokens'], 'INPUT_TOKEN_LIMIT_NO_GENERATION')
            finally:
                response.close()
            self.blocked = None
            prepared.append({'body': body, 'input_tokens': tokens, 'count_digest': digest(data)})
        self.pending = prepared

    def handle_request(self, request):
        settings = self._check()
        ensure(request.method == 'POST' and str(request.url) == ENDPOINT + ':generateContent', 'UNEXPECTED_PAID_ENDPOINT')
        ensure(self.pending and self.calls < settings['max_calls'], 'UNPREPARED_OR_EXCESS_PAID_REQUEST')
        body = load_response_object(request.content.decode())
        expected = self.pending[0]
        ensure(body == expected['body'], 'COUNTED_REQUEST_CHANGED')
        upper = price(settings, settings['max_input_tokens'], settings['max_output_tokens_including_thoughts'])
        ensure(self.reserved + upper <= Decimal(settings['usd_reservation_limit']), 'USD_RESERVATION_EXHAUSTED')
        index = self.calls
        reservation = {'sequence': index, **expected, 'reserved_usd': str(upper)}
        self.journal.write(f'paid-{index:03d}.reservation.json', reservation)
        self.calls += 1; self.reserved += upper; self.pending.pop(0)
        self.blocked = 'PAID_RESPONSE_UNRESOLVED'
        response = self.inner.handle_request(request)
        response.read()
        self.journal.write(f'paid-{index:03d}.wire.json', {
            'status': response.status_code, 'reservation_digest': digest(reservation),
            'body_base64': base64.b64encode(response.content).decode()})
        try:
            data = load_response_object(response.text)
            usage = data.get('usageMetadata', {})
            values = [usage.get(key) for key in ('promptTokenCount', 'candidatesTokenCount', 'thoughtsTokenCount')]
            known = all(type(v) is int and v >= 0 for v in values)
            actual = price(settings, values[0], values[1] + values[2]) if known else None
            valid = (known and values[0] <= settings['max_input_tokens'] and
                     values[1] + values[2] <= settings['max_output_tokens_including_thoughts'] and actual <= upper)
            receipt = {'sequence': index, 'usage': usage,
                       'estimated_usd': str(actual) if actual is not None else None,
                       'within_limits': valid, 'billing_verified': False}
            self.usages.append(receipt)
            self.journal.write(f'paid-{index:03d}.usage.json', receipt)
            if response.status_code == 200 and valid:
                self.blocked = None
        except (ValueError, TypeError, KeyError):
            pass  # Keep raw evidence; do not spend another call to repair a response.
        return response

    def close(self):
        self.inner.close()


class Exchange:
    def __init__(self, client, transport, journal, settings):
        self.client = client; self.transport = transport; self.journal = journal
        self.settings = settings; self.sequence = 0

    def prepare_round(self, raws):
        self.transport.prepare_round(raws)

    def __call__(self, raw):
        from google.genai import types
        ensure(sources() == self.settings['source_hashes'], 'OBSERVATION_SOURCE_CHANGED')
        sequence = self.sequence
        self.journal.write(f'agent-{sequence:03d}.request.json', load_response_object(raw))
        self.sequence += 1  # A failed attempt is never automatically issued again.
        response = self.client.models.generate_content(model=self.settings['model'], contents=raw,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type='application/json',
                max_output_tokens=self.settings['max_output_tokens_including_thoughts'],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
        self.journal.write(f'agent-{sequence:03d}.sdk.json', {
            'request_digest': digest(load_response_object(raw)),
            'response': response.model_dump(mode='json', exclude_none=False, exclude={'sdk_http_response'})})
        ensure(self.transport.blocked is None, 'USAGE_UNVERIFIED_NO_FURTHER_CALLS')
        return complete_response_text(response)


def execute(directory, credential, *, protocol_digest, inner=None):
    """Never overwrite or resume a run; all paid and count receipts survive a stop."""
    from google import genai
    from google.genai import types
    ensure(type(credential) is str and bool(credential) and not any(c.isspace() for c in credential), 'CREDENTIAL_REQUIRED')
    settings = profile()
    ensure(protocol_digest == digest(settings), 'PREPARED_PROTOCOL_CHANGED')
    baseline = load_baseline(ROOT / 'scenarios/v3/synthetic_baseline.json')
    network = load_network(ROOT / 'scenarios/v3/synthetic_network.json', baseline)
    world = TurnRunner(baseline, network, pool_location='MIL', context_id='v4-free-dialogue-observation',
                       search_budget=settings['settlement_search_budget'])
    live_transport = inner is None
    provider_mode = 'live_gemini' if live_transport else 'injected_transport_not_certified_live'
    runner = DialogueRunner(world, source='Gemini V4 exploratory observation' if live_transport
                            else 'Synthetic SDK transport fixture; not live Agent evidence')
    ensure(len(runner.states) == settings['participants'], 'PARTICIPANT_COUNT_CHANGED')
    checkpoint = runner.genesis(); directory = Path(directory)
    with exclusive_execution(directory):
        ensure(not directory.is_symlink(), 'OUTPUT_SYMLINK_FORBIDDEN')
        directory.mkdir(mode=0o700)  # Never overwrite or retry this saved run.
        journal = Journal(directory)
        journal.write('protocol.json', {'protocol': settings, 'digest': protocol_digest,
                                       'provider_mode': provider_mode,
                                       'dialogue_configuration': runner.config})
        journal.write('turn-000.json', checkpoint)
        transport = BudgetTransport(inner or httpx.HTTPTransport(retries=0), journal, settings, credential)
        budget = ExchangeBudget(settings['max_calls'])
        try:
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=120) as http:
                with genai.Client(vertexai=False, api_key=credential, http_options=types.HttpOptions(
                        base_url='https://generativelanguage.googleapis.com', api_version='v1beta',
                        httpx_client=http, timeout=120000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    exchange = Exchange(client, transport, journal, settings)
                    for turn in range(1, settings['turns'] + 1):
                        candidate = runner.run(checkpoint, exchange=exchange, budget=budget)
                        runner.replay(checkpoint, candidate)
                        journal.write(f'turn-{turn:03d}.json', candidate)
                        checkpoint = candidate
                        print(f'V4 TURN {turn}/{settings["turns"]} saved; generation calls {transport.calls}.', flush=True)
            summary = {'kind': settings['kind'] if live_transport else 'v4_transport_validation',
                       'provider_mode': provider_mode, 'status': 'observation_period_reached',
                       'completed_turns': checkpoint['dialogue']['turn'], 'api_calls': transport.calls,
                       'count_token_calls': transport.count_calls, 'api_calls_scope': 'generateContent only',
                       'reserved_usd': str(transport.reserved), 'usage': transport.usages,
                       'final_checkpoint_digest': checkpoint['checkpoint_digest'], 'billing_verified': False,
                       'formal_research_eligibility': False, 'automatic_retry': False}
            journal.write('result.json', summary)
            return summary
        except BaseException as error:
            journal.write('stopped.json', {'status': 'technical_stop', 'exception_type': type(error).__name__,
                'provider_mode': provider_mode,
                'code': getattr(error, 'code', None), 'not_an_agent_decision': True,
                'completed_turns': checkpoint['dialogue']['turn'], 'api_calls': transport.calls,
                'count_token_calls': transport.count_calls, 'api_calls_scope': 'generateContent only',
                'reserved_usd': str(transport.reserved), 'usage': transport.usages,
                'last_valid_checkpoint': checkpoint['checkpoint_digest'], 'automatic_retry': False})
            raise TechnicalFailure('OBSERVATION_STOPPED_WITH_EVIDENCE_NO_RETRY') from None
