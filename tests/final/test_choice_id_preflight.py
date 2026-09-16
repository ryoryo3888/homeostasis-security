from homeostasis_core.action_choices import build_action_choices,materialize_choice,validate_catalog
from homeostasis_core.feasibility import feasible_actions
from preflight_emergent import COUNTRIES,initial_states,run_preflight
from homeostasis_core.resources import RESOURCE_TYPES,load_resource_network
from pathlib import Path


def test_every_generated_choice_is_executable_without_api():
    states=initial_states();pool={r:0.0 for r in RESOURCE_TYPES};network=load_resource_network(Path("scenarios/resource_network_sample.json"),COUNTRIES);policy={"restricted":[],"suspended":[],"disrupted":[]}
    for country in COUNTRIES:
        feasible=feasible_actions(country,states,pool,network,policy);choices=build_action_choices(feasible)
        assert validate_catalog(country,choices,feasible)
        for choice in choices:
            maximum=float(choice["maximum_amount"]);amount=0 if maximum==0 else min(1.0,maximum)
            action=materialize_choice(choice["choice_id"],amount,"test",choices,feasible)
            assert action["action_id"]==choice["action_id"]
            assert action["parameters"]["resource"]==choice["resource"]
            assert action["parameters"]["recipient_type"]==choice["recipient_type"]
            assert action["parameters"]["target_country"]==choice["target_country"]


def test_eight_turn_preflight_uses_zero_api_calls():
    result=run_preflight(8)
    assert result["status"]=="PASS"
    assert result["api_calls"]==0
    assert result["turns"]==8
    assert len(result["events"])==8
