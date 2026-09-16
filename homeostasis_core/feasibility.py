"""Central, deterministic feasibility rules for structured national actions."""
from __future__ import annotations

from typing import Mapping

from .resources import RESOURCE_TYPES, ResourceNetwork

ACTION_IDS=("PROVIDE_RESOURCE","DRAW_WORLD_POOL","SUPPORT_LOGISTICS","PROVIDE_FUNDS","RESTRICT_EXPORTS","SUSPEND_SUPPLY","DISRUPT_LOGISTICS","DEFENSIVE_ESCORT","MEDIATE","PROTECT_RESERVES","NO_ACTION")
TRANSFER_ACTIONS={"PROVIDE_RESOURCE":None,"SUPPORT_LOGISTICS":"logistics","PROVIDE_FUNDS":"funds_economy"}

def _positive_number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and value>0

def _effective_links(country,network,policy):
    if network is None:return ()
    blocked=set((policy or {}).get("suspended",()))|set((policy or {}).get("restricted",()))
    return tuple(link for link in network.links if link.active and link.source not in blocked and link.transport_capacity>0 and link.reliability>0)

def feasible_actions(country_id,country_states,world_pool,resource_network:ResourceNetwork|None,network_policy=None):
    """Return concrete allowed actions and maximum quantities for one turn snapshot."""
    if country_id not in country_states:raise ValueError("unknown country_id")
    state=country_states[country_id];resources=state.get("resources")
    if not isinstance(resources,Mapping):raise ValueError("country resources are required")
    pool=world_pool or {};links=_effective_links(country_id,resource_network,network_policy)
    result=[]
    def add(action,recipient,target,resource,maximum):
        if maximum>0:result.append({"action_id":action,"recipient_type":recipient,"target_country":target,"resource":resource,"maximum_amount":round(float(maximum),8)})
    # Contributions to the persistent pool do not require a bilateral route, but do
    # require stock and national logistics capacity.
    logistics=float(resources.get("logistics",0))
    if logistics>0:
        for resource in RESOURCE_TYPES:
            stock=float(resources.get(resource,0))
            action="SUPPORT_LOGISTICS" if resource=="logistics" else "PROVIDE_FUNDS" if resource=="funds_economy" else "PROVIDE_RESOURCE"
            if stock>0:add(action,"world_pool",None,resource,min(stock,logistics))
    # Bilateral transfers require a currently operable directed route.
    candidate_links=links
    if resource_network is None:
        candidate_links=tuple(type("Route",(),{"source":country_id,"target":target_id,"resource":resource,"supply_amount":100,"transport_capacity":100,"reliability":100})() for target_id in sorted(country_states) if target_id!=country_id for resource in RESOURCE_TYPES)
    for link in candidate_links:
        if link.source!=country_id:continue
        target=country_states.get(link.target)
        if target is None or link.target==country_id:continue
        resource=link.resource;available=float(resources.get(resource,0));headroom=100-float(target.get("resources",{}).get(resource,100))
        maximum=min(available,headroom,logistics,float(link.supply_amount)*float(link.transport_capacity)/100*float(link.reliability)/100)
        action="SUPPORT_LOGISTICS" if resource=="logistics" else "PROVIDE_FUNDS" if resource=="funds_economy" else "PROVIDE_RESOURCE"
        add(action,"country",link.target,resource,maximum)
    # Pool withdrawals are possible only from existing stock and within receiver headroom.
    for target_id,target in sorted(country_states.items()):
        for resource in RESOURCE_TYPES:
            maximum=min(float(pool.get(resource,0)),100-float(target.get("resources",{}).get(resource,100)))
            add("DRAW_WORLD_POOL","country",target_id,resource,maximum)
    outgoing=[link for link in links if link.source==country_id]
    incoming=[link for link in links if link.target==country_id]
    if outgoing:
        result.extend(({"action_id":name,"recipient_type":"none","target_country":None,"resource":None,"maximum_amount":0} for name in ("RESTRICT_EXPORTS","SUSPEND_SUPPLY")))
    if logistics>0 and (outgoing or incoming):result.append({"action_id":"DISRUPT_LOGISTICS","recipient_type":"none","target_country":None,"resource":None,"maximum_amount":0})
    result.extend({"action_id":name,"recipient_type":"none","target_country":None,"resource":None,"maximum_amount":0} for name in ("DEFENSIVE_ESCORT","MEDIATE","PROTECT_RESERVES","NO_ACTION"))
    # A transfer-shaped response may explicitly elect not to transfer; this keeps
    # the contract backwards compatible while remaining physically inert.
    result.extend({"action_id":name,"recipient_type":"none","target_country":None,"resource":None,"maximum_amount":0} for name in TRANSFER_ACTIONS)
    return tuple(sorted(result,key=lambda x:(x["action_id"],x["recipient_type"],str(x["target_country"]),str(x["resource"]))))

def validate_action_feasible(country_id,action,feasible):
    """Validate one structured action against a previously generated snapshot set."""
    if not isinstance(action,Mapping):raise ValueError("action must be an object")
    action_id=action.get("action_id");parameters=action.get("parameters")
    if not isinstance(parameters,Mapping):raise ValueError("action parameters are required")
    amount=parameters.get("amount")
    if isinstance(amount,bool) or not isinstance(amount,(int,float)):raise ValueError("amount must be numeric")
    candidates=[x for x in feasible if x["action_id"]==action_id and x["recipient_type"]==parameters.get("recipient_type") and x["target_country"]==parameters.get("target_country") and x["resource"]==parameters.get("resource")]
    if not candidates:raise ValueError("action is not feasible in the current turn snapshot")
    maximum=candidates[0]["maximum_amount"]
    if maximum==0:
        if amount!=0:raise ValueError("non-transfer action amount must be 0")
    elif not (0<amount<=maximum):raise ValueError(f"amount must be greater than 0 and at most {maximum}")
    return True
