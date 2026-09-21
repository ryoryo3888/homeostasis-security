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
from homeostasis_v5.nation_topology import build_topology_request, compile_topology, TopologyError
from model_response_json import load_response_object
from v2_autonomous import Journal

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gemini-3.6-flash'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/' + MODEL
VERSION = 'v5-nation-initialization-6-proposal-collection'
LIMITS = {'map': {'input': 12000, 'output': 12288}, 'nation': {'input': 64000, 'output': 16384}}
CEILING = Decimal('1.50')
IDS = [f'nation-{n:03d}' for n in range(1, 13)]


def ensure(condition, code):
    if not condition:
        raise GenerationError(code)


def source_hashes():
    names = ('homeostasis_v5/nation_generation.py', 'homeostasis_v5/nation_generation_contract.py',
             'homeostasis_v5/nation_geometry.py', 'homeostasis_v5/nation_valuation.py', 'homeostasis_v5/nation_topology.py',
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
    context=dict(package['context'])
    prompt=package['prompt']
    schema=provider_schema(package['response_schema'])
    if stage=='nation':
        references=dict(package['input_references'])
        ensure(set(references)=={'map_sha256','catalog_sha256'},'REFERENCE_BINDING_REQUIRED')
        context['input_references']=references
        schema['properties']['geography_ref']['properties']['map_sha256']['enum']=[references['map_sha256']]
        prompt+='\ngeography_ref.map_sha256にはinput_references.map_sha256をそのまま転記してください。識別値を新しく生成・推測・再計算しません。'
    return {'contents': [{'role': 'user', 'parts': [
        {'text': prompt},
        {'text': json.dumps(context, ensure_ascii=False, separators=(',', ':'))}]}],
        'generationConfig': {'responseMimeType': 'application/json',
                             'responseJsonSchema': schema,
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


def prepare(directory, *, catalog, leader_references, reference_archive, predecessor=None):
    from jsonschema import Draft202012Validator
    Draft202012Validator(schema_for('catalog')).validate(catalog)
    ensure(len(leader_references) == 12 and len({r['leader_id'] for r in leader_references}) == 12,
           'TWELVE_FROZEN_LEADER_REFERENCES_REQUIRED')
    directory = Path(directory)
    ensure(date.today() <= date(2026, 12, 31), 'PRICE_WINDOW_EXPIRED')
    prior = _predecessor(predecessor, catalog, leader_references) if predecessor is not None else None
    with exclusive_execution(directory):
        ensure(not directory.exists() and not directory.is_symlink(), 'NEW_BATCH_REQUIRED')
        total = price(**{'input_tokens':12000, 'output_tokens':12288}) + 12 * price(64000,16384)
        ensure(total + Decimal(prior['reserved_usd'] if prior else '0') <= CEILING, 'BUDGET_NOT_SUFFICIENT')
        plan = {'version': VERSION, 'batch_id': 'v5-nations-' + uuid.uuid4().hex,
                'created_at': timestamp(), 'world_id': 'v5-world-' + uuid.uuid4().hex,
                'nation_ids': IDS, 'model': MODEL, 'limits': LIMITS, 'usd_stop_limit': str(CEILING),
                'maximum_reserved_usd': str(total), 'max_generation_calls': 13, 'max_count_calls': 13,
                'retry_count': 0, 'concurrency': 1, 'predecessor':prior,
                'map_method':'shared-boundaries-v2-complete-slots', 'valuation': 'V-A-new-equivalent-full-specification',
                'source_hashes': source_hashes(), 'runtime': _runtime(),
                'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                'catalog_sha256': record_hash(catalog), 'reference_archive': reference_archive,
                'leader_references': leader_references,
                'assignment': prior['assignment'] if prior else {'method':'sha256-rejection-fisher-yates-1','seed_hex':secrets.token_hex(32),
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



def _predecessor(directory, catalog, leader_references):
    """Verify the two known stopped map trials; never reopen or edit them."""
    directory=Path(directory)
    plan=read_record(directory/'plan.json')
    previous_version=plan['version']
    ensure(previous_version in ('v5-nation-initialization-1','v5-nation-initialization-2-shared-boundaries'),
           'UNSUPPORTED_PREDECESSOR')
    ensure(len(list(directory.glob('attempt-*')))==1 and (directory/'blocked-01.json').exists(),
           'PREDECESSOR_MUST_BE_STOPPED_AFTER_MAP')
    ensure(not (directory/'assignment.json').exists(),'PREDECESSOR_ASSIGNMENT_ALREADY_USED')
    evidence=verify(directory/'attempt-01')
    if previous_version=='v5-nation-initialization-1':
        ensure(evidence['status']=='success','PREDECESSOR_RESPONSE_INCOMPLETE')
        review=read_record(directory/'attempt-01/DERIVED/content-review.json')['report']
        ensure(review['accepted'] is False and review['evidence_hash']==evidence['evidence_hash'],
               'PREDECESSOR_REJECTION_NOT_VERIFIED')
    else:
        ensure(evidence['status']=='failure','PREDECESSOR_FAILURE_REQUIRED')
        error=read_record(directory/'attempt-01/RAW/error.json')
        ensure(error['code']=='COMPILED_MAP_GEOMETRY_REJECTED' and error['stage']=='validate_output',
               'UNSUPPORTED_PREDECESSOR_FAILURE')
        report=read_record(directory/'attempt-01/DERIVED/topology-validation-failure.json')['report']
        ensure(bool(report['stop_reasons']) and all(r['code']=='EMPTY_TERRITORY_REQUIRES_CONTENT_REVIEW'
               for r in report['stop_reasons']),'UNSUPPORTED_PREDECESSOR_FAILURE')
        ensure(plan.get('predecessor') is not None,'ORIGINAL_TRIAL_REFERENCE_REQUIRED')
    ensure(record_hash(catalog)==plan['catalog_sha256']
           and leader_references==plan['leader_references'],'PREDECESSOR_FIXED_INPUTS_CHANGED')
    reservation=read_record(directory/'reservation-01.json')
    ensure(Decimal(reservation['usd'])==price(12000,12288),'PREDECESSOR_RESERVATION_CHANGED')
    accumulated=Decimal(reservation['usd'])
    if plan.get('predecessor'):
        ancestor=_predecessor(plan['predecessor']['directory'],catalog,leader_references)
        ensure(ancestor==plan['predecessor'],'PREDECESSOR_ANCESTOR_CHANGED')
        accumulated+=Decimal(ancestor['reserved_usd'])
    receipt=read_record(directory/'attempt-01/RAW/receipt.json')
    return {'directory':str(directory),'plan_sha256':digest(plan),
            'evidence_hash':evidence['evidence_hash'],'reserved_usd':str(accumulated),
            'reported_cost_usd':receipt['accounting']['estimated_cost_usd'],
            'assignment':plan['assignment'],'reason':'Authorized separate trial with shared boundary representation'}


def _frozen_source(directory):
    """Read-only import of the accepted map and the diagnosed failed request.

    Completed responses with verified usage settle their reservation at the
    reported estimate. Unknown/incomplete costs keep their full reservation.
    Every original reservation, receipt and RAW remains immutable.
    """
    directory=Path(directory)
    plan=read_record(directory/'plan.json')
    ensure(plan['version']=='v5-nation-initialization-3-complete-map', 'UNSUPPORTED_FROZEN_SOURCE')
    ensure({p.name for p in directory.glob('attempt-*')}=={'attempt-01','attempt-02'}
           and (directory/'blocked-02.json').exists() and not (directory/'assignment.json').exists(),
           'FROZEN_SOURCE_SCOPE_CHANGED')
    ensure({p.name for p in directory.glob('reservation-*.json')}=={'reservation-01.json','reservation-02.json'},
           'FROZEN_RESERVATION_SET_CHANGED')
    for index,stage in ((1,'map'),(2,'nation')):
        root=directory/f'attempt-{index:02d}'
        manifest=read_record(root/'manifest.json')
        request=read_record(root/'RAW/generation.request.json')
        reservation=read_record(directory/f'reservation-{index:02d}.json')
        ensure(manifest['experiment_config']['plan_sha256']==digest(plan)
               and manifest['experiment_config']['index']==index
               and manifest['experiment_config']['stage']==stage
               and manifest['experiment_config']['request_sha256']==digest(request),
               'FROZEN_MANIFEST_PLAN_MISMATCH')
        ensure(reservation['index']==index and reservation['request_sha256']==digest(request)
               and Decimal(reservation['usd'])==price(LIMITS[stage]['input'],LIMITS[stage]['output']),
               'FROZEN_RESERVATION_CHANGED')
    map_evidence=verify(directory/'attempt-01')
    failed_evidence=verify(directory/'attempt-02')
    ensure(map_evidence['status']=='success' and failed_evidence['status']=='failure','FROZEN_SOURCE_STATUS_CHANGED')
    review=read_record(directory/'attempt-01/DERIVED/content-review.json')['report']
    ensure(review['accepted'] is True and review['evidence_hash']==map_evidence['evidence_hash'],
           'FROZEN_MAP_NOT_ACCEPTED')
    failure=read_record(directory/'attempt-02/RAW/error.json')
    ensure(failure['code']=='MAP_REFERENCE_MISMATCH' and failure['stage']=='validate_output',
           'UNSUPPORTED_FROZEN_FAILURE')
    geography=_map_output(directory/'attempt-01',plan)
    catalog=read_record(directory/'catalog.json')
    ensure(record_hash(catalog)==plan['catalog_sha256'],'FROZEN_CATALOG_CHANGED')
    ensure(plan.get('predecessor') is not None,'FROZEN_ANCESTRY_REQUIRED')
    ensure(_predecessor(plan['predecessor']['directory'],catalog,plan['leader_references'])==plan['predecessor'],
           'FROZEN_ANCESTRY_CHANGED')
    # Independently verify the adapter failure before permitting its retry.
    failed_package=read_record(directory/'attempt-02/RAW/offline-package.json')
    map_hash=record_hash(geography)
    ensure(failed_package['input_references']['map_sha256']==map_hash
           and map_hash not in json.dumps(read_record(directory/'attempt-02/RAW/generation.request.json')),
           'FROZEN_ADAPTER_DIAGNOSIS_CHANGED')
    ledger=[]
    cursor=directory
    visited=set()
    while cursor is not None:
        ensure(str(cursor.resolve()) not in visited,'FROZEN_ANCESTRY_CYCLE')
        visited.add(str(cursor.resolve()))
        current=read_record(cursor/'plan.json')
        for reservation_path in sorted(cursor.glob('reservation-*.json')):
            reservation=read_record(reservation_path)
            evidence_root=cursor/f"attempt-{reservation['index']:02d}"
            evidence=verify(evidence_root)
            maximum=Decimal(reservation['usd'])
            receipt_path=evidence_root/'RAW/receipt.json'
            charge=maximum;basis='unsettled_full_reservation'
            if evidence['completion_record_present'] and receipt_path.exists():
                receipt=read_record(receipt_path)
                wire=read_record(evidence_root/'RAW/generation.response.json')
                raw=base64.b64decode(wire['body_base64'],validate=True)
                ensure(wire['status']==200 and hashlib.sha256(raw).hexdigest()==wire['body_sha256'],
                       'FROZEN_USAGE_RESPONSE_CHANGED')
                response=load_response_object(raw.decode('utf-8'))
                accounting=account_usage(response.get('usageMetadata'))
                ensure(receipt['accounting']==accounting,'FROZEN_USAGE_RECEIPT_CHANGED')
                charge=Decimal(accounting['estimated_cost_usd'])
                ensure(charge<=maximum,'FROZEN_USAGE_EXCEEDED_RESERVATION')
                basis='verified_response_usage_estimate_not_invoice'
            ledger.append({'directory':str(evidence_root),'evidence_hash':evidence['evidence_hash'],
                           'original_reservation_usd':str(maximum),'charged_usd':str(charge),'basis':basis})
        parent=current.get('predecessor')
        cursor=Path(parent['directory']) if parent else None
    return {'directory':str(directory),'plan_sha256':digest(plan),'world_id':plan['world_id'],
            'map_evidence_hash':map_evidence['evidence_hash'],'failed_nation_evidence_hash':failed_evidence['evidence_hash'],
            'map_sha256':map_hash,'content_review_sha256':digest(review),'catalog_sha256':plan['catalog_sha256'],
            'assignment':plan['assignment'],'leader_references':plan['leader_references'],
            'reference_archive':plan['reference_archive'],'ledger':ledger,
            'charged_usd':str(sum((Decimal(x['charged_usd']) for x in ledger),Decimal(0)))}


def prepare_continuation(directory, *, frozen_source):
    """Create a new nation-only batch; never regenerate/import RAW as a new call."""
    source=_frozen_source(frozen_source)
    prior_plan=read_record(Path(frozen_source)/'plan.json')
    directory=Path(directory)
    with exclusive_execution(directory):
        ensure(not directory.exists() and not directory.is_symlink(),'NEW_BATCH_REQUIRED')
        ensure(date.today()<=date(2026,12,31),'PRICE_WINDOW_EXPIRED')
        maximum=12*price(LIMITS['nation']['input'],LIMITS['nation']['output'])
        ensure(maximum+Decimal(source['charged_usd'])<=CEILING,'BUDGET_NOT_SUFFICIENT')
        plan={**prior_plan,'version':VERSION,'batch_id':'v5-nations-'+uuid.uuid4().hex,
              'created_at':timestamp(),'maximum_reserved_usd':str(maximum),
              'max_generation_calls':12,'max_count_calls':12,'predecessor':None,'frozen_source':source,
              'source_hashes':source_hashes(),'runtime':_runtime(),
              'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'continuation':'nation-initialization-after-reference-adapter-fix',
              'prior_cost_basis':'verified_response_usage_or_unsettled_reservation'}
        ensure(plan['model']==MODEL and plan['limits']==LIMITS and plan['usd_stop_limit']==str(CEILING)
               and plan['nation_ids']==IDS and plan['retry_count']==0 and plan['concurrency']==1,
               'FROZEN_GENERATION_CONDITIONS_CHANGED')
        directory.mkdir(mode=0o700)
        Journal(directory).write('catalog.json',read_record(Path(frozen_source)/'catalog.json'))
        Journal(directory).write('plan.json',plan)
        return {'status':'prepared','plan_sha256':digest(plan),'maximum_reserved_usd':str(maximum),
                'prior_charged_usd':source['charged_usd'],'map_generation_calls':0}


def _collection_source(directory):
    """Import one unaccepted proposal; do not undo its earlier stop record."""
    directory=Path(directory)
    plan=read_record(directory/'plan.json')
    ensure(plan['version']=='v5-nation-initialization-5-frozen-map-continuation',
           'UNSUPPORTED_COLLECTION_SOURCE')
    ensure({p.name for p in directory.glob('attempt-*')}=={'attempt-02'}
           and {p.name for p in directory.glob('reservation-*.json')}=={'reservation-02.json'}
           and not (directory/'assignment.json').exists(),'COLLECTION_SOURCE_SCOPE_CHANGED')
    frozen=_frozen_source(plan['frozen_source']['directory'])
    ensure(frozen==plan['frozen_source'],'COLLECTION_MAP_SOURCE_CHANGED')
    ensure(plan['world_id']==frozen['world_id'] and plan['catalog_sha256']==frozen['catalog_sha256']
           and plan['assignment']==frozen['assignment'] and plan['leader_references']==frozen['leader_references'],
           'COLLECTION_FIXED_INPUTS_CHANGED')
    catalog=read_record(directory/'catalog.json')
    ensure(record_hash(catalog)==plan['catalog_sha256'],'COLLECTION_CATALOG_CHANGED')
    root=directory/'attempt-02'
    evidence=verify(root)
    ensure(evidence['status']=='success','COLLECTION_PROPOSAL_NOT_COMPLETE')
    manifest=read_record(root/'manifest.json')
    package=_package(directory,plan,2)
    body=http_body(package)
    ensure(manifest['experiment_config']['plan_sha256']==digest(plan)
           and manifest['experiment_config']['index']==2
           and manifest['experiment_config']['stage']=='nation'
           and manifest['experiment_config']['request_sha256']==digest(body),
           'COLLECTION_MANIFEST_MISMATCH')
    ensure(read_record(root/'RAW/generation.request.json')==body
           and base64.b64decode(read_record(root/'RAW/generation.wire.json')['body_base64'],validate=True)==wire_bytes(body),
           'COLLECTION_REQUEST_CHANGED')
    inspect_nation_output(_output(root),package)
    reservation=read_record(directory/'reservation-02.json')
    ensure(reservation['index']==2 and reservation['request_sha256']==digest(body)
           and Decimal(reservation['usd'])==price(64000,16384),'COLLECTION_RESERVATION_CHANGED')
    review=read_record(root/'DERIVED/content-review.json')['report']
    ensure(review['accepted'] is False and review['evidence_hash']==evidence['evidence_hash']
           and read_record(directory/'blocked-02.json')['code']=='CONTENT_REVIEW_REJECTED',
           'COLLECTION_SOURCE_REVIEW_CHANGED')
    receipt=read_record(root/'RAW/receipt.json')
    wire=read_record(root/'RAW/generation.response.json')
    response=load_response_object(base64.b64decode(wire['body_base64'],validate=True).decode('utf-8'))
    accounting=account_usage(response.get('usageMetadata'))
    ensure(receipt['accounting']==accounting
           and Decimal(accounting['estimated_cost_usd'])<=Decimal(reservation['usd']),
           'COLLECTION_USAGE_CHANGED')
    return {'directory':str(directory),'plan_sha256':digest(plan),
            'proposal_directory':str(root),'nation_id':IDS[0],
            'proposal_evidence_hash':evidence['evidence_hash'],
            'content_review_sha256':digest(review),'charged_usd':accounting['estimated_cost_usd'],
            'original_reservation_usd':reservation['usd'],
            'proposal_status':'unaccepted_original_proposal','reroll':False}


def prepare_collection(directory, *, proposal_source):
    """Option 1: collect the remaining eleven proposals before content review."""
    source=_collection_source(proposal_source)
    prior=read_record(Path(proposal_source)/'plan.json')
    directory=Path(directory)
    with exclusive_execution(directory):
        ensure(not directory.exists() and not directory.is_symlink(),'NEW_BATCH_REQUIRED')
        ensure(date.today()<=date(2026,12,31),'PRICE_WINDOW_EXPIRED')
        maximum=11*price(LIMITS['nation']['input'],LIMITS['nation']['output'])
        already=Decimal(prior['frozen_source']['charged_usd'])+Decimal(source['charged_usd'])
        ensure(maximum+already<=CEILING,'BUDGET_NOT_SUFFICIENT')
        plan={**prior,'version':VERSION,'batch_id':'v5-nations-'+uuid.uuid4().hex,
              'created_at':timestamp(),'maximum_reserved_usd':str(maximum),
              'max_generation_calls':11,'max_count_calls':11,'collection_source':source,
              'source_hashes':source_hashes(),'runtime':_runtime(),
              'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'continuation':'collect-remaining-proposals-before-bundled-review',
              'collection_policy':{'version':'proposal-collection-1','target_proposals':12,
                  'imported_proposals':1,'new_proposals':11,'defer_content_acceptance':True,
                  'unresolved_assets':'preserve_for_bundled_review','balance_errors':'derive_without_rewriting_raw',
                  'technical_errors':'preserve_and_stop','assignment_eligible':False,
                  'simulation_eligible':False,'supplemental_generation_authorized':False,
                  'catalog_stop_rule_scope':'stop_acceptance_and_physical_use_not_proposal_collection'},
              'conditions':{**prior['conditions'],'free_proposals':'preserve_and_stop_before_acceptance',
                            'proposal_collection_only':True}}
        ensure(plan['model']==MODEL and plan['limits']==LIMITS and plan['usd_stop_limit']==str(CEILING)
               and plan['nation_ids']==IDS and plan['retry_count']==0 and plan['concurrency']==1,
               'COLLECTION_GENERATION_CONDITIONS_CHANGED')
        directory.mkdir(mode=0o700)
        Journal(directory).write('catalog.json',read_record(Path(proposal_source)/'catalog.json'))
        Journal(directory).write('plan.json',plan)
        return {'status':'prepared','plan_sha256':digest(plan),'maximum_reserved_usd':str(maximum),
                'prior_charged_usd':str(already),'map_generation_calls':0,'imported_proposals':1,'new_proposals':11}


def _first_index(plan):
    return 3 if plan.get('collection_source') else 2 if plan.get('frozen_source') else 1


def _map_root(directory,plan):
    return Path(plan['frozen_source']['directory'])/'attempt-01' if plan.get('frozen_source') else directory/'attempt-01'


def _map_output(root, plan):
    raw=_output(root)
    result=compile_topology(raw,expected_world_id=plan['world_id'],expected_nation_ids=IDS)
    saved=read_record(root/'DERIVED/canonical-map.json')['report']
    ensure(saved['map']==result['map'] and saved['map_sha256']==record_hash(result['map'])
           and saved['raw_topology_sha256']==record_hash(raw),'CANONICAL_MAP_CHANGED')
    return result['map']


def _plan(directory):
    ensure(not directory.is_symlink() and directory.is_dir() and not directory.stat().st_mode & 0o077,
           'PRIVATE_BATCH_REQUIRED')
    plan = Journal(directory).read('plan.json')
    ensure(date.today() <= date(2026,12,31), 'PRICE_WINDOW_EXPIRED')
    ensure(plan['version']==VERSION and plan['model']==MODEL and plan['limits']==LIMITS
           and plan['usd_stop_limit']==str(CEILING) and plan['nation_ids']==IDS
           and plan['max_generation_calls']==(11 if plan.get('collection_source') else 12 if plan.get('frozen_source') else 13)
           and plan['max_count_calls']==plan['max_generation_calls']
           and plan['retry_count']==0 and plan['concurrency']==1
           and plan['map_method']=='shared-boundaries-v2-complete-slots', 'PLAN_SCOPE_CHANGED')
    ensure(plan['source_hashes']==source_hashes() and plan['runtime']==_runtime(), 'SOURCE_OR_RUNTIME_CHANGED')
    catalog=Journal(directory).read('catalog.json')
    ensure(record_hash(catalog)==plan['catalog_sha256'], 'CATALOG_CHANGED')
    if plan.get('predecessor'):
        ensure(_predecessor(plan['predecessor']['directory'],catalog,plan['leader_references'])==plan['predecessor'],
               'PREDECESSOR_CHANGED')
    if plan.get('frozen_source'):
        source=_frozen_source(plan['frozen_source']['directory'])
        ensure(source==plan['frozen_source'],'FROZEN_SOURCE_CHANGED')
        ensure(plan['world_id']==source['world_id'] and plan['assignment']==source['assignment']
               and plan['leader_references']==source['leader_references']
               and plan['catalog_sha256']==source['catalog_sha256'],'FROZEN_FIXED_INPUTS_CHANGED')
    if plan.get('collection_source'):
        ensure(_collection_source(plan['collection_source']['directory'])==plan['collection_source'],
               'COLLECTION_SOURCE_CHANGED')
        ensure(plan['collection_policy']['defer_content_acceptance'] is True
               and plan['collection_policy']['assignment_eligible'] is False
               and plan['collection_policy']['simulation_eligible'] is False,'COLLECTION_POLICY_CHANGED')
    return plan


def _output(root):
    wire=read_record(root/'RAW/generation.response.json')
    raw=base64.b64decode(wire['body_base64'],validate=True)
    ensure(wire['status']==200 and hashlib.sha256(raw).hexdigest()==wire['body_sha256'],'RESPONSE_BYTES_CHANGED')
    return _extract_persona(load_response_object(raw.decode('utf-8')))


def _package(directory, plan, index):
    if index==1:
        return build_topology_request(plan['world_id'],IDS)
    m=_map_output(_map_root(directory,plan),plan)
    c=Journal(directory).read('catalog.json')
    return build_nation_request(m,IDS[index-2],c,expected_map_hash=record_hash(m),expected_catalog_hash=plan['catalog_sha256'])


def _history(directory, plan, *, allow_unreviewed=False):
    ensure(not list(directory.glob('blocked-*.json')), 'BATCH_BLOCKED')
    result=[]
    for i in range(_first_index(plan),14):
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
        if plan.get('collection_source'):
            ensure(not review.exists(),'COLLECTION_MUST_NOT_ACCEPT_NATIONS')
        elif review.exists():
            report=read_record(review)['report']
            ensure(report['accepted'] is True and report['evidence_hash']==verified['evidence_hash'], 'CONTENT_REVIEW_REJECTED')
        else:
            ensure(allow_unreviewed and not (directory/f'attempt-{i+1:02d}').exists(),'CONTENT_REVIEW_REQUIRED')
        result.append({'index':i,'root':root,'verification':verified})
    return result


def _error(exc):
    if isinstance(exc,TopologyError):return exc.code
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
        index=len(history)+_first_index(plan)
        ensure(index<=13,'BATCH_COMPLETE')
        package=_package(directory,plan,index)
        body=http_body(package)
        stage_name=package['stage']
        maximum=price(LIMITS[stage_name]['input'],LIMITS[stage_name]['output'])
        reserved=sum((Decimal(read_record(p)['usd']) for p in directory.glob('reservation-*.json')),Decimal(0))
        reserved += Decimal(plan['predecessor']['reserved_usd'] if plan.get('predecessor') else '0')
        reserved += Decimal(plan['frozen_source']['charged_usd'] if plan.get('frozen_source') else '0')
        reserved += Decimal(plan['collection_source']['charged_usd'] if plan.get('collection_source') else '0')
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
                                'runtime':plan['runtime'],'parent_evidence_hash':(plan['frozen_source']['map_evidence_hash']
                                    if plan.get('frozen_source') else history[0]['verification']['evidence_hash'] if history else None),
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
                compiled=compile_topology(output,expected_world_id=plan['world_id'],expected_nation_ids=IDS)
                validation=compiled['report']
            else:
                validation=inspect_nation_output(output,package)
            # Success means the generation completed; final world acceptance remains separate.
            result=run.finish('success',completed_turns=0)
            stage='save_derived'
            run.derive('output.json',{'output':output,'raw_response_path':'RAW/generation.response.json'})
            run.derive('structural-validation.json',validation)
            if plan.get('collection_source'):
                from homeostasis_v5.nation_valuation import evaluate_initial_holdings
                run.derive('accounting-review.json',evaluate_initial_holdings(output,Journal(directory).read('catalog.json')))
                run.derive('proposal-status.json',{'status':'collected_pending_bundled_review',
                    'accepted_initial_nation':False,'world_physics_approved':False,
                    'raw_output_modified':False,'content_review_deferred':True})
            if index==1:
                run.derive('canonical-map.json',{'map':compiled['map'],
                    'map_sha256':record_hash(compiled['map']),
                    'raw_topology_sha256':record_hash(output),
                    'source':'RAW/generation.response.json'})
            return {**result,'index':index,'stage':stage_name,'estimated_cost_usd':actual,
                    'content_review_required':True,'proposal_collection_only':bool(plan.get('collection_source')),
                    'accepted_initial_nation':False}
        except (Exception,KeyboardInterrupt) as exc:
            error={'code':_error(exc),'exception_type':type(exc).__name__,'stage':stage,'generation_attempted':attempted}
            if not (run.root/'terminal.json').exists():
                run.write('error.json',error)
                run.finish('interrupted' if isinstance(exc,KeyboardInterrupt) else 'failure',completed_turns=0,error=error)
            if isinstance(exc,TopologyError):
                run.derive('topology-validation-failure.json',exc.report)
            Journal(directory).write(f'blocked-{index:02d}.json',error)
            return {'status':'failure','index':index,'error':error,'estimated_cost_usd':actual}


def review_last(directory, *, accepted, review_notes, balance_review_notes=None):
    """Human-assisted content gate: mechanical checks cannot grant semantic approval."""
    directory=Path(directory)
    with exclusive_execution(directory):
        plan=_plan(directory)
        ensure(not plan.get('collection_source'),'COLLECTION_ACCEPTANCE_DEFERRED')
        history=_history(directory,plan,allow_unreviewed=True)
        ensure(bool(history),'NO_GENERATION')
        last=history[-1];root=last['root'];index=last['index'];output=_output(root)
        ensure(not (root/'DERIVED/content-review.json').exists(),'ALREADY_REVIEWED')
        ensure(type(accepted) is bool and isinstance(review_notes,list) and review_notes,'REVIEW_REQUIRED')
        if accepted:
            if index==1:
                from homeostasis_v5.nation_geometry import derive_geometry
                check=derive_geometry(_map_output(root,plan))
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
