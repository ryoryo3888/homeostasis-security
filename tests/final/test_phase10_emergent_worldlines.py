from homeostasis_core.emergent_dynamics import initial_damage_from_scenario, initial_world_from_scenario, reconstruction_step


def _state(conflict=24, aid=0):
    affected={
        "indicators":{"recovery_capacity":38,"economy":40},
        "resources":{"logistics":28},
    }
    settlements=[]
    if aid:
        settlements.append({"target_country":"FRAGILE","resource":"funds_economy","realized":aid})
    executed={"true_world":{"conflict_load":conflict},"atomic_settlements":settlements}
    return executed,{"FRAGILE":affected}


def test_scenario_has_no_scripted_recovery_turns():
    scenario={"event":{"lost_annual_rice_capacity_tons":8000},"initial_world_state":{"food":82,"national_sovereignty":88}}
    assert initial_damage_from_scenario(scenario)==8000
    assert "national_sovereignty" not in initial_world_from_scenario(scenario)


def test_damage_does_not_fall_merely_because_a_turn_passed():
    executed,states=_state(conflict=60,aid=0)
    result=reconstruction_step(8000,executed,states)
    assert result["after"]==8000
    assert result["recovered"]==0


def test_realized_aid_can_change_recovery_path():
    no_aid,states=_state(conflict=24,aid=0)
    with_aid,states2=_state(conflict=24,aid=20)
    baseline=reconstruction_step(8000,no_aid,states)
    supported=reconstruction_step(8000,with_aid,states2)
    assert supported["after"] < baseline["after"]
    assert supported["external_support"] > 0


def test_conflict_suppresses_same_material_support():
    low,states=_state(conflict=20,aid=20)
    high,states2=_state(conflict=65,aid=20)
    assert reconstruction_step(8000,low,states)["recovered"] > reconstruction_step(8000,high,states2)["recovered"]
