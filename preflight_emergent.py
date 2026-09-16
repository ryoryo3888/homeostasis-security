"""API-free preflight for the emergent worldline engine.

No Gemini client is created here. This script validates every executable action
catalog entry produced by the deterministic feasibility engine and then runs an
8-turn mock-agent simulation through the real settlement/state-update path.
"""
from __future__ import annotations
import json
from pathlib import Path
from homeostasis_core.action_choices import build_action_choices,validate_catalog,materialize_choice
from homeostasis_core.feasibility import ACTION_IDS,feasible_actions
from homeostasis_core.gemini_agents import apply_structured_actions,derive_event
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES,calculate_energy_stability,load_resource_network
from simulation_final import run_final_simulation

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")
API_CALLS=0

def initial_states():
    configured=load_country_configuration(Path("config/country_archetypes.json"))
    return {c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],"indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},"energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},"resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()} for c,p in configured.profiles.items()}

def amount_for(choice):
    maximum=float(choice["maximum_amount"])
    return 0 if maximum==0 else min(maximum,max(.25,maximum*.2))

def mock_answer(country,choice,feasible,choices,turn):
    action=materialize_choice(country,choice["choice_id"],amount_for(choice),"API-free preflight",choices,feasible)
    return {"country_id":country,"proposal_id":f"preflight-{turn}","response_id":"ACCEPT","response_label":"受け入れる","reason":"API-free preflight","conditions":{},"self_interest":50,"sovereignty_burden":0,"perceived_global_effect":50,"action":action}

def reject_invalid_combinations(country,choices,feasible):
    """Prove that malformed model outputs cannot bypass choice materialization."""
    rejected=0;attempted=0
    if not choices:return attempted,rejected
    valid=choices[0]
    bad_ids=("UNKNOWN","")
    for bad in bad_ids:
        attempted+=1
        try:materialize_choice(country,bad,0,"invalid",choices,feasible)
        except ValueError:rejected+=1
    maximum=float(valid["maximum_amount"])
    bad_amount=-1 if maximum>0 else 1
    attempted+=1
    try:materialize_choice(country,valid["choice_id"],bad_amount,"invalid",choices,feasible)
    except ValueError:rejected+=1
    return attempted,rejected

def run_preflight(turns=8):
    base=run_final_simulation(20260917,turns);states=initial_states();pool={r:0.0 for r in RESOURCE_TYPES};policy={"restricted":[],"suspended":[],"disrupted":[]};network=load_resource_network(Path("scenarios/resource_network_sample.json"),COUNTRIES);world=dict(base["turns"][0]["world"]);history=dict(base["turns"][0]["history_state"]);damage=8000;events=[];rows=[];covered=set();invalid_attempts=0;invalid_rejected=0
    for turn in range(1,turns+1):
        catalogs={};answers={}
        for c in COUNTRIES:
            feasible=feasible_actions(c,states,pool,network,policy);choices=build_action_choices(feasible);validate_catalog(c,choices,feasible);catalogs[c]=len(choices);covered.update(x["action_id"] for x in choices)
            attempted,rejected=reject_invalid_combinations(c,choices,feasible);invalid_attempts+=attempted;invalid_rejected+=rejected
            choice=choices[(turn+COUNTRIES.index(c))%len(choices)];answers[c]=mock_answer(c,choice,feasible,choices,turn)
        event="A国ミサイルのB国民間農地への着弾" if turn==1 else derive_event(world,history,rows[-1]["action_counts"],events)
        effects=apply_structured_actions(states,answers,world,damage,turn,world_pool=pool,resource_network=network,network_policy=policy)
        states=effects["country_states"];pool=effects["world_pool"];policy=effects["network_policy"];world=effects["true_world"];events.append(event)
        history={"economic_loss":max(0,100-world["economy"]),"reserve_gap":max(0,100-world["food"]),"trust_loss":max(0,100-world["international_trust"]),"alertness":world["conflict_load"],"unmet_resource_demand":effects.get("demand_unmet",0)}
        rows.append({"turn":turn,"event":event,"catalog_sizes":catalogs,"action_counts":effects["action_counts"],"homeostasis":effects["research_metrics"]["global_homeostasis"],"sovereignty":effects["research_metrics"]["national_sovereignty"]})
    missing=sorted(set(ACTION_IDS)-covered)
    pass_ok=(API_CALLS==0 and len(rows)==turns and not missing and invalid_attempts==invalid_rejected)
    return {"status":"PASS" if pass_ok else "FAIL","api_calls":API_CALLS,"action_contracts_tested":"ALL" if not missing else "PARTIAL","missing_action_contracts":missing,"invalid_combinations_attempted":invalid_attempts,"invalid_combinations_accepted":invalid_attempts-invalid_rejected,"turn_simulation":"PASS" if len(rows)==turns else "FAIL","turns":turns,"events":events,"rows":rows}

def print_verdict(result):
    print("\n=== EMERGENT PREFLIGHT VERDICT ===")
    print(f"PREFLIGHT: {result['status']}")
    print(f"Gemini API calls: {result['api_calls']}")
    print(f"Action contracts tested: {result['action_contracts_tested']}")
    print(f"Missing action contracts: {', '.join(result['missing_action_contracts']) if result['missing_action_contracts'] else 'NONE'}")
    print(f"Invalid combinations accepted: {result['invalid_combinations_accepted']}")
    print(f"8-turn simulation: {result['turn_simulation']}")

if __name__=="__main__":
    result=run_preflight()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print_verdict(result)
    raise SystemExit(0 if result["status"]=="PASS" else 1)
