"""API-free preflight for the emergent worldline engine."""
from __future__ import annotations
import json
from pathlib import Path
from homeostasis_core.action_choices import build_action_choices,validate_catalog
from homeostasis_core.feasibility import feasible_actions,settle_atomic_actions
from homeostasis_core.gemini_agents import apply_structured_actions,derive_event
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES,calculate_energy_stability,load_resource_network
from simulation_final import run_final_simulation

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")

def initial_states():
    configured=load_country_configuration(Path("config/country_archetypes.json"))
    return {c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],"indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},"energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},"resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()} for c,p in configured.profiles.items()}

def mock_answer(country,choice,turn):
    maximum=float(choice["maximum_amount"]);amount=0 if maximum==0 else min(maximum,max(.25,maximum*.2))
    return {"country_id":country,"proposal_id":f"preflight-{turn}","response_id":"ACCEPT","response_label":"受け入れる","reason":"API-free preflight","conditions":{},"self_interest":50,"sovereignty_burden":0,"perceived_global_effect":50,"action":{"action_id":choice["action_id"],"description":"preflight","parameters":{"recipient_type":choice["recipient_type"],"target_country":choice["target_country"],"resource":choice["resource"],"amount":amount}}}

def run_preflight(turns=8):
    base=run_final_simulation(20260917,turns);states=initial_states();pool={r:0.0 for r in RESOURCE_TYPES};policy={"restricted":[],"suspended":[],"disrupted":[]};network=load_resource_network(Path("scenarios/resource_network_sample.json"),COUNTRIES);world=dict(base["turns"][0]["world"]);history=dict(base["turns"][0]["history_state"]);damage=8000;events=[];rows=[]
    for turn in range(1,turns+1):
        catalogs={};answers={}
        for c in COUNTRIES:
            feasible=feasible_actions(c,states,pool,network,policy);choices=build_action_choices(feasible);validate_catalog(c,choices,feasible);catalogs[c]=len(choices)
            # Deterministically rotate through the catalog so transfer and non-transfer
            # contracts are both exercised without an API call.
            choice=choices[(turn+COUNTRIES.index(c))%len(choices)];answers[c]=mock_answer(c,choice,turn)
        event="A国ミサイルのB国民間農地への着弾" if turn==1 else derive_event(world,history,rows[-1]["action_counts"],events)
        effects=apply_structured_actions(states,answers,world,damage,turn,world_pool=pool,resource_network=network,network_policy=policy)
        states=effects["country_states"];pool=effects["world_pool"];policy=effects["network_policy"];world=effects["true_world"];events.append(event)
        history={"economic_loss":max(0,100-world["economy"]),"reserve_gap":max(0,100-world["food"]),"trust_loss":max(0,100-world["international_trust"]),"alertness":world["conflict_load"],"unmet_resource_demand":effects.get("demand_unmet",0)}
        rows.append({"turn":turn,"event":event,"catalog_sizes":catalogs,"action_counts":effects["action_counts"],"homeostasis":effects["research_metrics"]["global_homeostasis"],"sovereignty":effects["research_metrics"]["national_sovereignty"]})
    return {"status":"PASS","api_calls":0,"turns":turns,"events":events,"rows":rows}

if __name__=="__main__":print(json.dumps(run_preflight(),ensure_ascii=False,indent=2))
