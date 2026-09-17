"""Read-only observation of offline synthetic fixtures; no research claims."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import json
import ast
import unittest

from homeostasis_v3.physical import load_baseline
from homeostasis_v3.network import load_network
from homeostasis_v3.contracts import digest
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.turn import TurnRunner, CountryInput
from homeostasis_v3.observation import (observe, verify_observation, validate_observation, metric_cells,
    comparison_contract, interpretation, evaluator_view, resolve, hhi)
from homeostasis_v3.observation_registry import pending_evidence
from homeostasis_v3.metric_definitions import DEFINITIONS, DEFINITIONS_DIGEST
ROOT=Path(__file__).resolve().parents[2]


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b=load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
        cls.n=load_network(ROOT/'scenarios/v3/synthetic_network.json',cls.b)
        cls.runner=TurnRunner(cls.b,cls.n,pool_location='MIL',context_id='observation-fixture')
        cls.genesis=cls.runner.genesis()
        def catalogue(view):
            s=view.read()['settlement_snapshot']
            return [dict(choice_id='c-'+str(s['turn'])+'-'+str(i),actor_state_id='MIL',turn=s['turn'],snapshot_hash=digest(s),
                action_type='transfer',resource='food',maximum_amount=20,target='RES',route_preference='MIL-forward',
                conditions=[],allow_partial=True,minimum_amount=1) for i in range(2)]
        def choose(view,proposal):
            return [{'choice_id':t['choice_id'],'requested_amount':20,'provenance':{'source':'synthetic fixture','public_reason':'fixture only'}} for t in catalogue(view)]
        def consent(view,choices):return {c['choice_id']:True for c in choices.read()}
        cls.first=cls.runner.run(cls.genesis,catalogue=catalogue,countries={'MIL':CountryInput(choose,consent),'RES':CountryInput(lambda *_:[],consent)})
        cls.second=cls.runner.run(cls.first,shocks=[dict(event_id='loss',kind='demand_change',target='RES',resource='food',amount=10000,evidence='synthetic fixture')])
        cls.third=cls.runner.run(cls.second)

    def obs(self, cp=None, **kw):
        return observe(cp or self.first,worldline_id='fixture-world',provisional_reference='phase6-test',**kw)

    def test_deterministic_and_pure(self):
        before=deepcopy(self.first);a=self.obs();b=self.obs()
        self.assertEqual(a,b);self.assertEqual(self.first,before)

    def test_turn_end_only(self):
        with self.assertRaises(TechnicalFailure):self.obs(self.genesis)
        a=self.obs();self.assertEqual(a['measured_at_phase'],'TURN_CLOSE')
        self.assertEqual(a['observation_input_digest'],self.first['output_digest'])

    def test_observation_ledger_exact(self):
        record=self.obs()
        for row in self.first['ledger']:
            v=record['state_metrics'][row['owner']]['resources'][row['resource']]['shortage']['value']
            self.assertEqual(v['shortage'],row['shortage']);self.assertEqual(v['fulfilled'],row['consumed'])

    def test_world_and_distribution_separate(self):
        o=self.obs(self.second)
        for r in ('food','energy'):
            dist=o['resource_metrics'][r]['distribution']['value']
            aggregate=o['world_metrics']['homeostasis_components']['essential_fulfillment'][r]['value']
            self.assertEqual(sum(dist['shortage'].values()),aggregate['shortage'])
            self.assertEqual(len(dist['stock']),8)
            self.assertEqual(sum(dist['stock'].values()),o['resource_metrics'][r]['total']['value']['domestic'])

    def test_self_reliance_not_autonomy_score(self):
        o=self.obs();s=o['state_metrics']['MIL']
        self.assertIn('autonomy',s)
        v=s['resources']['food']['self_reliance']['value']
        for k in ('domestic_stock','essential_demand','domestic_production_capacity','reserve_buffer','reserve_only_full_turns','external_received_this_turn','potential_supplier_ids','additional_paths_per_supplier'):self.assertIn(k,v)
        self.assertNotIn('score',s['autonomy']['value'])
        self.assertEqual(s['autonomy']['value']['submitted_choices'],2)
        self.assertEqual(s['autonomy']['value']['feasible_unselected_options']['status'],'unknown')

    def test_receipts_distinct_from_intent(self):
        o=self.obs();rows=o['transaction_metrics']['choices']
        self.assertTrue(any(c['value']['fulfillment']=='partial' for c in rows))
        for c in rows:
            v=c['value'];self.assertEqual(v['requested'],20);self.assertEqual(v['arrived_as_of_turn_end'],0)
            self.assertEqual(v['dispatched'],v['settled'])
        second=self.obs(self.second)
        self.assertTrue(second['transaction_metrics']['receipts_this_turn']['value']['receipts'])

    def test_resilience_complete_history(self):
        o=self.obs(self.third,previous=[self.first,self.second])
        value=o['state_metrics']['RES']['resources']['food']['resilience']['value']
        expected=sum(next(r['shortage'] for r in c['ledger'] if r['owner']=='RES' and r['resource']=='food') for c in (self.first,self.second,self.third))
        self.assertEqual(value['cumulative_shortage'],expected)
        self.assertEqual(value['recovery_mechanism']['status'],'unknown')
        self.assertTrue(value['history_complete'])

    def test_missing_history_not_zero(self):
        o=self.obs(self.third)
        v=o['state_metrics']['RES']['resources']['food']['shortage']['value']['cumulative_shortage']
        self.assertEqual(v['status'],'unknown');self.assertIsNone(v['value'])

    def test_reference_explicit(self):
        unknown=self.obs()['state_metrics']['MIL']['resources']['food']['reference_deviation']
        self.assertEqual(unknown['status'],'unknown')
        known=self.obs(reference=self.genesis)['state_metrics']['MIL']['resources']['food']['reference_deviation']
        start=next(a['balance'] for a in self.b['world']['accounts'] if a['owner']=='MIL' and a['resource_id']=='food')
        end=next(a['balance'] for a in self.first['world_state']['physical']['world']['accounts'] if a['owner']=='MIL' and a['resource_id']=='food')
        self.assertEqual(known['value'],end-start)

    def test_routes_alternatives_and_load(self):
        o=self.obs();paths=o['network_metrics']['reachability']['value']
        self.assertTrue(any(len(p['routes'])>1 for p in paths))
        row=o['network_metrics']['routes']['MIL-forward']['value']
        dispatched=sum(s['dispatched_amount'] for s in self.first['world_state']['shipments'])
        self.assertEqual(row['used'],dispatched)
        self.assertEqual(row['in_transit'] if 'in_transit' in row else row['by_resource']['food']['in_transit'],dispatched)
        self.assertEqual(row['waiting']['status'],'unknown')

    def test_stopped_route_not_reachable(self):
        cp=self.runner.run(self.genesis,shocks=[dict(event_id='stop',kind='route_stop',target='MIL-forward',resource=None,amount=0,evidence='fixture')])
        o=self.obs(cp)
        self.assertFalse(any('MIL-forward' in p['routes'] for p in o['network_metrics']['reachability']['value']))
        self.assertFalse(o['network_metrics']['routes']['MIL-forward']['value']['available'])

    def test_concentration_hhi(self):
        self.assertEqual(hhi({'a':1,'b':1}),.5)
        self.assertEqual(hhi({'a':4}),1)
        self.assertEqual(hhi({})['status'],'not_applicable')
        o=self.obs();v=o['network_metrics']['concentration']['RES']['food']['value']
        self.assertIn('structural_route_counts',v);self.assertIn('observed_receipt_amounts',v)

    def test_unknown_conflict_and_unadopted_reaction(self):
        o=self.obs()
        self.assertEqual(o['world_metrics']['conflict_load']['status'],'unknown')
        for k in ('overreaction','underreaction'):
            self.assertEqual(o['world_metrics'][k]['status'],'not_measured');self.assertIsNone(o['world_metrics'][k]['value'])

    def test_propagation_is_not_causation(self):
        o=self.obs(self.second,previous=[self.first])
        rows=o['propagation_metrics']['value'];self.assertTrue(rows)
        self.assertTrue(all(x['causal_claim'] is False for x in rows))
        self.assertTrue(any(x['evidence_strength']=='change_along_dependency_path' for x in rows))
        for x in rows:
            self.assertIn('dependency_path',x)
            self.assertEqual(resolve(self.second,x['origin']['evidence_pointer'])['event_id'],x['origin']['event_id'])

    def test_evidence_and_full_recomputation(self):
        o=self.obs(reference=self.genesis)
        sources={c['checkpoint_digest']:c for c in (self.first,self.genesis)}
        self.assertEqual(verify_observation(o,sources),o)
        for cell in metric_cells(o):
            for e in cell['evidence']:
                self.assertEqual(digest(resolve(sources[e['checkpoint_digest']],e['pointer'])),e['value_digest'])

    def test_rehashed_value_tampering_rejected(self):
        o=self.obs();o['state_metrics']['MIL']['resources']['food']['shortage']['value']['shortage']+=1
        o.pop('observation_digest');o['observation_digest']=digest(o)
        with self.assertRaises(TechnicalFailure):verify_observation(o,{self.first['checkpoint_digest']:self.first})

    def test_broken_pointer_rejected(self):
        o=self.obs();next(metric_cells(o))['evidence'][0]['pointer']='/missing'
        o.pop('observation_digest');o['observation_digest']=digest(o)
        with self.assertRaises(TechnicalFailure):validate_observation(o,{self.first['checkpoint_digest']:self.first})

    def test_metric_definition_version_mismatch(self):
        o=self.obs();other=deepcopy(o);other['metric_definitions_digest']='0'*64
        with self.assertRaises(TechnicalFailure):comparison_contract(o,other)

    def test_comparison_no_causal_claim(self):
        o=self.obs();self.assertFalse(comparison_contract(o,o)['causal_comparison_established'])

    def test_no_formal_promotion(self):
        with self.assertRaises(TechnicalFailure):self.obs(artifact_class='formal_experiment')
        for kind in ('test_fixture','validation_run'):
            o=self.obs(artifact_class=kind);self.assertFalse(o['research_eligible']);self.assertIsNone(o['experiment_id'])

    def test_evaluator_separate_and_read_only(self):
        o=self.obs();before=deepcopy(o);view=evaluator_view(o)
        view.read()['world_metrics']={}
        with self.assertRaises(FrozenInstanceError):view.payload='{}'
        note=interpretation(o,text='Fixture commentary, not a research finding',evidence_paths=['/state_metrics/RES/resources/food/shortage'])
        self.assertFalse(note['changes_measurements']);self.assertEqual(o,before)
        self.assertEqual(note['kind'],'interpretation')

    def test_registry_pending_not_public(self):
        o=self.obs();c=pending_evidence(o,{self.first['checkpoint_digest']:self.first},path='results/v3-validation/observation.json')
        self.assertEqual(c['registration_status'],'not_registered');self.assertEqual(c['publication_status'],'withheld');self.assertFalse(c['source_eligible'])

    def test_registry_unsafe_path_rejected(self):
        o=self.obs();sources={self.first['checkpoint_digest']:self.first}
        for path in ('../secret.json','/tmp/a.json','.hidden/a.json','results/api_key.json','https://x/a.json'):
            with self.assertRaises(TechnicalFailure):pending_evidence(o,sources,path=path)

    def test_dictionary_has_required_definition_fields(self):
        for mid,d in DEFINITIONS.items():
            self.assertEqual(d['metric_id'],mid)
            self.assertEqual(set(d),{'metric_id','definition','inputs','calculation','unit','aggregation','known_limits','introduced_version'})
        self.assertEqual(digest(DEFINITIONS),DEFINITIONS_DIGEST)

    def test_path_budget_fail_closed(self):
        with self.assertRaises(TechnicalFailure):self.obs(path_limit=1)

    def test_duplicate_and_fork_history_rejected(self):
        with self.assertRaises(TechnicalFailure):self.obs(previous=[self.first])
        other=self.runner.run(self.genesis)
        with self.assertRaises(TechnicalFailure):self.obs(self.second,previous=[other])

    def test_no_control_or_io_entry_points(self):
        tree=ast.parse((ROOT/'homeostasis_v3/observation.py').read_text())
        banned={'run','settle','arrive','save','write_text','write_bytes','open','urlopen','request','generate_content'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):self.assertNotIn(node.func.attr,banned)
        self.assertNotIn('TurnRunner',(ROOT/'homeostasis_v3/observation.py').read_text())

    def test_serialization_roundtrip(self):
        o=self.obs()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture-observation.json';p.write_text(json.dumps(o,ensure_ascii=False))
            self.assertEqual(verify_observation(json.loads(p.read_text()),{self.first['checkpoint_digest']:self.first}),o)

    def test_global_improvement_does_not_hide_local_worsening(self):
        def shock(eid,owner,amount):
            return dict(event_id=eid,kind='demand_change',target=owner,resource='food',amount=amount,evidence='synthetic distribution fixture')
        a=self.runner.run(self.genesis,shocks=[shock('large','MIL',1000)])
        b=self.runner.run(a,shocks=[shock('reduced','MIL',0),shock('local','RES',300)])
        oa=self.obs(a);ob=self.obs(b,previous=[a])
        def world(o):return o['world_metrics']['homeostasis_components']['essential_fulfillment']['food']['value']['shortage']
        def local(o):return o['state_metrics']['RES']['resources']['food']['shortage']['value']['shortage']
        self.assertLess(world(ob),world(oa));self.assertGreater(local(ob),local(oa))

    def test_positive_reference_without_history_recomputes(self):
        o=self.obs(self.third,reference=self.first)
        sources={c['checkpoint_digest']:c for c in (self.first,self.third)}
        self.assertEqual(verify_observation(o,sources),o)
        self.assertFalse(o['provenance']['history_complete'])

    def test_recovery_capacity_does_not_invent_resource_propagation(self):
        cap=next(c for c in self.b['world']['capacities'] if c['category']=='recovery')
        cp=self.runner.run(self.genesis,shocks=[dict(event_id='recovery-loss',kind='capacity_loss',target=cap['capacity_id'],resource=None,amount=1,evidence='fixture')])
        rows=self.obs(cp)['propagation_metrics']['value']
        self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['resource']);self.assertEqual(rows[0]['evidence_strength'],'unknown')

    def test_zero_demand_ratio_not_zero_measurement(self):
        cp=self.runner.run(self.genesis,shocks=[dict(event_id='zero',kind='demand_change',target='MIL',resource='food',amount=0,evidence='fixture')])
        v=self.obs(cp)['state_metrics']['MIL']['resources']['food']['shortage']['value']
        self.assertEqual(v['shortage'],0);self.assertEqual(v['fulfillment_rate']['status'],'not_applicable')

    def test_no_choice_world_is_legitimate_observation(self):
        cp=self.runner.run(self.genesis);o=self.obs(cp)
        self.assertEqual(o['transaction_metrics']['summary']['value']['counts'],{'full':0,'partial':0,'not_established':0})
        self.assertEqual(o['state_metrics']['MIL']['autonomy']['value']['submitted_choices'],0)
        self.assertEqual(o['world_metrics']['conflict_load']['status'],'unknown')

    def test_inconsistent_closing_evidence_rejected(self):
        from homeostasis_v3.turn import seal
        cp=deepcopy(self.first);cp['audit']['CONSERVATION']['closing']['food']+=1
        for p in cp['phases']:
            if p['phase']=='CONSERVATION':p['evidence_hash']=digest(cp['audit']['CONSERVATION'])
        cp.pop('checkpoint_digest');cp=seal(cp)
        with self.assertRaises(TechnicalFailure):self.obs(cp)

    def test_schema_rejects_extra_measurement_claim(self):
        o=self.obs();o['world_is_good']=True;o.pop('observation_digest');o['observation_digest']=digest(o)
        with self.assertRaises(TechnicalFailure):validate_observation(o,{self.first['checkpoint_digest']:self.first})

    def test_missing_source_rejected(self):
        o=self.obs(self.second,previous=[self.first])
        with self.assertRaises(TechnicalFailure):verify_observation(o,{self.second['checkpoint_digest']:self.second})
