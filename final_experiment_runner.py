"""Safe emergent 8-turn Gemini experiment runner; dry-run is the default.

Research rule: only the initial shock is fixed. From turn 2 onward, events are
derived from the previous executed world state and agent actions. Farmland
recovery is likewise derived from realized reconstruction capacity, never from
a pre-scripted per-turn recovery table.
"""
from __future__ import annotations
import argparse,json,os,tempfile,statistics
from getpass import getpass
from pathlib import Path
from response_receipts import ResponseReceipts
from homeostasis_core.emergent_dynamics import (
    AFFECTED_COUNTRY, INITIAL_EVENT, initial_damage_from_scenario,
    initial_world_from_scenario, reconstruction_step,
)
from homeostasis_core.experiments import ResearchResult,save_result_atomic
from homeostasis_core.gemini_agents import (
    GeminiGateway,MODEL_NAME,SCHEMA_VERSION,build_private_views,create_gemini_client,
    derive_event,run_gemini_turn,
)
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resume_guard import read_resumable_checkpoint
from homeostasis_core.resources import RESOURCE_TYPES,calculate_energy_stability,load_resource_network

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")
TURNS=8;PLANNED_CALLS_PER_RUN=80;RETRY_LIMIT=3;MAX_CALLS_PER_RUN=240;MAX_RUNS=36
SCENARIO_PATH=Path("scenarios/scenario_01_farmland_missile.json")

def estimate(runs:int)->dict:
    if isinstance(runs,bool) or not isinstance(runs,int) or not 1<=runs<=MAX_RUNS:raise ValueError("runs must be 1..36")
    return {"mode":"dry-run","research_mode":"emergent-worldlines","runs":runs,"turns":TURNS,
            "agents_per_turn":10,"planned_api_calls":runs*PLANNED_CALLS_PER_RUN,
            "maximum_api_attempts":runs*MAX_CALLS_PER_RUN,"model":MODEL_NAME,
            "fixed_story_events":1,"derived_story_events":TURNS-1}

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

def _load_scenario()->dict:
    scenario=json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    if scenario.get("scenario_id")!="scenario_01_farmland_missile":raise ValueError("unexpected scenario")
    return scenario

def _initial_states(configured):
    return {c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],
               "indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},
                             "energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},
               "resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()}
            for c,p in configured.profiles.items()}

def _freshness(country_states):
    return {c:max(45,95-i*6) for i,c in enumerate(sorted(country_states))}

def _recovery_turn(turn_rows):
    for row in turn_rows:
        if row["executed_state"]["reconstruction"]["after"]<=0:return row["turn"]
    return None

