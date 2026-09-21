"""Bounded collection of approved nation-initialization addendum proposals.

Separate immutable evidence only: no original mutation, settlement, acceptance,
assignment, simulation, model repair, retry or publication.
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
from jsonschema import Draft202012Validator
from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.contracts import digest
from homeostasis_v4.evidence import EvidenceRun, FORMAT, read_record, timestamp, verify
from homeostasis_v5.persona_generation import (
    GenerationError, ensure, account_usage, _extract_persona, _runtime, price,
)
from homeostasis_v5.life_first_generation import wire_bytes
from homeostasis_v5.nation_addendum_contract import validate_addendum
from model_response_json import load_response_object
from v2_autonomous import Journal

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v5-nation-addendum-proposals-1'
MODEL = 'gemini-3.6-flash'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/' + MODEL
IDS = [f'nation-{i:03d}' for i in range(1, 13)]
MAX_INPUT, MAX_OUTPUT = 24000, 8192
CEILING = Decimal('0.58464')
CONFIG = {'responseMimeType': 'application/json', 'temperature': 1.0,
          'candidateCount': 1, 'maxOutputTokens': MAX_OUTPUT,
          'thinkingConfig': {'thinkingLevel': 'LOW', 'includeThoughts': False}}


def source_hashes():
    names = ('homeostasis_v5/nation_addendum_generation.py', 'homeostasis_v5/nation_addendum_contract.py',
             'homeostasis_v5/persona_generation.py', 'homeostasis_v5/life_first_generation.py',
             'homeostasis_core/execution_lock.py', 'homeostasis_v3/contracts.py',
             'homeostasis_v4/evidence.py', 'model_response_json.py', 'v2_autonomous.py',
             'v2_dialogue.py', 'tools/generate_v5_nation_addenda.py')
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}


def _sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _file_sha(path):
    path = Path(path)
    ensure(path.is_file() and not path.is_symlink(), 'REGULAR_SOURCE_REQUIRED')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plain(path):
    path = Path(path)
    ensure(path.is_file() and not path.is_symlink(), 'REGULAR_SOURCE_REQUIRED')
    return load_response_object(path.read_text())


def _load_approved_proposals(directory):
    directory = Path(directory)
    ensure(directory.is_dir() and not directory.is_symlink(), 'PROPOSAL_DIRECTORY_REQUIRED')
    path = directory / 'clarification-plan.proposed.json'
    plan = _plain(path)
    ensure(plan['draft_schema_revision'] == '2-component-scoped-proposals'
           and plan['model'] == MODEL and plan['tier'] == 'Standard'
           and plan['generation_calls_max'] == plan['count_calls_max'] == 12
           and plan['input_tokens_max_per_call'] == MAX_INPUT
           and plan['generated_tokens_max_per_call_including_thinking'] == MAX_OUTPUT
           and plan['retry_count'] == 0 and plan['concurrency'] == 1
           and Decimal(plan['estimate']['upper_bound_usd']) == CEILING, 'APPROVED_SCOPE_MISMATCH')
    refs = plan['references']
    ensure(_file_sha(refs['collection_index_path']) == refs['collection_index_file_sha256'], 'COLLECTION_INDEX_CHANGED')
    index = read_record(refs['collection_index_path'])
    ensure(len(index['rows']) == 12 and [r['nation_id'] for r in index['rows']] == IDS
           and [r['nation_id'] for r in plan['requests']] == IDS, 'TWELVE_ORIGINAL_NATIONS_REQUIRED')
    requests, originals = [], []
    for descriptor, original in zip(plan['requests'], index['rows']):
        ensure(Path(descriptor['path']).parent.resolve() == directory.resolve(), 'REQUEST_OUTSIDE_APPROVED_DIRECTORY')
        ensure(_file_sha(descriptor['path']) == descriptor['sha256'], 'PROPOSED_REQUEST_CHANGED')
        draft = _plain(descriptor['path']); body = draft['body']
        ensure(draft['not_sent'] is True and draft['model'] == MODEL
               and _sha(body) == draft['request_sha256'], 'DRAFT_BINDING_MISMATCH')
        ensure(set(body) == {'contents', 'generationConfig'}
               and {k:v for k,v in body['generationConfig'].items() if k != 'responseJsonSchema'} == CONFIG,
               'GENERATION_CONFIG_CHANGED')
        Draft202012Validator.check_schema(body['generationConfig']['responseJsonSchema'])
        context = load_response_object(body['contents'][0]['parts'][1]['text'])
        ensure(set(context) == {'world_id', 'nation_id', 'original_nation', 'source_evidence_sha256',
                               'common_geography', 'common_asset_specifications', 'review_targets'}, 'INPUT_SCOPE_CHANGED')
        checked = verify(original['raw_directory'], expected_evidence_hash=original['verification']['evidence_hash'])
        wire = read_record(Path(original['raw_directory']) / 'RAW/generation.response.json')
        raw = base64.b64decode(wire['body_base64'], validate=True)
        ensure(hashlib.sha256(raw).hexdigest() == wire['body_sha256'], 'ORIGINAL_RESPONSE_CHANGED')
        nation = _extract_persona(load_response_object(raw.decode('utf-8')))
        ensure(nation == original['proposal'] == context['original_nation']
               and _sha(nation) == draft['original_nation_sha256']
               and nation['nation_id'] == descriptor['nation_id'] == context['nation_id']
               and nation['world_id'] == context['world_id']
               and context['source_evidence_sha256'] == checked['evidence_hash'] == draft['source_evidence_sha256']
               and _sha(context['common_geography']) == refs['map_sha256']
               and _sha(context['common_asset_specifications']) == refs['catalog_sha256'], 'ORIGINAL_INPUT_CHANGED')
        requests.append({'nation_id': nation['nation_id'], 'name': nation['name'], 'body': body,
                         'request_sha256': digest(body), 'source_evidence_hash': checked['evidence_hash'],
                         'source_raw_evidence_hash': checked['raw_evidence_hash'],
                         'source_directory': original['raw_directory'], 'original_nation_sha256': _sha(nation)})
        originals.append({'directory': original['raw_directory'], 'evidence_hash': checked['evidence_hash'],
                          'nation_id': nation['nation_id']})
    return {'proposal_plan_sha256': _file_sha(path), 'proposal_plan_path': str(path),
            'collection_index_path': refs['collection_index_path'],
            'collection_index_file_sha256': refs['collection_index_file_sha256'],
            'source_references': originals, 'requests': requests,
            'map_sha256': refs['map_sha256'], 'catalog_sha256': refs['catalog_sha256']}


def _verify_originals(plan):
    source = plan['source']
    ensure(_file_sha(source['collection_index_path']) == source['collection_index_file_sha256'], 'COLLECTION_INDEX_CHANGED')
    ensure(_file_sha(source['proposal_plan_path']) == source['proposal_plan_sha256'], 'PROPOSAL_PLAN_CHANGED')
    for ref in source['source_references']:
        verify(ref['directory'], expected_evidence_hash=ref['evidence_hash'])


def prepare(directory, *, proposal_directory):
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    directory = Path(directory)
    loaded = _load_approved_proposals(proposal_directory)
    bodies = loaded['requests']
    source = {k:v for k,v in loaded.items() if k != 'requests'}
    ensure(price(MAX_INPUT, MAX_OUTPUT) * 12 == CEILING, 'PRICE_SCOPE_CHANGED')
    with exclusive_execution(directory):
        directory.mkdir(mode=0o700)
        requests = []
        for i, approved_record in enumerate(bodies, 1):
            raw = wire_bytes(approved_record['body'])
            record = {**approved_record, 'request_wire_base64': base64.b64encode(raw).decode(),
                      'request_wire_sha256': hashlib.sha256(raw).hexdigest()}
            name = f'request-{i:02d}.json'
            Journal(directory).write(name, record)
            requests.append({'file': name, 'sha256': digest(record), 'nation_id': record['nation_id']})
        plan = {'version': VERSION, 'batch_id': 'v5-nation-addenda-' + uuid.uuid4().hex,
                'created_at': timestamp(), 'source': source, 'requests': requests,
                'approval_scope': 'Collect twelve initial-specification addendum proposals; preserve originals; no acceptance or simulation',
                'model': MODEL, 'max_generation_calls': 12, 'max_count_calls': 12,
                'max_input_tokens': MAX_INPUT, 'max_output_tokens_including_thoughts': MAX_OUTPUT,
                'usd_stop_limit': str(CEILING), 'per_attempt_reservation_usd': str(price(MAX_INPUT, MAX_OUTPUT)),
                'retry_count': 0, 'concurrency': 1, 'seed': None,
                'generation_config_without_response_schema': CONFIG,
                'price_usd_per_million': {'input': '0.75', 'generated_including_thinking': '3.75'},
                'price_source': 'https://ai.google.dev/gemini-api/docs/pricing#gemini-3.6-flash',
                'price_valid_through': '2026-12-31',
                'source_hashes': source_hashes(), 'runtime': _runtime(),
                'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                'publication': 'private_unpublished', 'assignment_eligible': False,
                'simulation_eligible': False, 'automatic_acceptance': False}
        Journal(directory).write('plan.json', plan)
        return {'status': 'prepared', 'generation_calls_max': 12, 'maximum_usd': str(CEILING), 'plan_sha256': digest(plan)}


def _request(directory, ref):
    record = Journal(directory).read(ref['file'])
    ensure(digest(record) == ref['sha256'], 'REQUEST_CHANGED')
    raw = base64.b64decode(record['request_wire_base64'], validate=True)
    body = load_response_object(raw.decode('utf-8'))
    ensure(hashlib.sha256(raw).hexdigest() == record['request_wire_sha256']
           and body == record['body'] and digest(body) == record['request_sha256']
           and wire_bytes(body) == raw, 'REQUEST_WIRE_CHANGED')
    return {**record, 'body': body}


def _plan(directory):
    directory = Path(directory)
    ensure(directory.is_dir() and not directory.is_symlink() and not directory.stat().st_mode & 0o077,
           'PRIVATE_BATCH_REQUIRED')
    plan = Journal(directory).read('plan.json')
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    ensure(plan['version'] == VERSION and plan['model'] == MODEL
           and plan['max_generation_calls'] == plan['max_count_calls'] == 12
           and plan['max_input_tokens'] == MAX_INPUT and plan['max_output_tokens_including_thoughts'] == MAX_OUTPUT
           and plan['usd_stop_limit'] == str(CEILING)
           and plan['per_attempt_reservation_usd'] == str(price(MAX_INPUT, MAX_OUTPUT))
           and plan['generation_config_without_response_schema'] == CONFIG
           and plan['retry_count'] == 0 and plan['concurrency'] == 1
           and plan['automatic_acceptance'] is False and plan['simulation_eligible'] is False
           and plan['assignment_eligible'] is False, 'PLAN_SCOPE_CHANGED')
    ensure(plan['source_hashes'] == source_hashes() and plan['runtime'] == _runtime(), 'SOURCE_OR_RUNTIME_CHANGED')
    ensure([r['nation_id'] for r in plan['requests']] == IDS, 'REQUEST_ORDER_CHANGED')
    for ref in plan['requests']:
        _request(directory, ref)
    _verify_originals(plan)
    return plan


def _history(directory, plan):
    ensure(not list(directory.glob('blocked-*.json')), 'BATCH_BLOCKED')
    roots = sorted(directory.glob('attempt-*'))
    ensure([p.name for p in roots] == [f'attempt-{i:02d}' for i in range(1, len(roots)+1)]
           and len(roots) <= 12, 'HISTORY_GAP')
    ensure({p.name for p in directory.glob('reservation-*.json')} == {f'reservation-{i:02d}.json' for i in range(1, len(roots)+1)},
           'UNSETTLED_ATTEMPT_OR_RESERVATION')
    for i, root in enumerate(roots, 1):
        check = verify(root)
        ensure(check['status'] == 'success', 'PRIOR_ATTEMPT_NOT_SUCCESSFUL')
        manifest = read_record(root/'manifest.json')
        request = _request(directory, plan['requests'][i-1])
        body = request['body']
        ensure(manifest['experiment_config']['plan_sha256'] == digest(plan)
               and manifest['experiment_config']['index'] == i
               and manifest['experiment_config']['request_sha256'] == digest(body)
               and read_record(root/'RAW/generation.request.json') == body, 'HISTORY_INPUT_CHANGED')
        ensure(base64.b64decode(read_record(root/'RAW/generation.wire.json')['body_base64'], validate=True) == wire_bytes(body), 'HISTORY_WIRE_CHANGED')
        reservation = Journal(directory).read(f'reservation-{i:02d}.json')
        ensure(reservation['index'] == i and reservation['request_sha256'] == digest(body)
               and Decimal(reservation['usd']) == price(MAX_INPUT, MAX_OUTPUT), 'RESERVATION_CHANGED')
        receipt = read_record(root/'RAW/receipt.json')['accounting']
        ensure(Decimal(receipt['estimated_cost_usd']) <= Decimal(reservation['usd']), 'HISTORY_USAGE_OVER_RESERVATION')
    return roots


def _error(exc):
    if isinstance(exc, GenerationError): return str(exc)
    if isinstance(exc, httpx.TimeoutException): return 'TRANSPORT_TIMEOUT'
    if isinstance(exc, httpx.HTTPError): return 'TRANSPORT_ERROR'
    if isinstance(exc, KeyboardInterrupt): return 'INTERRUPTED'
    if isinstance(exc, OSError): return 'LOCAL_IO_ERROR'
    return 'VALIDATION_OR_RUNTIME_ERROR'


def generate_next(directory, *, credential, transport):
    directory = Path(directory)
    ensure(isinstance(credential, str) and bool(credential.strip()), 'CREDENTIAL_REQUIRED')
    with exclusive_execution(directory):
        plan = _plan(directory)
        history = _history(directory, plan)
        index = len(history)+1
        ensure(index <= 12, 'BATCH_COMPLETE')
        request = _request(directory, plan['requests'][index-1]); body = request['body']
        maximum = price(MAX_INPUT, MAX_OUTPUT)
        reserved = sum((Decimal(Journal(directory).read(p.name)['usd']) for p in directory.glob('reservation-*.json')), Decimal(0))
        ensure(reserved+maximum <= CEILING, 'BUDGET_EXHAUSTED')
        manifest = {'format': FORMAT, 'run_id': f"{plan['batch_id']}-{index:02d}", 'started_at': timestamp(),
                    'seed': None, 'seed_scope': 'Independent addendum contexts; model seed not specified',
                    'provider': 'google-gemini-api', 'model': MODEL, 'model_version_or_digest': None,
                    'generation_config': body['generationConfig'],
                    'experiment_config': {'method': VERSION, 'stage': 'initialization_addendum_proposal',
                        'index': index, 'nation_id': request['nation_id'], 'plan_sha256': digest(plan),
                        'request_sha256': digest(body), 'original_nation_sha256': request['original_nation_sha256']},
                    'world_config': {'number_of_worlds': 1, 'nation_count': 12,
                        'map_sha256': plan['source']['map_sha256'], 'catalog_sha256': plan['source']['catalog_sha256'],
                        'state_mutation': False, 'simulation_turns_executed': 0},
                    'provenance': {'source_hashes': plan['source_hashes'], 'source_commit': plan['source_commit'],
                        'runtime': plan['runtime'], 'parent_evidence_hash': request['source_evidence_hash'],
                        'purpose': 'Collect separately generated initialization detail proposals; original facts remain unchanged'}}
        run = EvidenceRun(directory/f'attempt-{index:02d}', manifest)
        stage, attempted, actual = 'save_request', False, None
        try:
            count_body = {'generateContentRequest': {'model': 'models/'+MODEL, **body}}
            for name, payload in [('generation', body), ('count', count_body)]:
                raw = wire_bytes(payload)
                run.write(name+'.request.json', payload)
                run.write(name+'.wire.json', {'body_base64': base64.b64encode(raw).decode(), 'body_sha256': hashlib.sha256(raw).hexdigest()})
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False,
                              timeout=httpx.Timeout(180, connect=30, write=30, pool=30)) as client:
                def send(method, payload):
                    ensure(digest(_plan(directory)) == digest(plan), 'PLAN_CHANGED')
                    response = client.post(ENDPOINT+':'+method, content=wire_bytes(payload),
                        headers={'x-goog-api-key': credential, 'content-type': 'application/json'})
                    raw = response.content
                    run.write(('count' if method == 'countTokens' else 'generation')+'.response.json', {
                        'status': response.status_code, 'received_at': timestamp(),
                        'body_base64': base64.b64encode(raw).decode(), 'body_sha256': hashlib.sha256(raw).hexdigest()})
                    ensure(digest(_plan(directory)) == digest(plan), 'PLAN_CHANGED')
                    ensure(response.status_code == 200, 'COUNT_HTTP_ERROR' if method == 'countTokens' else 'GENERATION_HTTP_ERROR')
                    return load_response_object(raw.decode('utf-8'))
                stage = 'count_tokens'
                count = send('countTokens', count_body).get('totalTokens')
                ensure(type(count) is int and 0 < count <= MAX_INPUT, 'INPUT_COUNT_INVALID_OR_OVER_LIMIT')
                stage = 'reserve_generation'
                Journal(directory).write(f'reservation-{index:02d}.json', {'usd': str(maximum), 'index': index,
                    'request_sha256': digest(body), 'counted_input_tokens': count, 'reserved_at': timestamp()})
                stage = 'generate_content'; attempted = True
                response = send('generateContent', body)
            stage = 'account_usage'
            accounting = account_usage(response.get('usageMetadata')); actual = accounting['estimated_cost_usd']
            run.write('receipt.json', {'usage_metadata': response.get('usageMetadata'), 'accounting': accounting,
                'billing_verified': False, 'model_version': response.get('modelVersion'),
                'response_id': response.get('responseId'), 'reservation_usd': str(maximum)})
            ensure(accounting['input_tokens'] <= MAX_INPUT and accounting['generated_tokens_including_thoughts'] <= MAX_OUTPUT
                   and Decimal(actual) <= maximum, 'USAGE_OVER_RESERVATION')
            stage = 'validate_output'
            output = _extract_persona(response)
            validation = validate_addendum(output, body)
            result = run.finish('success', completed_turns=0)
            stage = 'save_derived'
            run.derive('output.json', {'output': output, 'raw_response_path': 'RAW/generation.response.json'})
            run.derive('validation.json', validation)
            run.derive('proposal-status.json', {'accepted_initial_nation': False, 'world_physics_approved': False,
                'raw_modified': False, 'status': 'collected_pending_bundled_review'})
            return {**result, 'index': index, 'nation_id': request['nation_id'], 'estimated_cost_usd': actual,
                    'proposal_only': True, 'accepted_initial_nation': False}
        except (Exception, KeyboardInterrupt) as exc:
            error = {'code': _error(exc), 'exception_type': type(exc).__name__, 'stage': stage, 'generation_attempted': attempted}
            if not (run.root/'terminal.json').exists():
                run.write('error.json', error)
                run.finish('interrupted' if isinstance(exc, KeyboardInterrupt) else 'failure', completed_turns=0, error=error)
            Journal(directory).write(f'blocked-{index:02d}.json', error)
            return {'status': 'failure', 'index': index, 'nation_id': request['nation_id'],
                    'error': error, 'estimated_cost_usd': actual}
