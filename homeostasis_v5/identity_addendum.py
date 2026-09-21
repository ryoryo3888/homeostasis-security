"""Bounded post-hoc fictional identity creation; no original persona mutation."""
import base64
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

import httpx
from jsonschema import Draft202012Validator

from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v4.evidence import EvidenceRun, FORMAT, read_record, timestamp, verify
from homeostasis_v5 import persona_generation as original
from homeostasis_v5.persona_generation import ensure, price, account_usage, _extract_persona, _error_code, _runtime
from model_response_json import load_response_object
from v2_autonomous import Journal

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'docs/design/v5'
MAX_INPUT = 16000
MAX_OUTPUT = 2048
LIMIT = Decimal('0.20')
SCHEMA_VERSION = 'v5-identity-addendum-1'


def source_hashes():
    paths = ('homeostasis_v5/identity_addendum.py', 'tools/generate_v5_identity_addenda.py',
             'docs/design/v5/IDENTITY_ADDENDUM_PROMPT.txt', 'docs/design/v5/IDENTITY_ADDENDUM_SCHEMA.json',
             'docs/design/v5/IDENTITY_ADDENDUM_PLAN.md')
    return {**original.source_hashes(), **{p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}


def load_sources(source):
    source = Path(source)
    plan = original._plan(source)
    ensure(len(original._history(source, completed_before=plan['completed_before'])) + plan['completed_before'] == 8,
           'ORIGINAL_PERSONAS_NOT_COMPLETE')
    ensure(plan['completed_before'] == 1, 'EXPECTED_FROZEN_SOURCE_BATCH')
    recovered = read_record(source / 'recovered-leader-01.json')
    rows = []
    for index in range(1, 9):
        if index == 1:
            parent_name = plan['continuation']['parent_directory_name']
            directory = source.parent / parent_name / 'generation-01'
            persona = recovered['persona']
            relative = '../' + parent_name + '/generation-01'
            pin = recovered['parent_evidence_hash']
        else:
            directory = source / f'generation-{index:02d}'
            persona = read_record(directory / 'DERIVED/persona.json')['report']['persona']
            relative = f'generation-{index:02d}'
            pin = read_record(directory / 'DERIVED/content-review.json')['report']['evidence_hash']
        evidence = verify(directory, expected_evidence_hash=pin)
        wire = read_record(directory / 'RAW/generation.response.json')
        raw = base64.b64decode(wire['body_base64'], validate=True)
        ensure(hashlib.sha256(raw).hexdigest() == wire['body_sha256'], 'SOURCE_RESPONSE_CHANGED')
        ensure(_extract_persona(load_response_object(raw.decode())) == persona, 'SOURCE_PERSONA_CHANGED')
        rows.append({'leader_id': f'leader-{index:02d}', 'persona': persona, 'persona_sha256': digest(persona),
                     'evidence_hash': evidence['evidence_hash'], 'original_generation_id': evidence['run_id'],
                     'source_relative_directory': relative, 'response_body_sha256': wire['body_sha256']})
    return {'source_plan_sha256': digest(plan), 'people': rows}


def build_request(persona):
    schema = load_response_object((DESIGN / 'IDENTITY_ADDENDUM_SCHEMA.json').read_text())
    Draft202012Validator.check_schema(schema)
    return {'contents': [{'role': 'user', 'parts': [
        {'text': (DESIGN / 'IDENTITY_ADDENDUM_PROMPT.txt').read_text()},
        {'text': '参照データ（この一人の保存済み人格）\n' + canonical(persona)},
    ]}], 'generationConfig': {'responseMimeType': 'application/json', 'responseJsonSchema': schema,
        'temperature': 1.0, 'candidateCount': 1, 'maxOutputTokens': MAX_OUTPUT,
        'thinkingConfig': {'thinkingLevel': 'LOW', 'includeThoughts': False}}}


def validate_addendum(value):
    schema = load_response_object((DESIGN / 'IDENTITY_ADDENDUM_SCHEMA.json').read_text())
    ensure(not list(Draft202012Validator(schema).iter_errors(value)), 'ADDENDUM_SCHEMA_ERROR')
    ensure(all(v.strip() for v in value.values()), 'EMPTY_ADDENDUM')
    # Identity values, combinations, non-disclosure, and repetition are never scored.


def prepare(directory, source):
    directory, source = Path(directory), Path(source)
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    ensure(directory.parent.resolve() == source.parent.resolve() and directory.name != source.name,
           'NEW_SIBLING_REQUIRED')
    frozen = load_sources(source)
    ensure(price(MAX_INPUT, MAX_OUTPUT) * 8 <= LIMIT, 'BUDGET_LIMIT')
    batch = 'v5-identity-' + uuid.uuid4().hex
    requests = [build_request(p['persona']) for p in frozen['people']]
    plan = {'kind': 'post_hoc_fictional_identity_addendum', 'schema_version': SCHEMA_VERSION,
            'created_at': timestamp(), 'batch_id': batch, 'source_directory_name': source.name,
            'sources': frozen, 'requests': requests, 'request_hashes': [digest(r) for r in requests],
            'model': original.MODEL, 'generation_ids': [f'{batch}-leader-{i:02d}' for i in range(1, 9)],
            'max_generation_calls': 8, 'max_count_calls': 8, 'retry_count': 0, 'concurrency': 1,
            'usd_stop_limit': str(LIMIT), 'max_input_tokens': MAX_INPUT, 'max_output_tokens': MAX_OUTPUT,
            'per_attempt_reservation_usd': str(price(MAX_INPUT, MAX_OUTPUT)),
            'input_usd_per_million': str(original.INPUT_PRICE), 'output_usd_per_million': str(original.OUTPUT_PRICE),
            'price_source': 'https://ai.google.dev/gemini-api/docs/pricing#gemini-3.6-flash',
            'price_valid_through': '2026-12-31', 'source_hashes': source_hashes(), 'runtime': _runtime(),
            'source_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                             text=True, check=True).stdout.strip(),
            'publication': 'private_unpublished', 'other_agent_access': False,
            'simulation_wiring': False, 'original_persona_mutation': False,
            'classification_or_quota': None, 'seed': None}
    directory.mkdir(mode=0o700)
    Journal(directory).write('plan.json', plan)
    return {'status': 'prepared', 'additional_generations': 8, 'plan_sha256': digest(plan),
            'reservation_total_usd': str(price(MAX_INPUT, MAX_OUTPUT) * 8), 'usd_stop_limit': str(LIMIT)}


def checked_plan(directory):
    directory = Path(directory)
    ensure(not directory.is_symlink() and directory.stat().st_mode & 0o077 == 0, 'PRIVATE_BATCH_REQUIRED')
    plan = Journal(directory).read('plan.json')
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    ensure(plan['source_hashes'] == source_hashes() and plan['runtime'] == _runtime(), 'SOURCE_OR_RUNTIME_CHANGED')
    ensure(plan['max_generation_calls'] == 8 and plan['max_count_calls'] == 8
           and plan['usd_stop_limit'] == str(LIMIT) and plan['model'] == original.MODEL,
           'PLAN_LIMIT_CHANGED')
    name = plan['source_directory_name']
    ensure(Path(name).name == name, 'INVALID_SOURCE_REFERENCE')
    ensure(plan['sources'] == load_sources(directory.parent / name), 'PARENT_CHANGED')
    requests = [build_request(p['persona']) for p in plan['sources']['people']]
    ensure(plan['requests'] == requests and plan['request_hashes'] == [digest(r) for r in requests],
           'INPUT_CHANGED')
    return plan


def generate_next(directory, *, transport, credential):
    directory = Path(directory)
    ensure(isinstance(credential, str) and bool(credential.strip()), 'CREDENTIAL_REQUIRED')
    with exclusive_execution(directory):
        plan = checked_plan(directory)
        history = original._history(directory)
        ensure(len(history) < 8, 'BATCH_ALREADY_COMPLETE')
        index = len(history) + 1
        person = plan['sources']['people'][index - 1]
        body = plan['requests'][index - 1]
        gid = plan['generation_ids'][index - 1]
        upper = price(MAX_INPUT, MAX_OUTPUT)
        reserved = sum((Decimal(read_record(p)['usd']) for p in directory.glob('reservation-*.json')), Decimal(0))
        ensure(reserved + upper <= LIMIT, 'BUDGET_EXHAUSTED')
        reservation_name = f'reservation-{index:02d}.json'
        ensure(not (directory / reservation_name).exists(), 'UNRESOLVED_RESERVATION')
        manifest = {'format': FORMAT, 'run_id': gid, 'started_at': timestamp(), 'seed': None,
            'seed_scope': 'Not specified; separate request context for each original fictional person',
            'provider': 'google-gemini-api', 'model': original.MODEL, 'model_version_or_digest': None,
            'generation_config': body['generationConfig'],
            'experiment_config': {'kind': plan['kind'], 'schema_version': SCHEMA_VERSION,
                'leader_id': person['leader_id'], 'original_persona_sha256': person['persona_sha256'],
                'original_generation_id': person['original_generation_id'], 'request_sha256': digest(body),
                'plan_sha256': digest(plan), 'other_agent_access': False, 'original_persona_mutation': False},
            'world_config': {'assigned_nation': None, 'simulation_run': False, 'other_personas_provided': False},
            'provenance': {'source_hashes': plan['source_hashes'], 'source_commit': plan['source_commit'],
                'runtime': plan['runtime'], 'parent_evidence_hash': person['evidence_hash'],
                'purpose': 'New fictional identity setting added after original persona generation; not an inference'}}
        run = EvidenceRun(directory / f'generation-{index:02d}', manifest)
        stage, attempted, cost = 'save_request', False, None
        try:
            count_body = {'generateContentRequest': {'model': 'models/' + original.MODEL, **body}}
            run.write('count.request.json', count_body)
            run.write('generation.request.json', body)
            with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                              timeout=httpx.Timeout(180, connect=30, write=30, pool=30)) as client:
                def send(kind, request):
                    ensure(digest(checked_plan(directory)) == digest(plan), 'PLAN_CHANGED')
                    response = client.post(original.ENDPOINT + ':' + kind, content=canonical(request).encode(),
                        headers={'x-goog-api-key': credential, 'content-type': 'application/json'})
                    raw = response.content
                    run.write('count.response.json' if kind == 'countTokens' else 'generation.response.json',
                        {'status': response.status_code, 'received_at': timestamp(),
                         'body_base64': base64.b64encode(raw).decode(), 'body_sha256': hashlib.sha256(raw).hexdigest()})
                    ensure(digest(checked_plan(directory)) == digest(plan), 'PLAN_CHANGED')
                    ensure(response.status_code == 200, 'COUNT_HTTP_ERROR' if kind == 'countTokens' else 'GENERATION_HTTP_ERROR')
                    return load_response_object(raw.decode())
                stage = 'count_tokens'
                counted = send('countTokens', count_body)
                count = counted.get('totalTokens')
                ensure(type(count) is int and 0 < count <= MAX_INPUT, 'INPUT_OVER_LIMIT_OR_UNKNOWN')
                stage = 'reserve_generation'
                Journal(directory).write(reservation_name, {'generation_id': gid, 'usd': str(upper),
                    'reserved_at': timestamp(), 'input_tokens_counted': count, 'request_sha256': digest(body)})
                stage, attempted = 'generate_content', True
                response = send('generateContent', body)
            stage = 'validate_usage'
            usage = account_usage(response.get('usageMetadata'))
            cost = usage['estimated_cost_usd']
            run.write('receipt.json', {'usage_metadata': response['usageMetadata'], 'accounting': usage,
                'model_version': response.get('modelVersion'), 'response_id': response.get('responseId'),
                'billing_verified': False, 'estimated_cost_usd': cost})
            ensure(usage['input_tokens'] <= MAX_INPUT and usage['generated_tokens_including_thoughts'] <= MAX_OUTPUT
                   and Decimal(cost) <= upper, 'USAGE_OUTSIDE_LIMIT')
            stage = 'validate_addendum'
            value = _extract_persona(response)
            validate_addendum(value)
            result = run.finish('success', completed_turns=0)
            stage = 'save_derived'
            run.derive('addendum.json', {'leader_id': person['leader_id'], 'generation_id': gid,
                'original_persona_sha256': person['persona_sha256'], 'parent_evidence_hash': person['evidence_hash'],
                'kind': plan['kind'], 'identity': value, 'other_agent_access': False,
                'original_persona_mutation': False, 'schema_version': SCHEMA_VERSION})
            verify(run.root, expected_evidence_hash=result['evidence_hash'])
            return {**result, 'leader_id': person['leader_id'], 'estimated_cost_usd': cost,
                    'content_review_required': True}
        except (Exception, KeyboardInterrupt) as exc:
            error = {'code': _error_code(exc), 'stage': stage, 'generation_attempted': attempted}
            if (run.root / 'terminal.json').exists():
                Journal(directory).write(f'blocked-{index:02d}.json', error)
                return {'status': 'failure', 'error': error, 'estimated_cost_usd': cost}
            try:
                run.write('failure.json', error)
                result = run.finish('interrupted' if isinstance(exc, KeyboardInterrupt) else 'failure',
                                    completed_turns=0, error=error)
                return {**result, 'error': error, 'estimated_cost_usd': cost}
            except (Exception, KeyboardInterrupt):
                return {'status': 'unfinalized', 'error': error}