def run_live(client,output:Path,runs:int,seed:int,resume:bool=False)->dict:
    if os.path.lexists(output):raise FileExistsError("output already exists")
    estimate(runs);checkpoint=output.with_suffix(output.suffix+".checkpoint");completed=[];active=None
    scenario=_load_scenario()
    if resume:
        saved=read_resumable_checkpoint(checkpoint,runs=runs,seed=seed,
                                        turn_count=TURNS,model=MODEL_NAME,country_ids=COUNTRIES,schema_version=SCHEMA_VERSION)
        completed=saved["completed_runs"];active=saved.get("active_run")
    elif checkpoint.exists():raise FileExistsError("checkpoint exists; use --resume")
    receipts=ResponseReceipts.for_output(output)
    for record in completed+([active] if active is not None else []):
        receipts.verify(record["call_audit"])
    receipts.prepare(resume=resume)
    for run_number in range(len(completed)+1,runs+1):
        run_seed=seed+run_number-1
        gateway=GeminiGateway(client,max_calls=MAX_CALLS_PER_RUN,retry_limit=RETRY_LIMIT)
        configured=load_country_configuration(Path("config/country_archetypes.json"))
        initial_states=_initial_states(configured)
        resource_network=load_resource_network(Path("scenarios/resource_network_sample.json"),COUNTRIES)
        freshness=_freshness(initial_states)
        if active is not None:
            if active.get("run")!=run_number or active.get("seed")!=run_seed:raise ValueError("checkpoint run or seed mismatch")
            turn_rows=active["turns"];memories={c:tuple(active["memories"][c]) for c in COUNTRIES}
            current_world=dict(active["current_world"]);country_states=active["country_states"]
            world_pool=active["world_pool"];network_policy=active["network_policy"]
            history_state=active["history_state"];current_damage=float(active["current_damage"])
            gateway.calls=list(active["call_audit"])
        else:
            turn_rows=[];memories={c:() for c in COUNTRIES};current_world=initial_world_from_scenario(scenario)
            country_states=initial_states;world_pool={r:0.0 for r in RESOURCE_TYPES}
            network_policy={"restricted":[],"suspended":[],"disrupted":[]}
            history_state={"economic_loss":max(0,100-current_world["economy"]),
                           "reserve_gap":max(0,100-current_world["food"]),
                           "trust_loss":max(0,100-current_world["international_trust"]),
                           "alertness":current_world["conflict_load"],"unmet_resource_demand":0}
            current_damage=initial_damage_from_scenario(scenario)
        def save_attempt_audit(calls):
            in_progress={"run":run_number,"seed":run_seed,"completed_turn":len(turn_rows),"turns":turn_rows,
                         "memories":memories,"current_world":current_world,"country_states":country_states,
                         "world_pool":world_pool,"network_policy":network_policy,"history_state":history_state,
                         "current_damage":current_damage,"call_audit":calls}
            _checkpoint(checkpoint,{"completed_runs":completed,"active_run":in_progress})
        gateway.audit_hook=save_attempt_audit
        gateway.response_hook=receipts.record
        for turn in range(len(turn_rows)+1,TURNS+1):
            if turn==1:
                event=INITIAL_EVENT;event_origin="fixed_initial_condition"
            else:
                event=derive_event(current_world,history_state,
                                   turn_rows[-1]["executed_state"]["action_counts"],
                                   [x["snapshot"]["event"] for x in turn_rows])
                event_origin="derived_from_previous_executed_state"
            snapshot={"snapshot_id":f"run-{run_number}-turn-{turn}-start","decision_seed":run_seed,
                      "turn":turn,"world":current_world,"damage":current_damage,"event":event,
                      "event_origin":event_origin,"affected_country":AFFECTED_COUNTRY,
                      "initial_shock":scenario["event"],"history_state":history_state,
                      "world_pool":world_pool,"network_policy":network_policy,
                      "public_history":[x["snapshot"]["event"] for x in turn_rows]}
            views=build_private_views(snapshot["snapshot_id"],turn,current_world,country_states,freshness)
            for view in views.values():
                view["current_event"]=event;view["farmland_damage_tons"]=current_damage
                view["affected_country"]=AFFECTED_COUNTRY
            result=run_gemini_turn(gateway,run_number,turn,snapshot,views,memories,COUNTRIES,
                                   country_states=country_states,world_pool=world_pool,
                                   resource_network=resource_network,network_policy=network_policy)
            reconstruction=reconstruction_step(current_damage,result["executed_state"],
                                               result["executed_state"]["country_states"])
            result["executed_state"]["reconstruction"]=reconstruction
            result["executed_state"]["causal_record"]["farmland_reconstruction"]=reconstruction
            turn_rows.append(result)
            current_damage=reconstruction["after"]
            current_world=dict(result["executed_state"]["true_world"])
            country_states=result["executed_state"]["country_states"];world_pool=result["executed_state"]["world_pool"]
            network_policy=result["executed_state"]["network_policy"]
            history_state={"economic_loss":max(0,100-current_world["economy"]),
                           "reserve_gap":max(0,100-current_world["food"]),
                           "trust_loss":max(0,100-current_world["international_trust"]),
                           "alertness":current_world["conflict_load"],
                           "unmet_resource_demand":result["executed_state"].get("demand_unmet",0)}
            memories={c:memories[c]+({"response_id":result["country_responses"][c]["response_id"],
                                      "action_id":result["country_responses"][c]["action"]["action_id"],
                                      "realized":sum(x["realized"] for x in result["executed_state"].get("atomic_settlements",[]) if x["agent_id"]==c),
                                      "unmet":sum(x["unmet"] for x in result["executed_state"].get("atomic_settlements",[]) if x["agent_id"]==c),
                                      "event":event,"damage_after":current_damage},) for c in COUNTRIES}
            active={"run":run_number,"seed":run_seed,"completed_turn":turn,"turns":turn_rows,"memories":memories,
                    "current_world":current_world,"country_states":country_states,"world_pool":world_pool,
                    "network_policy":network_policy,"history_state":history_state,"current_damage":current_damage,
                    "call_audit":gateway.calls}
            _checkpoint(checkpoint,{"completed_runs":completed,"active_run":active})
        token_totals={k:sum(x["token_usage"][k] for x in gateway.calls if x["token_usage"][k] is not None)
                      for k in ("input_tokens","output_tokens","total_tokens")}
        completed.append({"run":run_number,"seed":run_seed,"model":MODEL_NAME,"research_mode":"emergent-worldlines",
                          "turns":turn_rows,"response_convergence_detected":all(x["response_convergence"] for x in turn_rows),
                          "call_audit":gateway.calls,"token_usage":token_totals,"resume_point":{"completed_turn":TURNS}})
        active=None;_checkpoint(checkpoint,{"completed_runs":completed,"active_run":None})
    rows=[]
    for r in completed:
        recovery_turn=_recovery_turn(r["turns"])
        rows.append({"recovered":recovery_turn is not None,
                     "final_homeostasis":r["turns"][-1]["research_metrics"]["global_homeostasis"],
                     "sovereignty_maintenance":r["turns"][-1]["research_metrics"]["national_sovereignty"],
                     "recovery_turns":recovery_turn if recovery_turn is not None else TURNS+1,"details":r})
    rows=tuple(rows)
    metadata={"mode":"gemini","research_mode":"emergent-worldlines","model":MODEL_NAME,"seed":seed,"runs":runs,
              "turns":TURNS,"provider":"GeminiGateway","fixed_initial_events":1,
              "derived_event_turns":list(range(2,TURNS+1))}
    homeostasis=[x["final_homeostasis"] for x in rows];sovereignty=[x["sovereignty_maintenance"] for x in rows]
    recovered_turns=[x["recovery_turns"] for x in rows if x["recovered"]]
    summary={"average_homeostasis":statistics.fmean(homeostasis),
             "homeostasis_stddev":statistics.pstdev(homeostasis),
             "recovery_rate":100*sum(x["recovered"] for x in rows)/len(rows),
             "sovereignty_maintenance_rate":statistics.fmean(sovereignty),
             "average_recovery_turns":statistics.fmean(recovered_turns) if recovered_turns else None}
    save_result_atomic(ResearchResult(metadata,rows,summary),output)
    checkpoint.unlink(missing_ok=True);return {"metadata":metadata,"runs":completed}

