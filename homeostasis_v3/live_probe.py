"""One explicitly approved connection probe; never a formal worldline runner."""
from copy import deepcopy
from decimal import Decimal
import importlib.metadata
import json
from pathlib import Path

from .agent_adapter import _object
from .autonomous import INITIATIVE_RESPONSE, opportunities
from .choices import ensure, check, materialize_choice, TechnicalFailure
from .contracts import canonical, digest
from .gemini_preflight import AttemptJournal, SYSTEM_INSTRUCTION
from .physical import load_baseline
from .network import load_network
from .turn import TurnRunner, TurnFailure

MODEL = 'gemini-2.5-flash-lite'
ENDPOINT = 'https://generativelanguage.googleapis.com'


def prepare(root):
    """Freeze the same pre-choice observation as the core, without adopting a TURN."""
    root = Path(root)
    baseline = load_baseline(root/'scenarios/v3/synthetic_baseline.json')
    network = load_network(root/'scenarios/v3/synthetic_network.json', baseline)
    runner = TurnRunner(baseline, network, pool_location='MIL', context_id='single-connection-probe')
    captured = []
    def capture(view):
        captured.append(view)
        raise TechnicalFailure('PROBE_OBSERVATION_CAPTURED')
    try:
        runner.run(runner.genesis(), catalogue=capture)
    except TurnFailure as error:
        ensure(error.code == 'PROBE_OBSERVATION_CAPTURED', 'OBSERVATION_CAPTURE_FAILED')
    ensure(len(captured) == 1, 'OBSERVATION_CAPTURE_FAILED')
    view = captured[0]
    request = dict(version='v3', phase='initiative', state_id='MIL',
                   observation_digest=view.hash, observation=view.read(),
                   payload={'opportunities': opportunities(view, 100), 'max_initiatives': 4,
                            'maximum_amount': 100, 'proposal': None,
                            'extension_policy': 'Record unimplemented law requests; never execute them.'})
    request['request_digest'] = digest(request)
    protocol = {'kind': 'v3_connection_probe', 'artifact_class': 'validation_run',
                'research_eligible': False, 'publication_status': 'withheld',
                'model': MODEL, 'endpoint': ENDPOINT, 'max_calls': 1,
                'max_input_bytes': 500000, 'max_output_tokens': 4096, 'thinking_budget': 0,
                'retry_attempts': 1, 'timeout_seconds': 30, 'request': request,
                'system_instruction': SYSTEM_INSTRUCTION, 'response_schema': INITIATIVE_RESPONSE,
                'sdk_version': importlib.metadata.version('google-genai'),
                'source_hashes': {p.name: digest(p.read_text()) for p in sorted((root/'homeostasis_v3').glob('*.py'))},
                'pricing': {'checked_date': '2026-09-18',
                            'source': 'https://ai.google.dev/gemini-api/docs/pricing',
                            'input_usd_per_million': '0.10', 'output_usd_per_million': '0.40',
                            'model_input_token_limit': 1048576,
                            'conservative_max_usd': '0.106496', 'approval_ceiling_usd': '0.11',
                            'basis': 'Full model input context plus output cap at published standard rates; excludes tax and FX. Not an account billing cap.'}}
    ensure(len(canonical(request).encode()) <= protocol['max_input_bytes'], 'INPUT_LIMIT_EXCEEDED')
    return {**protocol, 'protocol_digest': digest(protocol)}


def validate_answer(answer, request):
    check(INITIATIVE_RESPONSE, answer)
    ensure(answer['request_digest'] == request['request_digest'] and answer['state_id'] == request['state_id'],
           'PROVIDER_BINDING_MISMATCH')
    intents = answer['initiatives']
    ensure(len(intents) <= 4, 'INITIATIVE_LIMIT_EXCEEDED')
    ensure(len({i['opportunity_id'] for i in intents}) == len(intents), 'DUPLICATE_INITIATIVE')
    templates = {t['choice_id']: t for t in request['payload']['opportunities']}
    history = request['observation']['world_state']['seen_choice_ids']
    for item in intents:
        template = deepcopy(templates.get(item['opportunity_id']))
        ensure(template is not None, 'UNKNOWN_OPPORTUNITY')
        ensure(template['actor_state_id'] == request['state_id'], 'ACTOR_AUTHORITY_REQUIRED')
        template.update(conditions=item['conditions'], minimum_amount=item['minimum_amount'], allow_partial=item['allow_partial'])
        for condition in template['conditions']:
            ensure(condition['choice_id'] in (history if condition['kind'] == 'arrived_amount' else templates),
                   'UNKNOWN_CONDITION_REFERENCE')
        materialize_choice({'choice_id': template['choice_id'], 'requested_amount': item['requested_amount'],
                            'provenance': {'source': 'live connection probe', 'public_reason': item['public_reason']}}, [template])


