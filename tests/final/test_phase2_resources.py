from pathlib import Path
import unittest

from homeostasis_core.models import (
    CountryState, EnergyPortfolio, ResourcePortfolio, load_country_configuration,
)
from homeostasis_core.resources import (
    NATIONAL_INDICATORS, RESOURCE_TYPES, ResourceNetwork, SupplyLink,
    calculate_energy_stability, load_resource_network, process_resource_network,
)
from homeostasis_core.v2_adapter import load_v2_first_run


ROOT = Path(__file__).resolve().parents[2]


def state(code, *, food=50, economy=80, stability=80):
    portfolio = EnergyPortfolio(
        {"fossil_fuel": 50, "renewable_energy": 40, "nuclear": 10}, 30
    )
    resources = ResourcePortfolio({
        "food": food, "fossil_fuel": 70, "renewable_energy": 60,
        "nuclear": 50, "grid_storage_resilience": 75,
        "funds_economy": 70, "logistics": 70,
    })
    indicators = {
        "food_reserves": food, "energy_stability": 60, "economy": economy,
        "military_security": 60, "domestic_stability": stability,
        "recovery_capacity": 60, "international_trust": 60,
        "diplomatic_posture": 60,
    }
    return CountryState(code, 80, indicators, portfolio, resources=resources)


def network(*links, demands=None):
    return ResourceNetwork(1, tuple(links), demands or {})


class Phase2ResourceTests(unittest.TestCase):
    def test_eight_archetypes_use_common_country_models(self):
        loaded = load_country_configuration(ROOT / "config/country_archetypes.json")
        self.assertEqual(len(loaded.profiles), 8)
        self.assertEqual(
            {profile.archetype for profile in loaded.profiles.values()},
            {"軍事大国", "資源輸出国", "食料輸入国", "小国", "島嶼国",
             "経済大国", "紛争脆弱国", "中立国"},
        )
        for code, profile in loaded.profiles.items():
            self.assertEqual(profile.code, code)
            self.assertEqual(set(profile.initial_resources.levels), set(RESOURCE_TYPES))
            self.assertTrue(set(NATIONAL_INDICATORS) <= set(loaded.initial_states[code].indicators))

    def test_invalid_resource_and_country_values_are_rejected(self):
        with self.assertRaises(ValueError):
            ResourcePortfolio({"food": 101})
        with self.assertRaises(ValueError):
            CountryState("X", 80, {"economy": "high"})

    def test_bool_is_not_accepted_as_network_number(self):
        with self.assertRaises(ValueError):
            SupplyLink("x", "A", "B", "food", True, 100, 100)

    def test_additional_resource_type_is_data_extensible(self):
        countries = {"S": state("S"), "T": state("T")}
        countries = {
            code: CountryState(
                code, item.sovereignty, item.indicators, item.energy_portfolio,
                resources=ResourcePortfolio({**item.resources.levels, "water": 40 if code == "S" else 0}),
            )
            for code, item in countries.items()
        }
        link = SupplyLink("water", "S", "T", "water", 10, 100, 100)
        result = process_resource_network(
            countries, ResourceNetwork(1, (link,), {}, RESOURCE_TYPES + ("water",))
        )
        self.assertEqual(result.countries["T"].resources.levels["water"], 10)

    def test_energy_stability_is_derived_from_internal_mix(self):
        portfolio = EnergyPortfolio({"fossil_fuel": 100}, 25)
        resources = ResourcePortfolio({"fossil_fuel": 80, "grid_storage_resilience": 80})
        self.assertEqual(calculate_energy_stability(portfolio, resources), 75)

    def test_normal_supply_moves_resources(self):
        countries = {"S": state("S", food=80), "T": state("T", food=20)}
        link = SupplyLink("food", "S", "T", "food", 20, 100, 100)
        result = process_resource_network(countries, network(link))
        self.assertEqual(result.countries["S"].resources.levels["food"], 60)
        self.assertEqual(result.countries["T"].resources.levels["food"], 40)
        self.assertEqual(result.transfers[0].delivered, 20)

    def test_supply_stop_propagates_to_importer(self):
        countries = {"S": state("S", food=80), "T": state("T", food=40)}
        active = SupplyLink("food", "S", "T", "food", 20, 100, 100, True)
        stopped = SupplyLink("food", "S", "T", "food", 20, 100, 100, False)
        normal = process_resource_network(countries, network(active, demands={"T": {"food": 20}}))
        outage = process_resource_network(countries, network(stopped, demands={"T": {"food": 20}}))
        self.assertEqual(normal.countries["T"].resources.levels["food"], 40)
        self.assertEqual(outage.countries["T"].resources.levels["food"], 20)
        self.assertLess(outage.countries["T"].indicators["economy"], normal.countries["T"].indicators["economy"])
        self.assertLess(outage.countries["T"].indicators["domestic_stability"], normal.countries["T"].indicators["domestic_stability"])

    def test_lower_transport_capacity_reduces_supply(self):
        countries = {"S": state("S", food=80), "T": state("T", food=20)}
        full = SupplyLink("food", "S", "T", "food", 20, 100, 100)
        half = SupplyLink("food", "S", "T", "food", 20, 50, 100)
        self.assertEqual(process_resource_network(countries, network(full)).transfers[0].delivered, 20)
        self.assertEqual(process_resource_network(countries, network(half)).transfers[0].delivered, 10)

    def test_multiple_routes_are_aggregated(self):
        countries = {"S1": state("S1", food=80), "S2": state("S2", food=80), "T": state("T", food=20)}
        links = (
            SupplyLink("one", "S1", "T", "food", 10, 100, 100),
            SupplyLink("two", "S2", "T", "food", 15, 100, 100),
        )
        result = process_resource_network(countries, network(*links))
        self.assertEqual(result.countries["T"].resources.levels["food"], 45)
        self.assertEqual(sum(item.delivered for item in result.transfers), 25)

    def test_processing_does_not_mutate_inputs(self):
        countries = {"S": state("S", food=80), "T": state("T", food=20)}
        graph = network(SupplyLink("food", "S", "T", "food", 20, 100, 100))
        countries_before = {code: value.to_dict() for code, value in countries.items()}
        network_before = graph.to_dict()
        process_resource_network(countries, graph)
        self.assertEqual({code: value.to_dict() for code, value in countries.items()}, countries_before)
        self.assertEqual(graph.to_dict(), network_before)

    def test_output_values_remain_bounded(self):
        countries = {"S": state("S", food=100), "T": state("T", food=95, economy=1, stability=1)}
        links = (SupplyLink("high", "S", "T", "food", 100, 100, 100),)
        result = process_resource_network(countries, network(*links, demands={"T": {"food": 100}}))
        for country in result.countries.values():
            for value in (*country.resources.levels.values(), *country.indicators.values(), country.sovereignty):
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 100)

    def test_same_input_produces_same_result(self):
        countries = {"S": state("S", food=80), "T": state("T", food=20)}
        graph = network(SupplyLink("food", "S", "T", "food", 20, 75, 90))
        self.assertEqual(process_resource_network(countries, graph), process_resource_network(countries, graph))

    def test_sample_network_loads_and_runs(self):
        countries = load_country_configuration(ROOT / "config/country_archetypes.json")
        graph = load_resource_network(ROOT / "scenarios/resource_network_sample.json", countries.profiles)
        result = process_resource_network(countries.initial_states, graph)
        self.assertEqual(len(result.transfers), 6)
        self.assertEqual(set(result.countries), set(countries.profiles))

    def test_phase1_v2_adapter_remains_compatible(self):
        converted = load_v2_first_run(ROOT / "v2_first_run.json")
        self.assertEqual(len(converted.turns), 5)
        self.assertEqual(converted.final_result["outcome"], "recovered")


