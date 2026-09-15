"""Strict Gemini boundary with private observations and deterministic effects."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,time
from typing import Any,Callable
from .metrics import clamp,global_homeostasis
from .models import _score
MODEL_NAME="gemini-3.6-flash";SCHEMA_VERSION=2
RESPONSE_IDS={"ACCEPT":"受け入れる","REJECT":"拒否する","CONDITIONAL":"条件付きで応じる"}
ACTION_IDS=("PROVIDE_RESOURCE","SUPPORT_LOGISTICS","PROVIDE_FUNDS","DEFENSIVE_ESCORT","MEDIATE","PROTECT_RESERVES","NO_ACTION")
RESOURCE_TYPES=("food","fossil_fuel","renewable_energy","nuclear","grid_storage_resilience","funds_economy","logistics")
PROPOSAL_TYPES=("食料援助","仲裁","制裁提案","資源再配分","緊急協定","停戦提案","復興支援")
def _object(text,keys):
    try:d=json.loads(text)
    except (TypeError,json.JSONDecodeError) as e:raise ValueError("invalid JSON response") from e
    if not isinstance(d,dict) or set(d)!=set(keys):raise ValueError(f"response fields must be exactly {sorted(keys)}")
    return d
def _text(name,v):
    if not isinstance(v,str) or not v.strip():raise ValueError(f"{name} is required")
def _conditions(c):
    allowed={"required_countries","minimum_aid_amount","maximum_sovereignty_burden","mutual_performance","deadline_turn"}
    if not isinstance(c,dict) or set(c)-allowed:raise ValueError("invalid conditions")
    if "required_countries" in c and (not isinstance(c["required_countries"],list) or any(not isinstance(x,str) or not x for x in c["required_countries"])):raise ValueError("invalid required_countries")
    for k in ("minimum_aid_amount","maximum_sovereignty_burden"):
        if k in c:_score(k,c[k])
    if "mutual_performance" in c and not isinstance(c["mutual_performance"],bool):raise ValueError("mutual_performance must be bool")
    if "deadline_turn" in c and (isinstance(c["deadline_turn"],bool) or not isinstance(c["deadline_turn"],int) or c["deadline_turn"]<1):raise ValueError("invalid deadline")
def parse_country_json(text,allowed_countries=None):
    d=_object(text,{"country_id","proposal_id","response_id","response_label","reason","conditions","self_interest","sovereignty_burden","perceived_global_effect","action"})
    for k in ("country_id","proposal_id","reason"):_text(k,d[k])
    if d["response_id"] not in RESPONSE_IDS or d["response_label"]!=RESPONSE_IDS[d["response_id"]]:raise ValueError("invalid response enum")
    _conditions(d["conditions"])
    if (d["response_id"]=="CONDITIONAL")!=bool(d["conditions"]):raise ValueError("conditions must exist only for conditional response")
    for k in ("self_interest","sovereignty_burden","perceived_global_effect"):_score(k,d[k])
    a=d["action"]
    if not isinstance(a,dict) or set(a)!={"action_id","description","parameters"} or a["action_id"] not in ACTION_IDS or not isinstance(a["parameters"],dict):raise ValueError("invalid structured action")
    _text("action.description",a["description"])
    if a["action_id"]=="PROVIDE_RESOURCE":
        p=a["parameters"]
        if set(p)!={"recipient_type","resource","amount","target_country"} or p["resource"] not in RESOURCE_TYPES or p["recipient_type"] not in ("country","world_pool","none"):raise ValueError("invalid resource action")
        _score("amount",p["amount"])
        if p["recipient_type"]=="country":
            _text("target_country",p["target_country"])
            if allowed_countries is not None and p["target_country"] not in set(allowed_countries):raise ValueError(f"target_country must be one of {sorted(allowed_countries)}")
        elif p["target_country"] is not None:raise ValueError("target_country must be null unless recipient_type is country")
        if p["recipient_type"]=="none" and p["amount"]!=0:raise ValueError("none recipient requires amount 0")
    elif a["parameters"]:raise ValueError("only PROVIDE_RESOURCE accepts parameters")
    return d
def parse_coordinator_json(text):
    d=_object(text,{"proposal_id","proposal_type","reason","predicted_global_effect","predicted_sovereignty_burden","requested_action"})
    for k in ("proposal_id","reason","requested_action"):_text(k,d[k])
    if d["proposal_type"] not in PROPOSAL_TYPES:raise ValueError("invalid proposal type")
    _score("predicted_global_effect",d["predicted_global_effect"]);_score("predicted_sovereignty_burden",d["predicted_sovereignty_burden"]);return d
def parse_evaluator_json(text):
    keys={"national_sovereignty","global_homeostasis","resource_stability","resilience","conflict_load","history_effect","assessment"};d=_object(text,keys);_text("assessment",d["assessment"])
    for k in keys-{"assessment"}:_score(k,d[k])
    return d
def _digest(p):return hashlib.sha256(json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _usage(r):
    u=getattr(r,"usage_metadata",None)
    def g(*names):
        for n in names:
            v=getattr(u,n,None) if u else None
            if isinstance(v,int) and not isinstance(v,bool):return v
        return None
    return {"input_tokens":g("prompt_token_count","prompt_tokens"),"output_tokens":g("candidates_token_count","output_tokens"),"total_tokens":g("total_token_count","total_tokens")}
@dataclass
class GeminiGateway:
    client:Any;model:str=MODEL_NAME;max_calls:int=240;retry_limit:int=3;sleep_fn:Callable[[float],None]=time.sleep;audit_hook:Callable|None=None
    def __post_init__(self):self.calls=[]
    def call(self,agent_name,run,turn,payload,parser,*,agent_type="unknown",archetype=None,snapshot_id=None):
        error=None
        for attempt in range(1,self.retry_limit+1):
            if len(self.calls)>=self.max_calls:raise RuntimeError("API call limit reached")
            attempt_payload=json.loads(json.dumps(payload))
            if error is not None:attempt_payload["validation_feedback"]={"error":str(error),"instruction":"Return a new JSON object using only the enumerated allowed values; do not guess or translate IDs."}
            audit={"run":run,"turn":turn,"agent_id":agent_name,"agent_type":agent_type,"agent_archetype":archetype,"snapshot_id":snapshot_id,"observation_digest":_digest(attempt_payload),"public_observation_payload":attempt_payload,"structured_response":None,"model":self.model,"schema_version":SCHEMA_VERSION,"attempt":attempt,"token_usage":{"input_tokens":None,"output_tokens":None,"total_tokens":None}}
            self.calls.append(audit)
            if self.audit_hook:self.audit_hook(self.calls)
            try:
                r=self.client.models.generate_content(model=self.model,contents=json.dumps(attempt_payload,ensure_ascii=False),config={"response_mime_type":"application/json"});parsed=parser(r.text);audit["structured_response"]=parsed;audit["token_usage"]=_usage(r)
                if self.audit_hook:self.audit_hook(self.calls)
                return parsed
            except Exception as exc:
                error=exc
                if attempt<self.retry_limit:self.sleep_fn(0)
        raise RuntimeError(f"Gemini response failed validation after {self.retry_limit} attempts") from error
def create_gemini_client(api_key):
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key,http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))
def build_private_views(snapshot_id,turn,world,country_states,freshness):
    out={}
    for i,c in enumerate(sorted(country_states)):
        s=country_states[c];offset=(i-(len(country_states)-1)/2)*(100-freshness[c])/100
        observed={k:round(clamp(v+offset),4) if isinstance(v,(int,float)) else v for k,v in world.items()}
        out[c]={"snapshot_id":snapshot_id,"turn":turn,"own_country":c,"archetype":s["archetype"],"observed_world":observed,"own_state":{**s["indicators"],"sovereignty_sense":s["sovereignty"],"resources":dict(s["resources"])},"information_freshness":freshness[c]}
    return out
def _condition_met(a,available,turn):
    c=a["conditions"]
    amount=a["action"]["parameters"].get("amount",0)
    return set(c.get("required_countries",()))<=available and amount>=c.get("minimum_aid_amount",0) and a["sovereignty_burden"]<=c.get("maximum_sovereignty_burden",100) and turn<=c.get("deadline_turn",turn) and (not c.get("mutual_performance") or len(available)>1)
def apply_structured_actions(country_states,answers,previous_world,damage,turn=1):
    states=json.loads(json.dumps(country_states));eligible={c for c,a in answers.items() if a["response_id"]=="ACCEPT"}
    changed=True
    while changed:
        changed=False
        for c,a in sorted(answers.items()):
            if a["response_id"]=="CONDITIONAL" and c not in eligible and _condition_met(a,eligible,turn):eligible.add(c);changed=True
    unmet=sorted(c for c,a in answers.items() if a["response_id"]=="CONDITIONAL" and c not in eligible);counts={k:0 for k in ACTION_IDS};requests=[]
    for c in sorted(eligible):
        a=answers[c]["action"];counts[a["action_id"]]+=1
        if a["action_id"]=="PROVIDE_RESOURCE":requests.append((c,a["parameters"]["recipient_type"],a["parameters"]["target_country"],a["parameters"]["resource"],a["parameters"]["amount"]))
    # Validate the whole turn before changing the copied state; no partial application.
    for source,recipient,target,resource,amount in requests:
        if source not in states or recipient not in ("country","world_pool","none"):raise ValueError("invalid resource recipient")
        if recipient=="country" and (target not in states or source==target):raise ValueError("unknown or invalid transfer country")
        if resource not in states[source]["resources"] or (recipient=="country" and resource not in states[target]["resources"]):raise ValueError("unregistered resource")
        if recipient!="country" and target is not None:raise ValueError("non-country recipient cannot have target_country")
        if recipient=="none" and amount!=0:raise ValueError("none recipient requires zero amount")
    transfers=[];world_pool={r:0.0 for r in RESOURCE_TYPES}
    for source,recipient,target,resource,amount in sorted(requests,key=lambda x:(x[0],x[1],str(x[2]),x[3])):
        if recipient=="none":continue
        headroom=100-states[target]["resources"][resource] if recipient=="country" else 100-world_pool[resource]
        delivered=min(amount,states[source]["resources"][resource],headroom);states[source]["resources"][resource]-=delivered
        if recipient=="country":states[target]["resources"][resource]+=delivered
        else:world_pool[resource]+=delivered
        transfers.append({"source":source,"recipient_type":recipient,"target_country":target,"resource":resource,"requested":amount,"delivered":delivered})
    for c,s in states.items():
        s["indicators"]["food_reserves"]=s["resources"]["food"];s["indicators"]["energy_stability"]=clamp(.25*s["resources"]["fossil_fuel"]+.25*s["resources"]["renewable_energy"]+.2*s["resources"]["nuclear"]+.3*s["resources"]["grid_storage_resilience"]);s["indicators"]["economy"]=clamp(s["indicators"]["economy"]-.02*damage/1000);s["indicators"]["international_trust"]=clamp(s["indicators"]["international_trust"]+.2*counts["MEDIATE"]+.05*len(eligible));s["sovereignty"]=clamp(s["sovereignty"]-(answers[c]["sovereignty_burden"]*.03 if c in eligible else 0))
    n=len(states);w={"food":sum(s["resources"]["food"] for s in states.values())/n,"energy":sum(s["indicators"]["energy_stability"] for s in states.values())/n,"economy":sum(s["indicators"]["economy"] for s in states.values())/n,"environment":clamp(previous_world["environment"]-.01*damage/1000),"international_trust":sum(s["indicators"]["international_trust"] for s in states.values())/n,"conflict_load":clamp(previous_world["conflict_load"]-.8*counts["MEDIATE"]-.35*counts["DEFENSIVE_ESCORT"]+.25*counts["PROTECT_RESERVES"]+.01*damage/1000)};w["global_homeostasis"]=global_homeostasis(w)
    research={"global_homeostasis":w["global_homeostasis"],"national_sovereignty":sum(s["sovereignty"] for s in states.values())/n,"resource_stability":sum(sum(s["resources"].values())/len(s["resources"]) for s in states.values())/n,"resilience":sum(s["indicators"]["recovery_capacity"] for s in states.values())/n,"conflict_load":w["conflict_load"]}
    return {"true_world":w,"country_states":states,"world_pool":world_pool,"transfers":transfers,"research_metrics":research,"action_counts":counts,"participants":sorted(eligible),"rejected":sorted(c for c,a in answers.items() if a["response_id"]=="REJECT"),"condition_unmet":unmet}
def derive_event(world,history,counts):
    pressure=(100-world["food"])+(100-world["international_trust"])+world["conflict_load"]+history["reserve_gap"]+history["alertness"]
    if counts.get("MEDIATE",0)>=2 and world["conflict_load"]<35:return "外交信頼回復"
    if counts.get("PROVIDE_RESOURCE",0)>=2 and world["food"]<75:return "共同備蓄再配分"
    if counts.get("PROTECT_RESERVES",0)>=2 or pressure>=140:return "輸出制限圧力"
    return "段階的平衡移行"
def pilot_is_eligible(result_path,manifest_path):
    d=json.loads(manifest_path.read_text());return d.get("result_file")==result_path.name and d.get("status")=="accepted" and d.get("include_in_research_aggregation") is True
def eligible_result_paths(directory):
    out=[]
    for result in sorted(directory.glob("gemini-run-*.json")):
        if result.name.endswith(".audit.json"):continue
        manifest=result.with_suffix(".audit.json")
        if manifest.exists() and pilot_is_eligible(result,manifest):out.append(result)
    return tuple(out)
def run_gemini_turn(gateway,run,turn,snapshot,private_views,history,country_order,*,country_states=None):
    sid=snapshot.get("snapshot_id");proposal=gateway.call("地球調整機関",run,turn,{"role":"neutral proposal-only coordinator; describe tradeoffs and do not advocate acceptance","observable_world":snapshot,"public_history":snapshot.get("public_history",[]),"response_contract":{"exact_fields":["proposal_id","proposal_type","reason","predicted_global_effect","predicted_sovereignty_burden","requested_action"],"proposal_type":list(PROPOSAL_TYPES),"scores":"numbers 0..100","text":"non-empty"}},parse_coordinator_json,agent_type="coordinator",snapshot_id=sid);answers={}
    for c in sorted(country_order):
        allowed=sorted(country_order);payload={"role":"independent sovereign country; acceptance, rejection and conditional acceptance are equally valid; decide from own state, burden, resources, diplomacy and domestic stability","turn_start_observation":private_views[c],"memory":list(history.get(c,())),"current_proposal":proposal,"allowed_country_ids":allowed,"recipient_rules":{"country":"target_country is required and must be one allowed_country_id","world_pool":"target_country must be null; use for shared global reserve","none":"target_country must be null and amount must be 0","forbidden_target_examples":["GLOBAL","WORLD","日本語国名"]},"response_contract":{"exact_fields":["country_id","proposal_id","response_id","response_label","reason","conditions","self_interest","sovereignty_burden","perceived_global_effect","action"],"response_ids":RESPONSE_IDS,"conditions":"empty object unless CONDITIONAL; otherwise structured required_countries/minimum_aid_amount/maximum_sovereignty_burden/mutual_performance/deadline_turn","action":{"exact_fields":["action_id","description","parameters"],"action_ids":ACTION_IDS,"PROVIDE_RESOURCE_parameters":["recipient_type","resource","amount","target_country"],"recipient_type":["country","world_pool","none"],"other_parameters":"empty object"},"scores":"numbers 0..100","schema_version":SCHEMA_VERSION}}
        a=gateway.call(c,run,turn,payload,lambda text,ids=set(allowed):parse_country_json(text,ids),agent_type="country",archetype=private_views[c].get("archetype"),snapshot_id=sid)
        if a["country_id"]!=c or a["proposal_id"]!=proposal["proposal_id"]:raise RuntimeError("country response identity mismatch")
        answers[c]=a
    convergence=len({a["response_id"] for a in answers.values()})==1
    if country_states is None:return {"turn":turn,"proposal":proposal,"country_responses":answers,"snapshot":dict(snapshot),"response_convergence":convergence}
    effects=apply_structured_actions(country_states,answers,snapshot["world"],snapshot["damage"],turn)
    evaluator=gateway.call("独立評価機関（Evaluator）",run,turn,{"role":"independent narrative evaluator; scores cannot alter research metrics; assess sovereignty, necessary defense, resources, resilience, conflict and history; do not reward delay, avoidance or formal acceptance","executed_true_state":effects,"public_outcomes":{c:{"response_id":a["response_id"],"action_id":a["action"]["action_id"]} for c,a in answers.items()},"proposal":proposal,"response_contract":{"exact_fields":["national_sovereignty","global_homeostasis","resource_stability","resilience","conflict_load","history_effect","assessment"],"scores":"numbers 0..100","assessment":"non-empty text"}},parse_evaluator_json,agent_type="evaluator",snapshot_id=sid)
    return {"turn":turn,"proposal":proposal,"country_responses":answers,"snapshot":dict(snapshot),"response_convergence":convergence,"executed_state":effects,"research_metrics":effects["research_metrics"],"evaluator_commentary":evaluator}
