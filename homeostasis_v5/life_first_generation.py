"""Life-first generation in independent contexts, with immutable phase evidence.

One invocation sends at most one token count and one generation. Every completed
phase needs an offline boundary review. Failures block successors and retries.
No nation generation, simulation, publication, or persona selection exists here.
"""
from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

import httpx

from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.contracts import digest
from homeostasis_v4.evidence import EvidenceRun, FORMAT, read_record, timestamp, verify
from homeostasis_v5.life_first_contract import (
    PHASES, PHASE_LIMITS, MODEL, LEADER_COUNT, GENERATION_METHOD_VERSION,
    LifeFirstValidationError, build_request, validate_phase,
)
from homeostasis_v5.persona_generation import (
    GenerationError, account_usage, _extract_persona, _runtime, price,
)
from model_response_json import load_response_object
from v2_autonomous import Journal

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/' + MODEL


def ensure(condition, code):
    if not condition:
        raise GenerationError(code)


def wire_bytes(body):
    """Preserve schema and prompt insertion order, separately from hash encoding."""
    return json.dumps(body, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def source_hashes():
    files = (
        'homeostasis_v5/life_first_contract.py', 'homeostasis_v5/life_first_generation.py',
        'homeostasis_v5/persona_generation.py', 'homeostasis_v5/__init__.py',
        'docs/design/v5/PERSONA_GENERATOR_V1_MEASUREMENT_SCHEMA.proposed.json',
        'homeostasis_core/execution_lock.py', 'homeostasis_v3/contracts.py',
        'homeostasis_v4/evidence.py', 'model_response_json.py', 'v2_autonomous.py',
        'tools/generate_v5_life_first.py',
    )
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}


def phase_limit(phase):
    limits = PHASE_LIMITS[phase]
    return limits['max_input_tokens'], limits['max_output_tokens']


def prepare_batch(directory, *, budget_usd):
    directory = Path(directory)
    ceiling = Decimal(str(budget_usd))
    ensure(ceiling.is_finite() and ceiling > 0, 'INVALID_BUDGET')
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    upper = sum((price(*phase_limit(p)) for p in PHASES), Decimal(0)) * LEADER_COUNT
    ensure(upper <= ceiling, 'INSUFFICIENT_RESERVED_BUDGET')
    with exclusive_execution(directory):
        ensure(not directory.exists() and not directory.is_symlink(), 'NEW_BATCH_REQUIRED')
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
        plan = {
            'kind': 'life_first_persona_batch', 'method': GENERATION_METHOD_VERSION,
            'batch_id': 'v5-life-first-' + uuid.uuid4().hex, 'created_at': timestamp(),
            'leader_count': LEADER_COUNT, 'phases': list(PHASES),
            'max_generation_calls': LEADER_COUNT * len(PHASES),
            'max_count_calls': LEADER_COUNT * len(PHASES),
            'phase_limits': PHASE_LIMITS, 'budget_usd': str(ceiling),
            'maximum_reserved_usd': str(upper), 'model': MODEL,
            'generation_settings': {'temperature': 1.0, 'candidateCount': 1,
                                    'thinkingLevel': 'LOW'},
            'seed': None, 'seed_scope': 'Unspecified model seed; separate request contexts',
            'retry_count': 0, 'concurrency': 1, 'service_tier': 'standard_default',
            'input_usd_per_million': '0.75', 'output_usd_per_million': '3.75',
            'price_valid_through': '2026-12-31',
            'price_source': 'https://ai.google.dev/gemini-api/docs/pricing#gemini-3.6-flash',
            'runtime': _runtime(), 'source_hashes': source_hashes(), 'source_commit': commit,
            'selection_or_reroll': False, 'other_personas_provided': False,
            'assigned_nation_provided': False, 'publication': 'private_unpublished',
        }
        directory.mkdir(mode=0o700)
        Journal(directory).write('plan.json', plan)
        return {'status': 'prepared', 'plan_sha256': digest(plan),
                'generation_calls': plan['max_generation_calls'], 'maximum_reserved_usd': str(upper)}