class Phase2AuditRegressionTests(unittest.TestCase):
    def test_01_total_is_conserved_when_receiver_is_near_capacity(self):
        countries = {"S": state("S", food=100), "T": state("T", food=95)}
        graph = network(SupplyLink("one", "S", "T", "food", 20, 100, 100))
        result = process_resource_network(countries, graph)
        before = sum(item.resources.levels["food"] for item in countries.values())
        after = sum(item.resources.levels["food"] for item in result.countries.values())
        self.assertEqual(after, before)

    def test_02_receiver_headroom_is_proportionally_shared_by_sources(self):
        countries = {"S1": state("S1", food=100), "S2": state("S2", food=100), "T": state("T", food=90)}
        graph = network(
            SupplyLink("one", "S1", "T", "food", 30, 100, 100),
            SupplyLink("two", "S2", "T", "food", 10, 100, 100),
        )
        result = process_resource_network(countries, graph)
        delivered = {item.link_id: item.delivered for item in result.transfers}
        self.assertAlmostEqual(delivered["one"], 7.5)
        self.assertAlmostEqual(delivered["two"], 2.5)
        self.assertEqual(result.countries["T"].resources.levels["food"], 100)

    def test_03_reordering_links_produces_identical_complete_result(self):
        countries = {"S1": state("S1", food=80), "S2": state("S2", food=80), "T": state("T", food=20)}
        links = (
            SupplyLink("one", "S1", "T", "food", 10, 90, 90),
            SupplyLink("two", "S2", "T", "food", 15, 80, 95),
        )
        self.assertEqual(
            process_resource_network(countries, network(*links)),
            process_resource_network(countries, network(*reversed(links))),
        )

    def test_04_duplicate_semantic_route_is_rejected(self):
        links = (
            SupplyLink("one", "S", "T", "food", 10, 100, 100),
            SupplyLink("two", "S", "T", "food", 20, 100, 100),
        )
        with self.assertRaises(ValueError):
            network(*links)

    def test_05_source_must_register_supplied_resource(self):
        source = state("S")
        source = CountryState(
            "S", source.sovereignty, source.indicators, source.energy_portfolio,
            resources=ResourcePortfolio({key: value for key, value in source.resources.levels.items() if key != "food"}),
        )
        countries = {"S": source, "T": state("T")}
        with self.assertRaises(ValueError):
            process_resource_network(countries, network(SupplyLink("one", "S", "T", "food", 10, 100, 100)))

    def test_06_target_must_register_demanded_resource(self):
        countries = {"S": state("S"), "T": state("T")}
        source = countries["S"]
        countries["S"] = CountryState(
            "S", source.sovereignty, source.indicators, source.energy_portfolio,
            resources=ResourcePortfolio({**source.resources.levels, "water": 20}),
        )
        with self.assertRaises(ValueError):
            process_resource_network(
                countries,
                ResourceNetwork(1, (SupplyLink("one", "S", "T", "water", 10, 100, 100),), {"T": {"water": 5}}, ("water",)),
            )

    def test_07_explicitly_registered_extension_is_accepted(self):
        countries = {"S": state("S"), "T": state("T")}
        countries = {
            code: CountryState(
                code, item.sovereignty, item.indicators, item.energy_portfolio,
                resources=ResourcePortfolio({**item.resources.levels, "water": 40 if code == "S" else 0}),
            )
            for code, item in countries.items()
        }
        graph = ResourceNetwork(
            1, (SupplyLink("water", "S", "T", "water", 10, 100, 100),), {},
            RESOURCE_TYPES + ("water",),
        )
        result = process_resource_network(countries, graph)
        self.assertEqual(result.countries["T"].resources.levels["water"], 10)

    def test_08_total_before_and_after_delivery_is_conserved(self):
        countries = {"S1": state("S1", food=80), "S2": state("S2", food=60), "T": state("T", food=30)}
        graph = network(
            SupplyLink("one", "S1", "T", "food", 12.5, 88, 93),
            SupplyLink("two", "S2", "T", "food", 17.25, 77, 89),
        )
        result = process_resource_network(countries, graph)
        self.assertAlmostEqual(
            sum(item.resources.levels["food"] for item in countries.values()),
            sum(item.resources.levels["food"] for item in result.countries.values()),
            places=12,
        )

    def test_09_transfer_records_match_country_resource_deltas(self):
        countries = {"S1": state("S1", food=70), "S2": state("S2", food=65), "T": state("T", food=25)}
        graph = network(
            SupplyLink("one", "S1", "T", "food", 10, 80, 90),
            SupplyLink("two", "S2", "T", "food", 15, 90, 80),
        )
        result = process_resource_network(countries, graph)
        delivered = sum(item.delivered for item in result.transfers)
        target_gain = result.countries["T"].resources.levels["food"] - countries["T"].resources.levels["food"]
        source_loss = sum(
            countries[code].resources.levels["food"] - result.countries[code].resources.levels["food"]
            for code in ("S1", "S2")
        )
        self.assertAlmostEqual(target_gain, delivered, places=12)
        self.assertAlmostEqual(source_loss, delivered, places=12)

    def test_10_fractional_many_route_reordering_is_reproducible(self):
        countries = {**{f"S{i}": state(f"S{i}", food=1) for i in range(8)}, "T": state("T", food=99.5)}
        links = tuple(
            SupplyLink(f"link-{i}", f"S{i}", "T", "food", (i + 1) / 17, 91.3, 87.7)
            for i in range(8)
        )
        first = process_resource_network(countries, network(*links))
        second = process_resource_network(countries, network(*reversed(links)))
        self.assertEqual(first, second)

    def test_11_reported_delivery_equals_actual_gain_at_receiver_limit(self):
        countries = {"S": state("S", food=100), "T": state("T", food=97)}
        result = process_resource_network(
            countries, network(SupplyLink("one", "S", "T", "food", 20, 100, 100))
        )
        actual_gain = result.countries["T"].resources.levels["food"] - 97
        self.assertEqual(result.transfers[0].delivered, actual_gain)

    def test_12_multiple_resources_do_not_interfere(self):
        countries = {"S": state("S", food=80), "T": state("T", food=20)}
        before_fossil = countries["T"].resources.levels["fossil_fuel"]
        graph = network(
            SupplyLink("food", "S", "T", "food", 10, 100, 100),
            SupplyLink("funds", "S", "T", "funds_economy", 7, 100, 100),
        )
        result = process_resource_network(countries, graph)
        self.assertEqual(result.countries["T"].resources.levels["food"], 30)
        self.assertEqual(result.countries["T"].resources.levels["funds_economy"], 77)
        self.assertEqual(result.countries["T"].resources.levels["fossil_fuel"], before_fossil)


if __name__ == "__main__":
    unittest.main()
