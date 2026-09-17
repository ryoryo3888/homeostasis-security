"""Read-only saved-worldline analysis. No clients, gateways or experiment execution."""
import copy
import hashlib
import json
from pathlib import Path
import argparse
from collections import Counter

from final_experiment_runner import COUNTRIES, _initial_states, load_country_configuration
from homeostasis_core.resources import load_resource_network
from homeostasis_core.gemini_agents import (apply_structured_actions, event_candidates, derive_event,
    parse_country_choice_json)
from homeostasis_core.emergent_dynamics import reconstruction_step
from homeostasis_core.decision_audit import validate_choice_trace
from homeostasis_core.observability import inspect_run, validate_bundle, encoded, secret_scan

ROOT=Path(__file__).resolve().parents[1]

def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()

def derived(row, states):
    answers={a['agent_id']:a['structured_response'] for a in row['decisions']}
    x=row['executed_state'];eligible=set(x['participants']);edges=[];checks={}
    for c,a in answers.items():
        conditions=a['conditions'];p=a['action']['parameters']
        edges.extend({'dependent':c,'required':v} for v in conditions.get('required_countries',[]))
        checks[c]={'required_countries':set(conditions.get('required_countries',[]))<=eligible,
                   'minimum_aid_amount':p['amount']>=conditions.get('minimum_aid_amount',0),
                   'maximum_sovereignty_burden':a['sovereignty_burden']<=conditions.get('maximum_sovereignty_burden',100),
                   'deadline_turn':row['turn']<=conditions.get('deadline_turn',row['turn']),
                   'mutual_performance':not conditions.get('mutual_performance') or len(eligible)>1,
                   'participates':c in eligible}
    graph={c:{e['required'] for e in edges if e['dependent']==c} for c in COUNTRIES}
    def reach(c):
        seen=set();todo=list(graph[c])
        while todo:
            v=todo.pop()
            if v not in seen:seen.add(v);todo.extend(graph[v])
        return seen
    reachability={c:reach(c) for c in graph}
    cycles=sorted({tuple(sorted(v for v in graph if v==c or v in reachability[c] and c in reachability[v])) for c in graph if c in reachability[c]})
    return {'responses':dict(Counter(a['response_id'] for a in answers.values())),
            'condition_edges':edges,'cyclic_components':[list(v) for v in cycles],'condition_checks':checks,
            'resource_delta':{c:{r:value-states[c]['resources'][r] for r,value in s['resources'].items()} for c,s in x['country_states'].items()},
            'network_shortfall_total':sum(a['shortfall'] for a in x['network_transfers']),
            'action_outcomes':{c:{'participates':c in eligible,'action_id':a['action']['action_id'],
                'atomic_records':[v for v in x['atomic_settlements'] if v['agent_id']==c],
                'non_execution_reason':None if c in eligible else 'REJECT' if a['response_id']=='REJECT' else [k for k,v in checks[c].items() if k!='participates' and not v]} for c,a in answers.items()}}

def event_proof(row, previous):
    s=row['snapshot']
    if previous is None:return {'origin':'fixed_initial_condition','selected':s['event'],'candidates':[],'excluded_recent_events':[]}
    candidates=list(event_candidates(s['world'],s['history_state'],previous['executed_state']['action_counts']))
    return {'origin':'derived_from_previous_executed_state','selected':s['event'],'candidates':candidates,
            'excluded_recent_events':s['public_history'][-2:],
            'rule':'Highest ranked candidate outside last two events; if all excluded, highest ranked fallback.'}

def validate_timeline(data):
    secret_scan(data)
    if data['timeline_version']!=1 or len(data['turns'])!=8:raise ValueError('invalid timeline schema')
    states=copy.deepcopy(data['initial_country_states']);previous=None
    network=load_resource_network(ROOT/'scenarios/resource_network_sample.json',COUNTRIES)
    for number,row in enumerate(data['turns'],1):
        if row['turn']!=number or len(row['decisions'])!=8:raise ValueError('turn or decision count')
        s=row['snapshot'];answers={}
        for a in row['decisions']:
            validate_choice_trace(a)
            m=a['model_response'];catalog=a['public_observation_payload']['action_choices']
            parsed=parse_country_choice_json(json.dumps(m),a['agent_id'],row['proposal']['proposal_id'],set(COUNTRIES),catalog,catalog)
            if parsed!=a['structured_response']:raise ValueError('response mismatch')
            answers[a['agent_id']]=parsed
        if set(answers)!=set(COUNTRIES):raise ValueError('country set')
        if previous:
            p=previous['executed_state']
            if s['world']!=p['true_world'] or s['world_pool']!=p['world_pool'] or s['damage']!=p['reconstruction']['after']:raise ValueError('state continuity')
            if s['event']!=derive_event(s['world'],s['history_state'],p['action_counts'],s['public_history']):raise ValueError('derived event mismatch')
        out=apply_structured_actions(states,answers,s['world'],s['damage'],number,world_pool=s['world_pool'],resource_network=network,network_policy=s['network_policy'])
        out['causal_record']['event']=s['event']
        if sha(out)!=row['evaluator_input_sha256']:raise ValueError('evaluator input mismatch')
        recovery=reconstruction_step(s['damage'],out,out['country_states'])
        out['reconstruction']=recovery;out['causal_record']['farmland_reconstruction']=recovery
        if out!=row['executed_state']:raise ValueError('full executed state mismatch')
        if row['derived']!=derived(row,states) or row['event_derivation']!=event_proof(row,previous):raise ValueError('derived analysis mismatch')
        states=out['country_states'];previous=row
    return True

