"""Candidate baseline mapping tests. No new worldline or UI baseline approval."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
import unittest
from tools.build_v3_candidate import transform
ROOT=Path(__file__).resolve().parents[2]

class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.b=json.loads((ROOT/'scenarios/v3/synthetic_baseline.json').read_text())
        self.n=json.loads((ROOT/'scenarios/v3/synthetic_network.json').read_text())
        self.data=json.loads((ROOT/'ui/v3/baseline.json').read_text())
    def test_source_generated_consistency(self):
        expected=transform(self.b,self.n)
        for item in expected['provenance'].values():item['file_sha256']=hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()
        self.assertEqual(expected,self.data)
    def test_pure_transform(self):
        before=deepcopy((self.b,self.n));a=transform(self.b,self.n)
        self.assertEqual(before,(self.b,self.n));self.assertEqual(a,transform(self.b,self.n))
    def test_no_results_or_turns(self):
        self.assertEqual(self.data['artifact_class'],'synthetic_baseline')
        self.assertIsNone(self.data['turn']);self.assertIsNone(self.data['formal_worldline'])
        self.assertFalse(self.data['research_eligible']);self.assertTrue(all(v is None for v in self.data['measurements'].values()))
    def test_eight_abstract_states(self):
        self.assertEqual([s['label'] for s in self.data['states']],list('ABCDEFGH'))
        self.assertEqual([s['id'] for s in self.data['states']],[s['state_id'] for s in self.b['world']['countries']])
        for s in self.data['states']:self.assertEqual(set(s),{'id','label','resources'})
    def test_resource_stocks_and_capacities_not_invented(self):
        for s in self.data['states']:
            for r,v in s['resources'].items():
                a=next(a for a in self.b['world']['accounts'] if a['account_id']==v['account_id'])
                c=next(c for c in self.b['world']['capacities'] if c['capacity_id']==v['capacity_id'])
                self.assertEqual(v['stock'],a['balance']);self.assertEqual(v['production_capacity'],c['available'])
                self.assertLessEqual(v['stock'],self.data['scales'][r])
    def test_only_real_structural_routes(self):
        self.assertEqual(len(self.data['routes']),18)
        for r in self.data['routes']:
            source=next(x for x in self.n['routes'] if x['route_id']==r['id'])
            self.assertEqual((r['source'],r['target'],r['capacity'],r['delay']),(source['source'],source['destination'],source['capacity'],source['delay']))
            self.assertNotIn('flow',r)
    def test_candidate_not_approved(self):
        c=json.loads((ROOT/'ui/v3/frame.json').read_text())
        self.assertEqual(c['status'],'candidate');self.assertFalse(c['approved_visual_baseline'])
        self.assertEqual(self.data['visual_baseline'],'candidate')
    def test_no_meta_copy(self):
        text=(ROOT/'dashboard_v3.html').read_text()+(ROOT/'ui/v3/observatory.js').read_text()
        for banned in ('10秒','30秒','秒で理解','読み方','初心者向け','研究者向け','支援国','被災国'):self.assertNotIn(banned,text)
    def test_no_legacy_layers_or_api_client(self):
        html=(ROOT/'dashboard_v3.html').read_text();js=(ROOT/'ui/v3/observatory.js').read_text()
        self.assertNotIn('homeostasis-research-layer',html)
        for bad in ('generate_content','gemini','api_key','localStorage','sessionStorage','setInterval','requestAnimationFrame'):self.assertNotIn(bad,js)
        self.assertEqual(js.count('fetch('),1)
    def test_native_source_and_attribution(self):
        data=(ROOT/'ui/v3/vendor/ne_110m_land.geojson').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),'9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9')
        svg=(ROOT/'ui/v3/earth.svg').read_text();self.assertNotIn('<script',svg);self.assertNotIn('<image',svg)
    def test_frame_and_named_slots(self):
        text=(ROOT/'dashboard_v3.html').read_text();c=json.loads((ROOT/'ui/v3/frame.json').read_text())
        positions=[text.index('id="'+x+'"') for x in c['order']];self.assertEqual(positions,sorted(positions))
        for name in c['slots']:self.assertIn('data-v3-slot="'+name+'"',text)
    def test_control_typography_and_disabled(self):
        css=(ROOT/'ui/v3/observatory.css').read_text();html=(ROOT/'dashboard_v3.html').read_text()
        self.assertIn('font-size:17px;font-weight:800;letter-spacing:1.36px;line-height:26.35px;color:#67e8f9',css)
        self.assertEqual(html.count('<button disabled'),2)
