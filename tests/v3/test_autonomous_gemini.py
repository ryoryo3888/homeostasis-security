"""Synthetic decisions through real SDK serialization; network denied by suite."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from homeostasis_v3.agent_adapter import ExchangeBudget
from homeostasis_v3.autonomous import AutonomousRound, opportunities
from homeostasis_v3.gemini_preflight import OfflineGeminiExchange, AttemptJournal
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical,digest
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.network import load_network
from homeostasis_v3.turn import TurnRunner,TurnFailure,Snapshot

ROOT=Path(__file__).resolve().parents[2]


def synthetic_response(request, *, refuse=False, extensions=()):
    """Two independently authored, mutually conditional exchange fixtures."""
    reply={'request_digest':request['request_digest'],'state_id':request['state_id']}
    if request['phase']=='initiative':
        available=request['payload']['opportunities']
        a=next(t for t in available if t['route_preference']=='MIL-forward' and t['resource']=='food')
        b=next(t for t in available if t['route_preference']=='RES-reverse' and t['resource']=='energy')
        own,other=(a,b) if request['state_id']=='MIL' else (b,a)
        initiatives=[]
        if request['state_id'] in ('MIL','RES'):
            initiatives=[{'opportunity_id':own['choice_id'],'requested_amount':2,'minimum_amount':2,
                          'allow_partial':False,'conditions':[{'kind':'settled_amount',
                          'choice_id':other['choice_id'],'minimum_amount':2}],
                          'public_reason':'Synthetic conditional exchange / 合成検証'}]
        reply.update(initiatives=initiatives,extension_requests=list(extensions))
    else:
        reply.update(decisions=[],consents={c['choice_id']:not refuse for c in request['payload']['choices']})
    return reply


def provider_response(answer, *, finish='STOP', usage=True):
    body={'candidates':[{'content':{'parts':[{'text':canonical(answer)}],'role':'model'},'finishReason':finish}]}
    if usage: body['usageMetadata']={'promptTokenCount':10,'candidatesTokenCount':20,'totalTokenCount':30}
    return httpx.Response(200,json=body)


class AutonomousTests(unittest.TestCase):
    def setUp(self):
        self.baseline=load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
        self.network=load_network(ROOT/'scenarios/v3/synthetic_network.json',self.baseline)
        self.states=[c['state_id'] for c in self.baseline['world']['countries']]
        self.runner=TurnRunner(self.baseline,self.network,pool_location='MIL',context_id='autonomous-fixture')
        self.opening=self.runner.genesis()
        self.requests=[]

    def make_round(self,mutate=None,refuse=False):
        def exchange(raw):
            request=json.loads(raw); self.requests.append(request)
            answer=synthetic_response(request,refuse=refuse)
            if mutate: mutate(answer,request)
            return canonical(answer)
        return AutonomousRound(self.states,exchange=exchange,budget=ExchangeBudget(16),
                               maximum_amount=100,max_initiatives=4,source='synthetic fixture')

    def run_round(self,round,opening=None,**kwargs):
        return self.runner.run(opening or self.opening,catalogue=round.catalogue,
                               countries=round.countries(),**kwargs)

    def test_conditional_exchange_independent_without_coordinator(self):
        round=self.make_round(); cp=self.run_round(round)
        self.assertEqual(len(cp['world_state']['shipments']),2)
        self.assertTrue(all(s['dispatched_amount']==2 for s in cp['world_state']['shipments']))
        self.assertIsNone(cp['input']['proposal'])
        self.assertEqual(len(self.requests),16)
        self.assertEqual({r['observation_digest'] for r in self.requests}, {round.observation_hash})
        initiatives=[r for r in self.requests if r['phase']=='initiative']
        self.assertEqual(len(initiatives),8)
        self.assertTrue(all('plans' not in r['payload'] for r in initiatives))
        self.assertEqual(self.runner.replay(self.opening,cp['input']),cp)
        self.assertEqual(len(self.requests),16)

    def test_all_refusals_remain_valid_world(self):
        cp=self.run_round(self.make_round(refuse=True))
        self.assertEqual(cp['turn'],1)
        self.assertEqual(cp['world_state']['shipments'],[])

    def test_missing_reciprocal_offer_is_not_fabricated(self):
        def only_one(a,r):
            if r['phase']=='initiative' and r['state_id']=='RES': a['initiatives']=[]
        cp=self.run_round(self.make_round(only_one))
        self.assertFalse(cp['world_state']['shipments'])
        self.assertEqual(sum(len(v) for v in cp['input']['selections'].values()),1)
        self.assertEqual(len(cp['history'][0]['settlement']['choices']),1)
        self.assertIn('CONDITION_NOT_MET',cp['history'][0]['settlement']['choices'][0]['reason_codes'])
        self.assertEqual(self.runner.replay(self.opening,cp['input']),cp)

    def test_extensible_requests_preserved_but_not_executed(self):
        def extension(a,r):
            if r['phase']=='initiative': a['extension_requests']=['備蓄技術への投資を提案']
        round=self.make_round(extension); cp=self.run_round(round)
        self.assertEqual(len(round.record()['extension_requests']),8)
        self.assertEqual(round.record()['extension_status'],'unimplemented_not_executed')
        self.assertEqual(cp['audit']['RECOVERY']['applied'],[])

    def test_scope_record_does_not_change_inputs_or_world(self):
        round=self.make_round(); cp=self.run_round(round)
        before=deepcopy(cp); requests=deepcopy(self.requests)
        record=round.record(); scope=record['decision_scope']
        self.assertEqual(scope['executable_action_types'],['transfer'])
        self.assertEqual(scope['route_scope'],'existing_one_hop_routes')
        self.assertEqual(scope['extension_requests'],'recorded_only_not_executable')
        self.assertFalse(scope['general_action_execution'])
        self.assertEqual(scope['coordinator_protocol'],'not_configured')
        scope['executable_action_types'].append('invented')
        self.assertEqual(round.record()['decision_scope']['executable_action_types'],['transfer'])
        self.assertEqual(self.requests,requests)
        self.assertEqual(cp,before)
        self.assertEqual(self.runner.replay(self.opening,cp['input']),cp)

    def test_forged_authority_and_terms_rejected(self):
        mutations=[lambda a,r:a.update(world_state={}),
                   lambda a,r:a.update(state_id='OTHER'),
                   lambda a,r:a.update(request_digest='0'*64),
                   lambda a,r:a['initiatives'][0].update(requested_amount=True),
                   lambda a,r:a['initiatives'][0].update(requested_amount=101),
                   lambda a,r:a['initiatives'][0].update(allow_partial='yes'),
                   lambda a,r:a['initiatives'][0].update(conditions=[{'kind':'participation','choice_id':'invented','minimum_amount':0}]),
                   lambda a,r:a['initiatives'][0].update(opportunity_id=next(t['choice_id'] for t in r['payload']['opportunities'] if t['actor_state_id']!='MIL'))]
        for mutation in mutations:
            def modify(a,r):
                if r['phase']=='initiative' and r['state_id']=='MIL': mutation(a,r)
            round=self.make_round(modify)
            with self.subTest(mutation=mutations.index(mutation)):
                with self.assertRaises(TurnFailure): self.run_round(round)
                self.assertTrue(round.failed)
                with self.assertRaises(TechnicalFailure): round.catalogue(Snapshot.of({}))

    def test_unavailable_routes_are_not_hidden_or_rerouted(self):
        shock={'event_id':'route-stop-fixture','kind':'route_stop','target':'MIL-forward',
               'resource':None,'amount':0,'evidence':'synthetic route failure'}
        cp=self.run_round(self.make_round(),shocks=[shock])
        self.assertEqual(sum(len(v) for v in cp['input']['selections'].values()),2)
        self.assertFalse(cp['world_state']['shipments'])
        choice=next(c for c in cp['history'][0]['settlement']['choices'] if c['individual']['reason_codes'])
        self.assertIn('ROUTE_UNAVAILABLE',choice['individual']['reason_codes'])

    def test_other_route_is_authored_not_automatically_chosen(self):
        def alternate(a,r):
            if r['phase']=='initiative':
                a['initiatives']=[]
                if r['state_id']=='MIL':
                    t=next(t for t in r['payload']['opportunities'] if t['route_preference']=='MIL-cross' and t['resource']=='food')
                    a['initiatives']=[{'opportunity_id':t['choice_id'],'requested_amount':1,
                        'minimum_amount':1,'allow_partial':False,'conditions':[],'public_reason':'Synthetic independently chosen route'}]
        cp=self.run_round(self.make_round(alternate))
        self.assertEqual(len(cp['world_state']['shipments']),1)
        self.assertEqual(cp['world_state']['shipments'][0]['target'],'SMALL')

    def test_new_turn_cannot_reuse_round(self):
        round=self.make_round(); cp=self.run_round(round)
        with self.assertRaises(TurnFailure): self.run_round(round,cp)

    def test_fixture_order_cannot_leak_earlier_plans(self):
        a=self.make_round(); cp=self.run_round(a)
        payloads=[r['payload'] for r in self.requests if r['phase']=='initiative']
        self.assertEqual(len({digest(p) for p in payloads}),1)
        self.states.reverse()
        b=self.make_round(); self.assertEqual(self.run_round(b),cp)

    def test_stale_unselected_catalogue_entry_is_rejected(self):
        round=self.make_round()
        def stale(view):
            templates=round.catalogue(view)
            templates[0]['snapshot_hash']='0'*64
            return templates
        with self.assertRaises(TurnFailure):
            self.runner.run(self.opening,catalogue=stale,countries=round.countries())


class SDKTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'journal.sqlite'
        self.sent=[]

    def request(self, *, sid='MIL',turn=1):
        r={'version':'v3','phase':'consent','state_id':sid,'observation':{'turn':turn},
           'observation_digest':digest({'turn':turn}),'payload':{'choices':[]}}
        return {**r,'request_digest':digest(r)}

    def exchange(self,handler=None,**kwargs):
        def success(wire):
            self.sent.append(wire)
            r=json.loads(json.loads(wire.content)['contents'][0]['parts'][0]['text'])
            return provider_response({'request_digest':r['request_digest'],'state_id':r['state_id'],
                                      'decisions':[],'consents':{}},usage=False)
        exchange=OfflineGeminiExchange(handler=handler or success,journal_path=self.path,
                                        model='offline-model',max_calls=kwargs.pop('max_calls',4),**kwargs)
        self.addCleanup(exchange.close)
        return exchange

    def test_real_sdk_serializes_unicode_schema_prompt_and_limits(self):
        e=self.exchange(max_output_tokens=321)
        r=self.request(); r['payload']['note']='日本語の観測'
        r['request_digest']=digest({k:v for k,v in r.items() if k!='request_digest'})
        result=json.loads(e(canonical(r)))
        self.assertEqual(result['state_id'],'MIL')
        body=e.wire_requests[0]
        self.assertIn('日本語',body['contents'][0]['parts'][0]['text'])
        self.assertEqual(body['generationConfig']['maxOutputTokens'],321)
        self.assertEqual(body['generationConfig']['responseMimeType'],'application/json')
        self.assertIn('responseJsonSchema',body['generationConfig'])
        self.assertIn('systemInstruction',body)
        record=e.journal.records()[0]
        self.assertEqual(record['status'],'response_validated')
        self.assertTrue(all(v is None for v in record['usage'].values()))
        self.assertNotIn('offline-dummy',self.path.read_bytes().decode('latin1'))

    def test_real_sdk_503_and_timeout_never_retry(self):
        for mode in ('503','timeout'):
            with self.subTest(mode=mode):
                calls=[]; path=Path(self.temp.name)/(mode+'.sqlite')
                def fail(request):
                    calls.append(request)
                    if mode=='timeout': raise httpx.ReadTimeout('sensitive timeout',request=request)
                    return httpx.Response(503,json={'error':{'code':503,'message':'sensitive error','status':'UNAVAILABLE'}})
                e=OfflineGeminiExchange(handler=fail,journal_path=path,model='offline-model',max_calls=3)
                self.addCleanup(e.close)
                with self.assertRaisesRegex(TechnicalFailure,'SDK_OR_RESPONSE_FAILURE_NO_RETRY'): e(canonical(self.request()))
                with self.assertRaises(TechnicalFailure): e(canonical(self.request(turn=2)))
                self.assertEqual(len(calls),1)
                self.assertEqual(e.journal.records()[0]['status'],'failed')
                self.assertNotIn('sensitive',path.read_bytes().decode('latin1'))

    def test_journal_blocks_duplicate_across_restart(self):
        e=self.exchange(); e(canonical(self.request()))
        restarted=self.exchange()
        with self.assertRaises(TechnicalFailure): restarted(canonical(self.request()))
        self.assertEqual(len(self.sent),1)

    def test_crash_reservation_blocks_later_requests(self):
        e=self.exchange(); e.journal.reserve(self.request())
        restarted=self.exchange()
        with self.assertRaises(TechnicalFailure): restarted(canonical(self.request(turn=2)))
        self.assertFalse(self.sent)
        self.assertEqual(e.journal.records()[0]['status'],'reserved')

    def test_budget_and_configuration_binding(self):
        e=self.exchange(max_calls=1); e(canonical(self.request()))
        with self.assertRaises(TechnicalFailure): e(canonical(self.request(turn=2)))
        with self.assertRaises(TechnicalFailure): self.exchange(max_calls=2)
        self.assertEqual(len(self.sent),1)

    def test_invalid_request_rejected_before_sdk(self):
        e=self.exchange(max_input_bytes=500)
        for raw in (' '*501,canonical({**self.request(),'request_digest':'0'*64})):
            with self.assertRaises(TechnicalFailure): e(raw)
        self.assertFalse(self.sent); self.assertFalse(e.journal.records())

    def test_configuration_cannot_be_widened_during_run(self):
        e=self.exchange(max_calls=1)
        e.configuration['max_calls']=100
        with self.assertRaises(TechnicalFailure): e(canonical(self.request()))
        e.journal.configuration['max_calls']=100
        with self.assertRaises(TechnicalFailure): e.journal.reserve(self.request())
        self.assertFalse(self.sent)

    def test_truncated_or_misbound_reply_blocks_subsequent_dispatch(self):
        for mode in ('truncated','misbound','invalid_json'):
            path=Path(self.temp.name)/(mode+'.sqlite')
            def handler(wire):
                r=json.loads(json.loads(wire.content)['contents'][0]['parts'][0]['text'])
                a={'request_digest':r['request_digest'],'state_id':'OTHER' if mode=='misbound' else r['state_id'],
                   'decisions':[],'consents':{}}
                if mode=='invalid_json':
                    return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'not JSON'}]},'finishReason':'STOP'}]})
                return provider_response(a,finish='MAX_TOKENS' if mode=='truncated' else 'STOP')
            e=OfflineGeminiExchange(handler=handler,journal_path=path,model='offline-model',max_calls=3)
            self.addCleanup(e.close)
            with self.assertRaises(TechnicalFailure): e(canonical(self.request()))
            with self.assertRaises(TechnicalFailure): e(canonical(self.request(turn=2)))
            self.assertEqual(len(e.wire_requests),1)

    def test_end_to_end_real_sdk_country_choices_settlement_and_replay(self):
        b=load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json'); n=load_network(ROOT/'scenarios/v3/synthetic_network.json',b)
        def handler(wire):
            r=json.loads(json.loads(wire.content)['contents'][0]['parts'][0]['text'])
            return provider_response(synthetic_response(r))
        e=OfflineGeminiExchange(handler=handler,journal_path=self.path,model='offline-model',max_calls=16)
        self.addCleanup(e.close)
        round=AutonomousRound([c['state_id'] for c in b['world']['countries']],exchange=e,
                              budget=ExchangeBudget(16),maximum_amount=100,max_initiatives=4,source='synthetic SDK fixture')
        runner=TurnRunner(b,n,pool_location='MIL',context_id='sdk-fixture'); opening=runner.genesis()
        result=runner.run(opening,catalogue=round.catalogue,countries=round.countries())
        self.assertEqual(len(result['world_state']['shipments']),2)
        self.assertEqual(len(e.wire_requests),16)
        self.assertEqual(runner.replay(opening,result['input']),result)
        self.assertEqual(len(e.wire_requests),16)
        self.assertEqual(e.journal.records()[0]['usage']['input_tokens'],10)


if __name__=='__main__': unittest.main()
