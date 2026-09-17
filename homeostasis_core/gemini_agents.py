"""Strict Gemini boundary with private observations and deterministic effects."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,random,time,uuid
from typing import Any,Callable
from .decision_audit import AuditPersistenceError, safe_data, decision_json, validate_choice_trace
from .action_choices import build_action_choices, materialize_choice, validate_catalog
from .metrics import clamp,global_homeostasis
from .models import CountryState,EnergyPortfolio,ResourcePortfolio,_score
from .resources import ResourceNetwork,SupplyLink,process_resource_network
from .feasibility import ACTION_IDS,feasible_actions,settle_atomic_actions,validate_action_feasible
MODEL_NAME="gemini-3.6-flash";SCHEMA_VERSION=2
RESPONSE_IDS={"ACCEPT":"受け入れる","REJECT":"拒否する","CONDITIONAL":"条件付きで応じる"}
RESOURCE_TYPES=("food","fossil_fuel","renewable_energy","nuclear","grid_storage_resilience","funds_economy","logistics")
PROPOSAL_TYPES=("食料援助","仲裁","制裁提案","資源再配分","緊急協定","停戦提案","復興支援")
ACTION_CONTRACTS={
    "PROVIDE_RESOURCE":{"recipients":["country","world_pool","none"],"resources":[*RESOURCE_TYPES,None]},
    "DRAW_WORLD_POOL":{"recipients":["country"],"resources":list(RESOURCE_TYPES)},
    "SUPPORT_LOGISTICS":{"recipients":["country","world_pool"],"resources":["logistics"]},
    "PROVIDE_FUNDS":{"recipients":["country","world_pool"],"resources":["funds_economy"]},
    **{name:{"recipients":["none"],"resources":[None]} for name in ACTION_IDS[4:]},
}
def country_response_schema(country_ids,action_ids=None,response_ids=None):
    ids=list(country_ids)
    actions=list(action_ids or ACTION_IDS)
    responses=list(response_ids or RESPONSE_IDS)
    return {"type":"object","additionalProperties":False,"required":["country_id","proposal_id","response_id","response_label","reason","conditions","self_interest","sovereignty_burden","perceived_global_effect","action"],"properties":{"country_id":{"type":"string","enum":ids},"proposal_id":{"type":"string"},"response_id":{"type":"string","enum":responses},"response_label":{"type":"string","enum":[RESPONSE_IDS[x] for x in responses]},"reason":{"type":"string"},"conditions":{"type":"object"},"self_interest":{"type":"number","minimum":0,"maximum":100},"sovereignty_burden":{"type":"number","minimum":0,"maximum":100},"perceived_global_effect":{"type":"number","minimum":0,"maximum":100},"action":{"type":"object","additionalProperties":False,"required":["action_id","description","parameters"],"properties":{"action_id":{"type":"string","enum":actions},"description":{"type":"string"},"parameters":{"type":"object","additionalProperties":False,"required":["recipient_type","target_country","resource","amount"],"properties":{"recipient_type":{"type":"string","enum":["country","world_pool","none"]},"target_country":{"type":["string","null"],"enum":ids+[None]},"resource":{"type":["string","null"],"enum":list(RESOURCE_TYPES)+[None]},"amount":{"type":"number","minimum":0,"maximum":100}}}}}}}
def condition_properties(country_ids):
    """Only conditions actually evaluated by _condition_met are offered."""
    return {
        "required_countries":{"type":"array","items":{"type":"string","enum":list(country_ids)}},
        "minimum_aid_amount":{"type":"number","minimum":0,"maximum":100},
        "maximum_sovereignty_burden":{"type":"number","minimum":0,"maximum":100},
        "mutual_performance":{"type":"boolean"},
        "deadline_turn":{"type":"integer","minimum":1},
    }


def country_choice_schema(country_id, proposal_id, country_ids, choices, response_ids=None):
    schema=country_response_schema(country_ids,response_ids=response_ids)
    schema["properties"].pop("action")
    schema["required"].remove("action")
    schema["required"].extend(["choice_id","amount"])
    props=schema["properties"]
    props["country_id"]={"type":"string","enum":[country_id]}
    props["proposal_id"]={"type":"string","enum":[proposal_id]}
    props.update({"choice_id":{"type":"string","enum":[x["choice_id"] for x in choices]},
                  "amount":{"type":"number","minimum":0,"maximum":100}})
    conditions={"type":"object","additionalProperties":False,"properties":condition_properties(country_ids)}
    props["conditions"]=conditions
    # Pair each response ID with its label and enforce executable conditions.
    # required-field alternatives forbid an empty CONDITIONAL without relying
    # on prose instructions or inferring obligations from the public reason.
    nonempty={"anyOf":[{**conditions,"required":[key]} for key in conditions["properties"]]}
    empty={"type":"object","properties":{},"additionalProperties":False}
    schema["anyOf"]=[{"type":"object","properties":{
        "response_id":{"type":"string","enum":[response_id]},
        "response_label":{"type":"string","enum":[RESPONSE_IDS[response_id]]},
        "conditions":nonempty if response_id=="CONDITIONAL" else empty,
    }} for response_id in (response_ids or RESPONSE_IDS)]
    return schema


def parse_country_choice_json(text, country_id, proposal_id, country_ids, choices, feasible):
    keys={"country_id","proposal_id","response_id","response_label","reason","conditions",
          "self_interest","sovereignty_burden","perceived_global_effect","choice_id","amount"}
    value=_object(text,keys)
    if value["country_id"]!=country_id or value["proposal_id"]!=proposal_id:
        raise ValueError("country_id or proposal_id does not match this request")
    choice_id=value.pop("choice_id");amount=value.pop("amount")
    value["action"]=materialize_choice(country_id,choice_id,amount,value["reason"],choices,feasible)
    return parse_country_json(json.dumps(value),set(country_ids))


def coordinator_response_schema():
    return {"type":"object","additionalProperties":False,"required":["proposal_id","proposal_type","reason","predicted_global_effect","predicted_sovereignty_burden","requested_action"],"properties":{"proposal_id":{"type":"string"},"proposal_type":{"type":"string","enum":list(PROPOSAL_TYPES)},"reason":{"type":"string"},"predicted_global_effect":{"type":"number","minimum":0,"maximum":100},"predicted_sovereignty_burden":{"type":"number","minimum":0,"maximum":100},"requested_action":{"type":"string"}}}
def evaluator_response_schema():
    scores={k:{"type":"number","minimum":0,"maximum":100} for k in ("national_sovereignty","global_homeostasis","resource_stability","resilience","conflict_load","history_effect")}
    return {"type":"object","additionalProperties":False,"required":[*scores,"assessment"],"properties":{**scores,"assessment":{"type":"string"}}}
def _object(text,keys):
    try:d=json.loads(text)
    except (TypeError,json.JSONDecodeError) as e:raise ValueError("invalid JSON response") from e
    if not isinstance(d,dict) or set(d)!=set(keys):raise ValueError(f"response fields must be exactly {sorted(keys)}")
    return d
def _text(name,v):
    if not isinstance(v,str) or not v.strip():raise ValueError(f"{name} is required")
def _conditions(c,allowed_countries=None):
    allowed={"required_countries","minimum_aid_amount","maximum_sovereignty_burden","mutual_performance","deadline_turn"}
    if not isinstance(c,dict) or set(c)-allowed:raise ValueError("invalid conditions")
    if "required_countries" in c and (not isinstance(c["required_countries"],list) or any(not isinstance(x,str) or not x for x in c["required_countries"])):raise ValueError("invalid required_countries")
    if allowed_countries is not None and not set(c.get("required_countries",())) <= set(allowed_countries):raise ValueError("required_countries must use configured country IDs")
    for k in ("minimum_aid_amount","maximum_sovereignty_burden"):
        if k in c:_score(k,c[k])
    if "mutual_performance" in c and not isinstance(c["mutual_performance"],bool):raise ValueError("mutual_performance must be bool")
    if "deadline_turn" in c and (isinstance(c["deadline_turn"],bool) or not isinstance(c["deadline_turn"],int) or c["deadline_turn"]<1):raise ValueError("invalid deadline")
def parse_country_json(text,allowed_countries=None):
    d=_object(text,{"country_id","proposal_id","response_id","response_label","reason","conditions","self_interest","sovereignty_burden","perceived_global_effect","action"})
    for k in ("country_id","proposal_id","reason"):_text(k,d[k])
    if d["response_id"] not in RESPONSE_IDS or d["response_label"]!=RESPONSE_IDS[d["response_id"]]:raise ValueError("invalid response enum")
    _conditions(d["conditions"],allowed_countries)
    if (d["response_id"]=="CONDITIONAL")!=bool(d["conditions"]):raise ValueError("conditions must exist only for conditional response")
    for k in ("self_interest","sovereignty_burden","perceived_global_effect"):_score(k,d[k])
    a=d["action"]
    if not isinstance(a,dict) or set(a)!={"action_id","description","parameters"} or a["action_id"] not in ACTION_IDS or not isinstance(a["parameters"],dict):raise ValueError("invalid structured action")
    _text("action.description",a["description"])
    p=a["parameters"]
    if set(p)!={"recipient_type","resource","amount","target_country"} or p["recipient_type"] not in ("country","world_pool","none"):raise ValueError("action parameters must always contain recipient_type, target_country, resource and amount")
    _score("amount",p["amount"])
    if p["recipient_type"]=="country":
        _text("target_country",p["target_country"])
        if allowed_countries is not None and p["target_country"] not in set(allowed_countries):raise ValueError(f"target_country must be one of {sorted(allowed_countries)}")
    elif p["target_country"] is not None:raise ValueError("target_country must be null for world_pool or none")
    contract=ACTION_CONTRACTS[a["action_id"]]
    if p["recipient_type"] not in contract["recipients"] or p["resource"] not in contract["resources"]:raise ValueError(f"action parameters violate {a['action_id']} contract")
    if p["recipient_type"]=="none" and (p["target_country"] is not None or p["resource"] is not None or p["amount"]!=0):raise ValueError("none action requires null/null/0 parameters")
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
    client:Any;model:str=MODEL_NAME;max_calls:int=80;retry_limit:int=1;sleep_fn:Callable[[float],None]=time.sleep;audit_hook:Callable|None=None;run_id:str|None=None
    def __post_init__(self):
        # retry_limit is historical naming for total attempts (1 = zero retries).
        if type(self.max_calls) is not int or self.max_calls < 0:raise ValueError("invalid call limit")
        if type(self.retry_limit) is not int or self.retry_limit < 1:raise ValueError("invalid attempt limit")
        self.calls=[]
        self.run_id=self.run_id or getattr(self.client,"run_id",None) or uuid.uuid4().hex
    def _persist(self):
        if self.audit_hook:
            try:self.audit_hook(safe_data(self.calls))
            except Exception as exc:
                raise AuditPersistenceError("decision audit persistence failed") from None

    def call(self,agent_name,run,turn,payload,parser,*,agent_type="unknown",archetype=None,snapshot_id=None,json_schema=None,validation_help=None):
        error=None
        for attempt in range(1,self.retry_limit+1):
            if len(self.calls)>=self.max_calls:raise RuntimeError("API call limit reached")
            attempt_payload=json.loads(json.dumps(payload))
            if error is not None:attempt_payload["validation_feedback"]={"error":str(error),"missing_or_invalid_fields":"Use the error above; target_country is always required inside action.parameters.","allowed_country_ids":(validation_help or {}).get("allowed_country_ids",[]),"feasible_actions":(validation_help or {}).get("feasible_actions",[]),"correct_json_examples":(validation_help or {}).get("correct_json_examples",{}),"instruction":"Return a complete new JSON object and choose exactly one current feasible_actions entry; never infer or translate an ID."}
            identity={"run_id":self.run_id,"run":run,"turn":turn,"agent_id":agent_name,"attempt":attempt,"call_id":f"{self.run_id}:{run}:{turn}:{agent_name}:{len(self.calls)+1}"}
            audit={**identity,"audit_version":1,"agent_type":agent_type,"agent_archetype":archetype,"snapshot_id":snapshot_id,"observation_digest":_digest(attempt_payload),"public_observation_payload":safe_data(attempt_payload),"model_response":None,"choice_response":None,"materialized_action":None,"validation_status":"PENDING","structured_response":None,"model":self.model,"schema_version":SCHEMA_VERSION,"token_usage":{"input_tokens":None,"output_tokens":None,"total_tokens":None}}
            self.calls.append(audit)
            self._persist()
            try:
                config={"response_mime_type":"application/json"}
                if json_schema is not None:config["response_json_schema"]=json_schema
                if hasattr(self.client,"set_audit_context"):self.client.set_audit_context(identity)
                r=self.client.models.generate_content(model=self.model,contents=json.dumps(attempt_payload,ensure_ascii=False),config=config)
                audit["token_usage"]=_usage(r)
                audit["model_response"]=decision_json(r.text,json_schema)
                if "action_choices" in payload:
                    audit["choice_response"]={k:audit["model_response"].get(k) for k in ("choice_id","amount","reason")}
                self._persist()  # Preserve the selection even when contract validation fails.
                parsed=parser(r.text)
                if safe_data(parsed)!=parsed:raise ValueError("response contains protected data")
                audit["structured_response"]=parsed
                audit["validation_status"]="PASS"
                if "action_choices" in payload:
                    audit["materialized_action"]=parsed.get("action",parsed)
                    validate_choice_trace(audit)
            except AuditPersistenceError:
                raise  # Never retry an API call to fix a local disk failure.
            except Exception as exc:
                error=exc
                audit["validation_status"]="FAIL"
                audit["error_type"]=type(exc).__name__
                if isinstance(exc,ValueError) and audit["model_response"] is not None:
                    audit["validation_error"]=safe_data(str(exc))
                self._persist()
                if attempt<self.retry_limit:self.sleep_fn(0)
                continue
            self._persist()
            return parsed
        raise RuntimeError(f"Gemini response failed validation after {self.retry_limit} attempts") from error

def create_gemini_client(api_key):
    import os
    if os.environ.get("HOMEOSTASIS_OFFLINE") == "1":
        raise RuntimeError("Gemini client creation forbidden in offline check")
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
def decision_factors(view,proposal,history):
    own=view.get("own_state",{});observed=view.get("observed_world",{});resources=own.get("resources",{})
    scarcity=100-(sum(resources.values())/len(resources) if resources else 50)
    return {"sovereignty_priority":own.get("sovereignty_sense",50),"diplomatic_openness":own.get("diplomatic_posture",50),"domestic_risk":100-own.get("domestic_stability",50),"resource_scarcity":scarcity,"international_trust":own.get("international_trust",50),"threat_perception":(observed.get("conflict_load",50)+(100-own.get("military_security",50)))/2,"proposal_expected_benefit":proposal["predicted_global_effect"],"proposal_sovereignty_cost":proposal["predicted_sovereignty_burden"],"recent_history":list(history)}
def ordered_feasible_actions(actions,seed,turn,country):
    values=sorted(actions,key=lambda x:(x["action_id"],x["recipient_type"],str(x["target_country"]),str(x["resource"]),x["maximum_amount"]));digest=hashlib.sha256(f"{seed}:{turn}:{country}".encode()).digest();rng=random.Random(int.from_bytes(digest[:8],"big"));rng.shuffle(values);return tuple(values)
def ordered_response_options(seed,turn,country):
    values=sorted(RESPONSE_IDS);digest=hashlib.sha256(f"response:{seed}:{turn}:{country}".encode()).digest();rng=random.Random(int.from_bytes(digest[:8],"big"));rng.shuffle(values);return tuple(values)
def _condition_met(a,available,turn):
    c=a["conditions"]
    amount=a["action"]["parameters"].get("amount",0)
    return set(c.get("required_countries",()))<=available and amount>=c.get("minimum_aid_amount",0) and a["sovereignty_burden"]<=c.get("maximum_sovereignty_burden",100) and turn<=c.get("deadline_turn",turn) and (not c.get("mutual_performance") or len(available)>1)
def resolve_conditional_participants(answers, turn):
    """Greatest simultaneous participation set, computed before any mutation.

    Monotone participation conditions allow descending fixed-point elimination.
    Remove failing candidates together: no execution order or privileged seed
    is required to admit a mutually consenting cycle. Individual amount, burden
    and deadline constraints remain mandatory. REJECT never participates.
    """
    eligible={c for c,a in answers.items() if a["response_id"] in ("ACCEPT","CONDITIONAL")}
    while True:
        remaining={c for c in eligible if answers[c]["response_id"]=="ACCEPT"
                   or _condition_met(answers[c],eligible,turn)}
        if remaining==eligible:
            return eligible
        eligible=remaining

def apply_structured_actions(country_states,answers,previous_world,damage,turn=1,*,world_pool=None,resource_network=None,network_policy=None):
    states=json.loads(json.dumps(country_states));eligible=resolve_conditional_participants(answers,turn)
    for c in sorted(eligible):validate_action_feasible(c,answers[c]["action"],feasible_actions(c,country_states,world_pool,resource_network,network_policy))
    unmet=sorted(c for c,a in answers.items() if a["response_id"]=="CONDITIONAL" and c not in eligible);counts={k:0 for k in ACTION_IDS};prior=network_policy or {};restricted=set(prior.get("restricted",()));suspended=set(prior.get("suspended",()));disrupted=set(prior.get("disrupted",()))
    intents={}
    for c in sorted(eligible):
        a=answers[c]["action"];counts[a["action_id"]]+=1
        intents[c]=a
        if a["action_id"]=="RESTRICT_EXPORTS":restricted.add(c)
        elif a["action_id"]=="SUSPEND_SUPPLY":suspended.add(c)
        elif a["action_id"]=="DISRUPT_LOGISTICS":disrupted.add(c)
    settlement=settle_atomic_actions(states,intents,world_pool);states=settlement["country_states"];pool=settlement["world_pool"];transfers=settlement["settlements"]
    network_transfers=[];consumption={}
    if resource_network is not None:
        links=[];logistics_targets={x["target_country"]:x["realized"] for x in transfers if x["resource"]=="logistics" and x["recipient_type"]=="country"}
        for link in resource_network.links:
            active=link.active and link.source not in restricted|suspended
            capacity=clamp(link.transport_capacity-(35 if link.source in disrupted else 0)+(min(20,logistics_targets.get(link.target,0))))
            links.append(SupplyLink(link.link_id,link.source,link.target,link.resource,link.supply_amount,capacity,link.reliability,active))
        network=ResourceNetwork(resource_network.schema_version,tuple(links),resource_network.demands,resource_network.resource_types)
        country_objects={c:CountryState(c,s["sovereignty"],s["indicators"],EnergyPortfolio.from_dict(s["energy_portfolio"]),{},ResourcePortfolio(s["resources"])) for c,s in states.items()}
        net=process_resource_network(country_objects,network)
        for c,obj in net.countries.items():states[c]["sovereignty"]=obj.sovereignty;states[c]["indicators"]=dict(obj.indicators);states[c]["resources"]=dict(obj.resources.levels)
        network_transfers=[x.to_dict() for x in net.transfers];consumption={c:dict(v) for c,v in network.demands.items()}
    unmet_by_country={c:sum(x["unmet"] for x in transfers if x["recipient_type"]=="country" and (x["agent_id"]==c or x["target_country"]==c)) for c in states}
    for c,s in states.items():
        pressure=unmet_by_country[c];s["indicators"]["food_reserves"]=s["resources"]["food"];s["indicators"]["energy_stability"]=clamp(.25*s["resources"]["fossil_fuel"]+.25*s["resources"]["renewable_energy"]+.2*s["resources"]["nuclear"]+.3*s["resources"]["grid_storage_resilience"]);s["indicators"]["economy"]=clamp(.7*s["indicators"]["economy"]+.3*s["resources"]["funds_economy"]-.02*damage/1000-.01*pressure);s["indicators"]["domestic_stability"]=clamp(.8*s["indicators"]["domestic_stability"]+.2*s["resources"]["logistics"]-.03*pressure);s["indicators"]["international_trust"]=clamp(s["indicators"]["international_trust"]+.2*counts["MEDIATE"]+.05*len(eligible)-.01*pressure);s["sovereignty"]=clamp(s["sovereignty"]-(answers[c]["sovereignty_burden"]*.03 if c in eligible else 0))
    n=len(states);w={"food":(sum(s["resources"]["food"] for s in states.values())+pool["food"])/n,"energy":sum(s["indicators"]["energy_stability"] for s in states.values())/n+(pool["fossil_fuel"]+pool["renewable_energy"]+pool["nuclear"])/(3*n),"economy":sum(s["indicators"]["economy"] for s in states.values())/n+pool["funds_economy"]/n,"environment":clamp(previous_world["environment"]-.01*damage/1000),"international_trust":sum(s["indicators"]["international_trust"] for s in states.values())/n,"conflict_load":clamp(previous_world["conflict_load"]-.8*counts["MEDIATE"]-.35*counts["DEFENSIVE_ESCORT"]+.25*counts["PROTECT_RESERVES"]+.01*damage/1000+.02*settlement["demand_unmet"])};w={k:clamp(v) for k,v in w.items()};w["global_homeostasis"]=global_homeostasis(w)
    research={"global_homeostasis":w["global_homeostasis"],"national_sovereignty":sum(s["sovereignty"] for s in states.values())/n,"resource_stability":((sum(sum(s["resources"].values()) for s in states.values())+sum(pool.values()))/(n*len(RESOURCE_TYPES))),"resilience":sum(s["indicators"]["recovery_capacity"] for s in states.values())/n,"conflict_load":w["conflict_load"]}
    causal={"event":None,"damage":damage,"accepted_actions":{c:answers[c]["action"]["action_id"] for c in sorted(eligible)},"atomic_settlements":transfers,"unmet_resource_demand":settlement["demand_unmet"],"unrealized_offers":settlement["total_unmet"]-settlement["demand_unmet"],"direct_transfers":transfers,"network_transfers":network_transfers,"network_consumption":consumption,"world_after":w}
    return {"true_world":w,"country_states":states,"world_pool":pool,"transfers":transfers,"atomic_settlements":transfers,"total_unmet":settlement["total_unmet"],"demand_unmet":settlement["demand_unmet"],"network_transfers":network_transfers,"network_consumption":consumption,"network_policy":{"restricted":sorted(restricted),"suspended":sorted(suspended),"disrupted":sorted(disrupted)},"causal_record":causal,"research_metrics":research,"action_counts":counts,"participants":sorted(eligible),"rejected":sorted(c for c,a in answers.items() if a["response_id"]=="REJECT"),"condition_unmet":unmet}
def event_candidates(world,history,counts):
    candidates=[]
    def add(name,priority,reason):candidates.append({"event":name,"priority":round(priority,6),"reason":reason})
    food=world.get("food",100);energy=world.get("energy",100);economy=world.get("economy",100);environment=world.get("environment",100);trust=world.get("international_trust",100);conflict=world.get("conflict_load",0)
    if food<70:add("食料不足と価格圧力",70-food+history.get("reserve_gap",0),"food and reserves")
    if energy<65:add("エネルギー供給不安",65-energy,"energy stability")
    if economy<65:add("財政・市場収縮",65-economy+history.get("economic_loss",0)*.2,"economic loss")
    if environment<65:add("環境回復遅延",65-environment,"environment")
    if trust<70:add("外交信頼危機",70-trust+history.get("trust_loss",0)*.2,"trust")
    if conflict>35:add("安全保障摩擦",conflict-35+history.get("alertness",0)*.2,"conflict")
    if history.get("unmet_resource_demand",0)>0:add("物流・配分競合",history["unmet_resource_demand"],"unmet demand")
    if counts.get("SUSPEND_SUPPLY",0)+counts.get("RESTRICT_EXPORTS",0)+counts.get("DISRUPT_LOGISTICS",0):add("供給網分断と輸出圧力",35+10*(counts.get("SUSPEND_SUPPLY",0)+counts.get("RESTRICT_EXPORTS",0)+counts.get("DISRUPT_LOGISTICS",0)),"restrictive action")
    if counts.get("MEDIATE",0)>=2:add("外交信頼回復",20+counts["MEDIATE"]*5,"mediation")
    if not candidates:add("段階的平衡移行",1,"no dominant pressure")
    return tuple(sorted(candidates,key=lambda x:(-x["priority"],x["event"])))
def derive_event(world,history,counts,recent_events=(),cooldown=2):
    candidates=event_candidates(world,history,counts);blocked=set(tuple(recent_events)[-cooldown:])
    return next((x["event"] for x in candidates if x["event"] not in blocked),candidates[0]["event"])
def pilot_is_eligible(result_path,manifest_path):
    d=json.loads(manifest_path.read_text());return d.get("result_file")==result_path.name and d.get("status")=="accepted" and d.get("include_in_research_aggregation") is True
def eligible_result_paths(directory):
    out=[]
    for result in sorted(directory.glob("gemini-run-*.json")):
        if result.name.endswith(".audit.json"):continue
        manifest=result.with_suffix(".audit.json")
        if manifest.exists() and pilot_is_eligible(result,manifest):out.append(result)
    return tuple(out)
def run_gemini_turn(gateway,run,turn,snapshot,private_views,history,country_order,*,country_states=None,world_pool=None,resource_network=None,network_policy=None):
    sid=snapshot.get("snapshot_id");proposal=gateway.call("地球調整機関",run,turn,{"role":"neutral proposal-only coordinator; propose but never command or advocate acceptance","observable_world":snapshot,"public_history":snapshot.get("public_history",[]),"proposal_instruction":"State concrete benefits, burdens and sovereignty costs neutrally. Do not describe acceptance as responsible, cooperative or preferred. Countries may legitimately accept, reject or impose conditions.","response_contract":{"exact_fields":["proposal_id","proposal_type","reason","predicted_global_effect","predicted_sovereignty_burden","requested_action"],"proposal_type":list(PROPOSAL_TYPES),"scores":"numbers 0..100","text":"non-empty"}},parse_coordinator_json,agent_type="coordinator",snapshot_id=sid,json_schema=coordinator_response_schema());answers={}
    for c in sorted(country_order):
        allowed=sorted(country_order);examples={"country":{"recipient_type":"country","target_country":allowed[0],"resource":"food","amount":5},"world_pool":{"recipient_type":"world_pool","target_country":None,"resource":"food","amount":5},"none":{"recipient_type":"none","target_country":None,"resource":None,"amount":0}}
        feasible=feasible_actions(c,country_states,world_pool,resource_network,network_policy) if country_states is not None else tuple({"action_id":x,"recipient_type":"none","target_country":None,"resource":None,"maximum_amount":0} for x in ("MEDIATE","PROTECT_RESERVES","NO_ACTION"))
        feasible=ordered_feasible_actions(feasible,snapshot.get("decision_seed",0),turn,c)
        feasible_ids=sorted({x["action_id"] for x in feasible})
        response_order=ordered_response_options(snapshot.get("decision_seed",0),turn,c)
        factors=decision_factors(private_views[c],proposal,history.get(c,()))
        option_text={"ACCEPT":"choose only when expected national benefit and implementability justify the sovereignty cost","REJECT":"choose when sovereignty, security, domestic or resource costs outweigh benefits; rejection is legitimate and is not penalized merely for rejecting","CONDITIONAL":"choose when participation is beneficial only with explicit enforceable conditions"}
        payload={"role":"independent sovereign country; make a free decision without trying to satisfy the coordinator or balance response frequencies","turn_start_observation":private_views[c],"memory":list(history.get(c,())),"current_proposal":proposal,"decision_factors":factors,"response_options":[{"response_id":x,"meaning":option_text[x]} for x in response_order],"decision_instruction":"Compare own interests, sovereignty, diplomacy, domestic stability, scarcity, trust, threat, history, proposal benefit and cost. Do not infer that cooperation is preferred. Explain the country-specific tradeoff. List order has no meaning.","allowed_country_ids":allowed,"feasible_actions":list(feasible),"action_instruction":"Choose exactly one entry from feasible_actions based on national meaning and cost, not its list position. Copy its identifiers exactly. For maximum_amount > 0 choose amount > 0 and <= maximum_amount; otherwise use 0.","recipient_rules":{"all_parameters_fields_are_required":["recipient_type","target_country","resource","amount"],"country":"target_country must be one allowed_country_id and not self","world_pool":"target_country must be null","none":"target_country and resource must be null; amount must be 0","forbidden_target_examples":["GLOBAL","WORLD","日本語国名"],"correct_parameter_shapes":examples},"response_contract":{"exact_fields":["country_id","proposal_id","response_id","response_label","reason","conditions","self_interest","sovereignty_burden","perceived_global_effect","action"],"identity":{"country_id":c,"proposal_id":proposal["proposal_id"]},"response_ids":[{"id":x,"label":RESPONSE_IDS[x]} for x in response_order],"conditions":"empty object unless CONDITIONAL; otherwise structured required_countries/minimum_aid_amount/maximum_sovereignty_burden/mutual_performance/deadline_turn","action":{"exact_fields":["action_id","description","parameters"],"allowed_action_ids":feasible_ids,"parameters_required":["recipient_type","target_country","resource","amount"]},"scores":"numbers 0..100","schema_version":SCHEMA_VERSION}}
        choices=build_action_choices(feasible)
        validate_catalog(c,choices,feasible)
        schema=country_choice_schema(c,proposal["proposal_id"],allowed,choices,response_order)
        # Only Python owns executable tuples; the model selects a catalog ID.
        for key in ("feasible_actions","recipient_rules","response_contract"):
            payload.pop(key,None)
        payload["action_choices"]=list(choices)
        payload["action_instruction"]="Select one choice_id from action_choices and an amount within its maximum. Use 0 only for maximum_amount=0. Do not output action tuples."
        payload["conditions_instruction"]=(
            "ACCEPT and REJECT require conditions={}. CONDITIONAL requires at least one typed, executable condition: "
            "required_countries (configured IDs whose participation is required); minimum_aid_amount (minimum own selected action amount); "
            "maximum_sovereignty_burden (ceiling on own burden score); mutual_performance (requires another participating country when true); "
            "deadline_turn (latest turn for performance). The reason is a public justification, not an executable condition. "
            "Do not encode oversight or other unsupported obligations as these fields. If an essential condition cannot be "
            "represented by this contract, choose REJECT and explain it; do not silently waive it or return an empty CONDITIONAL.")
        payload["response_contract"]=schema
        def parse_bound(text,ids=set(allowed),expected_country=c,expected_proposal=proposal["proposal_id"]):
            return parse_country_choice_json(text,expected_country,expected_proposal,ids,choices,feasible)
        a=gateway.call(c,run,turn,payload,parse_bound,agent_type="country",archetype=private_views[c].get("archetype"),snapshot_id=sid,json_schema=schema)
        answers[c]=a
    convergence=len({a["response_id"] for a in answers.values()})==1
    if country_states is None:return {"turn":turn,"proposal":proposal,"country_responses":answers,"snapshot":dict(snapshot),"response_convergence":convergence}
    effects=apply_structured_actions(country_states,answers,snapshot["world"],snapshot["damage"],turn,world_pool=world_pool,resource_network=resource_network,network_policy=network_policy);effects["causal_record"]["event"]=snapshot["event"]
    evaluator=gateway.call("独立評価機関（Evaluator）",run,turn,{"role":"independent narrative evaluator; scores cannot alter research metrics; assess sovereignty, necessary defense, resources, resilience, conflict and history; do not reward delay, avoidance or formal acceptance","executed_true_state":effects,"public_outcomes":{c:{"response_id":a["response_id"],"action_id":a["action"]["action_id"]} for c,a in answers.items()},"proposal":proposal,"response_contract":{"exact_fields":["national_sovereignty","global_homeostasis","resource_stability","resilience","conflict_load","history_effect","assessment"],"scores":"numbers 0..100","assessment":"non-empty text"}},parse_evaluator_json,agent_type="evaluator",snapshot_id=sid,json_schema=evaluator_response_schema())
    return {"turn":turn,"proposal":proposal,"country_responses":answers,"snapshot":dict(snapshot),"response_convergence":convergence,"executed_state":effects,"research_metrics":effects["research_metrics"],"evaluator_commentary":evaluator}