def build(path):
    bundle=inspect_run(path);validate_bundle(bundle)
    if not bundle['validation']['research_eligible']:raise ValueError('research-ineligible source')
    detail=json.loads((path/'result.json').read_text())['runs'][0]['details'];rows=[]
    initial=_initial_states(load_country_configuration(ROOT/'config/country_archetypes.json'));states=initial
    for t in detail['turns']:
        calls=[a for a in detail['call_audit'] if a['turn']==t['turn']]
        decisions=[]
        for a in calls:
            if a['agent_type']!='country':continue
            trace={k:a[k] for k in ('run_id','run','turn','agent_id','attempt','call_id','audit_version','validation_status','model_response','choice_response','materialized_action','structured_response')}
            trace['public_observation_payload']={'action_choices':a['public_observation_payload']['action_choices']}
            decisions.append(trace)
        evaluator=next(a for a in calls if a['agent_type']=='evaluator')
        row={k:t[k] for k in ('turn','snapshot','proposal','executed_state','evaluator_commentary')}
        row['decisions']=decisions;row['evaluator_input_sha256']=sha(evaluator['public_observation_payload']['executed_true_state'])
        row['derived']=derived(row,states);row['event_derivation']=event_proof(row,rows[-1] if rows else None)
        rows.append(row);states=row['executed_state']['country_states']
    data={'timeline_version':1,'run_id':path.name,'classification':'analysis_of_one_observed_worldline','analysis_api_calls':0,
          'source_hashes':bundle['source_hashes'],'runtime':bundle['runtime'],'run':bundle['run'],'validation':bundle['validation'],
          'units':'Normalized model indices/resources, except farmland damage/recovery in scenario tons; no real-country forecasts.',
          'initial_country_states':initial,'turns':rows}
    validate_timeline(data);return data

def markdown(data):
    lines=['# TURN別資料: '+data['run_id'],'','保存原本から生成。数値は表示のみ丸め、timeline JSONは元の精度を保持。Evaluatorはモデルの公開評価であり、正式指標とは分離する。','']
    for row in data['turns']:
        x=row['executed_state'];lines += ['## TURN '+str(row['turn'])+'｜'+row['snapshot']['event'],'','### Coordinator proposal','',json.dumps(row['proposal'],ensure_ascii=False),'','### 国家判断・条件・実行','', '| Agent | response / choice | conditions | action / recipient / resource / amount | 決済 |','|---|---|---|---|---|']
        for a in row['decisions']:
            m=a['model_response'];p=a['materialized_action']['parameters'];o=row['derived']['action_outcomes'][a['agent_id']]
            status='不成立: '+str(o['non_execution_reason']) if not o['participates'] else '参加・非移転行動' if not o['atomic_records'] else '; '.join(f"実現 {z['realized']:.6g} / 要求 {z['requested']:.6g} / 未達 {z['unmet']:.6g}" for z in o['atomic_records'])
            lines.append(f"| {a['agent_id']} | {m['response_id']} / {m['choice_id']} | {json.dumps(m['conditions'],ensure_ascii=False)} | {a['materialized_action']['action_id']} / {p['target_country'] or p['recipient_type']} / {p['resource']} / {p['amount']} | {status} |")
        lines+=['','### 公開理由','']+[f"- {a['agent_id']}: {a['model_response']['reason']}" for a in row['decisions']]
        for title,value in [('条件依存・評価',{'edges':row['derived']['condition_edges'],'cycles':row['derived']['cyclic_components'],'checks':row['derived']['condition_checks']}),('world / research metrics',{'world':x['true_world'],'metrics':x['research_metrics']}),('資源移動・消費・pool',{'atomic':x['atomic_settlements'],'network':x['network_transfers'],'consumption':x['network_consumption'],'pool':x['world_pool']}),('各国resource変化',row['derived']['resource_delta']),('reconstruction',x['reconstruction']),('event生成証拠',row['event_derivation']),('Evaluator公開評価',row['evaluator_commentary'])]:
            lines+=['','### '+title,'','```json',json.dumps(value,ensure_ascii=False,indent=2),'```']
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run_id');args=parser.parse_args()
    data=build(ROOT/'results/research'/args.run_id)
    output=ROOT/'results/status/analyses'/args.run_id;output.mkdir(parents=True,exist_ok=True)
    (output/'timeline.json').write_bytes(encoded(data))
    report=ROOT/'docs/research';report.mkdir(parents=True,exist_ok=True)
    (report/(args.run_id+'-turns.md')).write_text(markdown(data),encoding='utf-8')
    print('Saved-worldline replay and timeline: PASS; API calls: 0')
