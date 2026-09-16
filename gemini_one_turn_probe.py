"""Bounded real-Gemini probe: eight country agents, exactly one turn.

Purpose: verify that independent country decisions can be selected through the
validated choice-id interface before any 8-turn paid run. This probe performs
at most one Gemini call per country and never retries. It does not call the
coordinator/evaluator and does not claim a research result.
"""
from __future__ import annotations
import json, os
from getpass import getpass
from pathlib import Path

from homeostasis_core.action_choices import build_action_choices, materialize_choice, validate_catalog
from homeostasis_core.emergent_dynamics import INITIAL_EVENT, initial_world_from_scenario, initial_damage_from_scenario, AFFECTED_COUNTRY
from homeostasis_core.gemini_agents import GeminiGateway, create_gemini_client, build_private_views, parse_country_json
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES, calculate_energy_stability, load_resource_network
from homeostasis_core.feasibility import enumerate_feasible_actions

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")
SCENARIO_PATH=Path("scenarios/scenario_01_farmland_missile.json")


def initial_states(configured):
    return {c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],
               "indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},
                             "energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},
               "resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()}
            for c,p in configured.profiles.items()}


def main():
    key=os.environ.get("GEMINI_API_KEY","").strip() or getpass("Gemini API Key（表示されません）: ").strip()
    if not key:raise SystemExit("APIキーなし。APIは呼び出していません。")
    scenario=json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    configured=load_country_configuration(Path("config/country_archetypes.json"))
    states=initial_states(configured)
    world=initial_world_from_scenario(scenario)
    pool={r:0.0 for r in RESOURCE_TYPES};policy={"restricted":[],"suspended":[],"disrupted":[]}
    network=load_resource_network(Path("scenarios/resource_network_sample.json"),COUNTRIES)
    freshness={c:max(45,95-i*6) for i,c in enumerate(sorted(states))}
    snapshot_id="one-turn-probe-start"
    views=build_private_views(snapshot_id,1,world,states,freshness)
    for v in views.values():
        v["current_event"]=INITIAL_EVENT;v["farmland_damage_tons"]=initial_damage_from_scenario(scenario);v["affected_country"]=AFFECTED_COUNTRY
    gateway=GeminiGateway(create_gemini_client(key),max_calls=len(COUNTRIES),retry_limit=0)
    rows=[]
    for country in COUNTRIES:
        feasible=enumerate_feasible_actions(country,states,pool,network,policy)
        choices=build_action_choices(feasible);validate_catalog(country,choices,feasible)
        payload={"task":"Choose exactly one executable action for this country in the current crisis. Return only JSON.",
                 "country":country,"private_view":views[country],"current_event":INITIAL_EVENT,
                 "action_choices":choices,
                 "rules":["Choose exactly one choice_id from action_choices.","Do not invent action_id, recipient, resource or target.","amount must be 0 for maximum_amount 0; otherwise >0 and <= maximum_amount."],
                 "output_schema":{"choice_id":"string","amount":"number","description":"short Japanese reason"}}
        raw=gateway.call(country,1,1,payload,lambda text,ids: json.loads(text),allowed_ids={x["choice_id"] for x in choices},agent_type="choice_probe",validation_help={})
        # Gateway parser is intentionally minimal here; validate the model output ourselves.
        if not isinstance(raw,dict):raise RuntimeError(f"{country}: response is not an object")
        choice_id=raw.get("choice_id");amount=raw.get("amount");description=raw.get("description","")
        if choice_id not in {x["choice_id"] for x in choices}:raise RuntimeError(f"{country}: unknown choice_id {choice_id!r}")
        action=materialize_choice(country,choice_id,amount,description,choices,feasible)
        rows.append({"country":country,"choice_id":choice_id,"action":action["action_id"],"contract":"PASS"})
    print("=== GEMINI ONE TURN PROBE ===")
    print("PROBE: PASS")
    print(f"Gemini API calls: {len(gateway.calls)}")
    print("Countries completed: 8/8")
    print("Contract validation: PASS (8/8)")
    print("Retries: 0")
    print("World settlement: NOT RUN (probe only)")
    for row in rows:print(f'{row["country"]}: {row["choice_id"]} -> {row["action"]} [{row["contract"]}]')

if __name__=="__main__":main()
