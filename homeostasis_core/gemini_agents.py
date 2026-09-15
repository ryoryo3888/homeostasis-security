"""Lazy Gemini adapter with strict schemas, bounded retries and privacy-safe audit records."""
from __future__ import annotations
from dataclasses import dataclass
import json,time
from typing import Any,Callable,Mapping
from .models import _score

MODEL_NAME="gemini-3.6-flash"
COUNTRY_RESPONSES=("受け入れる","拒否する","条件付きで応じる")
PROPOSAL_TYPES=("食料援助","仲裁","制裁提案","資源再配分","緊急協定","停戦提案","復興支援")

def _object(text:str,required:set[str])->dict[str,Any]:
    try:data=json.loads(text)
    except (TypeError,json.JSONDecodeError) as e:raise ValueError("invalid JSON response") from e
    if not isinstance(data,dict) or set(data)!=required:raise ValueError(f"response fields must be exactly {sorted(required)}")
    return data
def parse_country_json(text:str)->dict[str,Any]:
    d=_object(text,{"country_id","proposal_id","response","reason","conditions","self_interest","sovereignty_burden","perceived_global_effect","policy_action"})
    if not all(isinstance(d[k],str) and d[k].strip() for k in ("country_id","proposal_id")):raise ValueError("country and proposal IDs are required")
    if d["response"] not in COUNTRY_RESPONSES:raise ValueError("invalid country response")
    if not all(isinstance(d[k],str) and d[k].strip() for k in ("reason","policy_action")):raise ValueError("country text fields are required")
    if not isinstance(d["conditions"],dict) or set(d["conditions"])-{"required_countries","minimum_aid_amount","maximum_sovereignty_burden","mutual_performance","deadline_turn"}:raise ValueError("invalid conditions object")
    if d["response"]=="条件付きで応じる" and not d["conditions"]:raise ValueError("conditional response requires conditions")
    if d["response"]!="条件付きで応じる" and d["conditions"]:raise ValueError("only conditional responses may include conditions")
    conditions=d["conditions"]
    if "required_countries" in conditions:
        ids=conditions["required_countries"]
        if not isinstance(ids,list) or any(not isinstance(x,str) or not x.strip() for x in ids) or len(ids)!=len(set(ids)):raise ValueError("invalid required_countries")
    for key in ("minimum_aid_amount","maximum_sovereignty_burden"):
        if key in conditions:_score(key,conditions[key])
    if "mutual_performance" in conditions and not isinstance(conditions["mutual_performance"],bool):raise ValueError("mutual_performance must be boolean")
    if "deadline_turn" in conditions and (isinstance(conditions["deadline_turn"],bool) or not isinstance(conditions["deadline_turn"],int) or conditions["deadline_turn"]<1):raise ValueError("deadline_turn must be a positive integer")
    for k in ("self_interest","sovereignty_burden","perceived_global_effect"):_score(k,d[k])
    return d
def parse_coordinator_json(text:str)->dict[str,Any]:
    d=_object(text,{"proposal_id","proposal_type","reason","predicted_global_effect","predicted_sovereignty_burden","requested_action"})
    if d["proposal_type"] not in PROPOSAL_TYPES:raise ValueError("invalid proposal type")
    if not all(isinstance(d[k],str) and d[k].strip() for k in ("proposal_id","proposal_type","reason","requested_action")):raise ValueError("coordinator text fields are required")
    _score("predicted_global_effect",d["predicted_global_effect"]);_score("predicted_sovereignty_burden",d["predicted_sovereignty_burden"]);return d
def parse_evaluator_json(text:str)->dict[str,Any]:
    keys={"national_sovereignty","global_homeostasis","resource_stability","resilience","conflict_load","history_effect","assessment"};d=_object(text,keys)
    if not isinstance(d["assessment"],str) or not d["assessment"].strip():raise ValueError("assessment is required")
    for k in keys-{"assessment"}:_score(k,d[k])
    return d

