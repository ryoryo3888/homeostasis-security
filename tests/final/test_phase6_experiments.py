import tempfile, unittest
from pathlib import Path
from homeostasis_core.experiments import *

def runner(seed): return {"recovered":seed%2==0,"final_homeostasis":70+seed%5,"sovereignty_maintenance":80,"recovery_turns":4,"causal_history":["initial","recovery"]}
class Phase6Tests(unittest.TestCase):
    def plan(self,**kw): return ExperimentPlan("s1",kw.get("seed",10),kw.get("runs",3),kw.get("max_runs",10),kw.get("dry_run",False),0)
    def test_same_seed_reproducible(self): self.assertEqual(run_experiment(self.plan(),runner,code_version="x"),run_experiment(self.plan(),runner,code_version="x"))
    def test_different_seed_supported(self): self.assertNotEqual(run_experiment(self.plan(seed=1),runner,code_version="x").runs,run_experiment(self.plan(seed=2),runner,code_version="x").runs)
    def test_run_limit(self):
        with self.assertRaises(ValueError): self.plan(runs=11)
    def test_dry_run_estimate(self): self.assertEqual(estimate_experiment(self.plan(dry_run=True))["files"],0)
    def test_api_limit_structure(self): self.assertEqual(estimate_experiment(ExperimentPlan("s",1,3,3,False,2))["maximum_api_calls"],6)
    def test_summary(self):
        r=run_experiment(self.plan(),runner,code_version="v"); self.assertEqual(r.metadata["classification"],"deterministic prototype runs"); self.assertIn("homeostasis_stddev",r.summary)
    def test_atomic_save_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"result.json"; r=run_experiment(self.plan(),runner,code_version="v"); save_result_atomic(r,p); before=p.read_bytes()
            with self.assertRaises(FileExistsError): save_result_atomic(r,p)
            self.assertEqual(before,p.read_bytes())
    def test_missing_metric_rejected(self):
        with self.assertRaises(ValueError): run_experiment(self.plan(runs=1),lambda seed:{},code_version="v")
    def test_bool_numeric_rejected(self):
        with self.assertRaises(ValueError): ExperimentPlan("s",True,1)
if __name__=='__main__':unittest.main()