def _plan(directory):
    ensure(not directory.is_symlink() and directory.is_dir(), 'PRIVATE_BATCH_REQUIRED')
    ensure(not directory.stat().st_mode & 0o077, 'PRIVATE_BATCH_REQUIRED')
    plan = Journal(directory).read('plan.json')
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    ensure(plan['source_hashes'] == source_hashes() and plan['runtime'] == _runtime(), 'SOURCE_OR_RUNTIME_CHANGED')
    ensure(plan['method'] == GENERATION_METHOD_VERSION and plan['leader_count'] == LEADER_COUNT
           and plan['phases'] == list(PHASES) and plan['phase_limits'] == PHASE_LIMITS
           and plan['model'] == MODEL and plan['max_generation_calls'] == LEADER_COUNT * len(PHASES)
           and plan['max_count_calls'] == LEADER_COUNT * len(PHASES), 'PLAN_SCOPE_CHANGED')
    return plan


def _position(index):
    return (index - 1) // len(PHASES) + 1, PHASES[(index - 1) % len(PHASES)]


def _decoded(root):
    wire = read_record(root / 'RAW/generation.response.json')
    raw = base64.b64decode(wire['body_base64'], validate=True)
    ensure(wire['status'] == 200 and hashlib.sha256(raw).hexdigest() == wire['body_sha256'], 'RESPONSE_DIGEST_MISMATCH')
    return _extract_persona(load_response_object(raw.decode('utf-8')))


def _history(directory, plan, *, allow_last_unreviewed=False):
    ensure(not list(directory.glob('blocked-*.json')), 'BATCH_BLOCKED')
    history = []
    prior = {}
    for index in range(1, LEADER_COUNT * len(PHASES) + 1):
        root = directory / f'phase-{index:02d}'
        if not root.exists():
            ensure(not any((directory / f'phase-{n:02d}').exists()
                           for n in range(index + 1, LEADER_COUNT * len(PHASES) + 1)), 'HISTORY_GAP')
            break
        leader, phase = _position(index)
        if phase == PHASES[0]:
            prior = {}
        result = verify(root)
        ensure(result['status'] == 'success', 'PRIOR_PHASE_NOT_SUCCESSFUL')
        manifest = read_record(root / 'manifest.json')
        ensure(manifest['experiment_config']['plan_sha256'] == digest(plan)
               and manifest['experiment_config']['leader_index'] == leader
               and manifest['experiment_config']['phase'] == phase, 'PHASE_SCOPE_CHANGED')
        body = read_record(root / 'RAW/generation.request.json')
        expected_request = build_request(phase, prior)
        ensure(digest(body) == digest(expected_request), 'PHASE_INPUT_CHANGED')
        wire = read_record(root / 'RAW/generation.wire.json')
        ensure(base64.b64decode(wire['body_base64'], validate=True) == wire_bytes(expected_request), 'REQUEST_WIRE_CHANGED')
        output = _decoded(root)
        ensure(read_record(root / 'DERIVED/output.json')['report']['output'] == output, 'DERIVED_OUTPUT_CHANGED')
        validate_phase(phase, output, prior)
        review_path = root / 'DERIVED/boundary-review.json'
        if review_path.exists():
            review = read_record(review_path)['report']
            ensure(review['accepted'] is True and review['evidence_hash'] == result['evidence_hash'], 'REVIEW_REJECTED_OR_CHANGED')
            if phase == PHASES[-1]:
                frozen = Journal(directory).read(f'leader-{leader:03d}.freeze.json')
                expected = [{'phase': h['phase'], 'directory': h['root'].name,
                             'evidence_hash': h['result']['evidence_hash'], 'output_sha256': digest(h['output'])}
                            for h in history if h['leader'] == leader]
                expected.append({'phase': phase, 'directory': root.name,
                                 'evidence_hash': result['evidence_hash'], 'output_sha256': digest(output)})
                ensure(frozen['leader_index'] == leader and frozen['phases'] == expected, 'FREEZE_CHANGED')
        else:
            ensure(allow_last_unreviewed and not (directory / f'phase-{index + 1:02d}').exists(), 'BOUNDARY_REVIEW_REQUIRED')
        prior[phase] = output
        history.append({'index': index, 'leader': leader, 'phase': phase, 'root': root,
                        'result': result, 'output': output, 'prior': dict(prior)})
    return history


