"""CLI for explicitly saving new final-layer deterministic research results."""
from __future__ import annotations
import argparse
from homeostasis_core.experiments import ExperimentPlan,run_experiment,save_result_atomic
from simulation_final import run_final_simulation

def main():
    parser=argparse.ArgumentParser();parser.add_argument("output");parser.add_argument("--seed",type=int,default=20260915);parser.add_argument("--runs",type=int,default=1);parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args();plan=ExperimentPlan("scenario_01_farmland_missile",args.seed,args.runs,20,args.dry_run,0)
    if args.dry_run: print({"runs":plan.runs,"api_calls":0,"output":args.output});return
    def one(seed):
        result=run_final_simulation(seed);return {**result["summary"],"causal_history":result["causal_chain"]}
    result=run_experiment(plan,one,code_version="phase8",provider_type="deterministic")
    save_result_atomic(result,args.output)
if __name__=="__main__":main()
