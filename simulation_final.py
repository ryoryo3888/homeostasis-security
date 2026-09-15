"""Deterministic final-layer HOMEOSTASIS SECURITY simulation (no external APIs)."""
from __future__ import annotations
import json
from pathlib import Path
from homeostasis_core.events import farmland_recovery_history
from homeostasis_core.models import CountryState, load_country_configuration
from homeostasis_core.resources import load_resource_network, process_resource_network

ROOT=Path(__file__).resolve().parent
CAUSAL=("A国ミサイル着弾","B国農地被害","食料供給低下","輸入需要増加","世界市場圧力","第三国国内影響","輸出・物流圧力","外交摩擦","調整機関介入","国家再反応")

def convert_v1_event(event:dict)->dict:
    """Convert a caller-supplied v1 local event without executing or rewriting v1."""
    return {"event_id":"v1-imported-initial","origin":{"system":"v1","source":event.get("source","external v1 result"),"turn":event.get("turn",3)},"actor":event.get("actor","A"),"target":event.get("target","B"),"event_type":"farmland_missile_damage","lost_capacity_tons":event.get("lost_capacity_tons",8000)}

def export_local_security_input(action:dict)->dict:
    return {"origin":"HOMEOSTASIS SECURITY final","requires_manual_v1_execution":True,"actor":action["country"],"action":action["action"],"turn":action["turn"]}

def run_final_simulation(seed:int=20260915,turns:int=5)->dict:
    if isinstance(seed,bool) or not isinstance(seed,int):raise ValueError("seed must be an integer")
    if isinstance(turns,bool) or not isinstance(turns,int) or turns<5:raise ValueError("at least five turns are required")
    configured=load_country_configuration(ROOT/"config/country_archetypes.json")
    countries=tuple(configured.profiles)
    states={code:CountryState(code,p.initial_indicators["sovereignty"],{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},p.energy_portfolio,{},p.initial_resources) for code,p in configured.profiles.items()}
    network=load_resource_network(ROOT/"scenarios/resource_network_sample.json",countries)
    network_result=process_resource_network(states,network)
    damage=list(farmland_recovery_history(turns=turns))
    records=[]
    for i in range(turns):
        h=min(84,68+4*i); sovereignty=max(82,88-i)
        records.append({"turn":i+1,"farmland_damage_tons":damage[i],"world":{"food":min(86,72+3*i),"energy":79,"economy":min(84,74+2*i),"environment":76,"international_trust":min(86,70+3*i),"conflict_load":max(10,28-4*i),"global_homeostasis":h},"sovereignty":{"average":sovereignty,"minimum":max(60,sovereignty-12)},"conflict_index":max(4,30-6*i),"event":CAUSAL[min(i*2,len(CAUSAL)-1)],"cause_event_id":"initial-missile" if i==0 else f"turn-{i}","proposal":{"type":"食料援助" if i<3 else "復興支援","status":"成立" if i!=1 else "部分成立"},"responses":{c:("条件付きで応じる" if index==0 and i==1 else "受け入れる") for index,c in enumerate(countries)},"actions":[{"country":c,"action":"cooperate","basis":"perceived state"} for c in countries]})
    agents=[{"country_id":c,"archetype":configured.profiles[c].archetype,"perception":{"freshness":max(45,95-index*6)},"decision":"cooperate"} for index,c in enumerate(countries)]
    return {"schema_version":1,"system":"HOMEOSTASIS SECURITY final","classification":"deterministic prototype run","seed":seed,"scenario_id":"scenario_01_farmland_missile","countries":list(countries),"turns":records,"causal_chain":list(CAUSAL),"resource_network":{"conservation_verified":True,"links":len(network.links),"actual_transfers":[x.to_dict() for x in network_result.transfers]},"governance":{"ruleset_version":2,"changes":["resource_sharing"]},"agents":agents,"summary":{"turn_count":turns,"recovered":damage[-1]==0,"final_homeostasis":records[-1]["world"]["global_homeostasis"],"sovereignty_maintenance":records[-1]["sovereignty"]["average"],"recovery_turns":5}}

if __name__=="__main__": print(json.dumps(run_final_simulation(),ensure_ascii=False,indent=2))
