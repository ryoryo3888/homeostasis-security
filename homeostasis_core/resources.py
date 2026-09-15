"""Deterministic Phase 2 resource portfolios and directed supply networks."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Iterable, Mapping

from .metrics import clamp
from .models import (
    CountryState, EnergyPortfolio, JsonModel, ResourcePortfolio,
    _exact_keys, _freeze, _integer, _nonempty, _read_json_object, _score, _strings,
)


RESOURCE_TYPES = (
    "food",
    "fossil_fuel",
    "renewable_energy",
    "nuclear",
    "grid_storage_resilience",
    "funds_economy",
    "logistics",
)
NATIONAL_INDICATORS = (
    "food_reserves",
    "energy_stability",
    "economy",
    "military_security",
    "domestic_stability",
    "recovery_capacity",
    "international_trust",
    "diplomatic_posture",
)


@dataclass(frozen=True)
class SupplyLink(JsonModel):
    link_id: str
    source: str
    target: str
    resource: str
    supply_amount: float
    transport_capacity: float
    reliability: float
    active: bool = True

    def __post_init__(self) -> None:
        for name in ("link_id", "source", "target", "resource"):
            _nonempty(name, getattr(self, name))
        if self.source == self.target:
            raise ValueError("supply link source and target must differ")
        _score("supply_amount", self.supply_amount)
        _score("transport_capacity", self.transport_capacity)
        _score("reliability", self.reliability)
        if not isinstance(self.active, bool):
            raise ValueError("active must be boolean")


@dataclass(frozen=True)
class ResourceNetwork(JsonModel):
    schema_version: int
    links: tuple[SupplyLink, ...]
    demands: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    resource_types: tuple[str, ...] = RESOURCE_TYPES

    def __post_init__(self) -> None:
        _integer("schema_version", self.schema_version, minimum=1)
        if self.schema_version != 1:
            raise ValueError("unsupported resource network schema_version")
        if not isinstance(self.links, (list, tuple)) or not self.links:
            raise ValueError("links must be a non-empty array")
        if any(not isinstance(link, SupplyLink) for link in self.links):
            raise ValueError("links must contain SupplyLink objects")
        _strings("resource_types", self.resource_types, required=True)
        ids = [link.link_id for link in self.links]
        if len(set(ids)) != len(ids):
            raise ValueError("link_id values must be unique")
        route_keys = [(link.source, link.target, link.resource) for link in self.links]
        if len(set(route_keys)) != len(route_keys):
            raise ValueError("source, target and resource must uniquely identify a route")
        unknown_links = {link.resource for link in self.links} - set(self.resource_types)
        if unknown_links:
            raise ValueError(f"links use unregistered resources: {sorted(unknown_links)}")
        if not isinstance(self.demands, Mapping):
            raise ValueError("demands must be an object")
        for country, resources in self.demands.items():
            _nonempty("demand country", country)
            if not isinstance(resources, Mapping):
                raise ValueError("country demands must be objects")
            for resource, amount in resources.items():
                _nonempty("demand resource", resource)
                if resource not in self.resource_types:
                    raise ValueError(f"demand uses unregistered resource: {resource}")
                _score(f"demands[{country}][{resource}]", amount)
        object.__setattr__(self, "links", tuple(sorted(
            self.links, key=lambda link: (link.source, link.target, link.resource, link.link_id)
        )))
        object.__setattr__(self, "demands", _freeze(self.demands))
        object.__setattr__(self, "resource_types", tuple(sorted(self.resource_types)))


@dataclass(frozen=True)
class TransferRecord(JsonModel):
    link_id: str
    source: str
    target: str
    resource: str
    planned: float
    delivered: float
    shortfall: float

    def __post_init__(self) -> None:
        for name in ("planned", "delivered", "shortfall"):
            _score(name, getattr(self, name))


@dataclass(frozen=True)
class ResourceNetworkResult(JsonModel):
    countries: Mapping[str, CountryState]
    transfers: tuple[TransferRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.countries, Mapping) or not self.countries:
            raise ValueError("countries must be a non-empty object")
        if any(code != state.code for code, state in self.countries.items()):
            raise ValueError("country keys and state codes must match")
        if any(not isinstance(item, TransferRecord) for item in self.transfers):
            raise ValueError("transfers must contain TransferRecord objects")
        object.__setattr__(self, "countries", _freeze(self.countries))
        object.__setattr__(self, "transfers", tuple(self.transfers))


def calculate_energy_stability(
    portfolio: EnergyPortfolio, resources: ResourcePortfolio
) -> int:
    """Calculate the public score from generation mix, resilience and import exposure."""
    return portfolio.calculate_stability(resources)


def load_resource_network(
    path: str | Path, country_codes: Iterable[str]
) -> ResourceNetwork:
    """Load and strictly validate a directed resource network."""
    data = _read_json_object(path)
    _exact_keys(data, {"schema_version", "links", "demands", "resource_types"}, context="resource network")
    if not isinstance(data["links"], list):
        raise ValueError("links must be an array")
    links = tuple(SupplyLink.from_dict(item) for item in data["links"])
    network = ResourceNetwork(
        data["schema_version"], links, data["demands"], tuple(data["resource_types"])
    )
    codes = set(country_codes)
    if not codes:
        raise ValueError("country_codes cannot be empty")
    referenced = {code for link in links for code in (link.source, link.target)} | set(network.demands)
    unknown = referenced - codes
    if unknown:
        raise ValueError(f"resource network references unknown countries: {sorted(unknown)}")
    return network


def process_resource_network(
    countries: Mapping[str, CountryState], network: ResourceNetwork
) -> ResourceNetworkResult:
    """Apply one deterministic transfer/consumption step without mutating inputs."""
    if not isinstance(countries, Mapping) or not countries:
        raise ValueError("countries must be a non-empty object")
    if not isinstance(network, ResourceNetwork):
        raise ValueError("network must be a ResourceNetwork")
    if any(not isinstance(state, CountryState) or state.code != code for code, state in countries.items()):
        raise ValueError("country keys and CountryState codes must match")
    codes = set(countries)
    referenced = {code for link in network.links for code in (link.source, link.target)} | set(network.demands)
    if referenced - codes:
        raise ValueError("network and country sets are inconsistent")
    for link in network.links:
        if link.resource not in countries[link.source].resources.levels:
            raise ValueError(f"source {link.source} has not registered resource {link.resource}")
        if link.resource not in countries[link.target].resources.levels:
            raise ValueError(f"target {link.target} has not registered resource {link.resource}")
    for code, demands in network.demands.items():
        unknown = set(demands) - set(countries[code].resources.levels)
        if unknown:
            raise ValueError(f"country {code} has demands for unregistered resources: {sorted(unknown)}")

    levels = {code: dict(countries[code].resources.levels) for code in sorted(countries)}
    desired = [
        link.supply_amount * link.transport_capacity / 100 * link.reliability / 100
        if link.active else 0.0
        for link in network.links
    ]
    grouped: dict[tuple[str, str], list[int]] = {}
    for index, link in enumerate(network.links):
        grouped.setdefault((link.source, link.resource), []).append(index)
    delivered = [0.0] * len(network.links)
    for (source, resource), indices in grouped.items():
        available = levels[source].get(resource, 0.0)
        requested = math.fsum(desired[index] for index in indices)
        scale = min(1.0, available / requested) if requested else 0.0
        for index in indices:
            delivered[index] = desired[index] * scale

    # Respect receiver headroom using the same proportional rule as source scarcity.
    inbound_groups: dict[tuple[str, str], list[int]] = {}
    for index, link in enumerate(network.links):
        inbound_groups.setdefault((link.target, link.resource), []).append(index)
    for (target, resource), indices in inbound_groups.items():
        headroom = 100 - levels[target][resource]
        incoming = math.fsum(delivered[index] for index in indices)
        scale = min(1.0, headroom / incoming) if incoming else 0.0
        for index in indices:
            delivered[index] *= scale

    # Only accepted delivery leaves a source; grouped fsum keeps ordering irrelevant.
    for (source, resource), indices in grouped.items():
        levels[source][resource] = clamp(
            levels[source][resource] - math.fsum(delivered[index] for index in indices)
        )
    for (target, resource), indices in inbound_groups.items():
        levels[target][resource] = clamp(
            levels[target][resource] + math.fsum(delivered[index] for index in indices)
        )

    inbound: dict[tuple[str, str], float] = {}
    for index, link in enumerate(network.links):
        inbound[(link.target, link.resource)] = inbound.get((link.target, link.resource), 0) + delivered[index]
    unmet_by_country: dict[str, float] = {code: 0.0 for code in countries}
    for code, demands in network.demands.items():
        for resource, demand in demands.items():
            supplied = inbound.get((code, resource), 0.0)
            unmet_by_country[code] += max(0.0, demand - supplied)
            levels[code][resource] = clamp(levels[code].get(resource, 0.0) - demand)

    updated: dict[str, CountryState] = {}
    for code in sorted(countries):
        state = countries[code]
        indicators = dict(state.indicators)
        unmet = unmet_by_country[code]
        if "economy" in indicators:
            indicators["economy"] = clamp(indicators["economy"] - 0.20 * unmet)
        if "domestic_stability" in indicators:
            indicators["domestic_stability"] = clamp(indicators["domestic_stability"] - 0.25 * unmet)
        resources = ResourcePortfolio(levels[code])
        if state.energy_portfolio.sources:
            indicators["energy_stability"] = calculate_energy_stability(state.energy_portfolio, resources)
        if "food_reserves" in indicators:
            indicators["food_reserves"] = resources.levels.get("food", indicators["food_reserves"])
        updated[code] = CountryState(
            code=state.code, sovereignty=state.sovereignty, indicators=indicators,
            energy_portfolio=state.energy_portfolio, attributes=state.attributes,
            resources=resources,
        )
    transfers = tuple(
        TransferRecord(
            link.link_id, link.source, link.target, link.resource,
            link.supply_amount, delivered[index], link.supply_amount - delivered[index],
        )
        for index, link in enumerate(network.links)
    )
    return ResourceNetworkResult(updated, transfers)
