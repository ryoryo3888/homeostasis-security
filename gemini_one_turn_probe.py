"""Bounded real-Gemini probe: eight country agents, exactly one turn.

At most one Gemini call per country, no retries. This stage validates that all
8 independent countries can select immutable Python-generated choice IDs.
World settlement is deliberately deferred until this paid boundary passes.
"""
from __future__ import annotations
import json, os
from getpass import getpass
from pathlib import Path

from homeostasis_core.action_choices import build_action_choices, materialize_choice, validate_catalog
from homeostasis_core.emergent_dynamics import INITIAL_EVENT, initial_world_from_scenario, initial_damage_from_scenario, AFFECTED_COUNTRY
from homeostasis_core.gemini_agents import MODEL_NAME, create_gemini_client, build_private_views
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES, calculate_energy_stability, load_resource_network
from homeostasis_core.feasibility import feasible_actions

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")
SCENARIO_PATH=Path("scenarios/scenario_01_farmland_missile.json")


def initial_states(configured):
    return {c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],
               "indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},
                             "energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},
               "resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()}
            for c,p in configured.profiles.items()}


def main():
    scenario=json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    configured=load_country_configuration(Path("config/country_archetypes.json"));states=initial_states(configured)
    world=initial_world_from_scenario(scenario);pool={r:0.0 for r in RESOURCE_TYPES};policy={"restricted":[],"suspended":[],"disrupted":[]}
    network=load_resource_network(Path("scenarios/resource_network_sample.json"),COUNTRIES)
    freshness={c:max(45,95-i*6) for i,c in enumerate(sorted(states))};views=build_private_views("one-turn-probe-start",1,world,states,freshness)
    for v in views.values():v.update({"current_event":INITIAL_EVENT,"farmland_damage_tons":initial_damage_from_scenario(scenario),"affected_country":AFFECTED_COUNTRY})
    # Build and validate every country's catalog BEFORE asking for an API key.
    prepared={}
    for country in COUNTRIES:
        feasible=feasible_actions(country,states,pool,network,policy);choices=build_action_choices(feasible);validate_catalog(country,choices,feasible)
        if not choices:raise SystemExit(f"PROBE: FAIL before API - {country} has no choices; Gemini API calls: 0")
        prepared[country]=(feasible,choices)
    key=os.environ.get("GEMINI_API_KEY","").strip() or getpass("Gemini API Key（表示されません）: ").strip()
    if not key:raise SystemExit("PROBE: STOP - API key missing; Gemini API calls: 0")
    client=create_gemini_client(key);calls=0;rows=[]
    for country in COUNTRIES:
        feasible,choices=prepared[country]
        payload={"probe":"eight-country-one-turn-choice-boundary","country_id":country,"current_event":INITIAL_EVENT,"private_observation":views[country],
                 "instruction":"Choose exactly one choice_id. Do not invent action fields. fraction=0 when maximum_amount=0; otherwise fraction must be >0 and <=1.","action_choices":list(choices)}
        schema={"type":"object","additionalProperties":False,"required":["choice_id","fraction","reason"],"properties":{"choice_id":{"type":"string","enum":[x["choice_id"] for x in choices]},"fraction":{"type":"number","minimum":0,"maximum":1},"reason":{"type":"string"}}}
        try:
            calls+=1
            response=client.models.generate_content(model=MODEL_NAME,contents=json.dumps(payload,ensure_ascii=False),config={"response_mime_type":"application/json","response_json_schema":schema})
            answer=json.loads(response.text);chosen=next(x for x in choices if x["choice_id"]==answer["choice_id"]);maximum=float(chosen["maximum_amount"]);fraction=float(answer["fraction"])
            if maximum==0:
                if fraction!=0:raise ValueError("zero-amount choice requires fraction=0")
                amount=0.0
            else:
                if not 0<fraction<=1:raise ValueError("transfer choice requires fraction >0 and <=1")
                amount=maximum*fraction
            action=materialize_choice(country,answer["choice_id"],amount,answer["reason"],choices,feasible)
            rows.append((country,answer["choice_id"],action["action_id"]))
        except Exception as exc:
            print("=== GEMINI ONE TURN PROBE ===");print("PROBE: FAIL");print(f"Gemini API calls: {calls}");print(f"Countries completed: {len(rows)}/8");print("Retries: 0");print(f"Failed country: {country}");print(f"Error: {type(exc).__name__}: {exc}");raise SystemExit(1)
    print("=== GEMINI ONE TURN PROBE ===");print("PROBE: PASS");print(f"Gemini API calls: {calls}");print("Countries completed: 8/8");print("Contract validation: PASS (8/8)");print("Retries: 0");print("World settlement: NOT RUN (probe only)")
    for country,choice,action in rows:print(f"{country}: {choice} -> {action} [PASS]")

if __name__=="__main__":main()