def execute(root, protocol, approval_digest, credential):
    """Credential is supplied only at explicit execution; no files or dotenv searched.

    The single journal path is independent of output directories. New output paths
    do not renew the one-call allowance. A timeout/crash consumes that allowance.
    """
    import httpx
    from google import genai
    from google.genai import types
    ensure(protocol == prepare(root), 'PROTOCOL_CHANGED_REVIEW_REQUIRED')
    ensure(approval_digest == protocol['protocol_digest'], 'EXPLICIT_APPROVAL_DIGEST_REQUIRED')
    ensure(type(credential) is str and bool(credential.strip()), 'CREDENTIAL_REQUIRED')
    request = protocol['request']
    journal = AttemptJournal(Path(root)/'.artifacts/v3-live-single-probe/attempts.sqlite',
                             configuration={'max_calls': 1, 'protocol_digest': approval_digest})
    class GuardedTransport(httpx.BaseTransport):
        def __init__(self):
            self.inner = httpx.HTTPTransport(retries=0)
            self.sent = False
        def handle_request(self, wire):
            ensure(not self.sent, 'SECOND_HTTP_REQUEST_FORBIDDEN')
            ensure(str(wire.url) == ENDPOINT+'/v1beta/models/'+MODEL+':generateContent'
                   and wire.method == 'POST', 'UNEXPECTED_LIVE_ENDPOINT')
            self.sent = True
            return self.inner.handle_request(wire)
        def close(self):
            self.inner.close()
    config = types.GenerateContentConfig(response_mime_type='application/json',
        response_json_schema=protocol['response_schema'], system_instruction=protocol['system_instruction'],
        temperature=0, candidate_count=1, max_output_tokens=4096,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    usage = {'input_tokens': None, 'output_tokens': None, 'thought_tokens': None, 'total_tokens': None}
    # Reserve before constructing the network client. No automatic retry, even if setup fails.
    journal.reserve(request)
    try:
        with httpx.Client(transport=GuardedTransport(), trust_env=False, follow_redirects=False, timeout=30) as http:
            with genai.Client(vertexai=False, api_key=credential, http_options=types.HttpOptions(
                base_url=ENDPOINT, api_version='v1beta', httpx_client=http, timeout=30000,
                retry_options=types.HttpRetryOptions(attempts=1))) as client:
                response = client.models.generate_content(model=MODEL, contents=canonical(request), config=config)
                for key, name in [('input_tokens', 'prompt_token_count'), ('output_tokens', 'candidates_token_count'),
                                  ('thought_tokens', 'thoughts_token_count'), ('total_tokens', 'total_token_count')]:
                    value = getattr(response.usage_metadata, name, None)
                    usage[key] = value if type(value) is int and value >= 0 else None
                ensure(response.candidates and len(response.candidates) == 1 and
                       response.candidates[0].finish_reason == 'STOP', 'INCOMPLETE_PROVIDER_RESPONSE')
                text = response.text
                ensure(type(text) is str and len(text.encode()) <= 65536, 'INVALID_RESPONSE_SIZE')
                answer = json.loads(text, object_pairs_hook=_object)
                validate_answer(answer, request)
    except Exception:
        journal.finish(request['request_digest'], 'failed', usage)
        raise TechnicalFailure('LIVE_PROBE_FAILED_NO_RETRY') from None
    journal.finish(request['request_digest'], 'response_validated', usage)
    cost = None
    if all(usage[k] is not None for k in ('input_tokens', 'output_tokens', 'thought_tokens')):
        cost = str((Decimal(usage['input_tokens'])*Decimal('0.10') +
                    Decimal(usage['output_tokens']+usage['thought_tokens'])*Decimal('0.40')) / 1000000)
    return {'kind': 'v3_connection_probe_result', 'artifact_class': 'validation_run',
            'research_eligible': False, 'publication_status': 'withheld', 'api_calls': 1,
            'turns_adopted': 0, 'protocol_digest': approval_digest, 'answer': answer,
            'usage': usage, 'estimated_usd': cost, 'billing_verified': False,
            'status': 'response_validated', 'automatic_retry': False}
