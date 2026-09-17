"""Phase-four synthetic choices only. No Agents, APIs or research worldlines."""
from copy import deepcopy
from dataclasses import replace
from itertools import permutations
from pathlib import Path
import unittest
from unittest.mock import patch
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.network import load_network
from homeostasis_v3.contracts import digest
from homeostasis_v3.choices import Authority, Principal, Envelope, TechnicalFailure, materialize_choice
from homeostasis_v3.settlement import SettlementEngine, Policy
ROOT=Path(__file__).resolve().parents[2]


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.b=load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
        self.n=load_network(ROOT/'scenarios/v3/synthetic_network.json',self.b)
        self.build()

    def build(self, *, pool=None, budget=200000, actions=None):
        self.n['baseline_hash']=digest(self.b)
        self.auth=Authority([c['state_id'] for c in self.b['world']['countries']])
        self.people={c['state_id']:self.auth.issue('country',c['state_id']) for c in self.b['world']['countries']}
        self.core=self.auth.issue('core');self.pool=self.auth.issue('pool')
        self.e=SettlementEngine(self.b,self.n,self.auth,[Policy('baseline'),Policy('no-reserve',False),
            Policy('priority',True,'lexicographic_choice_priority')],pool_location='MIL',context_id='offline-fixture',pool_balances=pool,search_budget=budget,action_registry=actions)
        self.s=self.e.initial

    def choice(self, cid='c1', actor='MIL', target='RES', route='MIL-forward', amount=4,
               partial=True, minimum=1, conditions=None, action='transfer', resource='food', state=None):
        s=self.e.read(self.s if state is None else state)
        template={'choice_id':cid,'actor_state_id':actor,'turn':s['turn'],'snapshot_hash':digest(s),
            'action_type':action,'resource':resource,'maximum_amount':max(amount,1),'target':target,
            'route_preference':route,'conditions':conditions or [],'allow_partial':partial,'minimum_amount':minimum}
        return materialize_choice({'choice_id':cid,'requested_amount':amount,
            'provenance':{'source':'synthetic test fixture','public_reason':'No predicted outcome'}},[template])

    def signatures(self, choices, *, omit=(), denied=()):
        out=[]
        for c in choices:
            for sid,p in [*self.people.items(),('world_pool',self.pool)]:
                if sid not in omit:out.append(self.auth.consent(p,c,accepted=sid not in denied))
        return out

    def run_batch(self, choices, *, policy='baseline', consents=None, state=None):
        submissions=[self.auth.submit(self.people[c['actor_state_id']],c) for c in choices]
        return self.e.settle(self.core,self.s if state is None else state,submissions,
            self.signatures(choices) if consents is None else consents,policy_id=policy)

    def audit(self,s):return self.e.read(s)['audits'][-1]['choices']

    def test_choice_materialization_owns_tuple(self):
        c=self.choice();template={k:v for k,v in c.items() if k not in ('requested_amount','provenance')}
        selection={'choice_id':'c1','requested_amount':4,'provenance':c['provenance'],'target':'ECON'}
        with self.assertRaises(TechnicalFailure):materialize_choice(selection,[template])
        with self.assertRaises(TechnicalFailure):materialize_choice({k:v for k,v in selection.items() if k!='target'},[template,template])

    def test_intent_does_not_mutate(self):
        before=self.e.read(self.s);c=self.choice();self.auth.submit(self.people['MIL'],c)
        self.assertEqual(self.e.read(self.s),before)
        c['world_patch']={'food':500}
        with self.assertRaises(TechnicalFailure):self.auth.submit(self.people['MIL'],c)

    def test_individual_success(self):
        c=self.choice();p=self.e.individual_feasibility(self.s,self.auth.submit(self.people['MIL'],c),self.signatures([c]),'baseline')
        self.assertEqual(p['feasible_amount'],4)
        self.assertEqual(p['reason_codes'],[])

    def test_stock_and_essential_reserve(self):
        self.b['world']['accounts'][0]['balance']=2;self.build()
        c=self.choice(amount=4)
        r=self.audit(self.run_batch([c]))[0]
        self.assertEqual(r['settled_amount'],0)
        self.assertIn('INSUFFICIENT_STOCK',r['reason_codes']);self.assertIn('ESSENTIAL_RESERVE_CONFLICT',r['reason_codes'])

    def test_reserve_policy_exchange(self):
        self.b['world']['accounts'][0]['balance']=20;self.build();c=self.choice(amount=4)
        self.assertEqual(self.audit(self.run_batch([c]))[0]['settled_amount'],2)
        self.build();c=self.choice(amount=4)
        self.assertEqual(self.audit(self.run_batch([c],policy='no-reserve'))[0]['settled_amount'],4)

    def test_no_route(self):
        r=self.audit(self.run_batch([self.choice(route='unknown')]))[0]
        self.assertFalse(r['established']);self.assertIn('NO_ROUTE',r['reason_codes'])

    def test_invalid_target(self):
        r=self.audit(self.run_batch([self.choice(target='ECON')]))[0]
        self.assertIn('INVALID_TARGET',r['reason_codes'])

    def test_invalid_resource(self):
        r=self.audit(self.run_batch([self.choice(resource='unknown')]))[0]
        self.assertIn('INVALID_RESOURCE',r['reason_codes'])

    def test_route_unavailable(self):
        self.n['routes'][0]['availability']=False;self.build()
        self.assertIn('ROUTE_UNAVAILABLE',self.audit(self.run_batch([self.choice()]))[0]['reason_codes'])

    def test_partial_vs_full(self):
        r=self.audit(self.run_batch([self.choice(amount=10)]))[0]
        self.assertEqual(r['settled_amount'],6);self.assertIn('ROUTE_CAPACITY_EXCEEDED',r['reason_codes'])
        self.build();r=self.audit(self.run_batch([self.choice(amount=10,partial=False)]))[0]
        self.assertEqual(r['settled_amount'],0);self.assertIn('FULL_AMOUNT_REQUIRED',r['reason_codes'])

    def test_minimum_partial(self):
        r=self.audit(self.run_batch([self.choice(amount=10,minimum=7)]))[0]
        self.assertIn('MINIMUM_AMOUNT_NOT_MET',r['reason_codes'])

    def test_missing_and_refused_consent(self):
        c=self.choice();r=self.audit(self.run_batch([c],consents=self.signatures([c],omit=('RES',))))[0]
        self.assertIn('MISSING_CONSENT',r['reason_codes'])
        self.build();c=self.choice();r=self.audit(self.run_batch([c],consents=self.signatures([c],denied=('RES',))))[0]
        self.assertIn('CONSENT_REFUSED',r['reason_codes'])

    def test_shared_individually_feasible_joint_scaled(self):
        self.n['shared_capacities'][0]['capacity']=7;self.build()
        cs=[self.choice(amount=5),self.choice('c2','ISLAND','ECON','ISLAND-forward',5)]
        for c in cs:self.assertEqual(self.e.individual_feasibility(self.s,self.auth.submit(self.people[c['actor_state_id']],c),self.signatures([c]),'baseline')['feasible_amount'],5)
        rows=self.audit(self.run_batch(cs))
        self.assertEqual(sorted(r['settled_amount'] for r in rows),[3,4])
        self.assertTrue(any('SHARED_CAPACITY_CONFLICT' in r['reason_codes'] for r in rows))

    def test_joint_full_only_one(self):
        self.n['shared_capacities'][0]['capacity']=7;self.build()
        cs=[self.choice(amount=5,partial=False),self.choice('c2','ISLAND','ECON','ISLAND-forward',5,False)]
        self.assertEqual(sorted(r['settled_amount'] for r in self.audit(self.run_batch(cs))),[0,5])

    def test_duplicate_reservation(self):
        self.b['world']['accounts'][0]['balance']=24;self.build()
        cs=[self.choice(amount=5),self.choice('c2','MIL','NEUTRAL','MIL-reverse',5)]
        rows=self.audit(self.run_batch(cs));self.assertEqual(sum(r['settled_amount'] for r in rows),6)
        self.assertTrue(any('DOUBLE_RESERVATION' in r['reason_codes'] for r in rows))

    def test_mutual_participation_cycle(self):
        cs=[self.choice(conditions=[{'kind':'participation','choice_id':'c2','minimum_amount':0}]),
            self.choice('c2','RES','MIL','RES-reverse',4,conditions=[{'kind':'participation','choice_id':'c1','minimum_amount':0}])]
        self.assertTrue(all(r['established'] for r in self.audit(self.run_batch(cs))))

    def test_settled_quantity_condition(self):
        cs=[self.choice(conditions=[{'kind':'settled_amount','choice_id':'c2','minimum_amount':5}]),
            self.choice('c2','RES','MIL','RES-reverse',4)]
        rows=self.audit(self.run_batch(cs));self.assertEqual(rows[0]['settled_amount'],0)
        self.assertIn('CONDITION_NOT_MET',rows[0]['reason_codes'])

    def test_arrival_is_not_dispatch(self):
        cs=[self.choice(conditions=[{'kind':'arrived_amount','choice_id':'c2','minimum_amount':4}]),
            self.choice('c2','RES','MIL','RES-reverse',4)]
        self.assertEqual(self.audit(self.run_batch(cs))[0]['settled_amount'],0)

    def test_past_arrival_condition(self):
        sent=self.run_batch([self.choice()]);arrived=self.e.arrive(self.core,sent,turn=1)
        c=self.choice('c2','RES','MIL','RES-reverse',3,state=arrived,
            conditions=[{'kind':'arrived_amount','choice_id':'c1','minimum_amount':4}])
        self.assertTrue(self.audit(self.run_batch([c],state=arrived))[0]['established'])

    def test_delay_ownership_conservation(self):
        before=self.e.read(self.s);sent=self.run_batch([self.choice()]);s=self.e.read(sent)
        self.assertEqual(s['stock']['MIL']['food'],64);self.assertEqual(s['stock']['RES']['food'],72)
        sh=s['shipments'][0];self.assertEqual((sh['owner'],sh['arrived_amount'],sh['dispatched_amount']),('RES',0,4))
        arrived=self.e.arrive(self.core,sent,turn=1);after=self.e.read(arrived)
        self.assertEqual(after['stock']['RES']['food'],76)
        self.assertEqual(self.e._totals(before),self.e._totals(after))
        with self.assertRaises(TechnicalFailure):self.e.arrive(self.core,sent,turn=2)

    def test_duplicate_choice_is_technical(self):
        c=self.choice()
        with self.assertRaises(TechnicalFailure) as error:self.run_batch([c,c])
        self.assertEqual(error.exception.code,'CHOICE_ID_COLLISION')
        self.run_batch([c])  # Original head still valid after rejected batch.

    def test_choice_id_reuse_across_turns(self):
        sent=self.run_batch([self.choice()]);arrived=self.e.arrive(self.core,sent,turn=1)
        c=self.choice(state=arrived)
        with self.assertRaises(TechnicalFailure) as error:self.run_batch([c],state=arrived)
        self.assertEqual(error.exception.code,'CHOICE_ID_COLLISION')

    def test_tampered_choice_signature(self):
        c=self.choice();signed=self.auth.submit(self.people['MIL'],c)
        altered=Envelope(signed.payload.replace('"requested_amount":4','"requested_amount":5'),signed.signature)
        with self.assertRaises(TechnicalFailure):self.e.settle(self.core,self.s,[altered],self.signatures([c]),policy_id='baseline')

    def test_stale_consent(self):
        c=self.choice();old=self.signatures([c]);c['requested_amount']=3
        with self.assertRaises(TechnicalFailure):self.run_batch([c],consents=old)

    def test_coordinator_and_evaluator_no_authority(self):
        c=self.choice()
        for role in ['coordinator','evaluator']:
            p=self.auth.issue(role)
            with self.subTest(role=role),self.assertRaises(TechnicalFailure):self.auth.submit(p,c)
            with self.assertRaises(TechnicalFailure):self.auth.consent(p,c,accepted=True)
            with self.assertRaises(TechnicalFailure):self.e.settle(p,self.s,[],[],policy_id='baseline')
            with self.assertRaises(TechnicalFailure):self.e.arrive(p,self.s,turn=1)

    def test_forged_principal(self):
        with self.assertRaises(TechnicalFailure):self.auth.submit(Principal('country','MIL'),self.choice())

    def test_rollback_after_internal_exception(self):
        before=self.s;c=self.choice()
        with patch.object(self.e,'_validate_state',side_effect=TechnicalFailure('FAULT_INJECTION')):
            with self.assertRaises(TechnicalFailure):self.run_batch([c])
        self.assertEqual(self.s,before)
        self.assertTrue(self.audit(self.run_batch([c]))[0]['established'])

    def test_exact_search_budget_fails_closed(self):
        self.build(budget=1);c=self.choice()
        with self.assertRaises(TechnicalFailure) as error:self.run_batch([c])
        self.assertEqual(error.exception.code,'SEARCH_BUDGET_EXCEEDED')
        self.assertEqual(self.e.read(self.s)['shipments'],[])

    def test_policy_selection_logged(self):
        rows=self.audit(self.run_batch([self.choice()],policy='priority'))
        self.assertEqual(rows[0]['policy']['allocation'],'lexicographic_choice_priority')
        self.assertNotIn('homeostasis',rows[0]['policy'])

    def test_unknown_policy(self):
        with self.assertRaises(TechnicalFailure):self.run_batch([self.choice()],policy='invented')

    def test_action_contract_extension(self):
        self.build(actions={'aid-v2':'transfer'})
        self.assertTrue(self.audit(self.run_batch([self.choice(action='aid-v2')]))[0]['established'])

    def test_future_action_not_implicitly_allowed(self):
        with self.assertRaises(TechnicalFailure):self.run_batch([self.choice(action='magic-recovery')])

    def test_pool_competition(self):
        self.build(pool={'food':5,'energy':0})
        cs=[self.choice('c1','RES','RES','MIL-forward',4,action='pool_withdraw'),
            self.choice('c2','FOOD','RES','MIL-forward',4,action='pool_withdraw')]
        rows=self.audit(self.run_batch(cs));self.assertEqual(sum(r['settled_amount'] for r in rows),5)
        self.assertTrue(any('POOL_CONFLICT' in r['reason_codes'] for r in rows))

    def test_same_turn_deposit_cannot_fund_draw(self):
        cs=[self.choice('c1','RES','world_pool','RES-reverse',4,action='pool_deposit'),
            self.choice('c2','FOOD','RES','MIL-forward',4,action='pool_withdraw')]
        result=self.run_batch(cs);rows=self.audit(result)
        self.assertEqual([r['settled_amount'] for r in rows],[4,0])
        self.assertEqual(self.e.read(result)['pool']['food'],0)
        a=self.e.arrive(self.core,result,turn=2);self.assertEqual(self.e.read(a)['pool']['food'],4)

    def test_pool_requires_delegation(self):
        self.build(pool={'food':5,'energy':0});c=self.choice('c1','RES','RES','MIL-forward',4,action='pool_withdraw')
        row=self.audit(self.run_batch([c],consents=self.signatures([c],omit=('world_pool',))))[0]
        self.assertIn('MISSING_CONSENT',row['reason_codes'])

    def test_input_order_independent(self):
        results=[]
        for order in permutations(range(3)):
            self.build()
            cs=[self.choice('c1',amount=4),self.choice('c2','ISLAND','ECON','ISLAND-forward',4),self.choice('c3','RES','MIL','RES-reverse',4)]
            result=self.run_batch([cs[i] for i in order]);results.append(self.e.read(result))
        self.assertTrue(all(r==results[0] for r in results))

    def test_empty_turn_is_valid(self):
        result=self.run_batch([])
        self.assertEqual(self.audit(result),[])
        self.assertEqual(self.e.read(result)['stock'],self.e.read(self.s)['stock'])

    def test_unknown_condition_is_technical(self):
        c=self.choice(conditions=[{'kind':'participation','choice_id':'missing','minimum_amount':0}])
        with self.assertRaises(TechnicalFailure):self.run_batch([c])

    def test_world_rejection_returns_audit_not_exception(self):
        c=self.choice(route='missing')
        self.assertFalse(self.audit(self.run_batch([c]))[0]['established'])

    def test_no_second_batch_priority_same_turn(self):
        result=self.run_batch([self.choice()]);c=self.choice('c2',state=result)
        with self.assertRaises(TechnicalFailure) as error:self.run_batch([c],state=result)
        self.assertEqual(error.exception.code,'TURN_ALREADY_SETTLED')

    def test_commit_cas_rejects_stale_parallel_candidate(self):
        original=self.e.read(self.s)
        self.run_batch([self.choice()])
        with self.assertRaises(TechnicalFailure) as error:self.e._commit(original,original)
        self.assertEqual(error.exception.code,'STALE_STATE')

    def test_context_trace_identity(self):
        c=self.choice();row=self.audit(self.run_batch([c]))[0]
        self.assertEqual(row['trace_id'],digest({'context_id':'offline-fixture','choice_id':'c1'}))
        self.assertNotEqual(row['trace_id'],digest({'context_id':'other-fixture','choice_id':'c1'}))

    def test_signed_state_cannot_be_patched(self):
        changed=Envelope(self.s.payload.replace('"food":68','"food":999'),self.s.signature)
        with self.assertRaises(TechnicalFailure):self.e.arrive(self.core,changed,turn=1)

    def test_owner_refusal_overrides_submission(self):
        c=self.choice();row=self.audit(self.run_batch([c],consents=self.signatures([c],denied=('MIL',))))[0]
        self.assertIn('CONSENT_REFUSED',row['reason_codes'])

    def test_input_arrays_cannot_change_engine_routes(self):
        self.n['routes'][0]['capacity']=0
        self.assertEqual(self.audit(self.run_batch([self.choice()]))[0]['settled_amount'],4)

    def test_no_assumed_production_stock(self):
        self.b['world']['accounts'][0]['balance']=0;self.build()
        row=self.audit(self.run_batch([self.choice()]))[0]
        self.assertEqual(row['settled_amount'],0)
        self.assertIn('INSUFFICIENT_STOCK',row['reason_codes'])

    def test_route_resource_and_transport_limits(self):
        self.n['routes'][0]['resource_types']=['energy'];self.build()
        self.assertIn('ROUTE_RESOURCE_MISMATCH',self.audit(self.run_batch([self.choice()]))[0]['reason_codes'])
        self.setUp();self.n['routes'][0]['capacity']=50;self.n['shared_capacities'][0]['capacity']=50;self.build()
        self.assertIn('TRANSPORT_CAPACITY_EXCEEDED',self.audit(self.run_batch([self.choice(amount=20)]))[0]['reason_codes'])

    def test_consents_cannot_be_forged_by_another_authority(self):
        other=Authority(self.people.keys());p=other.issue('country','RES');c=self.choice()
        with self.assertRaises(TechnicalFailure):self.run_batch([c],consents=[other.consent(p,c,accepted=True)])

    def test_zero_amount_is_schema_failure(self):
        with self.assertRaises(TechnicalFailure):self.choice(amount=0)

    def test_joint_conditions_can_disable_mutual_group(self):
        self.n['shared_capacities'][0]['capacity']=7;self.build()
        cs=[self.choice(amount=5,partial=False,conditions=[{'kind':'participation','choice_id':'c2','minimum_amount':0}]),
            self.choice('c2','ISLAND','ECON','ISLAND-forward',5,False,conditions=[{'kind':'participation','choice_id':'c1','minimum_amount':0}])]
        self.assertEqual([r['settled_amount'] for r in self.audit(self.run_batch(cs))],[0,0])

    def test_eight_independent_states_fixture(self):
        states=[c['state_id'] for c in self.b['world']['countries']]
        cs=[self.choice('c'+str(i),actor,states[(i+1)%len(states)],actor+'-forward',1)
            for i,actor in enumerate(states)]
        rows=self.audit(self.run_batch(cs))
        self.assertEqual(len(rows),8)
        self.assertTrue(all(r['settled_amount']==1 for r in rows))

    def test_arrival_rollback(self):
        sent=self.run_batch([self.choice()]);before=self.e.read(sent)
        with patch.object(self.e,'_validate_state',side_effect=TechnicalFailure('FAULT_INJECTION')):
            with self.assertRaises(TechnicalFailure):self.e.arrive(self.core,sent,turn=1)
        self.assertEqual(self.e.read(sent),before)
        self.e.arrive(self.core,sent,turn=1)

    def test_pool_arrived_stock_can_be_used_next_turn(self):
        c=self.choice('deposit','RES','world_pool','RES-reverse',4,action='pool_deposit')
        s=self.run_batch([c]);s=self.e.arrive(self.core,s,turn=2)
        draw=self.choice('draw','RES','RES','MIL-forward',4,action='pool_withdraw',state=s)
        s=self.run_batch([draw],state=s)
        self.assertEqual(self.audit(s)[0]['settled_amount'],4)
        self.assertEqual(self.e.read(s)['pool']['food'],0)

    def test_configuration_mutation_rejected(self):
        self.e.network['routes'][0]['capacity']=1000
        with self.assertRaises(TechnicalFailure) as error:self.run_batch([self.choice()])
        self.assertEqual(error.exception.code,'CONFIGURATION_CHANGED')
