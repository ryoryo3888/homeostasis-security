"""Saved real decisions and synthetic boundary cases; no Gemini client or calls."""
import copy
import hashlib
import itertools
import json
import math
import random
from pathlib import Path
import unittest

from final_experiment_runner import COUNTRIES, _initial_states, load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES, load_resource_network
from homeostasis_core.feasibility import settle_atomic_actions, feasible_actions
from homeostasis_core.gemini_agents import apply_structured_actions, parse_country_choice_json, derive_event
from homeostasis_core.emergent_dynamics import reconstruction_step

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT/'tests/fixtures/settlement_20260917T071205Z.json'

class MixedSettlementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = json.loads(FIXTURE.read_text())
        cls.network = load_resource_network(ROOT/'scenarios/resource_network_sample.json', COUNTRIES)

    def execute(self, states, answers, world, damage, turn, pool, policy):
        return apply_structured_actions(states, answers, world, damage, turn,
            world_pool=pool, resource_network=self.network, network_policy=policy)

    def test_saved_turns_one_two_full_world_reconstruction_and_evaluator(self):
        states = _initial_states(load_country_configuration(ROOT/'config/country_archetypes.json'))
        for t in self.f['turns']:
            s=t['snapshot']
            out=self.execute(states,t['country_responses'],s['world'],s['damage'],t['turn'],s['world_pool'],s['network_policy'])
            out['causal_record']['event']=s['event']
            evaluator=next(c for c in self.f['calls'] if c['turn']==t['turn'] and c['agent_type']=='evaluator')
            self.assertEqual(out,evaluator['public_observation_payload']['executed_true_state'])
            recovery=reconstruction_step(s['damage'],out,out['country_states'])
            out['reconstruction']=recovery;out['causal_record']['farmland_reconstruction']=recovery
            self.assertEqual(out,t['executed_state'])
            states=out['country_states']
        self.assertEqual(states,self.f['turn3_opening']['country_states'])

    def test_all_saved_country_answers_strictly_parse_unchanged(self):
        count=0
        for c in self.f['calls']:
            if c['agent_type']!='country': continue
            p=c['public_observation_payload'];a=c['model_response']
            parsed=parse_country_choice_json(json.dumps(a),c['agent_id'],a['proposal_id'],set(COUNTRIES),p['action_choices'],p['action_choices'])
            self.assertEqual(parsed,c['structured_response']);count+=1
        self.assertEqual(count,24)

    def test_turn_three_counterfactual_all_orders_and_no_input_mutation(self):
        s=self.f['turn3_opening'];before=copy.deepcopy(s)
        answers={c['agent_id']:c['structured_response'] for c in self.f['calls'] if c['turn']==3 and c['agent_type']=='country'}
        def replay(a):return self.execute(s['country_states'],a,s['current_world'],s['current_damage'],3,s['world_pool'],s['network_policy'])
        out=replay(answers)
        self.assertEqual(len(out['participants']),8)
        rows={r['agent_id']:r for r in out['atomic_settlements']}
        for agent,requested in [('MIL',5),('FOOD',20),('FRAGILE',65.2)]:
            self.assertAlmostEqual(rows[agent]['realized'],requested*65.2/90.2)
        self.assertAlmostEqual(out['world_pool']['logistics'],100-(20+65.2)*65.2/90.2)
        # All 8! orders check the shared allocator cheaply; full effects checked
        # on forward/reverse orders plus the saved TURN1/2 replay above.
        intents={c:a['action'] for c,a in answers.items()}
        expected=settle_atomic_actions(s['country_states'],intents,s['world_pool'])
        for order in itertools.permutations(intents):
            self.assertEqual(settle_atomic_actions(s['country_states'],{c:intents[c] for c in order},s['world_pool']),expected)
        self.assertEqual(out,replay(dict(reversed(list(answers.items())))))
        self.assertEqual(s,before)
        self.assertTrue(math.isfinite(reconstruction_step(s['current_damage'],out,out['country_states'])['after']))
        event=derive_event(s['current_world'],s['history_state'],self.f['turns'][-1]['executed_state']['action_counts'],[t['snapshot']['event'] for t in self.f['turns']])
        self.assertEqual(event,'物流・配分競合')

    def action(self,kind,target,resource,amount,recipient='country'):
        return {'action_id':kind,'description':'synthetic boundary','parameters':{'recipient_type':recipient,'target_country':target,'resource':resource,'amount':amount}}

    def assert_conserved(self,states,pool,out):
        for r in RESOURCE_TYPES:
            before=math.fsum(s['resources'][r] for s in states.values())+pool.get(r,0)
            after=math.fsum(s['resources'][r] for s in out['country_states'].values())+out['world_pool'][r]
            self.assertAlmostEqual(before,after,places=8)
            self.assertTrue(-1e-9<=out['world_pool'][r]<=100+1e-9)
            for s in out['country_states'].values():self.assertTrue(0<=s['resources'][r]<=100)
        for row in out['settlements']:
            self.assertTrue(0<=row['realized']<=row['requested'])
            self.assertAlmostEqual(row['realized']+row['unmet'],row['requested'])

    def test_mixed_channels_all_resources_pool_scarcity_and_receiver_boundaries(self):
        for r,stock,pool_stock in itertools.product(RESOURCE_TYPES,(0,34.8,99.99999999,100),(0,0.01,30,100)):
            states={c:{'resources':{x:100.0 for x in RESOURCE_TYPES}} for c in 'ABCD'}
            states['C']['resources'][r]=stock;pool={r:pool_stock}
            intents={'A':self.action('PROVIDE_RESOURCE','C',r,100-stock),'B':self.action('DRAW_WORLD_POOL','C',r,min(pool_stock,100-stock)),'D':self.action('PROVIDE_RESOURCE',None,r,10,'world_pool')}
            out=settle_atomic_actions(states,intents,pool)
            self.assert_conserved(states,pool,out)
            self.assertEqual(out,settle_atomic_actions(states,dict(reversed(list(intents.items()))),pool))
            if not pool_stock:self.assertEqual(next(x for x in out['settlements'] if x['agent_id']=='B')['realized'],0)

    def test_later_turns_legal_catalog_maxima_seeded_state_boundaries(self):
        rng=random.Random(20260917)
        for turn in range(4,9):
            for _ in range(40):
                states={c:{'resources':{r:rng.uniform(0,100) for r in RESOURCE_TYPES}} for c in 'ABCDEFGH'}
                pool={r:rng.uniform(0,100) for r in RESOURCE_TYPES}
                intents={}
                for c in states:
                    choices=feasible_actions(c,states,pool,None)
                    a=rng.choice(choices)
                    intents[c]=self.action(a['action_id'],a['target_country'],a['resource'],a['maximum_amount'],a['recipient_type'])
                original=copy.deepcopy(states)
                out=settle_atomic_actions(states,intents,pool)
                self.assert_conserved(states,pool,out)
                self.assertEqual(states,original)
                self.assertEqual(out,settle_atomic_actions(states,dict(reversed(list(intents.items()))),pool))

    def test_catalog_fractional_maximum_never_exceeds_stock(self):
        stock=0.123456789
        states={c:{'resources':{r:50.0 for r in RESOURCE_TYPES}} for c in 'AB'}
        states['A']['resources']['food']=stock
        choices=feasible_actions('A',states,{},None)
        for a in choices:
            if a['resource']=='food' and a['action_id']=='PROVIDE_RESOURCE':
                self.assertLessEqual(a['maximum_amount'],stock)
                action=self.action(a['action_id'],a['target_country'],'food',a['maximum_amount'],a['recipient_type'])
                out=settle_atomic_actions(states,{'A':action},{})
                self.assert_conserved(states,{},out)

    def test_invalid_source_overdraft_fails_closed_without_mutation(self):
        states={c:{'resources':{r:10.0 for r in RESOURCE_TYPES}} for c in 'AB'}
        before=copy.deepcopy(states);pool={}
        with self.assertRaisesRegex(ValueError,'out-of-range resource'):
            settle_atomic_actions(states,{'A':self.action('PROVIDE_RESOURCE','B','food',50)},pool)
        self.assertEqual(states,before);self.assertEqual(pool,{})

    def test_synthetic_turn_four_to_eight_state_chain_without_model_answers(self):
        # Boundary testing only, NOT an imagined continuation of the real run.
        s=self.f['turn3_opening']
        saved={c['agent_id']:c['structured_response'] for c in self.f['calls'] if c['turn']==3 and c['agent_type']=='country'}
        out=self.execute(s['country_states'],saved,s['current_world'],s['current_damage'],3,s['world_pool'],s['network_policy'])
        damage=reconstruction_step(s['current_damage'],out,out['country_states'])['after']
        rng=random.Random(40917)
        for turn in range(4,9):
            answers={}
            for country in COUNTRIES:
                choices=feasible_actions(country,out['country_states'],out['world_pool'],self.network,out['network_policy'])
                a=rng.choice(choices)
                answer=copy.deepcopy(saved[country]);answer.update(response_id='ACCEPT',response_label='受け入れる',conditions={})
                answer['action']=self.action(a['action_id'],a['target_country'],a['resource'],a['maximum_amount'],a['recipient_type'])
                answers[country]=answer
            fresh=self.execute(out['country_states'],answers,out['true_world'],damage,turn,out['world_pool'],out['network_policy'])
            self.assertEqual(fresh,self.execute(out['country_states'],dict(reversed(list(answers.items()))),out['true_world'],damage,turn,out['world_pool'],out['network_policy']))
            for state in fresh['country_states'].values():
                self.assertTrue(all(math.isfinite(v) and 0<=v<=100 for v in state['resources'].values()))
            damage=reconstruction_step(damage,fresh,fresh['country_states'])['after']
            self.assertTrue(math.isfinite(damage) and damage>=0)
            out=fresh

    def test_source_artifacts_unchanged_and_failure_not_research(self):
        p=ROOT/'results/rejected'/self.f['run_id']
        for name,sha in self.f['source_hashes'].items():
            if (p/name).exists():self.assertEqual(hashlib.sha256((p/name).read_bytes()).hexdigest(),sha)
        self.assertFalse((ROOT/'results/research'/self.f['run_id']).exists())