def _error_code(exc):
    if isinstance(exc, (GenerationError, LifeFirstValidationError)):
        return str(exc)
    if isinstance(exc, httpx.TimeoutException):
        return 'TRANSPORT_TIMEOUT'
    if isinstance(exc, httpx.HTTPError):
        return 'TRANSPORT_ERROR'
    if isinstance(exc, KeyboardInterrupt):
        return 'INTERRUPTED'
    if isinstance(exc, OSError):
        return 'LOCAL_IO_ERROR'
    return 'PHASE_VALIDATION_OR_RUNTIME_ERROR'


def generate_next(directory, *, transport, credential):
    directory = Path(directory)
    ensure(isinstance(credential, str) and bool(credential.strip()), 'CREDENTIAL_REQUIRED')
    with exclusive_execution(directory):
        plan = _plan(directory)
        history = _history(directory, plan)
        index = len(history) + 1
        ensure(index <= LEADER_COUNT * len(PHASES), 'BATCH_COMPLETE')
        leader, phase = _position(index)
        prior = {} if phase == PHASES[0] else history[-1]['prior']
        body = build_request(phase, prior)
        max_input, max_output = phase_limit(phase)
        upper = price(max_input, max_output)
        reservation_name = f'reservation-{index:02d}.json'
        ensure(not (directory / reservation_name).exists(), 'UNRESOLVED_PAID_RESERVATION')
        reserved = sum((Decimal(read_record(p)['usd']) for p in directory.glob('reservation-*.json')), Decimal(0))
        ensure(reserved + upper <= Decimal(plan['budget_usd']), 'BUDGET_EXHAUSTED')
        parents = [{'phase': h['phase'], 'evidence_hash': h['result']['evidence_hash']}
                   for h in history if h['leader'] == leader]
        manifest = {
            'format': FORMAT, 'run_id': f"{plan['batch_id']}-leader-{leader:03d}-{phase}",
            'started_at': timestamp(), 'seed': None, 'seed_scope': plan['seed_scope'],
            'provider': 'google-gemini-api', 'model': MODEL, 'model_version_or_digest': None,
            'generation_config': body['generationConfig'],
            'experiment_config': {'method': GENERATION_METHOD_VERSION, 'leader_index': leader,
                                  'phase': phase, 'plan_sha256': digest(plan), 'request_sha256': digest(body),
                                  'parent_phases': parents, 'model_version_missing_reason': 'Not yet returned'},
            'world_config': {'assigned_nation': None, 'other_personas_provided': False, 'simulation_run': False},
            'provenance': {'source_hashes': plan['source_hashes'], 'source_commit': plan['source_commit'],
                           'runtime': plan['runtime'], 'parent_evidence_hash': parents[-1]['evidence_hash'] if parents else None,
                           'purpose': 'Generate and preserve one stage of one fictional life-first persona'},
        }
        run = EvidenceRun(directory / f'phase-{index:02d}', manifest)
        stage = 'save_request'
        attempted = False
        actual_cost = None
        try:
            count_body = {'generateContentRequest': {'model': 'models/' + MODEL, **body}}
            run.write('generation.request.json', body)
            run.write('count.request.json', count_body)
            for name, payload in [('generation', body), ('count', count_body)]:
                raw = wire_bytes(payload)
                run.write(name + '.wire.json', {'body_base64': base64.b64encode(raw).decode('ascii'),
                                                'body_sha256': hashlib.sha256(raw).hexdigest()})
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False,
                              timeout=httpx.Timeout(180, connect=30, write=30, pool=30)) as client:
                def send(kind, payload):
                    ensure(digest(_plan(directory)) == digest(plan), 'PLAN_CHANGED')
                    response = client.post(ENDPOINT + ':' + kind, content=wire_bytes(payload),
                                           headers={'x-goog-api-key': credential, 'content-type': 'application/json'})
                    raw = response.content
                    run.write(('count' if kind == 'countTokens' else 'generation') + '.response.json', {
                        'status': response.status_code, 'received_at': timestamp(),
                        'body_base64': base64.b64encode(raw).decode('ascii'),
                        'body_sha256': hashlib.sha256(raw).hexdigest(),
                    })
                    ensure(digest(_plan(directory)) == digest(plan), 'PLAN_CHANGED')
                    ensure(response.status_code == 200, 'COUNT_HTTP_ERROR' if kind == 'countTokens' else 'GENERATION_HTTP_ERROR')
                    return load_response_object(raw.decode('utf-8'))

                stage = 'count_tokens'
                count = send('countTokens', count_body).get('totalTokens')
                ensure(type(count) is int and 0 < count <= max_input, 'INPUT_COUNT_INVALID_OR_OVER_LIMIT')
                stage = 'reserve_generation'
                Journal(directory).write(reservation_name, {
                    'phase_index': index, 'usd': str(upper), 'reserved_at': timestamp(),
                    'request_sha256': digest(body), 'counted_input_tokens': count,
                })
                stage = 'generate_content'
                attempted = True
                response = send('generateContent', body)
            stage = 'account_usage'
            accounting = account_usage(response.get('usageMetadata'))
            actual_cost = accounting['estimated_cost_usd']
            run.write('receipt.json', {'usage_metadata': response.get('usageMetadata'), 'accounting': accounting,
                                      'billing_verified': False, 'model_version': response.get('modelVersion'),
                                      'response_id': response.get('responseId'), 'reservation_usd': str(upper)})
            ensure(accounting['input_tokens'] <= max_input
                   and accounting['generated_tokens_including_thoughts'] <= max_output
                   and Decimal(actual_cost) <= upper, 'USAGE_OVER_RESERVATION')
            stage = 'validate_phase'
            output = _extract_persona(response)
            validation = validate_phase(phase, output, prior)
            result = run.finish('success', completed_turns=0)
            stage = 'save_derived'
            run.derive('output.json', {'phase': phase, 'leader_index': leader, 'output': output,
                                       'raw_response_path': 'RAW/generation.response.json'})
            run.derive('validation.json', validation)
            return {**result, 'leader_index': leader, 'phase': phase, 'phase_index': index,
                    'estimated_cost_usd': actual_cost, 'boundary_review_required': True,
                    'output_path': str(run.root / 'DERIVED/output.json')}
        except (Exception, KeyboardInterrupt) as exc:
            error = {'code': _error_code(exc), 'stage': stage, 'generation_attempted': attempted}
            if (run.root / 'terminal.json').exists():
                Journal(directory).write(f'blocked-{index:02d}.json', error)
                return {'status': 'failure', 'error': error, 'estimated_cost_usd': actual_cost}
            try:
                run.write('failure.json', error)
                result = run.finish('interrupted' if isinstance(exc, KeyboardInterrupt) else 'failure', completed_turns=0, error=error)
                return {**result, 'error': error, 'estimated_cost_usd': actual_cost}
            except (Exception, KeyboardInterrupt):
                return {'status': 'unfinalized', 'error': error, 'estimated_cost_usd': actual_cost}


