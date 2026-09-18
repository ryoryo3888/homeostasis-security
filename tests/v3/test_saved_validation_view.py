"""Read saved excerpts only; never creates or replays a simulation."""
import unittest,json
from copy import deepcopy
from pathlib import Path
from tools.build_v3_validation import project,filehash
ROOT=Path(__file__).resolve().parents[2]
class SavedViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=json.loads((ROOT/'ui/v3/validation/evidence.json').read_text())
        cls.view=project(cls.package)
    def test_classification(self):
        self.assertFalse(self.view['research_eligible']);self.assertEqual(self.view['api_calls'],0)
        self.assertEqual(self.view['decision_origin'],'synthetic_fixture')
    def test_all_saved_turns(self):
        self.assertEqual([len(c['turns']) for c in self.view['cases']],[8,3,3,3])
    def test_source_export_pinned(self):
        m=json.loads((ROOT/'ui/v3/validation/manifest.json').read_text())
        self.assertEqual(m['file_sha256'],filehash(ROOT/'ui/v3/validation/evidence.json'))
    def test_generated_consistency_and_purity(self):
        before=deepcopy(self.package);self.assertEqual(self.view,project(self.package));self.assertEqual(before,self.package)
        self.assertEqual(self.view,json.loads((ROOT/'ui/v3/validation/view.json').read_text()))
    def test_formal_promotion_rejected(self):
        p=deepcopy(self.package);p['research_eligible']=True
        with self.assertRaises(AssertionError):project(p)
    def test_corrupted_evidence_rejected(self):
        p=deepcopy(self.package);p['cases'][0]['turns'][0]['evidence']['ledger']['value'][0]['consumed']+=1
        with self.assertRaises(AssertionError):project(p)
    def test_missing_turn_rejected(self):
        p=deepcopy(self.package);p['cases'][0]['turns'].pop(1)
        with self.assertRaises(AssertionError):project(p)
    def test_secret_rejected(self):
        p=deepcopy(self.package);p['secret']='AIza'+'a'*35
        with self.assertRaises(AssertionError):project(p)
    def test_dispatch_not_arrival(self):
        t=self.view['cases'][1]['turns'][0]
        self.assertTrue(any(a['dispatched']>0 and a['arrived']==0 for a in t['transactions']))
        self.assertTrue(any(s['arrival_turn'] is None for s in t['shipments']))
    def test_refusal_is_valid_world_outcome(self):
        t=self.view['cases'][2]['turns'][0];self.assertTrue(t['transactions'])
        self.assertTrue(all(a['settled']==0 for a in t['transactions']))
    def test_abstention_not_refusal(self):
        for t in self.view['cases'][0]['turns']:self.assertEqual(t['transactions'],[])
    def test_choice_trace(self):
        for c in self.view['cases']:
            for t in c['turns']:
                for a in t['transactions']:
                    self.assertEqual(a['choice_id'],a['materialized_action']['choice_id'])
                    self.assertEqual(a['requested'],a['materialized_action']['requested_amount'])
    def test_networkless_viewer(self):
        s=(ROOT/'ui/v3/validation/viewer.js').read_text()
        for bad in ('fetch(', 'XMLHttpRequest','localStorage','setInterval','innerHTML'):self.assertNotIn(bad,s)
