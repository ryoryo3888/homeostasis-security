"""Bounded real-Gemini probe: eight country agents, exactly one turn.

At most one Gemini call per country, no retries. This stage validates that all
8 independent countries can select immutable Python-generated choice IDs.
World settlement is deliberately deferred until this paid boundary passes.
"""
from __future__ import annotations
import json, os
from pathlib import Path

from homeostasis_core.action_choices import build_action_choices, materialize_choice, validate_catalog
from homeostasis_core.emergent_dynamics import INITIAL_EVENT, initial_world_from_scenario, initial_damage_from_scenario, AFFECTED_COUNTRY
from homeostasis_core.gemini_agents import MODEL_NAME, create_gemini_client, build_private_views
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES, calculate_energy_stability, load_resource_network
from homeostasis_core.feasibility import feasible_actions

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")
SCENARIO_PATH=Path("scenarios/scenario_01_farmland_missile.json")


def initial_states(configured):
    return {c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],
               "indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},
                             "energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},
               "resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()}
            for c,p in configured.profiles.items()}


def main():
    """Delegate to the guarded workflow; default is a zero-call plan."""
    import sys
    from research_workflow import main as workflow_main
    return workflow_main(["turn", *sys.argv[1:]])


if __name__ == "__main__":
    main()
