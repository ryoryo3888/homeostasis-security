"""Phase-two offline checks, not research worldlines."""
from copy import deepcopy
from pathlib import Path
import unittest
from jsonschema import ValidationError
from homeostasis_v3.physical import (load_baseline, validate_baseline, physical_step,
    validate_step, distribution, self_reliance_components, numeric_paths)

PATH=Path(__file__).resolve().parents[2]/'scenarios/v3/synthetic_baseline.json'
ERRORS=(ValueError,ValidationError)


class PhysicalTests(unittest.TestCase):
    def setUp(self): self.data=load_baseline(PATH)

    def row(self,result,country='MIL',resource='food'):
        return next(r for r in result['ledger'] if (r['state_id'],r['resource_id'])==(country,resource))

    def test_eight_asymmetric_states(self):
        states=self.data['world']['countries']
        self.assertEqual(len(states),8)
        self.assertEqual(len({tuple(a['balance'] for a in self.data['world']['accounts'] if a['owner']==c['state_id']) for c in states}),8)
        components=self_reliance_components(self.data)
        margins=[r['production_per_turn']-r['essential_demand'] for c in components.values() for r in c.values()]
        self.assertTrue(any(m<0 for m in margins));self.assertTrue(any(m>0 for m in margins))
        self.assertTrue(all(r['reserve_only_full_turns']>=1 for c in components.values() for r in c.values()))

    def test_accounting_and_no_mutation(self):
        before=deepcopy(self.data);r=physical_step(self.data)
        self.assertEqual(before,self.data)
        self.assertEqual(len(r['ledger']),16)
        for row in r['ledger']:
            self.assertEqual(row['closing_stock'],row['opening_stock']+row['production']-row['consumption'])
            self.assertEqual(row['required_demand'],row['fulfilled_demand']+row['unmet_demand'])
            self.assertGreaterEqual(row['closing_stock'],0)
        opening=distribution(self.data['world'])['total'];closing=r['distribution']['total']
        for resource in opening:
            rows=[x for x in r['ledger'] if x['resource_id']==resource]
            self.assertEqual(closing[resource],opening[resource]+sum(x['production']-x['consumption']-x['loss'] for x in rows))
        validate_step(self.data,r)

    def test_shortage_without_phantom_consumption(self):
        self.data['world']['accounts'][0]['balance']=70
        self.data['world']['countries'][0]['demands'][0]['quantity']=100
        row=self.row(physical_step(self.data))
        self.assertEqual((row['consumption'],row['unmet_demand'],row['fulfillment_rate']),(70,30,0.7))
        # Production is closing availability, never borrowed earlier in this step.
        self.assertEqual(row['closing_stock'],row['production'])

    def test_zero_demand(self):
        self.data['world']['countries'][0]['demands'][0]['quantity']=0
        row=self.row(physical_step(self.data))
        self.assertEqual((row['consumption'],row['unmet_demand'],row['fulfillment_rate']),(0,0,None))
        self.assertIsNone(self_reliance_components(self.data)['MIL']['food']['reserve_only_full_turns'])

    def test_empty_stock(self):
        self.data['world']['accounts'][0]['balance']=0
        row=self.row(physical_step(self.data))
        self.assertEqual(row['consumption'],0);self.assertEqual(row['unmet_demand'],18)

    def test_loss_explicit_and_conserved(self):
        r=physical_step(self.data,losses={'MIL:food':{'quantity':60,'evidence_id':'test-loss'}})
        row=self.row(r);self.assertEqual((row['loss'],row['consumption'],row['unmet_demand'],row['closing_stock']),(60,8,10,12))
        with self.assertRaises(ERRORS):physical_step(self.data,losses={'MIL:food':{'quantity':69,'evidence_id':'test-loss'}})
        with self.assertRaises(ERRORS):physical_step(self.data,losses={'unknown':{'quantity':1,'evidence_id':'test-loss'}})

    def test_national_isolation_and_distribution(self):
        original=physical_step(self.data)
        self.data['world']['accounts'][0]['balance']=0
        changed=physical_step(self.data)
        for before,after in zip(original['ledger'],changed['ledger']):
            if before['state_id']!='MIL':
                self.assertEqual({k:v for k,v in before.items() if k!='evidence'}, {k:v for k,v in after.items() if k!='evidence'})
        self.assertGreater(changed['distribution']['total']['food'],self.row(changed)['closing_stock'])
        self.assertGreater(self.row(changed)['unmet_demand'],0)

    def test_fractional_utilization_floor(self):
        self.data['capacity_profiles'][0]['utilization_ppm']=333333
        self.data['world']['capacities'][0]['available']=3
        self.assertEqual(self.row(physical_step(self.data))['production'],3)

    def test_overcapacity_rejected(self):
        self.data['capacity_profiles'][0]['current_capacity']=100
        with self.assertRaises(ERRORS):validate_baseline(self.data)

    def test_capability_is_not_stock(self):
        self.data['world']['accounts'][0]=self.data['world']['capacities'][0]
        with self.assertRaises(ERRORS):validate_baseline(self.data)

    def test_missing_demand_rejected(self):
        self.data['world']['countries'][0]['demands']=[]
        with self.assertRaises(ERRORS):validate_baseline(self.data)

    def test_no_roles_or_timeline(self):
        for field in ['future_role','recovery_turn','planned_crisis']:
            d=deepcopy(self.data);d['world']['countries'][0][field]='test'
            with self.subTest(field=field),self.assertRaises(ERRORS):validate_baseline(d)

    def test_all_numeric_origins(self):
        self.data['provenance'].pop()
        with self.assertRaises(ERRORS):validate_baseline(self.data)

    def test_tampered_balanced_production_rejected(self):
        r=physical_step(self.data);r['ledger'][0]['production']+=100;r['ledger'][0]['closing_stock']+=100
        with self.assertRaises(ERRORS):validate_step(self.data,r)

    def test_no_transit_execution(self):
        self.data['world']['accounts'][0]['in_transit']=True
        with self.assertRaises(ERRORS):physical_step(self.data)

    def test_transit_counted_once_in_distribution(self):
        w=self.data['world'];w['accounts'][0]['in_transit']=True
        d=distribution(w)
        self.assertEqual(d['by_country']['MIL']['food'],0)
        self.assertEqual(d['in_transit_total']['food'],68)
        self.assertEqual(d['total']['food'],sum(a['balance'] for a in w['accounts'] if a['resource_id']=='food'))

    def test_not_hardcoded_eight(self):
        d=self.data;cid='MIL'
        d['world']['countries']=[c for c in d['world']['countries'] if c['state_id']==cid]
        d['world']['accounts']=[a for a in d['world']['accounts'] if a['owner']==cid]
        d['world']['capacities']=[c for c in d['world']['capacities'] if c['owner']==cid]
        d['capacity_profiles']=[p for p in d['capacity_profiles'] if p['capacity_id'].startswith(cid+':')]
        paths=[*numeric_paths(d['world'],'/world'),*numeric_paths(d['capacity_profiles'],'/capacity_profiles')]
        d['provenance']=[{'path':p,'kind':'synthetic_assumption','explanation':'Single-country test only','source':'test'} for p in paths]
        self.assertEqual(len(physical_step(d)['ledger']),2)

    def test_order_independent(self):
        before=physical_step(self.data)
        d=self.data;d['world']['countries'].reverse()
        # Arrays change source hashes/provenance paths, not physical results.
        after=physical_step(d)
        self.assertEqual([{k:v for k,v in r.items() if k!='evidence'} for r in before['ledger']],
                         [{k:v for k,v in r.items() if k!='evidence'} for r in after['ledger']])
