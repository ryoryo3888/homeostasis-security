"""Saved validation artifacts only. Never runs a TURN, replay, Agent or transport."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from homeostasis_v3.contracts import digest
from homeostasis_v3.observation import verify_observation, resolve
from tools.secret_scan import has_secret
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'ui/v3/validation'
CASES=(('abstention','8TURN・不作為','v3-preflight-20260918-verified',8),
       ('conditional_exchange','条件付き取引','v3-agent-sdk-20260918-final/conditional_exchange',3),
       ('all_refuse','全拒否','v3-agent-sdk-20260918-final/all_refuse',3),
       ('missing_offer','相手の提案なし','v3-agent-sdk-20260918-final/missing_offer',3))

def filehash(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def extract(root):
    result={'schema_version':1,'artifact_class':'validation_run','research_eligible':False,
            'api_calls':0,'decision_origin':'synthetic_fixture','cases':[]}
    for ident,label,subdir,total in CASES:
        folder=root/subdir
        protocol_path=folder/'protocol.json' if ident=='abstention' else folder.parent/'report.json'
        protocol=json.loads(protocol_path.read_text())
        assert protocol['api_calls']==0 and protocol['research_eligible'] is False and protocol['artifact_class']=='validation_run'
        source_hashes=protocol['source_hashes']
        revision=subprocess.check_output(['git','rev-parse','b4adb20' if ident=='abstention' else '7f69d43'],cwd=ROOT,text=True).strip()
        assert all(hashlib.sha256(subprocess.check_output(['git','show',revision+':homeostasis_v3/'+name],cwd=ROOT)).hexdigest()==value for name,value in source_hashes.items()), 'V3 historical source mismatch'
        cps={};files={}
        for p in (folder/'checkpoints').glob('*.json'):
            if p.name=='HEAD.json':continue
            c=json.loads(p.read_text());cps[c['checkpoint_digest']]=c;files[c['checkpoint_digest']]=p
        head=json.loads((folder/'checkpoints/HEAD.json').read_text());assert cps[head['checkpoint_digest']]['turn']==total
        adopted=set();cursor=cps[head['checkpoint_digest']]
        while True:
            adopted.add(cursor['checkpoint_digest'])
            if cursor['turn']==0:break
            cursor=cps[cursor['input']['opening']]
        case={'id':ident,'label':label,'source_directory':subdir,'protocol_sha256':filehash(protocol_path),
              'source_commit':revision,'source_hashes':source_hashes,'head_digest':head['checkpoint_digest'],'turns':[]}
        observations=sorted(folder.glob('observation-*.json'))
        assert len(observations)==total
        for p in observations:
            obs=json.loads(p.read_text());verify_observation(obs,{k:cps[k] for k in obs['provenance']['source_checkpoints']})
            cp=cps[obs['checkpoint_digest']]
            assert cp['checkpoint_digest'] in adopted, 'Unadopted observation'
            refs={}
            paths={'world':'/world_state/physical/world','shipments':'/world_state/shipments',
                   'selection':'/input/selections','choices':'/audit/JOINT_SETTLEMENT/choices',
                   'ledger':'/ledger','production':'/audit/PRODUCTION','conservation':'/audit/CONSERVATION',
                   'events':'/input/shocks','reservations':'/audit/JOINT_SETTLEMENT/joint_reservations'}
            for name,pointer in paths.items():
                value=resolve(cp,pointer);refs[name]={'checkpoint_digest':cp['checkpoint_digest'],'pointer':pointer,'value_digest':digest(value),'value':value}
            case['turns'].append({'turn':cp['turn'],'checkpoint_digest':cp['checkpoint_digest'],
                'checkpoint_file_sha256':filehash(files[cp['checkpoint_digest']]),'observation_digest':obs['observation_digest'],
                'observation_file_sha256':filehash(p),'worldline_id':obs['worldline_id'],
                'context_id':cp['context_id'],'configuration_hash':cp['config_hash'],
                'source_observation_recomputed':True,'evidence':refs})
        assert [t['turn'] for t in case['turns']]==list(range(1,total+1))
        result['cases'].append(case)
    assert not has_secret(json.dumps(result,ensure_ascii=False)), 'Secret rejected'
    return result

def project(package):
    assert package['schema_version']==1 and package['artifact_class']=='validation_run'
    assert package['research_eligible'] is False and package['api_calls']==0 and package['decision_origin']=='synthetic_fixture'
    assert not has_secret(json.dumps(package,ensure_ascii=False))
    model={k:package[k] for k in ('schema_version','artifact_class','research_eligible','api_calls','decision_origin')};model['cases']=[]
    states=json.loads((ROOT/'ui/v3/baseline.json').read_text())['states'];labels={s['id']:s['label'] for s in states}
    for case in package['cases']:
        out={'id':case['id'],'label':case['label'],'turns':[]}
        assert [t['turn'] for t in case['turns']]==list(range(1,len(case['turns'])+1))
        for t in case['turns']:
            e=t['evidence'];assert t['source_observation_recomputed'] is True
            for ref in e.values():
                assert ref['checkpoint_digest']==t['checkpoint_digest'] and digest(ref['value'])==ref['value_digest']
                assert ref['pointer'].startswith('/')
            world=e['world']['value'];ledger=e['ledger']['value'];choices=e['choices']['value'];ships=e['shipments']['value']
            assert set(c['state_id'] for c in world['countries'])==set(labels)
            turn={'turn':t['turn'],'checkpoint_digest':t['checkpoint_digest'],'states':[],'transactions':[],
                  'conservation':e['conservation']['value'],'production':e['production']['value'],
                  'shipments':ships,'events':e['events']['value'],'reservations':e['reservations']['value']}
            for sid,label in labels.items():
                resources=[]
                for resource in ('food','energy'):
                    account=next(a for a in world['accounts'] if a['owner']==sid and a['resource_id']==resource)
                    row=next(r for r in ledger if r['owner']==sid and r['resource']==resource)
                    assert row['required']==row['consumed']+row['shortage'] and account['balance']>=0
                    resources.append({'id':resource,'unit':account['unit_id'],'stock':account['balance'],**row})
                turn['states'].append({'id':sid,'label':label,'resources':resources,'selections':e['selection']['value'].get(sid,[])})
            for choice_index,a in enumerate(choices):
                intent=a['intent'];sid=intent['actor_state_id'];assert sid in labels
                selected=next(s for s in e['selection']['value'][sid] if s['choice_id']==a['choice_id'])
                assert selected['requested_amount']==intent['requested_amount']
                assert selected['provenance']==intent['provenance'] and a['intent_hash']==digest(intent)
                assert 0<=a['settled_amount']<=a['individual']['feasible_amount']<=intent['requested_amount']
                assert a['dispatched_amount']==a['settled_amount']
                arrived=sum(s['arrived_amount'] for s in ships if s['choice_id']==a['choice_id'])
                turn['transactions'].append({'choice_id':a['choice_id'],'actor':sid,'target':a['individual'].get('target'),
                    'resource':intent['resource'],'action':intent['action_type'],'conditions':intent['conditions'],
                    'public_reason':intent['provenance']['public_reason'],'requested':intent['requested_amount'],
                    'feasible':a['individual']['feasible_amount'],'settled':a['settled_amount'],
                    'unsettled':intent['requested_amount']-a['settled_amount'],'dispatched':a['dispatched_amount'],
                    'arrived':arrived,'reason_codes':a['reason_codes'],'consents':a['consent_evidence'],
                    'materialized_action':intent,'state_change':a['state_change'],'trace_id':a['trace_id'],'evidence_pointer':f"/cases/{len(model['cases'])}/turns/{t['turn']-1}/evidence/choices/value/{choice_index}"})
            out['turns'].append(turn)
        model['cases'].append(out)
    return model

def build():
    p=DEST/'evidence.json';manifest=json.loads((DEST/'manifest.json').read_text())
    assert manifest['file_sha256']==filehash(p),'Unreviewed evidence change'
    data=json.loads(p.read_text());model=project(data);write(DEST/'view.json',model)
    return model
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--import-saved',type=Path);a=parser.parse_args()
    if a.import_saved:
        assert not (DEST/'evidence.json').exists(),'Never overwrite approved evidence'
        data=extract(a.import_saved);project(data);write(DEST/'evidence.json',data)
        write(DEST/'manifest.json',{'artifact_class':'validation_run','research_eligible':False,'public_scope':'sanitized validation evidence only; not research registry',
            'file_sha256':filehash(DEST/'evidence.json'),'source_verification':'17 saved observations recomputed; no TURN or model execution'})
    build();print('Saved V3 validation view built; no simulation or API')