@dataclass
class GeminiGateway:
    client:Any; model:str=MODEL_NAME; max_calls:int=240; retry_limit:int=3; sleep_fn:Callable[[float],None]=time.sleep; audit_hook:Callable[[list[dict]],None]|None=None
    def __post_init__(self):self.calls=[]
    def call(self,agent_name:str,run:int,turn:int,payload:Mapping[str,Any],parser:Callable[[str],dict])->dict:
        # Audit metadata intentionally excludes prompts, API keys and private payloads.
        error=None
        for attempt in range(1,self.retry_limit+1):
            if len(self.calls)>=self.max_calls:raise RuntimeError("API call limit reached")
            self.calls.append({"agent":agent_name,"run":run,"turn":turn,"attempt":attempt,"model":self.model})
            if self.audit_hook is not None:self.audit_hook(self.calls)
            try:
                response=self.client.models.generate_content(model=self.model,contents=json.dumps(payload,ensure_ascii=False),config={"response_mime_type":"application/json"})
                return parser(response.text)
            except Exception as exc:
                error=exc
                if attempt<self.retry_limit:self.sleep_fn(0)
        raise RuntimeError(f"Gemini response failed validation after {self.retry_limit} attempts") from error

def create_gemini_client(api_key:str)->Any:
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key,http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))

def run_gemini_turn(gateway:GeminiGateway,run:int,turn:int,snapshot:Mapping[str,Any],private_views:Mapping[str,Mapping[str,Any]],history:Mapping[str,tuple],country_order:tuple[str,...])->dict:
    proposal=gateway.call("地球調整機関",run,turn,{"role":"proposal-only coordinator","observable_world":snapshot,"public_history":snapshot.get("public_history",[]),"response_contract":{"proposal_id":"non-empty string","proposal_type":list(PROPOSAL_TYPES),"reason":"non-empty string","predicted_global_effect":"number 0..100","predicted_sovereignty_burden":"number 0..100","requested_action":"non-empty string"}},parse_coordinator_json)
    answers={}
    for country in sorted(country_order):
        # Every country gets its own view of the same turn-start snapshot; no prior answer is included.
        payload={"role":"independent sovereign country","turn_start_observation":private_views[country],"memory":list(history.get(country,())),"current_proposal":proposal,"response_contract":{"country_id":country,"proposal_id":proposal["proposal_id"],"response":list(COUNTRY_RESPONSES),"reason":"non-empty string","conditions":"structured object; empty unless conditional","self_interest":"number 0..100","sovereignty_burden":"number 0..100","perceived_global_effect":"number 0..100","policy_action":"non-empty string"}}
        answer=gateway.call(country,run,turn,payload,parse_country_json)
        if answer["country_id"]!=country or answer["proposal_id"]!=proposal["proposal_id"]:raise RuntimeError("country response identity mismatch")
        answers[country]=answer
    public_answers={c:{"response":a["response"],"policy_action":a["policy_action"]} for c,a in answers.items()}
    accepted=sum(a["response"]!="拒否する" for a in answers.values())/len(answers)
    world=dict(snapshot["world"])
    for key in ("food","economy","international_trust"):
        if key in world:world[key]=min(100,max(0,world[key]+accepted-.35))
    if "conflict_load" in world:world["conflict_load"]=min(100,max(0,world["conflict_load"]-(accepted-.25)))
    executed={**snapshot,"world":world,"participation_ratio":accepted}
    evaluation=gateway.call("独立評価機関（Evaluator）",run,turn,{"role":"independent evaluator","executed_world":executed,"public_outcomes":public_answers,"proposal":proposal,"response_contract":{"national_sovereignty":"number 0..100","global_homeostasis":"number 0..100","resource_stability":"number 0..100","resilience":"number 0..100","conflict_load":"number 0..100","history_effect":"number 0..100","assessment":"non-empty string"}},parse_evaluator_json)
    return {"turn":turn,"proposal":proposal,"country_responses":answers,"evaluation":evaluation,"snapshot":dict(snapshot),"executed_world":executed}
