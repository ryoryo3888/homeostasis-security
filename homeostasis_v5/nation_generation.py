"""Approved, serial nation initialization; immutable attempts and no retries.

Preparation is offline. Each call sends at most one count and one generation.
A successful response is still a proposal until its separate content review.
No simulation, resource effects, publishing, or persona generation exists here.
"""
from __future__ import annotations
import base64
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import uuid
import httpx

from homeostasis_core.execution_lock import exclusive_execution
from homeostasis_v3.contracts import digest
from homeostasis_v4.evidence import EvidenceRun, FORMAT, read_record, timestamp, verify
from homeostasis_v5.nation_generation_contract import (
    build_map_request, build_nation_request, record_hash, schema_for,
    inspect_map_output, inspect_nation_output, NationContractError,
)
from homeostasis_v5.persona_generation import GenerationError, account_usage, _extract_persona, _runtime, price
from homeostasis_v5.life_first_generation import wire_bytes
from model_response_json import load_response_object
from v2_autonomous import Journal

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gemini-3.6-flash'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/' + MODEL
VERSION = 'v5-nation-initialization-1'
LIMITS = {'map': {'input': 12000, 'output': 12288}, 'nation': {'input': 64000, 'output': 16384}}
CEILING = Decimal('1.50')
IDS = [f'nation-{n:03d}' for n in range(1, 13)]


def ensure(condition, code):
    if not condition:
        raise GenerationError(code)


def source_hashes():
    names = ('homeostasis_v5/nation_generation.py', 'homeostasis_v5/nation_generation_contract.py',
             'homeostasis_v5/nation_geometry.py', 'homeostasis_v5/nation_valuation.py',
             'homeostasis_v5/life_first_generation.py', 'homeostasis_v5/persona_generation.py',
             'homeostasis_core/execution_lock.py', 'homeostasis_v4/evidence.py',
             'homeostasis_v3/contracts.py', 'model_response_json.py', 'v2_autonomous.py', 'v2_dialogue.py',
             'tools/generate_v5_nations.py')
    return {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in names}


