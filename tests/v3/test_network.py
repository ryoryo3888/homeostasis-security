"""Synthetic offline graph and transit evidence, never a research simulation."""
from copy import deepcopy
from pathlib import Path
import unittest
from jsonschema import ValidationError
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.contracts import digest
from homeostasis_v3.network import (validate_network, load_network, candidate_paths,
    dependency_trace, network_components, new_transport_check, dispatch_for_check,
    arrive_for_check, transport_inventory)
ROOT=Path(__file__).resolve().parents[2]
ERRORS=(ValueError,ValidationError)


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.b=load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
        self.n=load_network(ROOT/'scenarios/v3/synthetic_network.json',self.b)
        self.s=new_transport_check(self.n,self.b)

    def send(self, s=None, **kwargs):
        args={'shipment_id':'test','route_id':'MIL-forward','resource_id':'food','quantity':4}
        args.update(kwargs)
        return dispatch_for_check(self.s if s is None else s,self.n,self.b,**args)

    def test_baseline_sparse_connected(self):
        ids=[c['state_id'] for c in self.b['world']['countries']]
        self.assertEqual(len(ids),8)
        self.assertLess(len(self.n['routes']),len(ids)*(len(ids)-1))
        for a in ids:
            for b in ids:
                if a!=b:self.assertTrue(candidate_paths(self.n,self.b,a,b,'food'))

    def test_unknown_route_references(self):
        for field in ['source','destination','shared_capacity_group']:
            n=deepcopy(self.n);n['routes'][0][field]='unknown'
            with self.subTest(field=field),self.assertRaises(ERRORS):validate_network(n,self.b)

    def test_unknown_resource(self):
        self.n['routes'][0]['resource_types']=['unknown']
        with self.assertRaises(ERRORS):validate_network(self.n,self.b)

    def test_bad_numbers(self):
        for field,value in [('capacity',-1),('delay',0),('delay',-1),('delay',0.5),('capacity',True)]:
            n=deepcopy(self.n);n['routes'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ERRORS):validate_network(n,self.b)

    def test_self_route(self):
        self.n['routes'][0]['destination']='MIL'
        with self.assertRaises(ERRORS):validate_network(self.n,self.b)

    def test_production_references(self):
        for field in ['producer_state','production_capacity_id','input_resource','output_resource','input_unit']:
            n=deepcopy(self.n);n['production_dependencies'][0][field]='unknown'
            with self.subTest(field=field),self.assertRaises(ERRORS):validate_network(n,self.b)

    def test_production_wrong_owner_or_kind(self):
        for cap in ['RES:produce:food','MIL:transport','MIL:produce:energy']:
            n=deepcopy(self.n);n['production_dependencies'][0]['production_capacity_id']=cap
            with self.subTest(cap=cap),self.assertRaises(ERRORS):validate_network(n,self.b)

    def test_production_self_reference(self):
        self.n['production_dependencies'][0]['input_resource']='food'
        with self.assertRaises(ERRORS):validate_network(self.n,self.b)

    def test_transport_production_types_distinct(self):
        self.n['routes'][0]=self.n['production_dependencies'][0]
        with self.assertRaises(ERRORS):validate_network(self.n,self.b)

    def test_multihop_and_alternatives(self):
        paths=candidate_paths(self.n,self.b,'MIL','FOOD','energy')
        self.assertGreater(len(paths),1)
        self.assertIn(['MIL-forward','RES-forward'],paths)
        self.assertTrue(all(len(p)==len(set(p)) for p in paths))

    def test_directions_not_inferred(self):
        n=deepcopy(self.n);n['routes']=n['routes'][:1]
        self.assertEqual(candidate_paths(n,self.b,'RES','MIL','food'),[])
        self.assertEqual(candidate_paths(n,self.b,'MIL','RES','food'),[['MIL-forward']])

    def test_no_automatic_reroute(self):
        self.n['routes'][0]['availability']=False
        paths=candidate_paths(self.n,self.b,'MIL','RES','food')
        self.assertTrue(paths);self.assertTrue(all('MIL-forward' not in p for p in paths))
        self.assertEqual(new_transport_check(self.n,self.b)['shipments'],[])

    def test_zero_capacity_no_path(self):
        n=deepcopy(self.n);n['routes']=n['routes'][:1];n['routes'][0]['capacity']=0
        self.assertEqual(candidate_paths(n,self.b,'MIL','RES','food'),[])

    def test_path_budget_fail_not_truncate(self):
        with self.assertRaises(ERRORS):candidate_paths(self.n,self.b,'MIL','FOOD','food',limit=1)

    def test_trace_energy_to_food_to_other_country(self):
        t=dependency_trace(self.n,self.b,'MIL','energy')
        self.assertIn(('FOOD','food'),t['nodes'])
        self.assertTrue(any(e['kind']=='production_input' and e['id']=='RES-food-energy' for e in t['edges']))
        self.assertTrue(any(e['kind']=='transport' and e['id']=='RES-forward' and e['source']==('RES','food') for e in t['edges']))

    def test_dependency_cycle_terminates(self):
        t=dependency_trace(self.n,self.b,'MIL','energy')
        self.assertLessEqual(len(t['nodes']),16)
        self.assertEqual(len(t['edges']),len({(e['kind'],e['id'],e['source']) for e in t['edges']}))

    def test_self_reliance_is_separate(self):
        c=network_components(self.n,self.b)['MIL']['food']
        self.assertEqual(c['domestic']['domestic_stock'],68)
        self.assertGreater(len(c['potential_direct_suppliers']),1)
        self.assertNotIn('score',c)

    def test_no_moves_without_explicit_dispatch(self):
        inv=transport_inventory(self.s,self.n,self.b)
        self.assertEqual(inv['domestic']['MIL']['food'],68)
        self.assertEqual(inv['in_transit']['food'],0)

    def test_transit_and_delayed_arrival(self):
        sent=self.send();inv=transport_inventory(sent,self.n,self.b)
        self.assertEqual((inv['domestic']['MIL']['food'],inv['domestic']['RES']['food'],inv['in_transit']['food']),(64,72,4))
        with self.assertRaises(ERRORS):arrive_for_check(sent,self.n,self.b,shipment_id='test',turn=0)
        arrived=arrive_for_check(sent,self.n,self.b,shipment_id='test',turn=1)
        inv2=transport_inventory(arrived,self.n,self.b)
        self.assertEqual((inv2['domestic']['RES']['food'],inv2['in_transit']['food']),(76,0))
        self.assertEqual(inv['total'],inv2['total'])
        with self.assertRaises(ERRORS):arrive_for_check(arrived,self.n,self.b,shipment_id='test',turn=2)

    def test_duplicate_dispatch_and_negative(self):
        sent=self.send()
        with self.assertRaises(ERRORS):self.send(sent)
        for quantity in [-1,0,True]:
            with self.subTest(quantity=quantity),self.assertRaises(ERRORS):self.send(quantity=quantity)

    def test_route_capacity(self):
        with self.assertRaises(ERRORS):self.send(quantity=7)

    def test_shared_capacity_across_routes_and_resources(self):
        # Group 0 covers MIL and ISLAND routes: resource load is aggregated.
        self.n['shared_capacities'][0]['capacity']=7;self.s=new_transport_check(self.n,self.b)
        sent=self.send(quantity=4)
        with self.assertRaises(ERRORS):self.send(sent,shipment_id='second',route_id='ISLAND-forward',resource_id='energy',quantity=4)

    def test_state_transport_capacity_across_groups(self):
        self.n['routes'][0]['capacity']=20;self.n['shared_capacities'][0]['capacity']=50
        self.s=new_transport_check(self.n,self.b)
        with self.assertRaises(ERRORS):self.send(quantity=19)

    def test_stock_double_spend(self):
        self.b['world']['accounts'][0]['balance']=5;self.n['baseline_hash']=digest(self.b)
        self.s=new_transport_check(self.n,self.b);sent=self.send(quantity=4)
        with self.assertRaises(ERRORS):self.send(sent,shipment_id='second',route_id='MIL-reverse',quantity=2)

    def test_baseline_hash(self):
        self.n['baseline_hash']='0'*64
        with self.assertRaises(ERRORS):validate_network(self.n,self.b)

    def test_no_mutation_and_input_order_independence(self):
        before=deepcopy((self.n,self.b,self.s));paths=candidate_paths(self.n,self.b,'MIL','FOOD','food')
        self.send();self.assertEqual(before,(self.n,self.b,self.s))
        self.n['routes'].reverse()
        self.assertEqual(paths,candidate_paths(self.n,self.b,'MIL','FOOD','food'))

    def test_reject_future_script(self):
        for key in ['failure_turn','recovery_route','future_role','chosen_route']:
            n=deepcopy(self.n);n['routes'][0][key]='forbidden'
            with self.subTest(key=key),self.assertRaises(ERRORS):validate_network(n,self.b)

    def test_tampered_transit(self):
        sent=self.send();sent['shipments'][0]['arrival_turn']=0
        with self.assertRaises(ERRORS):transport_inventory(sent,self.n,self.b)
        sent=self.send();sent['shipments'].append(deepcopy(sent['shipments'][0]))
        with self.assertRaises(ERRORS):transport_inventory(sent,self.n,self.b)

    def test_explicit_two_hop_transit_conservation(self):
        s=self.send()
        s=arrive_for_check(s,self.n,self.b,shipment_id='test',turn=1)
        s=self.send(s,shipment_id='hop2',route_id='RES-forward',quantity=4)
        inv=transport_inventory(s,self.n,self.b)
        self.assertEqual(inv['domestic']['RES']['food'],72)
        self.assertEqual(inv['domestic']['FOOD']['food'],42)
        self.assertEqual(inv['in_transit']['food'],4)
        with self.assertRaises(ERRORS):arrive_for_check(s,self.n,self.b,shipment_id='hop2',turn=2)
        s=arrive_for_check(s,self.n,self.b,shipment_id='hop2',turn=3)
        inv=transport_inventory(s,self.n,self.b)
        self.assertEqual(inv['domestic']['FOOD']['food'],46)
        self.assertEqual(inv['in_transit']['food'],0)
        self.assertEqual(inv['total'],transport_inventory(self.s,self.n,self.b)['total'])

    def test_resource_capacity_conversion(self):
        self.n['transport_costs'][0]['transport_units_per_stock_unit']=2
        self.s=new_transport_check(self.n,self.b)
        self.send(quantity=3)
        with self.assertRaises(ERRORS):self.send(quantity=4)

    def test_duplicate_and_missing_provenance(self):
        self.n['routes'].append(deepcopy(self.n['routes'][0]))
        with self.assertRaises(ERRORS):validate_network(self.n,self.b)
        self.n['routes'].pop();self.n['routes'][0].pop('provenance')
        with self.assertRaises(ERRORS):validate_network(self.n,self.b)

    def test_inputs_and_shared_capacity_invalid(self):
        for field in ['required_input','output_batch','output_delay']:
            n=deepcopy(self.n);n['production_dependencies'][0][field]=0
            with self.subTest(field=field),self.assertRaises(ERRORS):validate_network(n,self.b)
        self.n['shared_capacities'][0]['capacity']=-1
        with self.assertRaises(ERRORS):validate_network(self.n,self.b)