def review_last(directory, *, accepted, notes=''):
    directory = Path(directory)
    ensure(type(accepted) is bool and isinstance(notes, str), 'INVALID_REVIEW')
    with exclusive_execution(directory):
        checked_plan(directory)
        ensure(not list(directory.glob('blocked-*.json')), 'BATCH_BLOCKED')
        paths = sorted(directory.glob('generation-*'))
        ensure(bool(paths), 'NOTHING_TO_REVIEW')
        root = paths[-1]
        result = verify(root)
        ensure(result['status'] == 'success', 'CANNOT_REVIEW_FAILURE')
        value = read_record(root / 'DERIVED/addendum.json')['report']['identity']
        validate_addendum(value)
        wire = read_record(root / 'RAW/generation.response.json')
        raw = base64.b64decode(wire['body_base64'], validate=True)
        ensure(hashlib.sha256(raw).hexdigest() == wire['body_sha256']
               and _extract_persona(load_response_object(raw.decode())) == value, 'ADDENDUM_DIFFERS_FROM_RAW')
        Journal(root / 'DERIVED').write('content-review.json', {'raw_evidence_hash': result['raw_evidence_hash'],
            'report': {'accepted': accepted, 'reviewed_at': timestamp(), 'evidence_hash': result['evidence_hash'],
                'scope': 'Only the approved two fields; no rewriting of original persona or additional world settings',
                'identity_desirability_scored': False, 'notes': notes, 'extra_model_calls': 0}})
        return {'accepted': accepted, 'completed_addenda': len(paths), 'batch_complete': len(paths) == 8 and accepted}