def provider_schema(value):
    """Use a singleton enum for const; preserve the full local contract otherwise."""
    if isinstance(value, list):
        return [provider_schema(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: provider_schema(v) for k, v in value.items() if k != "const"}
    if "const" in value:
        fixed = value["const"]
        ensure(isinstance(fixed, str), "UNSUPPORTED_SCHEMA_CONSTANT")
        result.update(type="string", enum=[fixed])
    return result


def http_body(package):
    """Explicit adapter; no offline flags or approval records become API fields."""
    stage = package['stage']
    ensure(stage in LIMITS, 'INVALID_STAGE')
    return {'contents': [{'role': 'user', 'parts': [
        {'text': package['prompt']},
        {'text': json.dumps(package['context'], ensure_ascii=False, separators=(',', ':'))}]}],
        'generationConfig': {'responseMimeType': 'application/json',
                             'responseJsonSchema': provider_schema(package['response_schema']),
                             'temperature': 1.0, 'candidateCount': 1,
                             'maxOutputTokens': LIMITS[stage]['output'],
                             'thinkingConfig': {'thinkingLevel': 'LOW', 'includeThoughts': False}}}


def permutation(seed, leader_ids):
    """Versioned Fisher-Yates; SHA256 stream with rejection avoids modulo bias."""
    values = list(leader_ids)
    counter = 0
    key = bytes.fromhex(seed)
    ensure(len(key) == 32 and len(values) == 12 and len(set(values)) == 12, 'INVALID_ASSIGNMENT_INPUT')
    for i in range(len(values) - 1, 0, -1):
        bound = i + 1
        ceiling = (1 << 256) - (1 << 256) % bound
        while True:
            value = int.from_bytes(hashlib.sha256(key + counter.to_bytes(8, 'big')).digest(), 'big')
            counter += 1
            if value < ceiling:
                break
        j = value % bound
        values[i], values[j] = values[j], values[i]
    return values


def prepare(directory, *, catalog, leader_references, reference_archive):
    from jsonschema import Draft202012Validator
    Draft202012Validator(schema_for('catalog')).validate(catalog)
    ensure(len(leader_references) == 12 and len({r['leader_id'] for r in leader_references}) == 12,
           'TWELVE_FROZEN_LEADER_REFERENCES_REQUIRED')
    directory = Path(directory)
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    with exclusive_execution(directory):
        ensure(not directory.exists() and not directory.is_symlink(), 'NEW_BATCH_REQUIRED')
        total = price(**{'input_tokens':12000, 'output_tokens':12288}) + 12 * price(64000,16384)
        ensure(total <= CEILING, 'BUDGET_NOT_SUFFICIENT')
        plan = {'version': VERSION, 'batch_id': 'v5-nations-' + uuid.uuid4().hex,
                'created_at': timestamp(), 'world_id': 'v5-world-' + uuid.uuid4().hex,
                'nation_ids': IDS, 'model': MODEL, 'limits': LIMITS, 'usd_stop_limit': str(CEILING),
                'maximum_reserved_usd': str(total), 'max_generation_calls': 13, 'max_count_calls': 13,
                'retry_count': 0, 'concurrency': 1, 'valuation': 'V-A-new-equivalent-full-specification',
                'source_hashes': source_hashes(), 'runtime': _runtime(),
                'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                'catalog_sha256': record_hash(catalog), 'reference_archive': reference_archive,
                'leader_references': leader_references,
                'assignment': {'method':'sha256-rejection-fisher-yates-1','seed_hex':secrets.token_hex(32),
                               'leader_id_order':[r['leader_id'] for r in leader_references], 'nation_id_order':IDS},
                'pricing':{'input_usd_per_million':'0.75','output_usd_per_million':'3.75',
                           'valid_through':'2026-12-31','tier':'standard_default'},
                'conditions':{'worlds':1,'nations':12,'leaders_per_nation':1,'future_turns':3,
                              'future_days_per_turn':30,'persona_context_supplied':False,
                              'previous_nation_context_supplied':False,'simulation_started':False,
                              'free_proposals':'preserve_and_stop_if_unresolved',
                              'physical_effects':'not_inferred_from_generation_or_price'},
                'publication':'private_unpublished'}
        directory.mkdir(mode=0o700)
        Journal(directory).write('catalog.json',catalog)
        Journal(directory).write('plan.json',plan)
        return {'status':'prepared','plan_sha256':digest(plan),'maximum_reserved_usd':str(total)}


def _plan(directory):
    ensure(not directory.is_symlink() and directory.is_dir() and not directory.stat().st_mode & 0o077,
           'PRIVATE_BATCH_REQUIRED')
    plan = Journal(directory).read('plan.json')
    ensure(date.today() <= date(2026,12,31), 'PRICE_WINDOW_EXPIRED')
    ensure(plan['version']==VERSION and plan['model']==MODEL and plan['limits']==LIMITS
           and plan['usd_stop_limit']==str(CEILING) and plan['nation_ids']==IDS
           and plan['max_generation_calls']==13 and plan['max_count_calls']==13
           and plan['retry_count']==0 and plan['concurrency']==1, 'PLAN_SCOPE_CHANGED')
    ensure(plan['source_hashes']==source_hashes() and plan['runtime']==_runtime(), 'SOURCE_OR_RUNTIME_CHANGED')
    ensure(record_hash(Journal(directory).read('catalog.json'))==plan['catalog_sha256'], 'CATALOG_CHANGED')
    return plan


def _output(root):
    wire=read_record(root/'RAW/generation.response.json')
    raw=base64.b64decode(wire['body_base64'],validate=True)
    ensure(wire['status']==200 and hashlib.sha256(raw).hexdigest()==wire['body_sha256'],'RESPONSE_BYTES_CHANGED')
    return _extract_persona(load_response_object(raw.decode('utf-8')))


def _package(directory, plan, index):
    if index==1:
        return build_map_request(plan['world_id'],IDS)
    m=_output(directory/'attempt-01')
    c=Journal(directory).read('catalog.json')
    return build_nation_request(m,IDS[index-2],c,expected_map_hash=record_hash(m),expected_catalog_hash=plan['catalog_sha256'])


def _history(directory, plan, *, allow_unreviewed=False):
    ensure(not list(directory.glob('blocked-*.json')), 'BATCH_BLOCKED')
    result=[]
    for i in range(1,14):
        root=directory/f'attempt-{i:02d}'
        if not root.exists():
            ensure(not any((directory/f'attempt-{j:02d}').exists() for j in range(i+1,14)),'HISTORY_GAP')
            break
        verified=verify(root)
        ensure(verified['status']=='success','PRIOR_ATTEMPT_NOT_SUCCESSFUL')
        manifest=read_record(root/'manifest.json')
        ensure(manifest['experiment_config']['plan_sha256']==digest(plan),'PRIOR_PLAN_MISMATCH')
        body=http_body(_package(directory,plan,i))
        ensure(read_record(root/'RAW/generation.request.json')==body,'PRIOR_INPUT_CHANGED')
        wire=read_record(root/'RAW/generation.wire.json')
        ensure(base64.b64decode(wire['body_base64'],validate=True)==wire_bytes(body),'PRIOR_WIRE_CHANGED')
        review=root/'DERIVED/content-review.json'
        if review.exists():
            report=read_record(review)['report']
            ensure(report['accepted'] is True and report['evidence_hash']==verified['evidence_hash'], 'CONTENT_REVIEW_REJECTED')
        else:
            ensure(allow_unreviewed and not (directory/f'attempt-{i+1:02d}').exists(),'CONTENT_REVIEW_REQUIRED')
        result.append({'index':i,'root':root,'verification':verified})
    return result


def _error(exc):
    if isinstance(exc,(GenerationError,NationContractError)):
        return str(exc)
    if isinstance(exc,httpx.TimeoutException):return 'TRANSPORT_TIMEOUT'
    if isinstance(exc,httpx.HTTPError):return 'TRANSPORT_ERROR'
    if isinstance(exc,KeyboardInterrupt):return 'INTERRUPTED'
    if isinstance(exc,OSError):return 'LOCAL_IO_ERROR'
    return 'VALIDATION_OR_RUNTIME_ERROR'


def generate_next(directory, *, credential, transport):
    directory=Path(directory)
    ensure(isinstance(credential,str) and bool(credential.strip()),'CREDENTIAL_REQUIRED')
    with exclusive_execution(directory):
        plan=_plan(directory)
        history=_history(directory,plan)
        index=len(history)+1
        ensure(index<=13,'BATCH_COMPLETE')
        package=_package(directory,plan,index)
        body=http_body(package)
        stage_name=package['stage']
        maximum=price(LIMITS[stage_name]['input'],LIMITS[stage_name]['output'])
        reserved=sum((Decimal(read_record(p)['usd']) for p in directory.glob('reservation-*.json')),Decimal(0))
        ensure(reserved+maximum<=CEILING,'BUDGET_EXHAUSTED')
        ensure(not (directory/f'reservation-{index:02d}.json').exists(),'UNRESOLVED_RESERVATION')
        manifest={'format':FORMAT,'run_id':f"{plan['batch_id']}-{index:02d}",'started_at':timestamp(),
                  'seed':None,'seed_scope':'Unspecified model seed; separate generation contexts',
                  'provider':'google-gemini-api','model':MODEL,'model_version_or_digest':None,
                  'generation_config':body['generationConfig'],
                  'experiment_config':{'method':VERSION,'stage':stage_name,'index':index,
                                       'plan_sha256':digest(plan),'request_sha256':digest(body)},
                  'world_config':plan['conditions'],
                  'provenance':{'source_hashes':plan['source_hashes'],'source_commit':plan['source_commit'],
                                'runtime':plan['runtime'],'parent_evidence_hash':history[0]['verification']['evidence_hash'] if history else None,
                                'purpose':'Preserve generated geography or one independently initialized nation'}}
        run=EvidenceRun(directory/f'attempt-{index:02d}',manifest)
        stage='save_request';attempted=False;actual=None
        try:
            count_body={'generateContentRequest':{'model':'models/'+MODEL,**body}}
            run.write('offline-package.json',package)
            for name,payload in [('generation',body),('count',count_body)]:
                raw=wire_bytes(payload)
                run.write(name+'.request.json',payload)
                run.write(name+'.wire.json',{'body_base64':base64.b64encode(raw).decode(),'body_sha256':hashlib.sha256(raw).hexdigest()})
            with httpx.Client(transport=transport,trust_env=False,follow_redirects=False,
                              timeout=httpx.Timeout(180,connect=30,write=30,pool=30)) as client:
                def send(method,payload):
                    ensure(digest(_plan(directory))==digest(plan),'PLAN_CHANGED')
                    response=client.post(ENDPOINT+':'+method,content=wire_bytes(payload),
                                         headers={'x-goog-api-key':credential,'content-type':'application/json'})
                    raw=response.content
                    run.write(('count' if method=='countTokens' else 'generation')+'.response.json',{
                        'status':response.status_code,'received_at':timestamp(),
                        'body_base64':base64.b64encode(raw).decode(),'body_sha256':hashlib.sha256(raw).hexdigest()})
                    ensure(digest(_plan(directory))==digest(plan),'PLAN_CHANGED')
                    ensure(response.status_code==200,'COUNT_HTTP_ERROR' if method=='countTokens' else 'GENERATION_HTTP_ERROR')
                    return load_response_object(raw.decode('utf-8'))
                stage='count_tokens'
                count=send('countTokens',count_body).get('totalTokens')
                ensure(type(count) is int and 0<count<=LIMITS[stage_name]['input'],'INPUT_COUNT_INVALID_OR_OVER_LIMIT')
                stage='reserve_generation'
                Journal(directory).write(f'reservation-{index:02d}.json',{'usd':str(maximum),'index':index,
                    'request_sha256':digest(body),'counted_input_tokens':count,'reserved_at':timestamp()})
                stage='generate_content';attempted=True
                response=send('generateContent',body)
            stage='account_usage'
            accounting=account_usage(response.get('usageMetadata'));actual=accounting['estimated_cost_usd']
            run.write('receipt.json',{'usage_metadata':response.get('usageMetadata'),'accounting':accounting,
                                    'billing_verified':False,'model_version':response.get('modelVersion'),
                                    'response_id':response.get('responseId'),'reservation_usd':str(maximum)})
            ensure(accounting['input_tokens']<=LIMITS[stage_name]['input'] and
                   accounting['generated_tokens_including_thoughts']<=LIMITS[stage_name]['output'] and
                   Decimal(actual)<=maximum,'USAGE_OVER_RESERVATION')
            stage='validate_output'
            output=_extract_persona(response)
            if index==1:
                validation=inspect_map_output(output,expected_world_id=plan['world_id'],expected_nation_ids=IDS)
            else:
                validation=inspect_nation_output(output,package)
            # Success means the generation completed; final world acceptance remains separate.
            result=run.finish('success',completed_turns=0)
            stage='save_derived'
            run.derive('output.json',{'output':output,'raw_response_path':'RAW/generation.response.json'})
            run.derive('structural-validation.json',validation)
            return {**result,'index':index,'stage':stage_name,'estimated_cost_usd':actual,'content_review_required':True}
        except (Exception,KeyboardInterrupt) as exc:
            error={'code':_error(exc),'exception_type':type(exc).__name__,'stage':stage,'generation_attempted':attempted}
            if not (run.root/'terminal.json').exists():
                run.write('error.json',error)
                run.finish('interrupted' if isinstance(exc,KeyboardInterrupt) else 'failure',completed_turns=0,error=error)
            Journal(directory).write(f'blocked-{index:02d}.json',error)
            return {'status':'failure','index':index,'error':error,'estimated_cost_usd':actual}


def review_last(directory, *, accepted, review_notes, balance_review_notes=None):
    """Human-assisted content gate: mechanical checks cannot grant semantic approval."""
    directory=Path(directory)
    with exclusive_execution(directory):
        plan=_plan(directory);history=_history(directory,plan,allow_unreviewed=True)
        ensure(bool(history),'NO_GENERATION')
        last=history[-1];root=last['root'];index=last['index'];output=_output(root)
        ensure(not (root/'DERIVED/content-review.json').exists(),'ALREADY_REVIEWED')
        ensure(type(accepted) is bool and isinstance(review_notes,list) and review_notes,'REVIEW_REQUIRED')
        if accepted:
            if index==1:
                from homeostasis_v5.nation_geometry import derive_geometry
                check=derive_geometry(output)
                ensure(check['accepted_for_nation_context'],'GEOMETRY_NOT_ACCEPTED')
            else:
                from homeostasis_v5.nation_valuation import evaluate_initial_holdings
                check=evaluate_initial_holdings(output,Journal(directory).read('catalog.json'))
                ensure(check['accepted_initial_accounting'],'VALUATION_UNRESOLVED')
                if check['requires_manual_balance_review']:
                    ensure(isinstance(balance_review_notes, str) and bool(balance_review_notes.strip()),
                           'EXPLICIT_BALANCE_REVIEW_REQUIRED')
                    check['manual_balance_review'] = {
                        'notes':balance_review_notes,
                        'canonical_balance':'exact_retained_points in DERIVED',
                        'raw_reported_value_modified':False}
            evidence=object.__new__(EvidenceRun);evidence.root=root
            evidence.derive('initialization-check.json',check)
        evidence=object.__new__(EvidenceRun);evidence.root=root
        evidence.derive('content-review.json',{'accepted':accepted,'notes':review_notes,
                                             'evidence_hash':last['verification']['evidence_hash'],
                                             'simulation_physics_approved':False})
        if not accepted:
            Journal(directory).write(f'blocked-{index:02d}.json',{'code':'CONTENT_REVIEW_REJECTED','generation_attempted':False})
        if accepted and index==13:
            assignment=permutation(plan['assignment']['seed_hex'],plan['assignment']['leader_id_order'])
            Journal(directory).write('assignment.json',{'plan_sha256':digest(plan),
                'method':plan['assignment'],'pairs':[{'nation_id':n,'leader_id':l} for n,l in zip(IDS,assignment)],
                'diplomatic_pairing':False,'simulation_started':False})
        return {'status':'reviewed' if accepted else 'blocked','index':index,'accepted':accepted}
