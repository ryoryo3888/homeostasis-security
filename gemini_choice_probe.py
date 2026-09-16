"""Exactly-one-call Gemini probe for the choice-ID boundary.

This is deliberately NOT a simulation run. It tests only the paid boundary:
Gemini sees one country's private observation plus immutable Python-generated
choices, returns one choice_id and bounded amount fraction, and Python
materializes/validates the executable action. No retry is performed.
"""
from __future__ import annotations
import json, os
from pathlib import Path

from homeostasis_core.action_choices import build_action_choices, materialize_choice
from homeostasis_core.feasibility import feasible_actions
from homeostasis_core.gemini_agents import MODEL_NAME, create_gemini_client
from homeostasis_core.models import load_country_configuration
from homeostasis_core.resources import RESOURCE_TYPES, calculate_energy_stability, load_resource_network

COUNTRIES=("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")
COUNTRY="MIL"


def initial_states():
    configured=load_country_configuration(Path("config/country_archetypes.json"))
    return {c:{"archetype":p.archetype,"sovereignty":p.initial_indicators["sovereignty"],"indicators":{**{k:v for k,v in p.initial_indicators.items() if k!="sovereignty"},"energy_stability":calculate_energy_stability(p.energy_portfolio,p.initial_resources)},"resources":dict(p.initial_resources.levels),"energy_portfolio":p.energy_portfolio.to_dict()} for c,p in configured.profiles.items()}


def main():
    """Delegate to the guarded workflow; default is a zero-call plan."""
    import sys
    from research_workflow import main as workflow_main
    return workflow_main(["probe", *sys.argv[1:]])


if __name__ == "__main__":
    main()