def review_last(directory, *, accepted):
    """Boundary review only; age, traits, similarity and preferences are not scores."""
    directory = Path(directory)
    ensure(type(accepted) is bool, 'BOOLEAN_REVIEW_REQUIRED')
    with exclusive_execution(directory):
        plan = _plan(directory)
        history = _history(directory, plan, allow_last_unreviewed=True)
        ensure(bool(history), 'NO_PHASE_TO_REVIEW')
        last = history[-1]
        Journal(last['root'] / 'DERIVED').write('boundary-review.json', {
            'raw_evidence_hash': last['result']['raw_evidence_hash'],
            'report': {'accepted': accepted, 'evidence_hash': last['result']['evidence_hash'],
                       'reviewed_at': timestamp(), 'reviewer': 'implementation_assistant',
                       'scope': 'No forbidden inputs, assigned nation, future simulation script or changed life facts',
                       'personality_quality_scored': False, 'extra_model_calls': 0},
        })
        if accepted and last['phase'] == PHASES[-1]:
            own = [h for h in history if h['leader'] == last['leader']]
            Journal(directory).write(f"leader-{last['leader']:03d}.freeze.json", {
                'leader_index': last['leader'], 'method': GENERATION_METHOD_VERSION,
                'phases': [{'phase': h['phase'], 'directory': h['root'].name,
                            'evidence_hash': h['result']['evidence_hash'], 'output_sha256': digest(h['output'])} for h in own],
                'completed_at': timestamp(), 'assigned_nation': None, 'publication': 'private_unpublished',
            })
        return {'accepted': accepted, 'reviewed_phases': len(history),
                'completed_leaders': len(list(directory.glob('leader-*.freeze.json'))),
                'batch_complete': accepted and len(history) == LEADER_COUNT * len(PHASES)}
