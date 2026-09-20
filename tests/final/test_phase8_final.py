from tools.visual_baseline import protected_bytes
import hashlib,json,subprocess,unittest
from pathlib import Path
from simulation_final import run_final_simulation,convert_v1_event,export_local_security_input
ROOT=Path(__file__).parents[2]
class Phase8Tests(unittest.TestCase):
    def test_eight_countries_and_five_turns(self):
        r=run_final_simulation();self.assertEqual(len(r["countries"]),8);self.assertEqual(len(r["turns"]),8)
    def test_recovery_and_causal_chain(self):
        r=run_final_simulation();self.assertEqual([t["farmland_damage_tons"] for t in r["turns"]],[8000,6000,4000,2000,0,0,0,0]);self.assertGreaterEqual(len(r["causal_chain"]),10);self.assertTrue(all("history_state" in t for t in r["turns"][5:]))
    def test_saved_result_matches_dashboard_values(self):
        saved=json.loads((ROOT/"results/final/deterministic_prototype_8turn.json").read_text());html=(ROOT/"dashboard_final.html").read_text();sim=run_final_simulation();self.assertEqual(saved["global_homeostasis"],[t["world"]["global_homeostasis"] for t in sim["turns"]]);self.assertEqual(saved["farmland_damage_tons"],[t["farmland_damage_tons"] for t in sim["turns"]]);self.assertIn(json.dumps(saved["global_homeostasis"],separators=(",",":")),html);self.assertIn(json.dumps(saved["farmland_damage_tons"],separators=(",",":")),html);self.assertFalse(saved["gemini_executed"])
    def test_dashboard_is_self_contained_and_responsive(self):
        html=(ROOT/"dashboard_final.html").read_text();self.assertIn('name="viewport"',html);self.assertNotIn("https://",html);self.assertIn("@media",html)
    def test_every_dashboard_tab_has_scrollable_substantive_content(self):
        html=(ROOT/"dashboard_final.html").read_text()
        for label in ("概要","国家","地球","統治","資源","ログ／研究結果"):
            self.assertIn(f"'{label}'",html)
        for branch in range(6): self.assertIn(f"if(tab==={branch})content.innerHTML",html)
        for heading in ("自動生成イベントと因果","国家Agentの認識と判断","地球調整機関","統治ルール","有向資源ネットワーク","因果・行動ログ","指標推移"):
            self.assertIn(heading,html)
        self.assertIn("#content{min-height:72vh",html)
        self.assertNotIn("overflow:hidden",html.replace(" ",""))
    def test_dashboard_uses_required_japanese_display_labels_without_changing_ids(self):
        html=(ROOT/"dashboard_final.html").read_text()
        for label in ("再現可能な恒常性研究シミュレーション","軍事大国","資源輸出国","食料輸入国","小国","島嶼国","経済大国","紛争脆弱国","中立国","独立評価機関（Evaluator）","1回実行"):
            self.assertIn(label,html)
        self.assertIn("`ターン${i+1}`",html)
        self.assertNotIn("DETERMINISTIC RESEARCH PROTOTYPE",html)
        self.assertNotIn("`Turn ${i+1}`",html)
        data=json.loads(html.split('<script id="data" type="application/json">',1)[1].split('</script>',1)[0])
        self.assertEqual(data["countries"],["MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL"])
        self.assertEqual(len(data["damage"]),8);self.assertFalse(data["gemini_executed"]);self.assertIn("Gemini本番結果ではありません",html)
    def test_v1_bridge_is_explicit_and_nonexecuting(self):
        event=convert_v1_event({"actor":"A","target":"B","turn":3});self.assertEqual(event["origin"]["system"],"v1");out=export_local_security_input({"country":"MIL","action":"de-escalate","turn":5});self.assertTrue(out["requires_manual_v1_execution"])
    def test_reproducible(self):self.assertEqual(run_final_simulation(),run_final_simulation())
    def test_readme_original_preserved_in_history_block(self):
        # The authorized repository organization places the current guide first.
        # Retain the whole pre-organization README, not only its oldest prefix.
        current=(ROOT/"README.md").read_bytes()
        original=subprocess.check_output(["git","show","c7c0faad77f80a2c05bd412c68f69159d7b89782:README.md"],cwd=ROOT)
        start=b'<!-- HOMEOSTASIS_RETAINED_README_BEGIN -->\n'
        end=b'<!-- HOMEOSTASIS_RETAINED_README_END -->'
        self.assertEqual(current.count(start),1)
        self.assertEqual(current.count(end),1)
        retained=current.split(start,1)[1].split(end,1)[0]
        self.assertEqual(retained,original)
    def test_protected_baseline_except_readme(self):
        bad=[]
        archived={item['original_path']:item['path'] for item in json.loads((ROOT/'archive/manifest.json').read_text())['files']}
        for line in (ROOT/'tests/layout/protected-baseline.sha256').read_text().splitlines():
            digest,name=line.split('  ',1)
            if name=="README.md":continue
            if name in {"simulation_v2.py", "test_simulation_v2.py"}:
                approved=subprocess.check_output(["git","show","0b66d885822797ad88af584bd5b5b43a71af5db3:"+name],cwd=ROOT)
                self.assertEqual((ROOT/name).read_bytes(),approved,name)
                continue
            if name in {"simulation.py", "test_simulation.py", "experiment_runner.py"}:
                approved=subprocess.check_output(["git","show","fe73d5acfdb259e48c0576012ca8a777b3a0b37d:"+name],cwd=ROOT)
                self.assertEqual((ROOT/name).read_bytes(),approved,name)
                continue
            if hashlib.sha256(protected_bytes(ROOT/archived.get(name,name))).hexdigest()!=digest:bad.append(name)
        self.assertEqual(bad,[])
    def test_archived_backups_preserve_exact_source_and_paths(self):
        manifest=json.loads((ROOT/'archive/manifest.json').read_text())
        base='c7c0faad77f80a2c05bd412c68f69159d7b89782'
        self.assertEqual(manifest['source_commit'],base)
        originals=subprocess.check_output(['git','ls-tree','--name-only',base],cwd=ROOT,text=True).splitlines()
        expected={name for name in originals if name.startswith(('simulation_before_','dashboard_before_','dashboard_v1_before_','index_before_')) or name in {
            'simulation_backup.py','index_failed_globe_trial.html','index.html.txt',
            'dashboard_experiments_restored_v8.html','dashboard_final_working.html','dashboard_reason_test.html',
            'dashboard_working_complete.html','dashboard_working_final_ui.html'}}
        self.assertEqual(len(expected),35)
        self.assertEqual(len(manifest['files']),35)
        self.assertEqual({item['original_path'] for item in manifest['files']},expected)
        for item in manifest['files']:
            name=item['original_path']
            folder='legacy-python' if name.endswith('.py') else 'legacy-pages'
            self.assertEqual(item['path'],f'archive/{folder}/{name}')
            self.assertFalse((ROOT/name).exists())
            path=ROOT/item['path']
            self.assertFalse(path.is_symlink())
            original=subprocess.check_output(['git','show',base+':'+name],cwd=ROOT)
            self.assertEqual(path.read_bytes(),original,name)
            self.assertEqual(hashlib.sha256(original).hexdigest(),item['sha256'],name)
if __name__=='__main__':unittest.main()
