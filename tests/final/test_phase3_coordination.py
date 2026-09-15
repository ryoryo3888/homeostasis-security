from collections import OrderedDict
import unittest

from homeostasis_core.coordination import (
    PROPOSAL_TYPES, ConfiguredProposalCoordinator, CoordinationPipeline,
    CountryResponse, DeterministicResponsePolicy, GlobalProposal,
    GovernanceEvaluation, IndependentGovernanceEvaluator,
    ProposedResourceTransfer, ResponseConditions, execute_proposal,
    build_proposal_catalog, build_response_map,
)
from homeostasis_core.metrics import global_homeostasis
from homeostasis_core.models import CountryProfile, CountryState, ResourcePortfolio, WorldState


def country(code, *, sovereignty=80, diplomacy=70, stability=70, food=50):
    indicators = {
        "diplomatic_posture": diplomacy,
        "domestic_stability": stability,
        "economy": 75,
        "food_reserves": food,
    }
    resources = ResourcePortfolio({"food": food, "funds_economy": 60})
    state = CountryState(code, sovereignty, indicators, resources=resources)
    profile = CountryProfile(
        code, "common role", ("stability",), ("cooperate",),
        {"sovereignty": sovereignty}, initial_resources=resources,
    )
    return profile, state


def fixture_world(order=("S", "T", "N")):
    pairs = {code: country(code, food={"S": 90, "T": 20, "N": 50}[code]) for code in order}
    states = {code: pair[1] for code, pair in pairs.items()}
    profiles = {code: pair[0] for code, pair in pairs.items()}
    indicators = {
        "food": 72, "energy": 78, "economy": 76, "environment": 74,
        "international_trust": 70, "conflict_load": 24,
    }
    world = WorldState(0, indicators, states, global_homeostasis=global_homeostasis(indicators))
    return profiles, world


def proposal(
    proposal_type="食料援助", *, proposal_id="p1", participants=("S", "T"),
    targets=("T",), amount=20, effect=80, burden=5, transfers=True,
):
    moves = (ProposedResourceTransfer("S", "T", "food", amount),) if transfers else ()
    return GlobalProposal(
        proposal_id, proposal_type, "deterministic reason", targets, participants, moves,
        {code: "cooperate" for code in participants}, effect,
        {code: burden for code in participants}, 2,
    )


def response(code, prop, choice="受け入れる", *, conditions=None, burden=None):
    return CountryResponse(
        code, prop.proposal_id, choice, "independent reason", conditions,
        70, prop.predicted_sovereignty_burden[code] if burden is None else burden, 75,
    )


