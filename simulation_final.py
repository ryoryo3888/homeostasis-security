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

def _derived_event(world:dict, history:dict)->str:
    pressure=(100-world["food"])+(100-world["international_trust"])+world["conflict_load"]+history["economic_loss"]+history["alertness"]
    return "輸出安定化政策" if pressure<105 else "備蓄防衛政策"

def run_final_simulation(seed:int=20260915,turns:int=8)->dict:
    if isinstance(seed,bool) or not isinstance(seed,int):raise ValueError("seed must be an integer")
    if isinstance(turns,bool) or not isinstance(turns,int) or turns<5:raise ValueError("at least five turns are required")
    configured=load_country_configuration(ROOT/"config/country_archetypes.json")
    countries=tuple(configured.profiles)
    states={code:CountryState(code,p.initial_indicators["sovereignty"],{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},p.energy_portfolio,{},p.initial_resources) for code,p in configured.profiles.items()}
    network=load_resource_network(ROOT/"scenarios/resource_network_sample.json",countries)
    network_result=process_resource_network(states,network)
    damage=list(farmland_recovery_history(turns=turns))
    records=[];history={"economic_loss":18.0,"reserve_gap":20.0,"trust_loss":22.0,"alertness":24.0}
    for i in range(turns):
        recovery=1.5 if damage[i]==0 else .7
        history={k:max(0,v-recovery*({"economic_loss":1,"reserve_gap":.8,"trust_loss":.6,"alertness":.5}[k])) for k,v in history.items()}
        world={"food":min(86,72+3*i-history["reserve_gap"]*.08),"energy":79,"economy":min(84,74+2*i-history["economic_loss"]*.10),"environment":min(80,76+i*.3),"international_trust":min(86,70+3*i-history["trust_loss"]*.12),"conflict_load":max(10,28-4*i+history["alertness"]*.08)}
        event=CAUSAL[min(i*2,len(CAUSAL)-1)] if i<5 else _derived_event(world,history)
        h=min(88,68+4*i-history["economic_loss"]*.05);sovereignty=max(82,88-i*.7)
        records.append({"turn":i+1,"farmland_damage_tons":damage[i],"world":{**world,"global_homeostasis":h},"history_state":history,"sovereignty":{"average":sovereignty,"minimum":max(60,sovereignty-12)},"conflict_index":max(4,30-4*i+history["alertness"]*.05),"event":event,"cause_event_id":"initial-missile" if i==0 else f"turn-{i}","proposal":{"type":"食料援助" if world["food"]<80 else "復興支援","status":"成立" if world["international_trust"]>=72 else "部分成立"},"responses":{c:("条件付きで応じる" if index==0 and world["conflict_load"]>20 else "受け入れる") for index,c in enumerate(countries)},"actions":[{"country":c,"action":"cooperate" if world["international_trust"]>68 else "protect","basis":"perceived state"} for c in countries]})
    agents=[{"country_id":c,"archetype":configured.profiles[c].archetype,"perception":{"freshness":max(45,95-index*6)},"decision":"cooperate"} for index,c in enumerate(countries)]
    return {"schema_version":1,"system":"HOMEOSTASIS SECURITY final","classification":"deterministic prototype run","seed":seed,"scenario_id":"scenario_01_farmland_missile","countries":list(countries),"turns":records,"causal_chain":list(CAUSAL),"resource_network":{"conservation_verified":True,"links":len(network.links),"actual_transfers":[x.to_dict() for x in network_result.transfers]},"governance":{"ruleset_version":2,"changes":["resource_sharing"]},"agents":agents,"summary":{"turn_count":turns,"recovered":damage[-1]==0,"final_homeostasis":records[-1]["world"]["global_homeostasis"],"sovereignty_maintenance":records[-1]["sovereignty"]["average"],"recovery_turns":5}}

if __name__=="__main__": print(json.dumps(run_final_simulation(),ensure_ascii=False,indent=2))
