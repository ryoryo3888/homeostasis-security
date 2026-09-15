"""Read-only compatibility adapter for the existing v2 first-run artifact."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .models import (
    CoordinatorProposal, CountryDecision, CountryState, DamageRecord,
    ExperimentMetadata, PerceivedState, TurnRecord, WorldState,
)


WORLD_KEYS = ("food", "energy", "economy", "environment", "international_trust", "conflict_load")
LEGACY_COUNTRIES = ("A", "B", "C")
LEGACY_DAMAGE_BEFORE = (8000, 6000, 4000, 2000, 0)
LEGACY_RECOVERED = (2000, 2000, 2000, 2000, 0)
LEGACY_DAMAGE_AFTER = (6000, 4000, 2000, 0, 0)
LEGACY_SOVEREIGNTY = (88, 87, 86, 86, 86)
LEGACY_HOMEOSTASIS = (70, 73, 76, 80, 82)


@dataclass(frozen=True)
class V2CompatibilityResult:
    metadata: ExperimentMetadata
    initial_world_state: WorldState
    turns: tuple[TurnRecord, ...]
    final_result: dict[str, Any]
    source_event: dict[str, Any]


def _countries(codes: tuple[str, ...], sovereignty: float) -> dict[str, CountryState]:
    return {code: CountryState(code=code, sovereignty=sovereignty) for code in codes}


def _world(raw: Mapping[str, Any], turn: int, codes: tuple[str, ...], damage: DamageRecord | None) -> WorldState:
    return WorldState(
        turn=turn,
        indicators={key: raw[key] for key in WORLD_KEYS},
        countries=_countries(codes, raw["national_sovereignty"]),
        damages=(damage,) if damage else (),
        global_homeostasis=raw["global_homeostasis"],
    )


def convert_v2_data(data: Mapping[str, Any]) -> V2CompatibilityResult:
    """Convert parsed legacy JSON without mutating the supplied mapping."""
    turns_raw = data.get("turns")
    if not isinstance(turns_raw, list) or not turns_raw:
        raise ValueError("v2 data must contain a non-empty turns list")
    codes = tuple(turns_raw[0]["countries"].keys())
    if any(tuple(row["countries"].keys()) != codes for row in turns_raw):
        raise ValueError("country set or order changes between v2 turns")
    source = dict(data["source_event"])
    initial_amount = source["lost_annual_rice_capacity_tons"]

    def damage(remaining: float) -> DamageRecord:
        return DamageRecord(
            damage_id="scenario-01-farmland-capacity", target_country="B",
            category="food_production_capacity", initial_amount=initial_amount,
            remaining_amount=remaining, unit="tons_per_year",
            recovery_turns=source["recovery_turns"], details={"legacy_source": source["event"]},
        )

    initial_raw = dict(data["initial_world_state"])
    initial = _world(initial_raw, 0, codes, damage(initial_amount))
    records: list[TurnRecord] = []
    before = initial
    for row in turns_raw:
        number = row["turn"]
        effects = dict(row["persistent_effects"])
        remaining = effects["remaining_lost_capacity_tons"]
        after = _world(row["world_state"], number, codes, damage(remaining) if remaining else None)
        perceptions = {
            code: PerceivedState(
                country_code=code, turn=number,
                public_indicators=dict(before.indicators),
                narrative=country["observation"], visible_damage=before.damages,
            )
            for code, country in row["countries"].items()
        }
        decisions = {
            code: CountryDecision(
                country_code=code, action=country["action"],
                proposal_response=country["proposal_response"], reason=country["reason"],
            )
            for code, country in row["countries"].items()
        }
        proposal = CoordinatorProposal(**row["coordinator_proposal"])
        records.append(TurnRecord(
            turn=number, world_before=before, perceptions=perceptions,
            coordinator_proposal=proposal, decisions=decisions,
            action_results={"persistent_effects": effects, "action_log": list(row["action_log"])},
            world_after=after, evaluation=dict(row["evaluator"]),
        ))
        before = after
    raw_meta = data["metadata"]
    metadata = ExperimentMetadata(
        schema_version=raw_meta["schema_version"], engine=raw_meta["engine"],
        mode=raw_meta["mode"], model=raw_meta.get("model"),
        turn_count=raw_meta["turn_count"], generated_at_utc=raw_meta.get("generated_at_utc"),
        research_question=data.get("research_question"), source_format="v2_first_run.json",
    )
    result = V2CompatibilityResult(metadata, initial, tuple(records), dict(data["final_result"]), source)
    validate_v2_compatibility(result)
    return result


def load_v2_first_run(path: str | Path = "v2_first_run.json") -> V2CompatibilityResult:
    with Path(path).open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    return convert_v2_data(data)


def validate_v2_compatibility(result: V2CompatibilityResult) -> None:
    if result.metadata.turn_count != 5 or len(result.turns) != 5:
        raise ValueError("legacy v2 compatibility requires five turns")
    if tuple(result.initial_world_state.countries) != LEGACY_COUNTRIES:
        raise ValueError("legacy v2 country set was not preserved")
    effects = [record.action_results["persistent_effects"] for record in result.turns]
    before_damage = tuple(item["lost_capacity_before_actions_tons"] for item in effects)
    recovered = tuple(item["recovered_this_turn_tons"] for item in effects)
    after_damage = tuple(item["remaining_lost_capacity_tons"] for item in effects)
    sovereignties = tuple(record.world_after.countries["A"].sovereignty for record in result.turns)
    homeostasis = tuple(record.world_after.global_homeostasis for record in result.turns)
    if before_damage != LEGACY_DAMAGE_BEFORE or recovered != LEGACY_RECOVERED or after_damage != LEGACY_DAMAGE_AFTER:
        raise ValueError("legacy damage sequence was not preserved")
    if sovereignties != LEGACY_SOVEREIGNTY:
        raise ValueError("legacy sovereignty sequence was not preserved")
    if homeostasis != LEGACY_HOMEOSTASIS or result.initial_world_state.global_homeostasis != 68:
        raise ValueError("legacy global homeostasis sequence was not preserved")
    expected_final = {
        "outcome": "recovered", "global_homeostasis_change": 14,
        "remaining_lost_capacity_tons": 0, "national_sovereignty": 86,
        "global_homeostasis": 82,
    }
    if result.final_result != expected_final:
        raise ValueError("legacy final outcome was not preserved")