class Phase3CoordinationTests(unittest.TestCase):
    def test_realized_world_effect_is_zero_when_aid_delivery_is_zero(self):
        _, world = fixture_world()
        source = world.countries["S"]
        empty_source = CountryState(
            "S", source.sovereignty, {**source.indicators, "food_reserves": 0},
            resources=ResourcePortfolio({"food": 0, "funds_economy": 60}),
        )
        zero_world = WorldState(
            world.turn, world.indicators, {**world.countries, "S": empty_source},
            global_homeostasis=world.global_homeostasis,
        )
        prop = proposal()
        result = execute_proposal(
            zero_world, prop, {code: response(code, prop) for code in ("S", "T")}, 1,
        )
        self.assertEqual(sum(item.delivered for item in result.actual_transfers), 0)
        self.assertEqual(result.world_after.indicators, zero_world.indicators)
        self.assertEqual(result.world_after.global_homeostasis, zero_world.global_homeostasis)

    def test_replaying_same_proposal_id_is_rejected_without_double_consumption(self):
        _, world = fixture_world()
        prop = proposal()
        responses = {code: response(code, prop) for code in ("S", "T")}
        first = execute_proposal(world, prop, responses, 1)
        before_replay = first.world_after.to_dict()
        with self.assertRaises(ValueError):
            execute_proposal(first.world_after, prop, responses, 2)
        self.assertEqual(first.world_after.to_dict(), before_replay)

    def test_mutual_conditional_cycle_does_not_bootstrap_itself(self):
        _, world = fixture_world()
        prop = proposal(transfers=False)
        responses = {
            "S": response("S", prop, "条件付きで応じる", conditions=ResponseConditions(("T",), mutual_performance=True)),
            "T": response("T", prop, "条件付きで応じる", conditions=ResponseConditions(("S",), mutual_performance=True)),
        }
        result = execute_proposal(world, prop, responses, 1)
        self.assertEqual(result.status, "不成立")
        self.assertEqual(result.condition_unmet_countries, ("S", "T"))

    def test_mutual_performance_requires_actual_resource_performance(self):
        _, world = fixture_world()
        source = world.countries["S"]
        empty_source = CountryState(
            "S", source.sovereignty, {**source.indicators, "food_reserves": 0},
            resources=ResourcePortfolio({"food": 0, "funds_economy": 60}),
        )
        zero_world = WorldState(
            world.turn, world.indicators, {**world.countries, "S": empty_source},
            global_homeostasis=world.global_homeostasis,
        )
        prop = proposal()
        conditions = ResponseConditions(("S",), mutual_performance=True)
        result = execute_proposal(
            zero_world, prop,
            {"S": response("S", prop),
             "T": response("T", prop, "条件付きで応じる", conditions=conditions)}, 1,
        )
        self.assertEqual(result.status, "部分成立")
        self.assertEqual(result.condition_unmet_countries, ("T",))
        self.assertEqual(result.actual_transfers, ())

    def test_response_mapping_order_does_not_change_execution(self):
        _, world = fixture_world()
        prop = proposal()
        forward = OrderedDict((code, response(code, prop)) for code in ("S", "T"))
        reverse = OrderedDict(reversed(tuple(forward.items())))
        self.assertEqual(
            execute_proposal(world, prop, forward, 1),
            execute_proposal(world, prop, reverse, 1),
        )

    def test_sanction_target_is_distinct_from_voluntary_actors(self):
        _, world = fixture_world()
        prop = proposal(
            "制裁提案", participants=("S", "N"), targets=("T",), transfers=False,
        )
        result = execute_proposal(
            world, prop, {code: response(code, prop) for code in ("S", "N")}, 1,
        )
        self.assertEqual(result.status, "成立")
        self.assertNotIn("T", result.participating_countries)
        self.assertEqual(result.world_after.countries["T"], world.countries["T"])
        self.assertEqual(result.sovereignty_burden["T"], 0)

    def test_duplicate_proposal_and_response_ids_are_rejected_before_mapping(self):
        prop = proposal()
        with self.assertRaises(ValueError):
            build_proposal_catalog((prop, prop))
        duplicate = response("S", prop)
        with self.assertRaises(ValueError):
            build_response_map((duplicate, duplicate), prop)

    def test_seven_proposal_types_use_one_model(self):
        values = [proposal(kind, proposal_id=f"p-{index}") for index, kind in enumerate(PROPOSAL_TYPES)]
        self.assertEqual(len(values), 7)
        self.assertTrue(all(isinstance(value, GlobalProposal) for value in values))

    def test_invalid_proposal_type_country_numeric_and_bool_are_rejected(self):
        with self.assertRaises(ValueError):
            proposal("unknown")
        _, world = fixture_world()
        unknown_target = proposal(participants=("S",), targets=("UNKNOWN",), transfers=False)
        with self.assertRaises(ValueError):
            execute_proposal(
                world, unknown_target, {"S": response("S", unknown_target)}, 1,
            )
        with self.assertRaises(ValueError):
            proposal(effect=101)
        with self.assertRaises(ValueError):
            proposal(effect=True)

    def test_three_response_types_use_one_model(self):
        prop = proposal()
        condition = ResponseConditions(maximum_sovereignty_burden=10)
        values = (
            response("S", prop, "受け入れる"),
            response("S", prop, "拒否する"),
            response("S", prop, "条件付きで応じる", conditions=condition),
        )
        self.assertEqual({item.response for item in values}, {"受け入れる", "拒否する", "条件付きで応じる"})

    def test_conditional_response_requires_structured_conditions(self):
        prop = proposal()
        with self.assertRaises(ValueError):
            response("S", prop, "条件付きで応じる")

    def test_deterministic_policy_returns_identical_response(self):
        profiles, world = fixture_world()
        prop = proposal()
        policy = DeterministicResponsePolicy()
        first = policy.decide(profiles["S"], world.countries["S"], prop, 1)
        second = policy.decide(profiles["S"], world.countries["S"], prop, 1)
        self.assertEqual(first, second)

    def test_country_input_order_does_not_change_responses_or_result(self):
        profiles_a, world_a = fixture_world(("S", "T", "N"))
        profiles_b, world_b = fixture_world(("N", "T", "S"))
        pipeline = CoordinationPipeline(DeterministicResponsePolicy(), IndependentGovernanceEvaluator())
        prop = proposal()
        self.assertEqual(
            pipeline.process_turn(world_a, profiles_a, prop),
            pipeline.process_turn(world_b, profiles_b, prop),
        )

    def test_rejected_country_is_not_forced(self):
        _, world = fixture_world()
        prop = proposal()
        result = execute_proposal(
            world, prop, {"S": response("S", prop), "T": response("T", prop, "拒否する")}, 1
        )
        self.assertEqual(result.status, "部分成立")
        self.assertEqual(result.actual_transfers, ())
        self.assertEqual(result.world_after.countries["T"].resources, world.countries["T"].resources)
        self.assertEqual(result.world_after.countries["T"].sovereignty, world.countries["T"].sovereignty)

    def test_conditional_acceptance_is_established_when_conditions_hold(self):
        _, world = fixture_world()
        prop = proposal()
        conditions = ResponseConditions(("S",), 15, 10, True, 1)
        result = execute_proposal(
            world, prop,
            {"S": response("S", prop), "T": response("T", prop, "条件付きで応じる", conditions=conditions)}, 1,
        )
        self.assertEqual(result.status, "成立")
        self.assertIn("T", result.participating_countries)

    def test_conditional_acceptance_is_unmet_when_minimum_aid_fails(self):
        _, world = fixture_world()
        prop = proposal(amount=10)
        conditions = ResponseConditions(("S",), 30, 10, True, 1)
        result = execute_proposal(
            world, prop,
            {"S": response("S", prop), "T": response("T", prop, "条件付きで応じる", conditions=conditions)}, 1,
        )
        self.assertEqual(result.status, "部分成立")
        self.assertEqual(result.condition_unmet_countries, ("T",))
        self.assertEqual(result.actual_transfers, ())

    def test_minimum_aid_uses_deliverable_amount_after_receiver_limit(self):
        _, world = fixture_world()
        target = world.countries["T"]
        full_target = CountryState(
            "T", target.sovereignty, {**target.indicators, "food_reserves": 95},
            resources=ResourcePortfolio({"food": 95, "funds_economy": 60}),
        )
        limited_world = WorldState(
            world.turn, world.indicators, {**world.countries, "T": full_target},
            global_homeostasis=world.global_homeostasis,
        )
        prop = proposal(amount=20)
        conditions = ResponseConditions(("S",), 10, 10, True, 1)
        result = execute_proposal(
            limited_world, prop,
            {"S": response("S", prop), "T": response("T", prop, "条件付きで応じる", conditions=conditions)}, 1,
        )
        self.assertEqual(result.status, "部分成立")
        self.assertEqual(result.condition_unmet_countries, ("T",))

    def test_missing_required_participant_is_detected(self):
        _, world = fixture_world()
        prop = proposal(participants=("S", "T", "N"))
        conditions = ResponseConditions(("N",), 0, 10, False, 1)
        result = execute_proposal(
            world, prop,
            {"S": response("S", prop), "T": response("T", prop, "条件付きで応じる", conditions=conditions),
             "N": response("N", prop, "拒否する")}, 1,
        )
        self.assertEqual(result.condition_unmet_countries, ("T",))
        self.assertEqual(result.rejected_countries, ("N",))

    def test_condition_referencing_unknown_country_is_rejected(self):
        _, world = fixture_world()
        prop = proposal()
        invalid = ResponseConditions(("UNKNOWN",), 0, 10, False, 1)
        with self.assertRaises(ValueError):
            execute_proposal(
                world, prop,
                {"S": response("S", prop),
                 "T": response("T", prop, "条件付きで応じる", conditions=invalid)}, 1,
            )

    def test_maximum_burden_uses_applied_proposal_burden(self):
        _, world = fixture_world()
        prop = proposal(burden=80)
        conditions = ResponseConditions(("S",), 0, 20, False, 1)
        result = execute_proposal(
            world, prop,
            {"S": response("S", prop),
             "T": response("T", prop, "条件付きで応じる", conditions=conditions, burden=5)}, 1,
        )
        self.assertEqual(result.condition_unmet_countries, ("T",))

    def test_condition_failure_propagates_to_dependent_participants(self):
        _, world = fixture_world()
        prop = proposal(participants=("S", "T", "N"), transfers=False)
        s_condition = ResponseConditions(("T",), 0, 10, False, 1)
        t_condition = ResponseConditions(("N",), 0, 10, False, 1)
        responses = {
            "S": response("S", prop, "条件付きで応じる", conditions=s_condition),
            "T": response("T", prop, "条件付きで応じる", conditions=t_condition),
            "N": response("N", prop, "拒否する"),
        }
        result = execute_proposal(world, prop, responses, 1)
        self.assertEqual(result.status, "不成立")
        self.assertEqual(result.condition_unmet_countries, ("S", "T"))

    def test_sanctions_fixture_records_partial_establishment(self):
        _, world = fixture_world()
        prop = proposal("制裁提案", participants=("S", "T", "N"), transfers=False)
        result = execute_proposal(
            world, prop,
            {"S": response("S", prop), "T": response("T", prop, "拒否する"),
             "N": response("N", prop)}, 1,
        )
        self.assertEqual(result.status, "部分成立")
        self.assertEqual(result.participating_countries, ("N", "S"))

    def test_food_aid_preserves_resources_and_receiver_capacity(self):
        _, world = fixture_world()
        prop = proposal(amount=100)
        result = execute_proposal(
            world, prop, {code: response(code, prop) for code in ("S", "T")}, 1
        )
        before = sum(state.resources.levels["food"] for state in world.countries.values())
        after = sum(state.resources.levels["food"] for state in result.world_after.countries.values())
        self.assertEqual(before, after)
        self.assertLessEqual(result.world_after.countries["T"].resources.levels["food"], 100)
        self.assertLessEqual(sum(item.delivered for item in result.actual_transfers), 90)

    def test_logs_and_state_changes_match_actual_result(self):
        _, world = fixture_world()
        prop = proposal()
        result = execute_proposal(
            world, prop, {code: response(code, prop) for code in ("S", "T")}, 1
        )
        transferred_log = next(item for item in result.logs if item.startswith("transferred="))
        self.assertAlmostEqual(float(transferred_log.split("=", 1)[1]), sum(item.delivered for item in result.actual_transfers))
        for code in world.countries:
            self.assertEqual(
                result.country_state_changes[code]["resources_after"],
                result.world_after.countries[code].resources.to_dict()["levels"],
            )
        for name, change in result.world_state_changes.items():
            self.assertEqual(change, result.world_after.indicators[name] - world.indicators[name])

    def test_inputs_and_nested_mappings_are_not_mutated(self):
        _, world = fixture_world()
        prop = proposal()
        responses = {code: response(code, prop) for code in ("S", "T")}
        before_world = world.to_dict()
        before_proposal = prop.to_dict()
        before_responses = {code: item.to_dict() for code, item in responses.items()}
        execute_proposal(world, prop, responses, 1)
        self.assertEqual(world.to_dict(), before_world)
        self.assertEqual(prop.to_dict(), before_proposal)
        self.assertEqual({code: item.to_dict() for code, item in responses.items()}, before_responses)

    def test_all_governance_scores_are_bounded(self):
        _, world = fixture_world()
        prop = proposal(effect=100, burden=100)
        result = execute_proposal(
            world, prop, {code: response(code, prop) for code in ("S", "T")}, 1
        )
        evaluation = IndependentGovernanceEvaluator().evaluate(result)
        for value in evaluation.to_dict().values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)

    def test_sovereignty_and_homeostasis_can_both_be_maintained(self):
        _, world = fixture_world()
        prop = proposal(effect=80, burden=2)
        result = execute_proposal(
            world, prop, {code: response(code, prop) for code in ("S", "T")}, 1
        )
        evaluation = IndependentGovernanceEvaluator().evaluate(result)
        self.assertGreater(evaluation.national_sovereignty_maintenance, 75)
        self.assertGreater(evaluation.overall_improvement_effect, 50)
        self.assertLess(evaluation.sovereignty_homeostasis_conflict, 25)

    def test_opposing_sovereignty_and_global_effect_is_detected(self):
        _, world = fixture_world()
        prop = proposal(effect=90, burden=90)
        result = execute_proposal(
            world, prop, {code: response(code, prop) for code in ("S", "T")}, 1
        )
        evaluation = IndependentGovernanceEvaluator().evaluate(result)
        self.assertGreater(evaluation.overall_improvement_effect, 50)
        self.assertGreater(evaluation.sovereignty_homeostasis_conflict, 40)

    def test_all_rejections_preserve_sovereignty_but_can_reduce_homeostasis(self):
        _, world = fixture_world()
        prop = proposal(effect=90)
        result = execute_proposal(
            world, prop, {code: response(code, prop, "拒否する") for code in ("S", "T")}, 1
        )
        self.assertEqual(result.status, "不成立")
        self.assertEqual(
            {code: state.sovereignty for code, state in result.world_after.countries.items()},
            {code: state.sovereignty for code, state in world.countries.items()},
        )
        self.assertLess(result.world_after.global_homeostasis, world.global_homeostasis)

    def test_expired_proposal_is_not_executed(self):
        _, world = fixture_world()
        prop = proposal()
        result = execute_proposal(
            world, prop, {code: response(code, prop) for code in ("S", "T")}, 3
        )
        self.assertEqual(result.status, "不成立")
        self.assertEqual(result.actual_transfers, ())

    def test_evaluator_is_replaceable_and_independent_from_coordinator(self):
        profiles, world = fixture_world()
        prop = proposal()
        coordinator = ConfiguredProposalCoordinator({prop.proposal_id: prop})

        class StubEvaluator:
            called = False

            def evaluate(self, result):
                self.called = True
                return GovernanceEvaluation(80, 75, 5, 60, 10)

        evaluator = StubEvaluator()
        pipeline = CoordinationPipeline(DeterministicResponsePolicy(), evaluator)
        result = pipeline.process_configured_turn(world, profiles, coordinator, "p1")
        self.assertTrue(evaluator.called)
        self.assertEqual(result.evaluation.overall_improvement_effect, 60)

    def test_emergency_agreement_fixture_can_fail_all_conditions(self):
        _, world = fixture_world()
        prop = proposal("緊急協定", transfers=False, burden=80)
        impossible = ResponseConditions(("S", "T"), 50, 10, True, 0)
        responses = {
            code: response(code, prop, "条件付きで応じる", conditions=impossible) for code in ("S", "T")
        }
        result = execute_proposal(world, prop, responses, 1)
        self.assertEqual(result.status, "不成立")
        self.assertEqual(result.condition_unmet_countries, ("S", "T"))

    def test_v2_legacy_model_names_remain_separate(self):
        from homeostasis_core.models import CoordinatorProposal, CountryDecision
        self.assertNotEqual(GlobalProposal, CoordinatorProposal)
        self.assertNotEqual(CountryResponse, CountryDecision)


if __name__ == "__main__":
    unittest.main()
