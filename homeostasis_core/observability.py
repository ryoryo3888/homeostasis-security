"""Read-only run inspection and fail-closed, API-free public projections."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone

from .decision_audit import safe_data, validate_choice_trace
from .gemini_agents import parse_coordinator_json, parse_evaluator_json
from .research_validation import validate_research

RUN_ID = re.compile(r'^\d{8}T\d{6}Z-[a-f0-9]{8}$')
MAX_INPUT = 20_000_000
MAX_PUBLIC = 2_000_000
IDENTITY = ('run_id', 'run', 'turn', 'agent_id', 'attempt', 'call_id')
CATEGORIES = ('probe', 'rejected', 'research')
BEGIN = '<!-- MACHINE STATE START -->'
END = '<!-- MACHINE STATE END -->'


class PublicationError(ValueError):
    pass


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_digest(root):
    paths = [*root.glob('*.py'), *root.glob('homeostasis_core/*.py'), *root.glob('tools/**/*.py'),
             *root.glob('tests/**/*.py'), *root.glob('tests/fixtures/*.json'),
             *root.glob('config/*.json'), *root.glob('scenarios/*.json'),
             *root.glob('.github/workflows/*.yml'), *root.glob('.githooks/*'), *root.glob('requirements*.txt'), root/'Makefile']
    return digest(encoded({str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted(set(paths)) if p.is_file()}))


def secret_scan(value):
    """Reject credentials rather than publishing redacted-but-unverifiable evidence."""
    patterns = (r'AIza[\w-]{30,}', r'gh[pousr]_[A-Za-z0-9]{20,}', r'github_pat_[\w]+',
                r'-----BEGIN [A-Z ]*PRIVATE KEY-----', r'Bearer\s+[\w.-]{15,}',
                r'\bsk-[A-Za-z0-9_-]{20,}')
    secrets = [v for k,v in os.environ.items() if len(v)>3 and any(t in k.upper() for t in ('API_KEY','TOKEN','PASSWORD','SECRET'))]
    def visit(item):
        if isinstance(item, dict):
            for key, val in item.items():
                normal = re.sub('[^a-z]', '', key.lower())
                if ((any(t in normal for t in ('apikey','password','credentials')) or normal in ('secret','clientsecret')) or normal in ('authorization','accesstoken','refreshtoken')) and val not in (None, '', '[REDACTED]'):
                    raise PublicationError('SECRET_SCAN_FAILED')
                visit(key)
                visit(val)
        elif isinstance(item, list):
            for part in item: visit(part)
        elif isinstance(item, str):
            if len(item)>16000: raise PublicationError('OVERSIZED_TEXT')
            if any(re.search(p,item) for p in patterns) or any(v in item for v in secrets):
                raise PublicationError('SECRET_SCAN_FAILED')
    visit(value)


def read_json(path, optional=False):
    if not path.exists() and optional: return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT:
        raise PublicationError('INVALID_INPUT_FILE')
    try:
        value=json.loads(path.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        secret_scan(value)
        return value
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, PublicationError): raise
        raise PublicationError('INVALID_JSON') from None


def select(value, keys):
    return {k:value[k] for k in keys if k in value}


def public_decision(row):
    keys=(*IDENTITY,'audit_version','agent_type','model','schema_version','validation_status',
          'error_type','validation_error','token_usage','model_response','choice_response',
          'materialized_action','structured_response')
    out=select(row, keys)
    if isinstance(out.get('model_response'),dict):
        answer_fields=('country_id','proposal_id','response_id','response_label','reason','conditions',
                       'self_interest','sovereignty_burden','perceived_global_effect','choice_id','amount',
                       'proposal_type','predicted_global_effect','predicted_sovereignty_burden','requested_action',
                       'national_sovereignty','global_homeostasis','resource_stability','resilience','conflict_load',
                       'history_effect','assessment')
        out['model_response']=select(out['model_response'],answer_fields)

    payload=row.get('public_observation_payload',{})
    out['public_observation_payload']=select(payload,('action_choices','response_contract','allowed_country_ids'))
    out['contract_validation']=row['validation_status']
    if row.get('choice_response'):
        out.update(select(row['choice_response'],('choice_id','amount','reason')))
    if row.get('materialized_action'):
        out['recipient']=select(row['materialized_action']['parameters'],('recipient_type','target_country'))
        out['resource']=row['materialized_action']['parameters']['resource']
    return safe_data(out)


def check_audits(calls, transport, run_id, failed):
    for key in ('api_calls','maximum_api_calls'):
        if type(transport.get(key)) is not int:raise PublicationError('INVALID_TRANSPORT_COUNT')
    if not calls or len(calls)!=transport['api_calls'] or len(calls)!=len(transport['attempts']):
        raise PublicationError('AUDIT_COUNT_MISMATCH')
    if transport.get('run_id')!=run_id or not 0<len(calls)<=transport['maximum_api_calls']:
        raise PublicationError('TRANSPORT_LIMIT_OR_ID_MISMATCH')
    seen=set(); groups={}
    for number,(row,attempt) in enumerate(zip(calls,transport['attempts']),1):
        if row.get('run_id')!=run_id or row.get('call_id') in seen:
            raise PublicationError('DECISION_ID_MISMATCH')
        for key in ('run','turn','attempt'):
            if type(row.get(key)) is not int or row[key]<1:raise PublicationError('INVALID_DECISION_NUMBER')
        seen.add(row.get('call_id'))
        for key in IDENTITY:
            if not row.get(key) or row[key]!=attempt.get(key): raise PublicationError('AUDIT_IDENTITY_MISMATCH')
        if attempt.get('transport_attempt')!=number: raise PublicationError('TRANSPORT_SEQUENCE_MISMATCH')
        group=(row['run'],row['turn'],row['agent_id']);groups[group]=groups.get(group,0)+1
        if type(attempt.get('transport_attempt')) is not int:raise PublicationError('INVALID_TRANSPORT_ATTEMPT')
        if row['attempt']!=groups[group]: raise PublicationError('RETRY_SEQUENCE_MISMATCH')
        status=row.get('validation_status')
        if row.get('audit_version')!=1: raise PublicationError('UNSUPPORTED_AUDIT_VERSION')
        if status=='PASS':
            if attempt['status']!='returned': raise PublicationError('TRANSPORT_NOT_RETURNED')
            if row['agent_type']=='country': validate_choice_trace(row)
            else:
                parser={'coordinator':parse_coordinator_json,'evaluator':parse_evaluator_json}.get(row['agent_type'])
                if parser is None or parser(json.dumps(row['model_response']))!=row['structured_response']:
                    raise PublicationError('RESPONSE_AUDIT_MISMATCH')
        elif not failed or number!=len(calls) or status not in ('FAIL','PENDING'):
            raise PublicationError('UNEXPLAINED_INVALID_DECISION')
        elif status=='FAIL' and not row.get('error_type'):
            raise PublicationError('MISSING_FAILURE_TYPE')
    return sum(n-1 for n in groups.values())


def project_world(row):
    executed=row['executed_state'];snapshot=row['snapshot']
    if row['research_metrics']!=executed['research_metrics']:raise PublicationError('WORLD_METRIC_MISMATCH')
    required_world={'food','energy','economy','environment','international_trust','conflict_load','global_homeostasis'}
    if set(executed['true_world'])!=required_world or any(type(v) not in (int,float) or not 0<=v<=100 for v in executed['true_world'].values()):
        raise PublicationError('INVALID_WORLD_STATE')
    return {'turn':row['turn'], 'event':snapshot['event'], 'event_origin':snapshot['event_origin'],
            'world':executed['true_world'], 'research_metrics':row['research_metrics'],
            'country_states':{c:select(s,('archetype','sovereignty','indicators','resources','energy_portfolio')) for c,s in executed['country_states'].items()}, 'reconstruction':executed['reconstruction'],
            'world_pool':executed['world_pool'], 'network_policy':executed['network_policy'],
            'established_actions':executed['causal_record']['accepted_actions'],
            'atomic_settlements':executed['atomic_settlements'],
            'history_state':snapshot['history_state']}


def inspect_run(path):
    """Never modify a source run. Invalid legacy evidence is not reconstructed."""
    run_id=path.name
    if not RUN_ID.fullmatch(run_id) or path.is_symlink(): raise PublicationError('INVALID_RUN_PATH')
    data={name:read_json(path/name,optional=True) for name in
          ('result.json','result.audit.json','decision.audit.json','transport.audit.json','failure.json','result.json.checkpoint')}
    result=data['result.json'];transport=data['transport.audit.json'];failure=data['failure.json']
    if transport is None: raise PublicationError('MISSING_TRANSPORT_AUDIT')
    failed=failure is not None
    if result:
        manifest=data['result.audit.json']
        if not manifest or manifest['result_sha256']!=digest((path/'result.json').read_bytes()):
            raise PublicationError('RESULT_HASH_MISMATCH')
        if result.get('mode')=='probe':
            mode='probe';calls=result['call_audit'];turns=[]
            if result.get('run_id')!=run_id: raise PublicationError('MISSING_ORIGINAL_CHOICE_AUDIT')
            if result['action']!=calls[0]['materialized_action']: raise PublicationError('RESULT_ACTION_MISMATCH')
            if not data['decision.audit.json'] or data['decision.audit.json']['calls']!=calls:
                raise PublicationError('DECISION_FILE_MISMATCH')
        else:
            mode={1:'turn',8:'experiment'}[result['metadata']['turns']]
            if len(result['runs'])!=1: raise PublicationError('MULTI_RUN_NOT_SUPPORTED')
            detail=result['runs'][0]['details'];calls=detail['call_audit'];turns=detail['turns']
            if [t['turn'] for t in turns]!=list(range(1,result['metadata']['turns']+1)):
                raise PublicationError('INCOMPLETE_SUCCESS')
            for turn in turns:
                country_calls=[a for a in calls if a['turn']==turn['turn'] and a['agent_type']=='country']
                if len(country_calls)!=8 or {a['agent_id']:a['structured_response'] for a in country_calls}!=turn['country_responses']:
                    raise PublicationError('TURN_DECISION_MISMATCH')
    elif failed:
        mode=failure['mode'];checkpoint=data['result.json.checkpoint'];decision=data['decision.audit.json']
        if checkpoint:
            active=checkpoint['active_run'];calls=active['call_audit'];turns=active['turns']
            if active['completed_turn']!=len(turns): raise PublicationError('CHECKPOINT_TURN_MISMATCH')
        elif decision:
            calls=decision['calls'];turns=[]
        else: raise PublicationError('MISSING_DECISION_AUDIT')
        if failure['api_calls']!=transport['api_calls'] or failure.get('include_in_research_aggregation') is not False:
            raise PublicationError('FAILURE_AUDIT_MISMATCH')
    else: raise PublicationError('INCOMPLETE_RUN')
    if mode not in ('probe','turn','experiment'): raise PublicationError('INVALID_MODE')
    if transport['maximum_api_calls']!={'probe':1,'turn':10,'experiment':80}[mode]:
        raise PublicationError('UNEXPECTED_API_BUDGET')
    retry=check_audits(calls,transport,run_id,failed)
    eligible=False
    if path.parent.name=='research':
        if failed or mode!='experiment' or validate_research(result,transport) or data['result.audit.json'].get('include_in_research_aggregation') is not True:
            raise PublicationError('RESEARCH_ADMISSION_FAILED')
        eligible=True
    elif result and data['result.audit.json'].get('include_in_research_aggregation') is not False:
        raise PublicationError('RESEARCH_CLASSIFICATION_MISMATCH')
    status='failed' if failed else 'rejected' if mode=='experiment' and not eligible else 'success'
    diagnostic=None
    if failed:
        last=calls[-1]
        diagnostic={**select(last,IDENTITY), 'api_call_number':len(calls),
                    'validation':last['validation_status'], 'error_type':last.get('error_type',failure['error_type']),
                    'validation_error':last.get('validation_error'), 'include_in_research_aggregation':False}
        if last.get('model_response',{}).get('response_id')=='CONDITIONAL' and last['model_response'].get('conditions')=={}:
            diagnostic['derived_diagnosis']='CONDITIONAL_REQUIRES_EXECUTABLE_CONDITIONS'
    summary={'run_id':run_id,'mode':mode,'status':status,'turns_completed':len(turns),
             'api_calls':transport['api_calls'],'maximum_api_calls':transport['maximum_api_calls'],'retry_count':retry}
    bundle={'observation_version':1,'run':summary,
            'validation':{'contracts':'FAIL' if any(a['validation_status']!='PASS' for a in calls) else 'PASS',
                          'decision_audit':'PASS','transport_audit':'PASS','secret_scan':'PASS','research_eligible':eligible},
            'decisions':[public_decision(a) for a in calls], 'transport_audit':transport,
            'worlds':[project_world(t) for t in turns], 'failure':diagnostic,
            'result':{'metadata':select(result.get('metadata',{}),('mode','research_mode','model','seed','runs','turns','provider','fixed_initial_events','derived_event_turns')) if result else {},
                      'summary':result.get('summary',{}) if result else {},'include_in_research_aggregation':eligible},
            'source_hashes':{name:digest((path/name).read_bytes()) for name,value in data.items() if value is not None}}
    secret_scan(bundle)
    if len(encoded(bundle))>MAX_PUBLIC: raise PublicationError('PUBLIC_BUNDLE_TOO_LARGE')
    return bundle


def validate_bundle(bundle):
    secret_scan(bundle)
    r=bundle['run'];v=bundle['validation']
    if bundle['observation_version']!=1 or r['status'] not in ('success','failed','rejected'):
        raise PublicationError('INVALID_PUBLIC_SCHEMA')
    if not RUN_ID.fullmatch(r['run_id']) or r['mode'] not in ('probe','turn','experiment'):
        raise PublicationError('INVALID_PUBLIC_RUN')
    if check_audits(bundle['decisions'],bundle['transport_audit'],r['run_id'],r['status']=='failed')!=r['retry_count']:
        raise PublicationError('PUBLIC_RETRY_MISMATCH')
    if r['api_calls']!=bundle['transport_audit']['api_calls'] or r['turns_completed']!=len(bundle['worlds']):
        raise PublicationError('PUBLIC_COUNT_MISMATCH')
    if v['decision_audit']!='PASS' or v['transport_audit']!='PASS' or v['secret_scan']!='PASS':
        raise PublicationError('PUBLIC_AUDIT_FAILED')
    if v['contracts'] != ('FAIL' if any(a['validation_status']!='PASS' for a in bundle['decisions']) else 'PASS'):
        raise PublicationError('PUBLIC_CONTRACT_STATUS_MISMATCH')
    if r['status']=='success':
        expected={'probe':(0,1),'turn':(1,10),'experiment':(8,80)}[r['mode']]
        if (r['turns_completed'],r['api_calls'])!=expected or v['contracts']!='PASS':
            raise PublicationError('INCOMPLETE_PUBLIC_SUCCESS')
    if v['research_eligible'] and (r['status']!='success' or r['mode']!='experiment' or r['turns_completed']!=8):
        raise PublicationError('PUBLIC_RESEARCH_MISMATCH')
    for row in bundle['decisions']:
        if row.get('choice_response'):
            for key in ('choice_id','amount','reason'):
                if row[key]!=row['choice_response'][key]: raise PublicationError('PUBLIC_CHOICE_MISMATCH')
    return True


def human_block(state):
    run=state['latest_run']
    text=f"{BEGIN}\n## 現在地（機械可読stateから生成）\n\n一次情報: [results/status/latest.json](results/status/latest.json)。\n"
    text+=f"生成時branch: `{state['branch']}` / ソースcommit: `{state['commit']}`（公開コミット自身ではありません）。\n"
    if run:
        text+=f"最新run: `{run['run_id']}` / {run['mode']} / {run['status']} / 完了{run['turns_completed']}TURN / API {run['api_calls']} calls / retry {run['retry_count']}。\n"
    text+=f"無料検証: {state['validation']['preflight']}。次: {state['next_step']}\n"
    return text+f"今回の観測ファイル生成によるGemini API calls: 0。以下の既存文章は時点ごとの研究記録であり、現在地はこの欄を優先します。\n{END}\n"


def atomic_write(path, raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.publish-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if Path(tmp).exists():Path(tmp).unlink()


def prepare(root):
    """Prepare validated Git-ready files; never commit, push or invoke a model."""
    root=Path(root);bundles={};entries=[];blocked=[]
    for category in CATEGORIES:
        for path in sorted((root/'results'/category).glob('*')):
            if not path.is_dir() or not RUN_ID.fullmatch(path.name):continue
            try:
                bundle=inspect_run(path);validate_bundle(bundle)
                raw=encoded(bundle);relative=f'results/status/runs/{path.name}/{digest(raw)}.json'
                bundles[relative]=raw
                entries.append({**bundle['run'],'path':relative,'sha256':digest(raw),
                                'research_eligible':bundle['validation']['research_eligible']})
            except (ValueError,KeyError,TypeError,OSError,IndexError) as exc:
                code=str(exc) if isinstance(exc,PublicationError) else 'INVALID_AUDIT'
                blocked.append({'run_id':path.name,'category':category,'publication':'blocked','code':code})
    # Preserve already-published history when a clone has no private raw runs.
    old=root/'results/status/latest.json'
    if old.exists():
        validate_publication(root,check_human=False)
        old_state=read_json(old);old_index=read_json(root/old_state['history_index'])
        current={e['run_id'] for e in entries}|{e['run_id'] for e in blocked}
        for e in old_index['runs']:
            if e['run_id'] not in current:
                entries.append(e);bundles[e['path']]=(root/e['path']).read_bytes()
        blocked += [b for b in old_index['blocked'] if b['run_id'] not in current]
    entries.sort(key=lambda e:e['run_id']);blocked.sort(key=lambda e:e['run_id'])
    latest=entries[-1] if entries else None
    pointers={k:None for k in ('probe','turn','experiment','successful_research','failed_or_rejected')}
    for e in entries:
        pointers[e['mode']]=e['path']
        if e['research_eligible']:pointers['successful_research']=e['path']
        if e['status'] in ('failed','rejected'):pointers['failed_or_rejected']=e['path']
    report=read_json(root/'results/debug/check.json',optional=True)
    fingerprint=source_digest(root)
    preflight=report['status'] if report and report.get('source_digest')==fingerprint else 'UNKNOWN'
    b=json.loads(bundles[latest['path']]) if latest else None
    newest=max([e['run_id'] for e in entries]+[e['run_id'] for e in blocked],default=None)
    newest_blocked=next((e for e in blocked if e['run_id']==newest),None)
    next_step=('Resolve blocked publication; inspect local audit without running APIs.' if newest_blocked else
               'Inspect latest failure and pass free checks before separately authorizing a new attempt.' if latest and latest['status']!='success' else
               'Separately authorize the next minimal experiment; never automatically advance.')
    index={'index_version':1,'runs':entries,'blocked':blocked}
    index_raw=encoded(index);index_path=f'results/status/indexes/{digest(index_raw)}.json'
    def git(*args):
        return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
    state={'status_version':1,'updated_at':datetime.now(timezone.utc).isoformat(),
           'branch':git('branch','--show-current'),'commit':git('rev-parse','HEAD'),
           'commit_semantics':'source HEAD at export; source_digest includes uncommitted implementation',
           'source_digest':fingerprint,'research_stage':'publication_blocked' if newest_blocked else 'minimal_experiment_validation',
           'latest_run':{k:v for k,v in latest.items() if k not in ('path','sha256','research_eligible')} if latest else None,
           'latest_observed_run':newest,'latest_blocked_run':newest_blocked,
           'validation':{'preflight':preflight,**(b['validation'] if b else {'contracts':'UNKNOWN','decision_audit':'UNKNOWN','transport_audit':'UNKNOWN','research_eligible':False})},
           'next_step':next_step,'latest':pointers,'history_index':index_path,'history_sha256':digest(index_raw),
           'result_paths':{key:latest['path']+'#/'+section for key,section in
                           (('result','result'),('decision_audit','decisions'),('transport_audit','transport_audit'),('failure','failure'),('world_state','worlds'))} if latest else {},
           'publication_api_calls':0,'blocked_run_count':len(blocked)}
    secret_scan(state)
    for relative,raw in bundles.items():atomic_write(root/relative,raw)
    atomic_write(root/index_path,index_raw)
    atomic_write(root/'results/status/latest.json',encoded(state))
    document=root/'RESEARCH_STATE.md';text=document.read_text() if document.exists() else ''
    if BEGIN in text:text=text.split(BEGIN)[0]+text.split(END,1)[1].lstrip('\n')
    atomic_write(document,(human_block(state)+'\n'+text).encode())
    validate_publication(root)
    return state


def validate_publication(root,check_human=True):
    root=Path(root);state=read_json(root/'results/status/latest.json')
    if type(state.get('status_version')) is not int or state['status_version']!=1 or state['publication_api_calls']!=0 or state['validation']['preflight'] not in ('PASS','FAIL','UNKNOWN'):
        raise PublicationError('INVALID_STATUS_SCHEMA')
    def referenced(relative, expected=None):
        if not isinstance(relative,str) or not relative.startswith('results/status/') or '..' in Path(relative).parts:
            raise PublicationError('UNSAFE_POINTER')
        p=root/relative
        if not p.resolve().is_relative_to((root/'results/status').resolve()):raise PublicationError('UNSAFE_POINTER')
        d=read_json(p)
        if expected and digest(p.read_bytes())!=expected: raise PublicationError('PUBLIC_HASH_MISMATCH')
        return d
    index=referenced(state['history_index'],state['history_sha256'])
    if type(index.get('index_version')) is not int or index['index_version']!=1:raise PublicationError('INVALID_INDEX')
    paths=set();ids=set()
    for e in index['runs']:
        b=referenced(e['path'],e['sha256']);validate_bundle(b)
        if e['run_id'] in ids or any(e[k]!=v for k,v in b['run'].items()):raise PublicationError('INDEX_MISMATCH')
        paths.add(e['path']);ids.add(e['run_id'])
    for pointer in state['latest'].values():
        if pointer is not None and pointer not in paths:raise PublicationError('DANGLING_POINTER')
    for pointer in state['result_paths'].values():
        if pointer.split('#')[0] not in paths:raise PublicationError('DANGLING_RESULT_POINTER')
    expected={k:None for k in ('probe','turn','experiment','successful_research','failed_or_rejected')}
    for e in sorted(index['runs'],key=lambda x:x['run_id']):
        expected[e['mode']]=e['path']
        if e['research_eligible']:expected['successful_research']=e['path']
        if e['status'] in ('failed','rejected'):expected['failed_or_rejected']=e['path']
    if state['latest']!=expected:raise PublicationError('LATEST_POINTER_MISMATCH')
    if index['runs']:
        latest=max(index['runs'],key=lambda e:e['run_id'])
        expected_run={k:v for k,v in latest.items() if k not in ('path','sha256','research_eligible')}
        if state['latest_run']!=expected_run:raise PublicationError('LATEST_RUN_MISMATCH')
        bundle=referenced(latest['path'],latest['sha256'])
        if any(state['validation'][k]!=v for k,v in bundle['validation'].items()):raise PublicationError('STATUS_VALIDATION_MISMATCH')
    if check_human and human_block(state) not in (root/'RESEARCH_STATE.md').read_text():
        raise PublicationError('HUMAN_STATE_MISMATCH')
    return state
