"""Eight approved, independent persona generations with immutable evidence.

No simulation, repair, fallback model, automatic retry, or publication path.
Each completed generation requires a recorded content review before the next.
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
import subprocess
import uuid

import httpx
from jsonschema import Draft202012Validator

from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v4.evidence import EvidenceRun, FORMAT, read_record, timestamp, verify
from model_response_json import load_response_object
from v2_autonomous import Journal

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'docs/design/v5'
MODEL = 'gemini-3.6-flash'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/' + MODEL
MAX_PERSONAS = 8
MAX_INPUT = 16000
MAX_OUTPUT = 8192
LIMIT_USD = Decimal('0.40')
INPUT_PRICE = Decimal('0.75')
OUTPUT_PRICE = Decimal('3.75')
AXES = (
    'empathy', 'initial_trust', 'vigilance', 'risk_tolerance',
    'ambiguity_tolerance', 'instrumental_harm_tolerance', 'compromise_readiness',
    'retaliation_tendency', 'norm_commitment', 'outcome_orientation',
    'future_orientation', 'information_openness', 'power_seeking',
    'responsibility_ownership', 'national_interest_weight', 'external_welfare_weight',
)


class GenerationError(ValueError):
    """Only a fixed, non-sensitive code is allowed into reports."""


def ensure(condition, code):
    if not condition:
        raise GenerationError(code)


def price(input_tokens, output_tokens):
    return (Decimal(input_tokens) * INPUT_PRICE + Decimal(output_tokens) * OUTPUT_PRICE) / 1000000


def source_hashes():
    paths = [
        'homeostasis_v5/__init__.py', 'homeostasis_v5/persona_generation.py',
        'homeostasis_core/execution_lock.py', 'homeostasis_v3/contracts.py',
        'homeostasis_v4/evidence.py', 'model_response_json.py', 'v2_autonomous.py',
        'tools/generate_v5_leaders.py', 'docs/design/v5/LEADER_GENERATION_PLAN.md',
        'docs/design/v5/LEADER_GENERATION_PROMPT.txt',
        'docs/design/v5/LEADER_GENERATION_SCHEMA.proposed.json',
    ]
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}


def build_request():
    schema = load_response_object((DESIGN / 'LEADER_GENERATION_SCHEMA.proposed.json').read_text())
    Draft202012Validator.check_schema(schema)
    params = schema['properties']['layer1']['properties']['parameters']
    ensure(list(params['properties']) == list(AXES) and params['required'] == list(AXES),
           'APPROVED_AXES_MISMATCH')
    return {
        'contents': [{'role': 'user', 'parts': [{'text': (DESIGN / 'LEADER_GENERATION_PROMPT.txt').read_text()}]}],
        'generationConfig': {
            'responseMimeType': 'application/json', 'responseJsonSchema': schema,
            'temperature': 1.0, 'candidateCount': 1, 'maxOutputTokens': MAX_OUTPUT,
            'thinkingConfig': {'thinkingLevel': 'LOW', 'includeThoughts': False},
        },
    }


def validate_persona(persona, *, schema=None):
    if schema is None:
        schema = build_request()['generationConfig']['responseJsonSchema']
    ensure(not list(Draft202012Validator(schema).iter_errors(persona)), 'PERSONA_SCHEMA_ERROR')
    # JSON Schema considers 1.0 integral; the approved serialization requires integers.
    ensure(type(persona['layer1']['person_profile']['age_years']) is int, 'AGE_INTEGER_REQUIRED')
    ensure(all(type(value) is int for value in persona['layer1']['parameters'].values()),
           'AXIS_INTEGER_REQUIRED')

    def nonblank(value):
        if isinstance(value, str):
            ensure(bool(value.strip()), 'EMPTY_PERSONA_TEXT')
        elif isinstance(value, dict):
            for child in value.values():
                nonblank(child)
        elif isinstance(value, list):
            for child in value:
                nonblank(child)
    nonblank(persona)
    intro = persona['layer2']['text']
    count = len(intro.replace('\n', '').replace('\r', ''))
    return {'intro_character_count': count,
            'warnings': [] if 200 <= count <= 300 else ['INTRO_OUTSIDE_APPROXIMATE_LENGTH'],
            'content_review_required': True,
            'personality_alignment_scored': False}


def _runtime():
    return {'python': platform.python_version(),
            'httpx': importlib.metadata.version('httpx'),
            'jsonschema': importlib.metadata.version('jsonschema')}


def prepare_batch(directory):
    """No credentials or network; refuse existing output including failed batches."""
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    directory = Path(directory)
    request = build_request()
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    batch_id = 'v5-personas-' + uuid.uuid4().hex
    plan = {
        'kind': 'v5_leader_persona_generation', 'created_at': timestamp(), 'batch_id': batch_id,
        'approval_scope': 'Eight personas only; approved generation plan; no simulation or publication',
        'model': MODEL, 'service_tier': 'standard_default',
        'request': request, 'request_sha256': digest(request),
        'generation_ids': [f'{batch_id}-leader-{i:02d}' for i in range(1, MAX_PERSONAS + 1)],
        'max_generation_calls': MAX_PERSONAS, 'max_count_calls': MAX_PERSONAS,
        'max_input_tokens': MAX_INPUT, 'max_output_tokens_including_thoughts': MAX_OUTPUT,
        'seed': None, 'seed_scope': 'Model seed deliberately not specified; independent request contexts',
        'retry_count': 0, 'concurrency': 1,
        'timeout_seconds': {'connect': 30, 'read': 180, 'write': 30, 'pool': 30},
        'input_usd_per_million': str(INPUT_PRICE), 'output_usd_per_million': str(OUTPUT_PRICE),
        'usd_stop_limit': str(LIMIT_USD), 'per_attempt_reservation_usd': str(price(MAX_INPUT, MAX_OUTPUT)),
        'price_source': 'https://ai.google.dev/gemini-api/docs/pricing#gemini-3.6-flash',
        'price_valid_through': '2026-12-31',
        'source_hashes': source_hashes(), 'source_commit': commit, 'runtime': _runtime(),
        'publication': 'private_unpublished',
    }
    ensure(price(MAX_INPUT, MAX_OUTPUT) * MAX_PERSONAS <= LIMIT_USD, 'BATCH_PRICE_LIMIT')
    directory.mkdir(mode=0o700)
    Journal(directory).write('plan.json', plan)
    return {'status': 'prepared', 'max_personas': MAX_PERSONAS, 'plan_sha256': digest(plan)}


def _plan(directory):
    directory = Path(directory)
    ensure(not directory.is_symlink(), 'BATCH_SYMLINK')
    ensure((directory.stat().st_mode & 0o077) == 0, 'BATCH_NOT_PRIVATE')
    plan = Journal(directory).read('plan.json')
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    ensure(plan['source_hashes'] == source_hashes() and plan['runtime'] == _runtime(), 'SOURCE_OR_RUNTIME_CHANGED')
    ensure(plan['request'] == build_request() and plan['request_sha256'] == digest(build_request()),
           'APPROVED_INPUT_CHANGED')
    ensure(plan['max_generation_calls'] == MAX_PERSONAS and plan['max_count_calls'] == MAX_PERSONAS
           and plan['usd_stop_limit'] == str(LIMIT_USD)
           and plan['model'] == MODEL, 'PLAN_LIMIT_CHANGED')
    return plan


def _history(directory):
    """A pending, failed, interrupted or rejected generation blocks all successors."""
    ensure(not list(Path(directory).glob('blocked-*.json')), 'BATCH_BLOCKED')
    records = []
    for index in range(1, MAX_PERSONAS + 1):
        path = Path(directory) / f'generation-{index:02d}'
        if not path.exists():
            ensure(not any((Path(directory) / f'generation-{n:02d}').exists()
                           for n in range(index + 1, MAX_PERSONAS + 1)), 'NONCONTIGUOUS_HISTORY')
            break
        result = verify(path)
        ensure(result['status'] == 'success', 'PRIOR_ATTEMPT_NOT_SUCCESSFUL')
        review_path = path / 'DERIVED/content-review.json'
        ensure(review_path.exists(), 'PRIOR_CONTENT_REVIEW_REQUIRED')
        review = read_record(review_path)['report']
        ensure(review['accepted'] is True and review['evidence_hash'] == result['evidence_hash'],
               'PRIOR_CONTENT_REVIEW_REJECTED')
        records.append(result)
    return records


def _manifest(plan, generation_id):
    return {
        'format': FORMAT, 'run_id': generation_id, 'started_at': timestamp(),
        'seed': None, 'seed_scope': plan['seed_scope'], 'provider': 'google-gemini-api',
        'model': MODEL, 'model_version_or_digest': None,
        'generation_config': plan['request']['generationConfig'],
        'experiment_config': {
            'kind': 'independent_persona_generation', 'axis_count': 16,
            'input_mode_for_future_simulation': 'C',
            'request_sha256': plan['request_sha256'], 'plan_sha256': digest(plan),
            'schema_version': 'v5-leader-persona-1',
            'model_version_missing_reason': 'Unknown at start; response metadata is recorded separately',
        },
        'world_config': {'status': 'not_generated', 'assigned_nation': None,
                         'other_personas_provided': False, 'simulation_run': False},
        'provenance': {'source_hashes': plan['source_hashes'], 'source_commit': plan['source_commit'],
                       'runtime': plan['runtime'], 'parent_evidence_hash': None,
                       'purpose': 'Generate and preserve one fictional leader with three personality layers'},
    }


def _error_code(exc):
    # Never serialize exception text (URLs/credentials/local paths can be included).
    if isinstance(exc, GenerationError):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return 'TRANSPORT_TIMEOUT'
    if isinstance(exc, httpx.HTTPError):
        return 'TRANSPORT_ERROR'
    if isinstance(exc, OSError):
        return 'LOCAL_IO_ERROR'
    if isinstance(exc, KeyboardInterrupt):
        return 'INTERRUPTED'
    if isinstance(exc, ValueError):
        return 'JSON_OR_VALIDATION_ERROR'
    return 'RUNTIME_ERROR'


def generate_next(directory, *, transport: httpx.BaseTransport, credential: str):
    """One count + one generation at most. Caller must review before continuing."""
    directory = Path(directory)
    ensure(isinstance(credential, str) and bool(credential.strip()), 'CREDENTIAL_REQUIRED')
    with exclusive_execution(directory):
        plan = _plan(directory)
        history = _history(directory)
        ensure(len(history) < MAX_PERSONAS, 'BATCH_ALREADY_COMPLETE')
        index = len(history) + 1
        generation_id = plan['generation_ids'][index - 1]
        reservation_name = f'reservation-{index:02d}.json'
        ensure(not (directory / reservation_name).exists(), 'UNRESOLVED_PAID_RESERVATION')
        reserved = sum((Decimal(read_record(p)['usd']) for p in directory.glob('reservation-*.json')), Decimal(0))
        upper = price(MAX_INPUT, MAX_OUTPUT)
        ensure(reserved + upper <= LIMIT_USD, 'BUDGET_EXHAUSTED')
        run = EvidenceRun(directory / f'generation-{index:02d}', _manifest(plan, generation_id))
        body = plan['request']
        count_body = {'generateContentRequest': {'model': 'models/' + MODEL, **body}}
        stage = 'save_request'
        generation_attempted = False
        actual_cost = None
        wire = None
        try:
            run.write('count.request.json', count_body)
            run.write('generation.request.json', body)
            with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                              timeout=httpx.Timeout(180, connect=30, write=30, pool=30)) as client:
                def send(kind, payload):
                    nonlocal wire
                    wire = None
                    ensure(digest(_plan(directory)) == digest(plan), 'PLAN_CHANGED_DURING_REQUEST')
                    response = client.post(ENDPOINT + ':' + kind,
                                           content=canonical(payload).encode('utf-8'),
                                           headers={'x-goog-api-key': credential, 'content-type': 'application/json'})
                    raw = response.content
                    wire = {'status': response.status_code, 'received_at': timestamp(),
                            'body_base64': base64.b64encode(raw).decode('ascii'),
                            'body_sha256': hashlib.sha256(raw).hexdigest()}
                    filename = 'count.response.json' if kind == 'countTokens' else 'generation.response.json'
                    run.write(filename, wire)
                    ensure(digest(_plan(directory)) == digest(plan), 'PLAN_CHANGED_DURING_RESPONSE')
                    ensure(response.status_code == 200, 'COUNT_HTTP_ERROR' if kind == 'countTokens' else 'GENERATION_HTTP_ERROR')
                    return load_response_object(raw.decode('utf-8'))

                stage = 'count_tokens'
                counted = send('countTokens', count_body)
                input_tokens = counted.get('totalTokens')
                ensure(type(input_tokens) is int and 0 < input_tokens <= MAX_INPUT, 'COUNT_INVALID_OR_OVER_LIMIT')
                stage = 'reserve_generation'
                Journal(directory).write(reservation_name, {
                    'generation_id': generation_id, 'usd': str(upper), 'reserved_at': timestamp(),
                    'request_sha256': digest(body), 'input_tokens_counted': input_tokens,
                })
                stage = 'generate_content'
                generation_attempted = True
                response = send('generateContent', body)

            stage = 'validate_provider_response'
            usage = response.get('usageMetadata', {})
            keys = ('promptTokenCount', 'candidatesTokenCount', 'thoughtsTokenCount')
            values = [usage.get(k) for k in keys]
            known = all(type(value) is int and value >= 0 for value in values)
            if known:
                actual_cost = str(price(values[0], values[1] + values[2]))
            run.write('receipt.json', {
                'usage_metadata': usage, 'usage_complete': known, 'estimated_cost_usd': actual_cost,
                'billing_verified': False, 'reservation_usd': str(upper),
                'model_version': response.get('modelVersion'),
                'model_version_missing_reason': None if response.get('modelVersion') else 'Not returned by provider',
                'response_id': response.get('responseId'),
            })
            ensure(known, 'USAGE_UNKNOWN')
            ensure(values[0] <= MAX_INPUT and values[1] + values[2] <= MAX_OUTPUT
                   and Decimal(actual_cost) <= upper, 'USAGE_OUTSIDE_RESERVED_LIMIT')
            candidates = response.get('candidates')
            ensure(isinstance(candidates, list) and len(candidates) == 1, 'MISSING_OR_MULTIPLE_CANDIDATES')
            candidate = candidates[0]
            ensure(candidate.get('finishReason') == 'STOP', 'INCOMPLETE_PROVIDER_RESPONSE')
            parts = candidate.get('content', {}).get('parts')
            ensure(isinstance(parts, list) and bool(parts), 'MISSING_RESPONSE_PARTS')
            ensure(all(isinstance(p, dict) and not p.get('thought') and isinstance(p.get('text'), str)
                       and not any(k in p for k in ('functionCall', 'executableCode', 'inlineData')) for p in parts),
                   'UNEXPECTED_RESPONSE_PART')
            persona = load_response_object(''.join(part['text'] for part in parts))
            stage = 'validate_persona'
            validation = validate_persona(persona, schema=plan['request']['generationConfig']['responseJsonSchema'])
            result = run.finish('success', completed_turns=0)
            stage = 'derive_persona'
            run.derive('persona.json', {
                'generation_id': generation_id, 'leader_id': f'leader-{index:02d}',
                'schema_version': 'v5-leader-persona-1',
                'raw_response_path': 'RAW/generation.response.json',
                'raw_response_body_sha256': wire['body_sha256'],
                'language': 'ja', 'self_introduction_audience': 'other national leaders at first meeting',
                'principle_ids': [f'{generation_id}-principle-{n:02d}' for n in range(1, len(persona['layer3']) + 1)],
                'persona': persona,
            })
            run.derive('validation.json', validation)
            verify(run.root, expected_evidence_hash=result['evidence_hash'])
            return {**result, 'generation_id': generation_id, 'content_review_required': True,
                    'estimated_cost_usd': actual_cost, 'generation_attempted': True,
                    'intro_character_count': validation['intro_character_count'], 'warnings': validation['warnings']}
        except (Exception, KeyboardInterrupt) as exc:
            error = {'code': _error_code(exc), 'stage': stage, 'generation_attempted': generation_attempted}
            # Do not rewrite a sealed record if deriving or integrity validation failed.
            if (run.root / 'terminal.json').exists():
                Journal(directory).write(f'blocked-{index:02d}.json', error)
                return {'generation_id': generation_id, 'status': 'failure', 'error': error,
                        'estimated_cost_usd': actual_cost}
            try:
                run.write('failure.json', error)
                result = run.finish('interrupted' if isinstance(exc, KeyboardInterrupt) else 'failure',
                                    completed_turns=0, error=error)
            except (Exception, KeyboardInterrupt):
                # The incomplete directory itself blocks all later calls. Never claim saved evidence.
                return {'generation_id': generation_id, 'status': 'unfinalized', 'error': error,
                        'evidence_finalization_failed': True, 'estimated_cost_usd': actual_cost}
            return {**result, 'generation_id': generation_id, 'error': error, 'estimated_cost_usd': actual_cost}


def review_last(directory, *, accepted: bool, notes: str = ''):
    """Record a content review without modifying the generated text or scoring traits."""
    ensure(type(accepted) is bool and isinstance(notes, str), 'INVALID_REVIEW')
    directory = Path(directory)
    with exclusive_execution(directory):
        _plan(directory)
        ensure(not list(directory.glob('blocked-*.json')), 'BATCH_BLOCKED')
        existing = [directory / f'generation-{i:02d}' for i in range(1, MAX_PERSONAS + 1)
                    if (directory / f'generation-{i:02d}').exists()]
        ensure(bool(existing), 'NO_GENERATION_TO_REVIEW')
        path = existing[-1]
        result = verify(path)
        ensure(result['status'] == 'success', 'CANNOT_REVIEW_FAILED_GENERATION')
        # These must exist before a review can make this result eligible for continuation.
        read_record(path / 'DERIVED/persona.json')
        read_record(path / 'DERIVED/validation.json')
        Journal(path / 'DERIVED').write('content-review.json', {
            'raw_evidence_hash': result['raw_evidence_hash'],
            'report': {'accepted': accepted, 'notes': notes, 'reviewed_at': timestamp(),
                       'evidence_hash': result['evidence_hash'],
                       'scope': 'internal parameter disclosure, assigned nation and future event contamination only',
                       'reviewer': 'implementation_assistant', 'extra_model_calls': 0,
                       'personality_quality_scored': False},
        })
        return {'generation_id': result['run_id'], 'accepted': accepted,
                'completed_personas': len(existing), 'batch_complete': len(existing) == MAX_PERSONAS and accepted}