def parse_args():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=Path("results/final/gemini-emergent-worldlines.json"))
    p.add_argument("--runs",type=int,default=1);p.add_argument("--seed",type=int,default=20260917)
    p.add_argument("--execute",action="store_true");p.add_argument("--confirm");p.add_argument("--one-run",action="store_true")
    p.add_argument("--resume",action="store_true");return p.parse_args()

def main():
    a=parse_args();runs=1 if a.one_run else a.runs;print(json.dumps(estimate(runs),ensure_ascii=False,indent=2))
    if not a.execute:return
    if a.confirm!="YES":raise SystemExit("本番実行には --execute --confirm YES が必要です。APIは呼び出していません。")
    if os.path.lexists(a.output):raise SystemExit("出力先が存在します。APIは呼び出していません。")
    if a.resume:
        read_resumable_checkpoint(a.output.with_suffix(a.output.suffix+".checkpoint"),
                                  runs=runs,seed=a.seed,turn_count=TURNS,
                                  model=MODEL_NAME,country_ids=COUNTRIES,schema_version=SCHEMA_VERSION)
    key=os.environ.get("GEMINI_API_KEY","").strip() or getpass("Gemini API Key（表示されません）: ").strip()
    if not key:raise SystemExit("GEMINI_API_KEYがないため停止しました。APIは呼び出していません。")
    run_live(create_gemini_client(key),a.output,runs,a.seed,a.resume)
if __name__=="__main__":main()
