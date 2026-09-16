"""Safe 8-turn Gemini experiment runner; dry-run is the default."""
from __future__ import annotations
import argparse,json,os,tempfile,statistics
from getpass import getpass
from pathlib import Path
from homeostasis_core.experiments import ResearchResult,save_result_atomic
from homeostasis_core.gemini_agents import GeminiGateway,MODEL_NAME,build_private_views,create_gemini_client,derive_event,run_gemini_turn
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES,calculate_energy_stability,load_resource_network
from simulation_final import run_final_simulation

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")
TURNS=8;PLANNED_CALLS_PER_RUN=80;RETRY_LIMIT=3;MAX_CALLS_PER_RUN=240;MAX_RUNS=36

def estimate(runs:int)->dict:
    if isinstance(runs,bool) or not isinstance(runs,int) or not 1<=runs<=MAX_RUNS:raise ValueError("runs must be 1..36")
    return {"mode":"dry-run","runs":runs,"turns":TURNS,"agents_per_turn":10,"planned_api_calls":runs*PLANNED_CALLS_PER_RUN,"maximum_api_attempts":runs*MAX_CALLS_PER_RUN,"model":MODEL_NAME}

def _checkpoint(path:Path,data:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".checkpoint-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(data,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    except BaseException:
        try:os.unlink(name)
        except FileNotFoundError:pass
        raise

def run_live(client,output:Path,runs:int,seed:int,resume:bool=False)->dict:
    if output.exists():raise FileExistsError("output already exists")
    estimate(runs);checkpoint=output.with_suffix(output.suffix+".checkpoint");completed=[];active=None
    if resume and checkpoint.exists():
        saved=json.loads(checkpoint.read_text());completed=saved["completed_runs"];active=saved.get("active_run")
    elif checkpoint.exists():raise FileExistsError("checkpoint exists; use --resume")
    for run_number in range(len(completed)+1,runs+1):
        gateway=GeminiGateway(client,max_calls=MAX_CALLS_PER_RUN,retry_limit=RETRY_LIMIT)
        base=run_final_simulation(seed+run_number-1,TURNS)
        configured=load_country_configuration(Path("config/country_archetypes.json"))
        initial_states={c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],"indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},"energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},"resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()} for c,p in configured.profiles.items()}
        resource_network=load_resource_network(Path("scenarios/resource_network_sample.json"),COUNTRIES)
        freshness={a["country_id"]:a["perception"]["freshness"] for a in base["agents"]}
        if active is not None:
            if active.get("run")!=run_number or active.get("seed")!=seed+run_number-1:raise ValueError("checkpoint run or seed mismatch")
            turn_rows=active["turns"];memories={c:tuple(active["memories"][c]) for c in COUNTRIES};current_world=dict(active["current_world"]);country_states=active["country_states"];world_pool=active["world_pool"];network_policy=active["network_policy"];history_state=active["history_state"];gateway.calls=list(active["call_audit"])
        else:turn_rows=[];memories={c:() for c in COUNTRIES};current_world=dict(base["turns"][0]["world"]);country_states=initial_states;world_pool={r:0.0 for r in RESOURCE_TYPES};network_policy={"restricted":[],"suspended":[],"disrupted":[]};history_state=dict(base["turns"][0]["history_state"])
        def save_attempt_audit(calls):
            in_progress={"run":run_number,"seed":seed+run_number-1,"completed_turn":len(turn_rows),"turns":turn_rows,"memories":memories,"current_world":current_world,"country_states":country_states,"world_pool":world_pool,"network_policy":network_policy,"history_state":history_state,"call_audit":calls}
            _checkpoint(checkpoint,{"completed_runs":completed,"active_run":in_progress})
        gateway.audit_hook=save_attempt_audit
        for turn in range(len(turn_rows)+1,TURNS+1):
            row=base["turns"][turn-1]
            event=row["event"] if turn<=5 else derive_event(current_world,history_state,turn_rows[-1]["executed_state"]["action_counts"],[x["snapshot"]["event"] for x in turn_rows])
            snapshot={"snapshot_id":f"run-{run_number}-turn-{turn}-start","decision_seed":seed+run_number-1,"turn":turn,"world":current_world,"damage":row["farmland_damage_tons"],"event":event,"history_state":history_state,"world_pool":world_pool,"network_policy":network_policy,"public_history":[x["snapshot"]["event"] for x in turn_rows]}
            views=build_private_views(snapshot["snapshot_id"],turn,current_world,country_states,freshness)
            result=run_gemini_turn(gateway,run_number,turn,snapshot,views,memories,COUNTRIES,country_states=country_states,world_pool=world_pool,resource_network=resource_network,network_policy=network_policy);turn_rows.append(result)
            current_world=dict(result["executed_state"]["true_world"]);country_states=result["executed_state"]["country_states"];world_pool=result["executed_state"]["world_pool"];network_policy=result["executed_state"]["network_policy"]
            history_state={"economic_loss":max(0,100-current_world["economy"]),"reserve_gap":max(0,100-current_world["food"]),"trust_loss":max(0,100-current_world["international_trust"]),"alertness":current_world["conflict_load"],"unmet_resource_demand":result["executed_state"].get("demand_unmet",0)}
            memories={c:memories[c]+({"response_id":result["country_responses"][c]["response_id"],"action_id":result["country_responses"][c]["action"]["action_id"],"realized":sum(x["realized"] for x in result["executed_state"].get("atomic_settlements",[]) if x["agent_id"]==c),"unmet":sum(x["unmet"] for x in result["executed_state"].get("atomic_settlements",[]) if x["agent_id"]==c)},) for c in COUNTRIES}
            active={"run":run_number,"seed":seed+run_number-1,"completed_turn":turn,"turns":turn_rows,"memories":memories,"current_world":current_world,"country_states":country_states,"world_pool":world_pool,"network_policy":network_policy,"history_state":history_state,"call_audit":gateway.calls}
            _checkpoint(checkpoint,{"completed_runs":completed,"active_run":active})
        token_totals={k:sum(x["token_usage"][k] for x in gateway.calls if x["token_usage"][k] is not None) for k in ("input_tokens","output_tokens","total_tokens")}
        completed.append({"run":run_number,"seed":seed+run_number-1,"model":MODEL_NAME,"turns":turn_rows,"response_convergence_detected":all(x["response_convergence"] for x in turn_rows),"call_audit":gateway.calls,"token_usage":token_totals,"resume_point":{"completed_turn":TURNS}})
        active=None;_checkpoint(checkpoint,{"completed_runs":completed,"active_run":None})
    rows=tuple({"recovered":r["turns"][-1]["snapshot"]["damage"]==0,"final_homeostasis":r["turns"][-1]["research_metrics"]["global_homeostasis"],"sovereignty_maintenance":r["turns"][-1]["research_metrics"]["national_sovereignty"],"recovery_turns":next((x["turn"] for x in r["turns"] if x["snapshot"]["damage"]==0),TURNS),"details":r} for r in completed)
    metadata={"mode":"gemini","model":MODEL_NAME,"seed":seed,"runs":runs,"turns":TURNS,"provider":"GeminiGateway"}
    homeostasis=[x["final_homeostasis"] for x in rows];sovereignty=[x["sovereignty_maintenance"] for x in rows];recovery=[x["recovery_turns"] for x in rows]
    summary={"average_homeostasis":statistics.fmean(homeostasis),"homeostasis_stddev":statistics.pstdev(homeostasis),"recovery_rate":100*sum(x["recovered"] for x in rows)/len(rows),"sovereignty_maintenance_rate":statistics.fmean(sovereignty),"average_recovery_turns":statistics.fmean(recovery)}
    save_result_atomic(ResearchResult(metadata,rows,summary),output)
    checkpoint.unlink(missing_ok=True);return {"metadata":metadata,"runs":completed}

def parse_args():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=Path("results/final/gemini-run.json"));p.add_argument("--runs",type=int,default=1);p.add_argument("--seed",type=int,default=20260915);p.add_argument("--execute",action="store_true");p.add_argument("--confirm");p.add_argument("--one-run",action="store_true");p.add_argument("--resume",action="store_true");return p.parse_args()
def main():
    a=parse_args();runs=1 if a.one_run else a.runs;print(json.dumps(estimate(runs),ensure_ascii=False,indent=2))
    if not a.execute:return
    if a.confirm!="YES":raise SystemExit("本番実行には --execute --confirm YES が必要です。APIは呼び出していません。")
    if a.output.exists():raise SystemExit("出力先が存在します。APIは呼び出していません。")
    key=os.environ.get("GEMINI_API_KEY","").strip() or getpass("Gemini API Key（表示されません）: ").strip()
    if not key:raise SystemExit("GEMINI_API_KEYがないため停止しました。APIは呼び出していません。")
    run_live(create_gemini_client(key),a.output,runs,a.seed,a.resume)
if __name__=="__main__":main()
