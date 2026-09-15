import hashlib,json,subprocess,unittest
from pathlib import Path
from simulation_final import run_final_simulation,convert_v1_event,export_local_security_input
ROOT=Path(__file__).parents[2]
class Phase8Tests(unittest.TestCase):
    def test_eight_countries_and_five_turns(self):
        r=run_final_simulation();self.assertEqual(len(r["countries"]),8);self.assertEqual(len(r["turns"]),5)
    def test_recovery_and_causal_chain(self):
        r=run_final_simulation();self.assertEqual([t["farmland_damage_tons"] for t in r["turns"]],[8000,6000,4000,2000,0]);self.assertGreaterEqual(len(r["causal_chain"]),10)
    def test_saved_result_matches_dashboard_values(self):
        saved=json.loads((ROOT/"results/final/deterministic_prototype.json").read_text());html=(ROOT/"dashboard_final.html").read_text();sim=run_final_simulation();self.assertEqual(saved["global_homeostasis"],[t["world"]["global_homeostasis"] for t in sim["turns"]]);self.assertEqual(saved["farmland_damage_tons"],[t["farmland_damage_tons"] for t in sim["turns"]]);self.assertIn(json.dumps(saved["global_homeostasis"],separators=(",",":")),html);self.assertIn(json.dumps(saved["farmland_damage_tons"],separators=(",",":")),html)
    def test_dashboard_is_self_contained_and_responsive(self):
        html=(ROOT/"dashboard_final.html").read_text();self.assertIn('name="viewport"',html);self.assertNotIn("https://",html);self.assertIn("@media",html)
    def test_v1_bridge_is_explicit_and_nonexecuting(self):
        event=convert_v1_event({"actor":"A","target":"B","turn":3});self.assertEqual(event["origin"]["system"],"v1");out=export_local_security_input({"country":"MIL","action":"de-escalate","turn":5});self.assertTrue(out["requires_manual_v1_execution"])
    def test_reproducible(self):self.assertEqual(run_final_simulation(),run_final_simulation())
    def test_readme_original_prefix_preserved(self):
        current=(ROOT/"README.md").read_bytes();original=subprocess.check_output(["git","show","ba3232f:README.md"],cwd=ROOT);self.assertTrue(current.startswith(original))
    def test_protected_baseline_except_readme(self):
        bad=[]
        for line in Path('/tmp/homeostasis-final-baseline-sha256.txt').read_text().splitlines():
            digest,name=line.split('  ',1)
            if name=="README.md":continue
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:bad.append(name)
        self.assertEqual(bad,[])
if __name__=='__main__':unittest.main()
