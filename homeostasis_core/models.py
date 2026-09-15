"""Serializable domain models with no fixed country or scenario assumptions."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
import json
import math
from pathlib import Path
import types
from types import MappingProxyType
from typing import Any, Mapping, TypeVar, Union, get_args, get_origin, get_type_hints
import collections.abc


T = TypeVar("T", bound="JsonModel")


def _score(name: str, value: Any) -> None:
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or not 0 <= value <= 100
    ):
        raise ValueError(f"{name} must be a number from 0 through 100")


def _integer(name: str, value: Any, *, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer greater than or equal to {minimum}")


def _number(name: str, value: Any, *, minimum: float = 0) -> None:
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or value < minimum
    ):
        raise ValueError(f"{name} must be a number greater than or equal to {minimum}")


def _strings(name: str, values: Any, *, required: bool = False) -> None:
    if not isinstance(values, (list, tuple)) or (required and not values):
        raise ValueError(f"{name} must be {'a non-empty ' if required else ''}list of strings")
    for index, value in enumerate(values):
        _nonempty(f"{name}[{index}]", value)
    if len(set(values)) != len(values):
        raise ValueError(f"{name} cannot contain duplicates")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({_freeze(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _encode(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: _encode(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _nonempty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _decode(annotation: Any, value: Any) -> Any:
    if value is None or annotation is Any:
        return value
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        choices = [arg for arg in args if arg is not type(None)]
        return _decode(choices[0], value) if choices else value
    if origin in (list, tuple):
        if not isinstance(value, (list, tuple)):
            raise ValueError("expected a JSON array")
        subtype = args[0] if args else Any
        converted = [_decode(subtype, item) for item in value]
        return tuple(converted) if origin is tuple else converted
    if origin in (dict, Mapping, collections.abc.Mapping):
        if not isinstance(value, Mapping):
            raise ValueError("expected a JSON object")
        key_type, value_type = args or (Any, Any)
        return {_decode(key_type, key): _decode(value_type, item) for key, item in value.items()}
    if isinstance(annotation, type) and issubclass(annotation, JsonModel):
        return annotation.from_dict(value)
    return value


def _exact_keys(
    data: Mapping[str, Any], required: set[str], optional: set[str] | None = None, *, context: str
) -> None:
    optional = optional or set()
    missing = required - set(data)
    unknown = set(data) - required - optional
    if missing:
        raise ValueError(f"{context} missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{context} unknown fields: {sorted(unknown)}")


def _read_json_object(path: str | Path) -> Mapping[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load JSON configuration: {path}") from error
    if not isinstance(data, Mapping):
        raise ValueError("configuration root must be a JSON object")
    return data


class JsonModel:
    """Small standard-library-only JSON-compatible conversion mixin."""

    def to_dict(self) -> dict[str, Any]:
        return _encode(self)

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls: type[T], data: Mapping[str, Any]) -> T:
        if not isinstance(data, Mapping):
            raise ValueError(f"{cls.__name__} JSON value must be an object")
        hints = get_type_hints(cls)
        known = {item.name for item in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown {cls.__name__} fields: {sorted(unknown)}")
        try:
            values = {key: _decode(hints.get(key, Any), value) for key, value in data.items()}
            return cls(**values)
        except (TypeError, KeyError) as error:
            raise ValueError(f"invalid {cls.__name__} data: {error}") from error

    @classmethod
    def from_json(cls: type[T], text: str) -> T:
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid {cls.__name__} JSON") from error
        return cls.from_dict(data)


@dataclass(frozen=True)
class EnergyPortfolio(JsonModel):
    sources: dict[str, float] = field(default_factory=dict)
    import_dependency: float = 0

    def __post_init__(self) -> None:
        if not isinstance(self.sources, Mapping):
            raise ValueError("sources must be an object")
        _score("import_dependency", self.import_dependency)
        for source, share in self.sources.items():
            _nonempty("energy source", source)
            _score(f"sources[{source}]", share)
        if sum(self.sources.values()) > 100.000001:
            raise ValueError("energy source shares cannot total more than 100")
        object.__setattr__(self, "sources", _freeze(self.sources))


@dataclass(frozen=True)
class CountryProfile(JsonModel):
    code: str
    role: str
    interests: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    initial_indicators: dict[str, float] = field(default_factory=dict)
    energy_portfolio: EnergyPortfolio = field(default_factory=EnergyPortfolio)

    def __post_init__(self) -> None:
        _nonempty("code", self.code)
        _nonempty("role", self.role)
        _strings("interests", self.interests, required=True)
        _strings("allowed_actions", self.allowed_actions, required=True)
        if not isinstance(self.initial_indicators, Mapping):
            raise ValueError("initial_indicators must be an object")
        if "sovereignty" not in self.initial_indicators:
            raise ValueError("initial_indicators must contain sovereignty")
        for name, value in self.initial_indicators.items():
            _nonempty("indicator name", name)
            _score(f"initial_indicators[{name}]", value)
        if not isinstance(self.energy_portfolio, EnergyPortfolio):
            raise ValueError("energy_portfolio must be an EnergyPortfolio")
        object.__setattr__(self, "interests", tuple(self.interests))
        object.__setattr__(self, "allowed_actions", tuple(self.allowed_actions))
        object.__setattr__(self, "initial_indicators", _freeze(self.initial_indicators))


@dataclass(frozen=True)
class CountryState(JsonModel):
    code: str
    sovereignty: float
    indicators: dict[str, float] = field(default_factory=dict)
    energy_portfolio: EnergyPortfolio = field(default_factory=EnergyPortfolio)
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty("code", self.code)
        _score("sovereignty", self.sovereignty)
        if not isinstance(self.indicators, Mapping) or not isinstance(self.attributes, Mapping):
            raise ValueError("indicators and attributes must be objects")
        for name, value in self.indicators.items():
            _nonempty("indicator name", name)
            _score(f"indicators[{name}]", value)
        if not isinstance(self.energy_portfolio, EnergyPortfolio):
            raise ValueError("energy_portfolio must be an EnergyPortfolio")
        object.__setattr__(self, "indicators", _freeze(self.indicators))
        object.__setattr__(self, "attributes", _freeze(self.attributes))


@dataclass(frozen=True)
class DamageRecord(JsonModel):
    damage_id: str
    target_country: str
    category: str
    initial_amount: float
    remaining_amount: float
    unit: str
    recovery_turns: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty("damage_id", self.damage_id)
        _nonempty("target_country", self.target_country)
        _nonempty("category", self.category)
        _nonempty("unit", self.unit)
        _number("initial_amount", self.initial_amount)
        _number("remaining_amount", self.remaining_amount)
        if self.remaining_amount > self.initial_amount:
            raise ValueError("remaining_amount cannot exceed initial_amount")
        if self.recovery_turns is not None:
            _integer("recovery_turns", self.recovery_turns)
        if not isinstance(self.details, Mapping):
            raise ValueError("details must be an object")
        object.__setattr__(self, "details", _freeze(self.details))


@dataclass(frozen=True)
class WorldState(JsonModel):
    turn: int
    indicators: dict[str, float]
    countries: dict[str, CountryState]
    damages: tuple[DamageRecord, ...] = ()
    global_homeostasis: float | None = None

    def __post_init__(self) -> None:
        _integer("turn", self.turn)
        if not isinstance(self.indicators, Mapping) or not isinstance(self.countries, Mapping):
            raise ValueError("indicators and countries must be objects")
        for name, value in self.indicators.items():
            _score(f"indicators[{name}]", value)
        if self.global_homeostasis is not None:
            _score("global_homeostasis", self.global_homeostasis)
        if not self.countries:
            raise ValueError("countries cannot be empty")
        for code, state in self.countries.items():
            _nonempty("country map key", code)
            if not isinstance(state, CountryState) or code != state.code:
                raise ValueError("country values must be CountryState objects matching their keys")
        if not isinstance(self.damages, (tuple, list)) or any(not isinstance(item, DamageRecord) for item in self.damages):
            raise ValueError("damages must contain DamageRecord objects")
        unknown_targets = {item.target_country for item in self.damages} - set(self.countries)
        if unknown_targets:
            raise ValueError(f"damage targets unknown countries: {sorted(unknown_targets)}")
        object.__setattr__(self, "indicators", _freeze(self.indicators))
        object.__setattr__(self, "countries", _freeze(self.countries))
        object.__setattr__(self, "damages", tuple(self.damages))


@dataclass(frozen=True)
class EventDefinition(JsonModel):
    event_id: str
    name: str
    origin: str
    participants: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty("event_id", self.event_id)
        _nonempty("name", self.name)
        _nonempty("origin", self.origin)
        _strings("participants", self.participants, required=True)
        if not isinstance(self.parameters, Mapping):
            raise ValueError("parameters must be an object")
        object.__setattr__(self, "participants", tuple(self.participants))
        object.__setattr__(self, "parameters", _freeze(self.parameters))


@dataclass(frozen=True)
class EventInstance(JsonModel):
    definition: EventDefinition
    occurred_turn: int
    active: bool = True
    state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.definition, EventDefinition):
            raise ValueError("definition must be an EventDefinition")
        _integer("occurred_turn", self.occurred_turn)
        if not isinstance(self.active, bool):
            raise ValueError("active must be boolean")
        if not isinstance(self.state, Mapping):
            raise ValueError("state must be an object")
        object.__setattr__(self, "state", _freeze(self.state))


@dataclass(frozen=True)
class PerceivedState(JsonModel):
    country_code: str
    turn: int
    public_indicators: dict[str, float]
    narrative: str = ""
    visible_damage: tuple[DamageRecord, ...] = ()
    private_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty("country_code", self.country_code)
        _integer("turn", self.turn)
        if not isinstance(self.public_indicators, Mapping) or not isinstance(self.private_context, Mapping):
            raise ValueError("public_indicators and private_context must be objects")
        for name, value in self.public_indicators.items():
            _score(f"public_indicators[{name}]", value)
        if any(not isinstance(item, DamageRecord) for item in self.visible_damage):
            raise ValueError("visible_damage must contain DamageRecord objects")
        object.__setattr__(self, "public_indicators", _freeze(self.public_indicators))
        object.__setattr__(self, "visible_damage", tuple(self.visible_damage))
        object.__setattr__(self, "private_context", _freeze(self.private_context))


@dataclass(frozen=True)
class CountryDecision(JsonModel):
    country_code: str
    action: str
    proposal_response: str
    reason: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty("country_code", self.country_code)
        _nonempty("action", self.action)
        _nonempty("proposal_response", self.proposal_response)
        _nonempty("reason", self.reason)
        if not isinstance(self.parameters, Mapping):
            raise ValueError("parameters must be an object")
        object.__setattr__(self, "parameters", _freeze(self.parameters))


@dataclass(frozen=True)
class CoordinatorProposal(JsonModel):
    proposal: str
    reason: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty("proposal", self.proposal)
        _nonempty("reason", self.reason)
        if not isinstance(self.parameters, Mapping):
            raise ValueError("parameters must be an object")
        object.__setattr__(self, "parameters", _freeze(self.parameters))


@dataclass(frozen=True)
class TurnRecord(JsonModel):
    turn: int
    world_before: WorldState
    perceptions: dict[str, PerceivedState]
    coordinator_proposal: CoordinatorProposal
    decisions: dict[str, CountryDecision]
    action_results: dict[str, Any]
    world_after: WorldState
    evaluation: dict[str, Any]

    def __post_init__(self) -> None:
        _integer("turn", self.turn, minimum=1)
        if not isinstance(self.world_before, WorldState) or not isinstance(self.world_after, WorldState):
            raise ValueError("world_before and world_after must be WorldState objects")
        for name in ("perceptions", "decisions", "action_results", "evaluation"):
            if not isinstance(getattr(self, name), Mapping):
                raise ValueError(f"{name} must be an object")
        expected = set(self.world_before.countries)
        if set(self.world_after.countries) != expected or set(self.perceptions) != expected or set(self.decisions) != expected:
            raise ValueError("world, perception and decision country sets must match")
        if self.world_before.turn + 1 != self.turn or self.world_after.turn != self.turn:
            raise ValueError("TurnRecord turn must match consecutive world states")
        for code, perceived in self.perceptions.items():
            if not isinstance(perceived, PerceivedState) or perceived.country_code != code or perceived.turn != self.turn:
                raise ValueError("perception keys, country codes and turns must match")
        for code, decision in self.decisions.items():
            if not isinstance(decision, CountryDecision) or code != decision.country_code:
                raise ValueError("decision keys and country codes must match")
        if not isinstance(self.coordinator_proposal, CoordinatorProposal):
            raise ValueError("coordinator_proposal must be a CoordinatorProposal")
        for name in ("perceptions", "decisions", "action_results", "evaluation"):
            object.__setattr__(self, name, _freeze(getattr(self, name)))


@dataclass(frozen=True)
class ExperimentMetadata(JsonModel):
    schema_version: int
    engine: str
    mode: str
    turn_count: int
    model: str | None = None
    generated_at_utc: str | None = None
    research_question: str | None = None
    source_format: str | None = None

    def __post_init__(self) -> None:
        _integer("schema_version", self.schema_version, minimum=1)
        _integer("turn_count", self.turn_count)
        _nonempty("engine", self.engine)
        _nonempty("mode", self.mode)


@dataclass(frozen=True)
class CountryConfiguration(JsonModel):
    schema_version: int
    profiles: dict[str, CountryProfile]
    initial_states: dict[str, CountryState]

    def __post_init__(self) -> None:
        _integer("schema_version", self.schema_version, minimum=1)
        if not isinstance(self.profiles, Mapping) or not isinstance(self.initial_states, Mapping):
            raise ValueError("profiles and initial_states must be objects")
        if not self.profiles or set(self.profiles) != set(self.initial_states):
            raise ValueError("profile and initial-state country sets must be equal and non-empty")
        for code, profile in self.profiles.items():
            if not isinstance(profile, CountryProfile) or profile.code != code:
                raise ValueError("profile keys and codes must match")
            if not isinstance(self.initial_states[code], CountryState) or self.initial_states[code].code != code:
                raise ValueError("initial-state keys and codes must match")
        object.__setattr__(self, "profiles", _freeze(self.profiles))
        object.__setattr__(self, "initial_states", _freeze(self.initial_states))


@dataclass(frozen=True)
class ScenarioConfiguration(JsonModel):
    schema_version: int
    definition: EventDefinition
    event: EventInstance
    initial_world_state: WorldState

    def __post_init__(self) -> None:
        _integer("schema_version", self.schema_version, minimum=1)
        if not isinstance(self.definition, EventDefinition) or not isinstance(self.event, EventInstance):
            raise ValueError("definition and event must be event models")
        if self.event.definition != self.definition:
            raise ValueError("event definition must match scenario definition")
        if set(self.definition.participants) != set(self.initial_world_state.countries):
            raise ValueError("scenario and initial-world country sets must match")


def load_country_configuration(path: str | Path) -> CountryConfiguration:
    """Load schema v1 country data without ignoring missing or unknown fields."""
    data = _read_json_object(path)
    _exact_keys(data, {"schema_version", "countries"}, context="country configuration")
    _integer("schema_version", data["schema_version"], minimum=1)
    if data["schema_version"] != 1:
        raise ValueError("unsupported country configuration schema_version")
    countries = data["countries"]
    if not isinstance(countries, Mapping) or not countries:
        raise ValueError("countries must be a non-empty object")
    profiles: dict[str, CountryProfile] = {}
    states: dict[str, CountryState] = {}
    for code, raw in countries.items():
        _nonempty("country code", code)
        if not isinstance(raw, Mapping):
            raise ValueError(f"country {code} must be an object")
        _exact_keys(
            raw, {"role", "interests", "allowed_actions", "initial_indicators"},
            {"energy_portfolio"}, context=f"country {code}",
        )
        try:
            portfolio = EnergyPortfolio.from_dict(raw.get("energy_portfolio", {}))
            profile = CountryProfile(
                code=code, role=raw["role"], interests=raw["interests"],
                allowed_actions=raw["allowed_actions"],
                initial_indicators=raw["initial_indicators"], energy_portfolio=portfolio,
            )
        except TypeError as error:
            raise ValueError(f"invalid country {code}: {error}") from error
        sovereignty = profile.initial_indicators["sovereignty"]
        indicators = {name: value for name, value in profile.initial_indicators.items() if name != "sovereignty"}
        profiles[code] = profile
        states[code] = CountryState(code, sovereignty, indicators, portfolio)
    return CountryConfiguration(data["schema_version"], profiles, states)


def load_scenario_configuration(
    path: str | Path, countries: CountryConfiguration
) -> ScenarioConfiguration:
    """Load schema v1 scenario data and map scenario_id to EventDefinition.event_id."""
    if not isinstance(countries, CountryConfiguration):
        raise ValueError("countries must be a CountryConfiguration")
    data = _read_json_object(path)
    _exact_keys(
        data,
        {"schema_version", "scenario_id", "name", "origin", "participants", "event", "initial_world_state"},
        context="scenario configuration",
    )
    _integer("schema_version", data["schema_version"], minimum=1)
    if data["schema_version"] != 1:
        raise ValueError("unsupported scenario schema_version")
    _strings("participants", data["participants"], required=True)
    participants = tuple(data["participants"])
    if set(participants) != set(countries.profiles):
        raise ValueError("scenario participants must match configured countries")
    event_data = data["event"]
    if not isinstance(event_data, Mapping):
        raise ValueError("event must be an object")
    _exact_keys(
        event_data,
        {"actor_country", "target_country", "target_type", "lost_annual_rice_capacity_tons", "recovery_turns"},
        context="scenario event",
    )
    if event_data["actor_country"] not in participants or event_data["target_country"] not in participants:
        raise ValueError("event actor and target must be participants")
    _nonempty("target_type", event_data["target_type"])
    _number("lost_annual_rice_capacity_tons", event_data["lost_annual_rice_capacity_tons"])
    _integer("recovery_turns", event_data["recovery_turns"], minimum=1)
    definition = EventDefinition(
        data["scenario_id"], data["name"], data["origin"], participants, event_data
    )
    raw_world = data["initial_world_state"]
    required_world = {
        "food", "energy", "economy", "environment", "international_trust", "conflict_load",
        "national_sovereignty", "global_homeostasis",
    }
    if not isinstance(raw_world, Mapping):
        raise ValueError("initial_world_state must be an object")
    _exact_keys(raw_world, required_world, context="initial_world_state")
    for key in required_world:
        _score(f"initial_world_state[{key}]", raw_world[key])
    states = {
        code: CountryState(
            code, raw_world["national_sovereignty"], state.indicators,
            state.energy_portfolio, state.attributes,
        )
        for code, state in countries.initial_states.items()
    }
    indicators = {
        key: raw_world[key]
        for key in ("food", "energy", "economy", "environment", "international_trust", "conflict_load")
    }
    world = WorldState(0, indicators, states, global_homeostasis=raw_world["global_homeostasis"])
    event = EventInstance(definition, 0, True, event_data)
    return ScenarioConfiguration(data["schema_version"], definition, event, world)
