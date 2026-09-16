"""Exactly-one-call Gemini probe for the choice-ID boundary.

This is deliberately NOT a simulation run. It tests only the paid boundary:
Gemini sees one country's private observation plus immutable Python-generated
choices, returns one choice_id and bounded amount fraction, and Python
materializes/validates the executable action. No retry is performed.
"""
from __future__ import annotations
import json, os
from getpass import getpass
from pathlib import Path

from homeostasis_core.action_choices import build_action_choices, materialize_choice
from homeostasis_core.feasibility import feasible_actions
from homeostasis_core.gemini_agents import MODEL_NAME, create_gemini_client
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES, calculate_energy_stability, load_resource_network

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")
COUNTRY="MIL"


def initial_states():
    configured=load_country_configuration(Path("config/country_archetypes.json"))
    return {c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],"indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},"energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},"resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()} for c,p in configured.profiles.items()}


def main():
    states=initial_states();pool={r:0.0 for r in RESOURCE_TYPES};policy={"restricted":[],"suspended":[],"disrupted":[]}
    network=load_resource_network(Path("scenarios/resource_network_sample.json"),COUNTRIES)
    feasible=feasible_actions(COUNTRY,states,pool,network,policy);choices=build_action_choices(feasible)
    if not choices:raise SystemExit("PROBE: FAIL - no feasible choices; Gemini API calls: 0")
    key=os.environ.get("GEMINI_API_KEY","").strip() or getpass("Gemini API Key（表示されません）: ").strip()
    if not key:raise SystemExit("PROBE: STOP - API key missing; Gemini API calls: 0")
    payload={
        "probe":"choice-id-boundary-only",
        "country_id":COUNTRY,
        "instruction":"Choose exactly one choice_id from action_choices. Do not invent action fields. fraction must be 0 for maximum_amount=0; otherwise choose a number >0 and <=1.",
        "private_observation":{"archetype":states[COUNTRY]["archetype"],"sovereignty":states[COUNTRY]["sovereignty"],"indicators":states[COUNTRY]["indicators"],"resources":states[COUNTRY]["resources"]},
        "action_choices":list(choices),
    }
    schema={"type":"object","additionalProperties":False,"required":["choice_id","fraction","reason"],"properties":{"choice_id":{"type":"string","enum":[x["choice_id"] for x in choices]},"fraction":{"type":"number","minimum":0,"maximum":1},"reason":{"type":"string"}}}
    client=create_gemini_client(key);calls=0
    try:
        calls+=1
        response=client.models.generate_content(model=MODEL_NAME,contents=json.dumps(payload,ensure_ascii=False),config={"response_mime_type":"application/json","response_json_schema":schema})
        answer=json.loads(response.text)
        chosen=next(x for x in choices if x["choice_id"]==answer["choice_id"]);maximum=float(chosen["maximum_amount"])
        fraction=float(answer["fraction"])
        if maximum==0:
            if fraction!=0:raise ValueError("zero-amount choice requires fraction=0")
            amount=0.0
        else:
            if not 0<fraction<=1:raise ValueError("transfer choice requires fraction >0 and <=1")
            amount=maximum*fraction
        action=materialize_choice(COUNTRY,answer["choice_id"],amount,answer["reason"],choices,feasible)
    except Exception as exc:
        print("=== GEMINI CHOICE PROBE ===");print("PROBE: FAIL");print(f"Gemini API calls: {calls}");print(f"Error: {type(exc).__name__}: {exc}");raise SystemExit(1)
    print("=== GEMINI CHOICE PROBE ===");print("PROBE: PASS");print(f"Gemini API calls: {calls}");print(f"Country: {COUNTRY}");print(f"Choice ID: {answer['choice_id']}");print(f"Executable action: {action['action_id']}");print("Contract validation: PASS");print("Retries: 0")

if __name__=="__main__":main()
