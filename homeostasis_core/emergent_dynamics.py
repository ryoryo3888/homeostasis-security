"""Emergent world dynamics for HOMEOSTASIS SECURITY.

Only the initial shock is fixed. Later events and farmland recovery are derived
from executed agent actions and the resulting world state.
"""
from __future__ import annotations

INITIAL_EVENT = "A国ミサイルがB国民間農地へ着弾"
AFFECTED_COUNTRY = "FRAGILE"


def reconstruction_step(damage_tons: float, executed_state: dict, country_states: dict,
                        affected_country: str = AFFECTED_COUNTRY) -> dict:
    """Derive recovery from actual post-decision capacity and realized aid.

    Agents choose actions. This environment rule only converts the material
    conditions produced by those choices into reconstruction capacity.
    """
    if damage_tons <= 0:
        return {"before": 0.0, "after": 0.0, "recovered": 0.0,
                "domestic_recovery": 0.0, "external_support": 0.0,
                "conflict_factor": 1.0}

    affected = country_states[affected_country]
    indicators = affected["indicators"]
    resources = affected["resources"]
    conflict = float(executed_state["true_world"]["conflict_load"])

    # Domestic recovery is state-dependent rather than a fixed amount per turn.
    capacity = (
        float(indicators.get("recovery_capacity", 0))
        + float(indicators.get("economy", 0))
        + float(resources.get("logistics", 0))
        - 1.5 * conflict
    )
    domestic = max(0.0, capacity - 90.0) * 8.0

    # Only aid that was actually settled to the affected country counts.
    weights = {"funds_economy": 18.0, "logistics": 16.0, "food": 6.0}
    external = 0.0
    for row in executed_state.get("atomic_settlements", ()):
        if row.get("target_country") != affected_country:
            continue
        external += float(row.get("realized", 0)) * weights.get(row.get("resource"), 0.0)

    # Continuing conflict can suppress reconstruction even when resources exist.
    conflict_factor = max(0.0, min(1.0, (70.0 - conflict) / 50.0))
    recovered = min(float(damage_tons), (domestic + external) * conflict_factor)
    after = max(0.0, float(damage_tons) - recovered)
    return {
        "before": round(float(damage_tons), 4),
        "after": round(after, 4),
        "recovered": round(recovered, 4),
        "domestic_recovery": round(domestic * conflict_factor, 4),
        "external_support": round(external * conflict_factor, 4),
        "conflict_factor": round(conflict_factor, 4),
    }


def initial_world_from_scenario(scenario: dict) -> dict:
    state = dict(scenario["initial_world_state"])
    state.pop("national_sovereignty", None)
    return {k: float(v) for k, v in state.items()}


def initial_damage_from_scenario(scenario: dict) -> float:
    return float(scenario["event"]["lost_annual_rice_capacity_tons"])
