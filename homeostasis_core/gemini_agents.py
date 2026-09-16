"""Strict Gemini boundary with private observations and deterministic effects."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,time
from typing import Any,Callable
from .metrics import clamp,global_homeostasis
from .models import CountryState,EnergyPortfolio,ResourcePortfolio,_score
from .resources import ResourceNetwork,SupplyLink,process_resource_network
MODEL_NAME="gemini-3.6-flash";SCHEMA_VERSION=2
RESPONSE_IDS={"ACCEPT":"受け入れる","REJECT":"拒否する","CONDITIONAL":"条件付きで応じる"}
ACTION_IDS=("PROVIDE_RESOURCE","DRAW_WORLD_POOL","SUPPORT_LOGISTICS","PROVIDE_FUNDS","RESTRICT_EXPORTS","SUSPEND_SUPPLY","DISRUPT_LOGISTICS","DEFENSIVE_ESCORT","MEDIATE","PROTECT_RESERVES","NO_ACTION")
RESOURCE_TYPES=("food","fossil_fuel","renewable_energy","nuclear","grid_storage_resilience","funds_economy","logistics")
PROPOSAL_TYPES=("食料援助","仲裁","制裁提案","資源再配分","緊急協定","停戦提案","復興支援")
ACTION_CONTRACTS={
    "PROVIDE_RESOURCE":{"recipients":["country","world_pool","none"],"resources":[*RESOURCE_TYPES,None]},
    "DRAW_WORLD_POOL":{"recipients":["country"],"resources":list(RESOURCE_TYPES)},
    "SUPPORT_LOGISTICS":{"recipients":["country","world_pool"],"resources":["logistics"]},
    "PROVIDE_FUNDS":{"recipients":["country","world_pool"],"resources":["funds_economy"]},
    **{name:{"recipients":["none"],"resources":[None]} for name in ACTION_IDS[4:]},
}
def country_response_schema(country_ids):
    ids=list(country_ids)
    return {"type":"object","additionalProperties":False,"required":["country_id","proposal_id","response_id","response_label","reason","conditions","self_interest","sovereignty_burden","perceived_global_effect","action"],"properties":{"country_id":{"type":"string","enum":ids},"proposal_id":{"type":"string"},"response_id":{"type":"string","enum":list(RESPONSE_IDS)},"response_label":{"type":"string","enum":list(RESPONSE_IDS.values())},"reason":{"type":"string"},"conditions":{"type":"object"},"self_interest":{"type":"number","minimum":0,"maximum":100},"sovereignty_burden":{"type":"number","minimum":0,"maximum":100},"perceived_global_effect":{"type":"number","minimum":0,"maximum":100},"action":{"type":"object","additionalProperties":False,"required":["action_id","description","parameters"],"properties":{"action_id":{"type":"string","enum":list(ACTION_IDS)},"description":{"type":"string"},"parameters":{"type":"object","additionalProperties":False,"required":["recipient_type","target_country","resource","amount"],"properties":{"recipient_type":{"type":"string","enum":["country","world_pool","none"]},"target_country":{"type":["string","null"],"enum":ids+[None]},"resource":{"type":["string","null"],"enum":list(RESOURCE_TYPES)+[None]},"amount":{"type":"number","minimum":0,"maximum":100}}}}}}}
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
    client:Any;model:str=MODEL_NAME;max_calls:int=240;retry_limit:int=3;sleep_fn:Callable[[float],None]=time.sleep;audit_hook:Callable|None=None
    def __post_init__(self):self.calls=[]
    def call(self,agent_name,run,turn,payload,parser,*,agent_type="unknown",archetype=None,snapshot_id=None,json_schema=None,validation_help=None):
        error=None
        for attempt in range(1,self.retry_limit+1):
            if len(self.calls)>=self.max_calls:raise RuntimeError("API call limit reached")
            attempt_payload=json.loads(json.dumps(payload))
            if error is not None:attempt_payload["validation_feedback"]={"error":str(error),"missing_or_invalid_fields":"Use the error above; target_country is always required inside action.parameters.","allowed_country_ids":(validation_help or {}).get("allowed_country_ids",[]),"correct_json_examples":(validation_help or {}).get("correct_json_examples",{}),"instruction":"Return a complete new JSON object using only allowed values; never infer or translate an ID."}
            audit={"run":run,"turn":turn,"agent_id":agent_name,"agent_type":agent_type,"agent_archetype":archetype,"snapshot_id":snapshot_id,"observation_digest":_digest(attempt_payload),"public_observation_payload":attempt_payload,"structured_response":None,"model":self.model,"schema_version":SCHEMA_VERSION,"attempt":attempt,"token_usage":{"input_tokens":None,"output_tokens":None,"total_tokens":None}}
            self.calls.append(audit)
            if self.audit_hook:self.audit_hook(self.calls)
            try:
                config={"response_mime_type":"application/json"}
                if json_schema is not None:config["response_json_schema"]=json_schema
                r=self.client.models.generate_content(model=self.model,contents=json.dumps(attempt_payload,ensure_ascii=False),config=config);parsed=parser(r.text);audit["structured_response"]=parsed;audit["token_usage"]=_usage(r)
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
def apply_structured_actions(country_states,answers,previous_world,damage,turn=1,*,world_pool=None,resource_network=None,network_policy=None):
    states=json.loads(json.dumps(country_states));eligible={c for c,a in answers.items() if a["response_id"]=="ACCEPT"}
    changed=True
    while changed:
        changed=False
        for c,a in sorted(answers.items()):
            if a["response_id"]=="CONDITIONAL" and c not in eligible and _condition_met(a,eligible,turn):eligible.add(c);changed=True
    unmet=sorted(c for c,a in answers.items() if a["response_id"]=="CONDITIONAL" and c not in eligible);counts={k:0 for k in ACTION_IDS};requests=[]
    pool={r:float((world_pool or {}).get(r,0)) for r in RESOURCE_TYPES};draws=[];support=[];prior=network_policy or {};restricted=set(prior.get("restricted",()));suspended=set(prior.get("suspended",()));disrupted=set(prior.get("disrupted",()))
    for c in sorted(eligible):
        a=answers[c]["action"];counts[a["action_id"]]+=1
        if a["action_id"]=="PROVIDE_RESOURCE":requests.append((c,a["parameters"]["recipient_type"],a["parameters"]["target_country"],a["parameters"]["resource"],a["parameters"]["amount"]))
        elif a["action_id"]=="DRAW_WORLD_POOL":draws.append((c,a["parameters"]["target_country"],a["parameters"]["resource"],a["parameters"]["amount"]))
        elif a["action_id"] in ("SUPPORT_LOGISTICS","PROVIDE_FUNDS"):
            p=a["parameters"]
            if p["recipient_type"]=="world_pool":requests.append((c,"world_pool",None,p["resource"],p["amount"]))
            else:support.append((c,p["target_country"],p["resource"],p["amount"]))
        elif a["action_id"]=="RESTRICT_EXPORTS":restricted.add(c)
        elif a["action_id"]=="SUSPEND_SUPPLY":suspended.add(c)
        elif a["action_id"]=="DISRUPT_LOGISTICS":disrupted.add(c)
    # Validate the whole turn before changing the copied state; no partial application.
    for source,recipient,target,resource,amount in requests:
        if source not in states or recipient not in ("country","world_pool","none"):raise ValueError("invalid resource recipient")
        if recipient=="none":
            if target is not None or resource is not None or amount!=0:raise ValueError("none recipient requires null resource and zero amount")
            continue
        if recipient=="country" and (target not in states or source==target):raise ValueError("unknown or invalid transfer country")
        if resource not in states[source]["resources"] or (recipient=="country" and resource not in states[target]["resources"]):raise ValueError("unregistered resource")
        if recipient!="country" and target is not None:raise ValueError("non-country recipient cannot have target_country")
    for source,target,resource,amount in draws:
        if target not in states or resource not in states[target]["resources"] or amount>pool[resource]:raise ValueError("world pool draw exceeds available stock or has invalid target")
    for source,target,resource,amount in support:
        if source not in states or target not in states or source==target or amount>states[source]["resources"][resource] or states[target]["resources"][resource]+amount>100:raise ValueError("invalid support transfer")
    transfers=[]
    for source,recipient,target,resource,amount in sorted(requests,key=lambda x:(x[0],x[1],str(x[2]),x[3])):
        if recipient=="none":continue
        headroom=100-states[target]["resources"][resource] if recipient=="country" else 100-pool[resource]
        delivered=min(amount,states[source]["resources"][resource],headroom);states[source]["resources"][resource]-=delivered
        if recipient=="country":states[target]["resources"][resource]+=delivered
        else:pool[resource]+=delivered
        transfers.append({"source":source,"recipient_type":recipient,"target_country":target,"resource":resource,"requested":amount,"delivered":delivered})
    for source,target,resource,amount in sorted(draws):
        pool[resource]-=amount;states[target]["resources"][resource]+=amount;transfers.append({"source":"world_pool","recipient_type":"country","target_country":target,"resource":resource,"requested":amount,"delivered":amount})
    for source,target,resource,amount in sorted(support):
        states[source]["resources"][resource]-=amount;states[target]["resources"][resource]+=amount;transfers.append({"source":source,"recipient_type":"country","target_country":target,"resource":resource,"requested":amount,"delivered":amount})
    network_transfers=[];consumption={}
    if resource_network is not None:
        links=[];logistics_targets={target:amount for _,target,res,amount in support if res=="logistics"}
        for link in resource_network.links:
            active=link.active and link.source not in restricted|suspended
            capacity=clamp(link.transport_capacity-(35 if link.source in disrupted else 0)+(min(20,logistics_targets.get(link.target,0))))
            links.append(SupplyLink(link.link_id,link.source,link.target,link.resource,link.supply_amount,capacity,link.reliability,active))
        network=ResourceNetwork(resource_network.schema_version,tuple(links),resource_network.demands,resource_network.resource_types)
        country_objects={c:CountryState(c,s["sovereignty"],s["indicators"],EnergyPortfolio.from_dict(s["energy_portfolio"]),{},ResourcePortfolio(s["resources"])) for c,s in states.items()}
        net=process_resource_network(country_objects,network)
        for c,obj in net.countries.items():states[c]["sovereignty"]=obj.sovereignty;states[c]["indicators"]=dict(obj.indicators);states[c]["resources"]=dict(obj.resources.levels)
        network_transfers=[x.to_dict() for x in net.transfers];consumption={c:dict(v) for c,v in network.demands.items()}
    for c,s in states.items():
        s["indicators"]["food_reserves"]=s["resources"]["food"];s["indicators"]["energy_stability"]=clamp(.25*s["resources"]["fossil_fuel"]+.25*s["resources"]["renewable_energy"]+.2*s["resources"]["nuclear"]+.3*s["resources"]["grid_storage_resilience"]);s["indicators"]["economy"]=clamp(.7*s["indicators"]["economy"]+.3*s["resources"]["funds_economy"]-.02*damage/1000);s["indicators"]["domestic_stability"]=clamp(.8*s["indicators"]["domestic_stability"]+.2*s["resources"]["logistics"]);s["indicators"]["international_trust"]=clamp(s["indicators"]["international_trust"]+.2*counts["MEDIATE"]+.05*len(eligible));s["sovereignty"]=clamp(s["sovereignty"]-(answers[c]["sovereignty_burden"]*.03 if c in eligible else 0))
    n=len(states);w={"food":(sum(s["resources"]["food"] for s in states.values())+pool["food"])/n,"energy":sum(s["indicators"]["energy_stability"] for s in states.values())/n+(pool["fossil_fuel"]+pool["renewable_energy"]+pool["nuclear"])/(3*n),"economy":sum(s["indicators"]["economy"] for s in states.values())/n+pool["funds_economy"]/n,"environment":clamp(previous_world["environment"]-.01*damage/1000),"international_trust":sum(s["indicators"]["international_trust"] for s in states.values())/n,"conflict_load":clamp(previous_world["conflict_load"]-.8*counts["MEDIATE"]-.35*counts["DEFENSIVE_ESCORT"]+.25*counts["PROTECT_RESERVES"]+.01*damage/1000)};w={k:clamp(v) for k,v in w.items()};w["global_homeostasis"]=global_homeostasis(w)
    research={"global_homeostasis":w["global_homeostasis"],"national_sovereignty":sum(s["sovereignty"] for s in states.values())/n,"resource_stability":((sum(sum(s["resources"].values()) for s in states.values())+sum(pool.values()))/(n*len(RESOURCE_TYPES))),"resilience":sum(s["indicators"]["recovery_capacity"] for s in states.values())/n,"conflict_load":w["conflict_load"]}
    causal={"event":None,"damage":damage,"accepted_actions":{c:answers[c]["action"]["action_id"] for c in sorted(eligible)},"direct_transfers":transfers,"network_transfers":network_transfers,"network_consumption":consumption,"world_after":w}
    return {"true_world":w,"country_states":states,"world_pool":pool,"transfers":transfers,"network_transfers":network_transfers,"network_consumption":consumption,"network_policy":{"restricted":sorted(restricted),"suspended":sorted(suspended),"disrupted":sorted(disrupted)},"causal_record":causal,"research_metrics":research,"action_counts":counts,"participants":sorted(eligible),"rejected":sorted(c for c,a in answers.items() if a["response_id"]=="REJECT"),"condition_unmet":unmet}
def derive_event(world,history,counts):
    pressure=(100-world["food"])+(100-world["international_trust"])+world["conflict_load"]+history["reserve_gap"]+history["alertness"]
    if counts.get("SUSPEND_SUPPLY",0)+counts.get("RESTRICT_EXPORTS",0)+counts.get("DISRUPT_LOGISTICS",0)>=1:return "供給網分断と輸出圧力"
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
def run_gemini_turn(gateway,run,turn,snapshot,private_views,history,country_order,*,country_states=None,world_pool=None,resource_network=None,network_policy=None):
    sid=snapshot.get("snapshot_id");proposal=gateway.call("地球調整機関",run,turn,{"role":"neutral proposal-only coordinator; describe tradeoffs and do not advocate acceptance","observable_world":snapshot,"public_history":snapshot.get("public_history",[]),"response_contract":{"exact_fields":["proposal_id","proposal_type","reason","predicted_global_effect","predicted_sovereignty_burden","requested_action"],"proposal_type":list(PROPOSAL_TYPES),"scores":"numbers 0..100","text":"non-empty"}},parse_coordinator_json,agent_type="coordinator",snapshot_id=sid,json_schema=coordinator_response_schema());answers={}
    for c in sorted(country_order):
        allowed=sorted(country_order);examples={"country":{"recipient_type":"country","target_country":allowed[0],"resource":"food","amount":5},"world_pool":{"recipient_type":"world_pool","target_country":None,"resource":"food","amount":5},"none":{"recipient_type":"none","target_country":None,"resource":None,"amount":0}}
        payload={"role":"independent sovereign country; acceptance, rejection and conditional acceptance are equally valid; decide from own state, burden, resources, diplomacy and domestic stability","turn_start_observation":private_views[c],"memory":list(history.get(c,())),"current_proposal":proposal,"allowed_country_ids":allowed,"recipient_rules":{"all_parameters_fields_are_required":["recipient_type","target_country","resource","amount"],"country":"target_country must be one allowed_country_id","world_pool":"target_country must be null","none":"target_country and resource must be null; amount must be 0","forbidden_target_examples":["GLOBAL","WORLD","日本語国名"],"correct_examples":examples},"response_contract":{"exact_fields":["country_id","proposal_id","response_id","response_label","reason","conditions","self_interest","sovereignty_burden","perceived_global_effect","action"],"identity":{"country_id":c,"proposal_id":proposal["proposal_id"]},"response_ids":RESPONSE_IDS,"conditions":"empty object unless CONDITIONAL; otherwise structured required_countries/minimum_aid_amount/maximum_sovereignty_burden/mutual_performance/deadline_turn","action":{"exact_fields":["action_id","description","parameters"],"contracts":ACTION_CONTRACTS,"parameters_required":["recipient_type","target_country","resource","amount"]},"scores":"numbers 0..100","schema_version":SCHEMA_VERSION}}
        help_data={"allowed_country_ids":allowed,"correct_json_examples":examples}
        def parse_bound(text,ids=set(allowed),expected_country=c,expected_proposal=proposal["proposal_id"]):
            value=parse_country_json(text,ids)
            if value["country_id"]!=expected_country or value["proposal_id"]!=expected_proposal:raise ValueError("country_id or proposal_id does not match this request")
            return value
        a=gateway.call(c,run,turn,payload,parse_bound,agent_type="country",archetype=private_views[c].get("archetype"),snapshot_id=sid,json_schema=country_response_schema(allowed),validation_help=help_data)
        answers[c]=a
    convergence=len({a["response_id"] for a in answers.values()})==1
    if country_states is None:return {"turn":turn,"proposal":proposal,"country_responses":answers,"snapshot":dict(snapshot),"response_convergence":convergence}
    effects=apply_structured_actions(country_states,answers,snapshot["world"],snapshot["damage"],turn,world_pool=world_pool,resource_network=resource_network,network_policy=network_policy);effects["causal_record"]["event"]=snapshot["event"]
    evaluator=gateway.call("独立評価機関（Evaluator）",run,turn,{"role":"independent narrative evaluator; scores cannot alter research metrics; assess sovereignty, necessary defense, resources, resilience, conflict and history; do not reward delay, avoidance or formal acceptance","executed_true_state":effects,"public_outcomes":{c:{"response_id":a["response_id"],"action_id":a["action"]["action_id"]} for c,a in answers.items()},"proposal":proposal,"response_contract":{"exact_fields":["national_sovereignty","global_homeostasis","resource_stability","resilience","conflict_load","history_effect","assessment"],"scores":"numbers 0..100","assessment":"non-empty text"}},parse_evaluator_json,agent_type="evaluator",snapshot_id=sid,json_schema=evaluator_response_schema())
    return {"turn":turn,"proposal":proposal,"country_responses":answers,"snapshot":dict(snapshot),"response_convergence":convergence,"executed_state":effects,"research_metrics":effects["research_metrics"],"evaluator_commentary":evaluator}
