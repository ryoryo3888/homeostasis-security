import unittest
import json
from pathlib import Path
import tempfile

from homeostasis_core.engine import TurnEngine, TurnServices
from homeostasis_core.metrics import clamp, global_homeostasis, sovereignty_summary
from homeostasis_core.models import (
    CoordinatorProposal, CountryDecision, CountryProfile, CountryState,
    EnergyPortfolio, PerceivedState, WorldState,
    DamageRecord, load_country_configuration, load_scenario_configuration,
)


ROOT = Path(__file__).resolve().parents[2]


class Phase1ModelTests(unittest.TestCase):
    def test_arbitrary_country_code(self):
        profile = CountryProfile("JP-7", "observer", ("safety",), ("mediate",), {"sovereignty": 80})
        self.assertEqual(profile.code, "JP-7")

    def test_invalid_score_is_rejected(self):
        with self.assertRaises(ValueError):
            CountryState("X", 101)
        with self.assertRaises(ValueError):
            CountryState("X", -1)

    def test_nested_json_round_trip(self):
        world = WorldState(0, {"food": 82}, {"X": CountryState("X", 91, {"trust": 75})})
        restored = WorldState.from_json(world.to_json())
        self.assertEqual(restored, world)
        self.assertIsInstance(restored.countries["X"], CountryState)

    def test_sovereignty_average_and_minimum(self):
        summary = sovereignty_summary({"X": 90, "Y": 70, "Z": 80})
        self.assertEqual(summary["average"], 80)
        self.assertEqual(summary["minimum"], 70)
        self.assertEqual(summary["by_country"]["X"], 90)

    def test_clamp(self):
        self.assertEqual(clamp(120), 100)
        self.assertEqual(clamp(-4), 0)

    def test_homeostasis_formula(self):
        values = {"food": 82, "energy": 79, "economy": 81, "environment": 76,
                  "international_trust": 72, "conflict_load": 24}
        self.assertEqual(global_homeostasis(values), 68)

    def test_homeostasis_ignores_auxiliary_and_sovereignty_fields(self):
        values = {"food": 82, "energy": 79, "economy": 81, "environment": 76,
                  "international_trust": 72, "conflict_load": 24,
                  "national_sovereignty": 0, "auxiliary": 100}
        self.assertEqual(global_homeostasis(values), 68)

    def test_homeostasis_requires_contracted_indicators(self):
        with self.assertRaises(ValueError):
            global_homeostasis({"food": 80, "conflict_load": 20})

    def test_energy_validation(self):
        with self.assertRaises(ValueError):
            EnergyPortfolio({"solar": 70, "wind": 40})

    def test_bool_and_invalid_numeric_types_are_rejected(self):
        with self.assertRaises(ValueError):
            WorldState(True, {"food": 50}, {"X": CountryState("X", 80)})
        with self.assertRaises(ValueError):
            DamageRecord("d", "X", "kind", True, 0, "units")
        with self.assertRaises(ValueError):
            DamageRecord("d", "X", "kind", float("nan"), 0, "units")

    def test_configuration_loaders_map_models_and_country_sets(self):
        countries = load_country_configuration(ROOT / "config/country_types.json")
        self.assertEqual(set(countries.profiles), {"A", "B", "C"})
        for code in countries.profiles:
            self.assertEqual(countries.profiles[code].code, code)
            self.assertEqual(countries.initial_states[code].sovereignty, 88)
        scenario = load_scenario_configuration(
            ROOT / "tests/final/fixtures/scenario_schema_v1.json", countries
        )
        self.assertEqual(scenario.definition.event_id, "scenario_01_farmland_missile")
        self.assertEqual(scenario.schema_version, 1)
        self.assertEqual(set(scenario.initial_world_state.countries), {"A", "B", "C"})
        self.assertEqual(scenario.event.state["lost_annual_rice_capacity_tons"], 8000)
        self.assertEqual(type(countries).from_json(countries.to_json()), countries)
        self.assertEqual(type(scenario).from_json(scenario.to_json()), scenario)

    def test_country_loader_rejects_unknown_and_missing_fields(self):
        bad = {
            "schema_version": 1,
            "countries": {"X": {"role": "role", "interests": ["i"],
                                  "allowed_actions": ["a"], "unexpected": 1}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_country_configuration(path)

    def test_country_loader_rejects_string_instead_of_string_list(self):
        bad = {
            "schema_version": 1,
            "countries": {"X": {"role": "role", "interests": "not-a-list",
                                  "allowed_actions": ["a"],
                                  "initial_indicators": {"sovereignty": 80}}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_country_configuration(path)

    def test_frozen_models_defensively_copy_nested_data(self):
        indicators = {"trust": 75}
        state = CountryState("X", 80, indicators, attributes={"nested": {"value": 1}})
        indicators["trust"] = 1
        self.assertEqual(state.indicators["trust"], 75)
        with self.assertRaises(TypeError):
            state.attributes["nested"]["value"] = 2

    def test_turn_engine_uses_injected_processing_order(self):
        calls = []
        profile = CountryProfile("X9", "test", ("interest",), ("wait",), {"sovereignty": 80})
        before = WorldState(0, {"food": 50}, {"X9": CountryState("X9", 80)})

        def observe(world, country, event):
            calls.append("observe")
            return PerceivedState(country.code, 1, dict(world.indicators))

        def coordinate(world, perceptions):
            calls.append("coordinate")
            return CoordinatorProposal("offer", "reason")

        def decide(country, perceived, proposal):
            calls.append("decide")
            return CountryDecision(country.code, "wait", "conditional", "reason")

        def effects(world, decisions, proposal, event):
            calls.append("effects")
            return WorldState(1, {"food": 51}, world.countries), {"status": "applied"}

        def evaluate(old, new, decisions, results):
            calls.append("evaluate")
            self.assertEqual(new.indicators["food"], 51)
            return {"score": 51}

        record = TurnEngine({"X9": profile}, TurnServices(
            observe, coordinate, decide, effects, evaluate,
            recorder=lambda row: calls.append("record"),
        )).process_turn(before)
        self.assertEqual(calls, ["observe", "coordinate", "decide", "effects", "evaluate", "record"])
        self.assertEqual(record.world_after.turn, 1)
        with self.assertRaises(TypeError):
            record.action_results["status"] = "changed"

    def test_turn_engine_rejects_country_set_mismatch(self):
        profile = CountryProfile("Y", "test", ("interest",), ("wait",), {"sovereignty": 80})
        world = WorldState(0, {"food": 50}, {"X": CountryState("X", 80)})
        unused = lambda *args: None
        engine = TurnEngine({"Y": profile}, TurnServices(unused, unused, unused, unused, unused))
        with self.assertRaises(ValueError):
            engine.process_turn(world)


if __name__ == "__main__":
    unittest.main()
