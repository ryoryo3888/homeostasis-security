"""Free real-SDK/three-TURN fixtures. Never sends a request to Google."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    def denied(*_args,**_kwargs): raise RuntimeError('Network forbidden in SDK preflight')
    socket.socket.connect=denied; socket.create_connection=denied
    import httpx
    from homeostasis_v3.agent_adapter import ExchangeBudget
    from homeostasis_v3.autonomous import AutonomousRound
    from homeostasis_v3.gemini_preflight import OfflineGeminiExchange
    from homeostasis_v3.physical import load_baseline
    from homeostasis_v3.network import load_network
    from homeostasis_v3.turn import TurnRunner
    from homeostasis_v3.checkpoint import CheckpointStore
    from homeostasis_v3.observation import observe,validate_observation
    from homeostasis_v3.contracts import canonical,digest
    from homeostasis_v3.choices import ensure
    from homeostasis_v3.validation_runner import _write
    args.output.mkdir(parents=True,exist_ok=False)
    baseline=load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
    network=load_network(ROOT/'scenarios/v3/synthetic_network.json',baseline)
    states=[c['state_id'] for c in baseline['world']['countries']]
    report={'artifact_class':'validation_run','api_calls':0,'research_eligible':False,
            'publication_status':'withheld','formal_experiment_ready':False,
            'status':'running','scenarios':[],
            'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted((ROOT/'homeostasis_v3').glob('*.py'))}}
    _write(args.output/'report.json',report)
    try:
        for mode in ('conditional_exchange','all_refuse','missing_offer'):
            path=args.output/mode; path.mkdir()
            def handler(wire):
                request=json.loads(json.loads(wire.content)['contents'][0]['parts'][0]['text'])
                answer={'request_digest':request['request_digest'],'state_id':request['state_id']}
                if request['phase']=='initiative':
                    available=request['payload']['opportunities']
                    a=next(t for t in available if t['route_preference']=='MIL-forward' and t['resource']=='food')
                    b=next(t for t in available if t['route_preference']=='RES-reverse' and t['resource']=='energy')
                    own,other=(a,b) if request['state_id']=='MIL' else (b,a)
                    intents=[]
                    if request['state_id'] in ('MIL','RES') and not (mode=='missing_offer' and request['state_id']=='RES'):
                        intents=[{'opportunity_id':own['choice_id'],'requested_amount':2,'minimum_amount':2,
                                  'allow_partial':False,'conditions':[{'kind':'settled_amount',
                                  'choice_id':other['choice_id'],'minimum_amount':2}],
                                  'public_reason':'合成の接続検証。国家Agentの研究判断ではない。'}]
                    answer.update(initiatives=intents,extension_requests=[])
                else:
                    answer.update(decisions=[],consents={c['choice_id']:mode!='all_refuse' for c in request['payload']['choices']})
                return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{'text':canonical(answer)}]},'finishReason':'STOP'}]})
            exchange=OfflineGeminiExchange(handler=handler,journal_path=path/'attempts.sqlite',
                                            model='offline-model',max_calls=48)
            try:
                runner=TurnRunner(baseline,network,pool_location='MIL',context_id='sdk-'+mode)
                opening=reference=runner.genesis(); store=CheckpointStore(path/'checkpoints')
                store.save(opening,expected_digest=None)
                prior=[]; sources={opening['checkpoint_digest']:opening}
                for turn in range(1,4):
                    round=AutonomousRound(states,exchange=exchange,budget=ExchangeBudget(16),
                                          maximum_amount=100,max_initiatives=4,source='synthetic SDK fixture')
                    cp=runner.run(opening,catalogue=round.catalogue,countries=round.countries())
                    ensure(runner.replay(opening,cp['input'])==cp,'REPLAY_MISMATCH')
                    observation=observe(cp,worldline_id='sdk-'+mode,provisional_reference='sdk-boundary-fixture',
                                        previous=prior,reference=reference,artifact_class='validation_run')
                    sources[cp['checkpoint_digest']]=cp
                    validate_observation(observation,sources)
                    store.save(cp,expected_digest=opening['checkpoint_digest'])
                    _write(path/f'round-{turn}.json',round.record())
                    _write(path/f'observation-{turn}.json',observation)
                    prior.append(cp); opening=cp
                if mode=='conditional_exchange':
                    ensure(len(opening['world_state']['shipments'])==6,'FIXTURE_TRANSFER_MISSING')
                    ensure(any(s['arrival_turn'] is not None for s in opening['world_state']['shipments']),'FIXTURE_ARRIVAL_MISSING')
                else: ensure(not opening['world_state']['shipments'],'FIXTURE_UNEXPECTED_TRANSFER')
                report['scenarios'].append({'fixture':mode,'completed_turns':3,'replay_verified':3,
                    'sdk_mock_dispatches':len(exchange.wire_requests),'checkpoint_digest':opening['checkpoint_digest']})
                _write(path/'transport-config.json',exchange.configuration)
                _write(args.output/'report.json',report)
            finally: exchange.close()
        report['status']='completed'
    except Exception:
        report.update(status='technical_failure',automatic_retry=False)
        _write(args.output/'report.json',report)
        raise RuntimeError('SDK preflight failed; inspect saved evidence, no automatic retry') from None
    _write(args.output/'report.json',report)
    print(canonical({k:v for k,v in report.items() if k!='source_hashes'}))


if __name__=='__main__': main()
