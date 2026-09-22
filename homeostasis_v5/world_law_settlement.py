"""Conservative V5 world-law settlement with dispatch/arrival recording.

This is not a helper to make cooperation easier. It formalizes the minimum
conditions already intended by V5: speech is not physical action; resource or
recovery effects require explicit quantity, counterpart acceptance where
cross-border, route eligibility, transport capacity, and a requested effect.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any
import hashlib
import json
import re



def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class ContractError(ValueError):
    pass

def ensure(condition: bool, code: str):
    if not condition:
        raise ContractError(code)

VERSION = "v5-world-law-settlement-1"
QUANTITY_RE = re.compile(r"(\d+)\s*(単位|台|名|件|箱|トン|t|リットル|L|回|日分)")


@dataclass
class WorldLawState:
    world_id: str
    turn: int
    unmet_need: dict[str, int] = field(default_factory=dict)
    transport_capacity: dict[str, int] = field(default_factory=dict)
    route_eligibility: dict[str, bool] = field(default_factory=dict)
    dispatched: list[dict[str, Any]] = field(default_factory=list)
    arrivals: list[dict[str, Any]] = field(default_factory=list)
    world_state_mutations: list[dict[str, Any]] = field(default_factory=list)

    def route_key(self, source: str, target: str) -> str:
        return f"{source}->{target}"


def parse_quantity(text: str) -> int | None:
    match = QUANTITY_RE.search(text or "")
    if not match:
        return None
    return int(match.group(1))


def settlement_funnel(proposal: dict[str, Any], *, source_nation_id: str,
                      acceptances: list[dict[str, Any]], state: WorldLawState) -> dict[str, Any]:
    targets = list(proposal.get("to_nation_ids") or [])
    body = proposal.get("body") or ""
    quantity = parse_quantity(body)
    requested = proposal.get("requested_world_effect")
    action_type = proposal.get("action_type")
    cross_border = bool(targets and any(t != source_nation_id for t in targets))
    explicit_acceptance = False
    accepted_by = []
    if cross_border:
        for acc in acceptances:
            if acc.get("from_nation_id") in targets and source_nation_id in (acc.get("to_nation_ids") or []):
                explicit_acceptance = True
                accepted_by.append(acc.get("from_nation_id"))
    else:
        explicit_acceptance = True
    route_results = []
    capacity_results = []
    for target in targets or [source_nation_id]:
        route = state.route_key(source_nation_id, target)
        route_results.append({"route": route, "eligible": bool(state.route_eligibility.get(route, not cross_border))})
        capacity_results.append({"nation_id": source_nation_id, "capacity": state.transport_capacity.get(source_nation_id, 0)})
    route_eligible = all(item["eligible"] for item in route_results)
    capacity_available = quantity is not None and state.transport_capacity.get(source_nation_id, 0) >= quantity
    stages = {
        "proposal_recorded": True,
        "action_type_allows_physical_review": action_type in ("resource_offer", "resource_request", "domestic_resource_allocation", "domestic_public_health_measure", "domestic_infrastructure_repair", "domestic_logistics_adjustment", "route_protection", "protective_patrol"),
        "explicit_quantity": quantity is not None,
        "explicit_acceptance": explicit_acceptance,
        "route_eligible": route_eligible,
        "transport_capacity_available": capacity_available,
        "requested_world_effect_present": bool(requested),
    }
    if all(stages.values()):
        status = "dispatch_scheduled"
        stop_reason = None
    else:
        status = "not_dispatched"
        stop_reason = next(key for key, value in stages.items() if not value)
    return {
        "version": VERSION,
        "proposal_id": proposal.get("proposal_id"),
        "source_nation_id": source_nation_id,
        "target_nation_ids": targets,
        "quantity": quantity,
        "requested_world_effect": requested,
        "accepted_by": accepted_by,
        "route_results": route_results,
        "capacity_results": capacity_results,
        "stages": stages,
        "status": status,
        "stop_reason": stop_reason,
        "world_state_mutated": False,
        "funnel_sha256": _digest({"proposal": proposal, "source_nation_id": source_nation_id, "stages": stages, "status": status}),
    }


def apply_dispatch_if_scheduled(funnel: dict[str, Any], state: WorldLawState) -> dict[str, Any]:
    ensure(funnel["version"] == VERSION, "UNKNOWN_FUNNEL_VERSION")
    if funnel["status"] != "dispatch_scheduled":
        return {**funnel, "applied": False, "world_state_mutated": False}
    quantity = funnel["quantity"]
    source = funnel["source_nation_id"]
    ensure(quantity is not None and state.transport_capacity.get(source, 0) >= quantity,
           "DISPATCH_CAPACITY_CHANGED")
    state.transport_capacity[source] -= quantity
    dispatch = {
        "dispatch_id": f"dispatch-{len(state.dispatched)+1:04d}",
        "turn": state.turn,
        "source_nation_id": source,
        "target_nation_ids": funnel["target_nation_ids"],
        "quantity": quantity,
        "requested_world_effect": funnel["requested_world_effect"],
        "arrival_turn": state.turn + 1,
    }
    state.dispatched.append(dispatch)
    mutation = {"kind": "dispatch", "dispatch": dispatch}
    state.world_state_mutations.append(mutation)
    return {**funnel, "applied": True, "world_state_mutated": True, "dispatch": dispatch}


def process_arrivals(state: WorldLawState, *, turn: int) -> list[dict[str, Any]]:
    arrivals = []
    for dispatch in state.dispatched:
        if dispatch["arrival_turn"] == turn and not dispatch.get("arrived"):
            dispatch["arrived"] = True
            arrival = {"arrival_id": f"arrival-{len(state.arrivals)+1:04d}", "turn": turn, "dispatch_id": dispatch["dispatch_id"], "target_nation_ids": dispatch["target_nation_ids"], "quantity": dispatch["quantity"], "requested_world_effect": dispatch["requested_world_effect"]}
            state.arrivals.append(arrival)
            state.world_state_mutations.append({"kind": "arrival", "arrival": arrival})
            arrivals.append(arrival)
    return arrivals


def summarize_world_state(state: WorldLawState) -> dict[str, Any]:
    return {
        "version": VERSION,
        "world_id": state.world_id,
        "turn": state.turn,
        "unmet_need": dict(state.unmet_need),
        "transport_capacity": dict(state.transport_capacity),
        "dispatch_count": len(state.dispatched),
        "arrival_count": len(state.arrivals),
        "world_state_mutation_count": len(state.world_state_mutations),
        "state_sha256": _digest(asdict(state)),
    }
