"""One-turn orchestration skeleton using injected, API-agnostic collaborators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .models import (
    CoordinatorProposal, CountryDecision, CountryProfile,
    EventInstance, PerceivedState, TurnRecord, WorldState,
)


Observer = Callable[[WorldState, CountryProfile, EventInstance | None], PerceivedState]
Coordinator = Callable[[WorldState, Mapping[str, PerceivedState]], CoordinatorProposal]
CountryAgent = Callable[[CountryProfile, PerceivedState, CoordinatorProposal], CountryDecision]
EffectProcessor = Callable[
    [WorldState, Mapping[str, CountryDecision], CoordinatorProposal, EventInstance | None],
    tuple[WorldState, Mapping[str, Any]],
]
Evaluator = Callable[[WorldState, WorldState, Mapping[str, CountryDecision], Mapping[str, Any]], Mapping[str, Any]]
Recorder = Callable[[TurnRecord], None]


@dataclass(frozen=True)
class TurnServices:
    observer: Observer
    coordinator: Coordinator
    country_agent: CountryAgent
    effect_processor: EffectProcessor
    evaluator: Evaluator
    recorder: Recorder | None = None


class TurnEngine:
    """Defines ordering only; all observation, policy, effects and evaluation are injected."""

    def __init__(self, profiles: Mapping[str, CountryProfile], services: TurnServices):
        self.profiles = dict(profiles)
        self.services = services
        if not self.profiles:
            raise ValueError("at least one country profile is required")
        if any(code != profile.code for code, profile in self.profiles.items()):
            raise ValueError("profile map keys must match CountryProfile.code")

    def process_turn(self, world: WorldState, event: EventInstance | None = None) -> TurnRecord:
        if set(world.countries) != set(self.profiles):
            raise ValueError("world and profile country sets must match")
        turn = world.turn + 1
        perceptions = {
            code: self.services.observer(world, profile, event)
            for code, profile in self.profiles.items()
        }
        for code, perceived in perceptions.items():
            if not isinstance(perceived, PerceivedState) or perceived.country_code != code or perceived.turn != turn:
                raise ValueError("observer must return the requested country and turn")
        proposal = self.services.coordinator(world, perceptions)
        if not isinstance(proposal, CoordinatorProposal):
            raise ValueError("coordinator must return a CoordinatorProposal")
        decisions = {
            code: self.services.country_agent(profile, perceptions[code], proposal)
            for code, profile in self.profiles.items()
        }
        for code, decision in decisions.items():
            if not isinstance(decision, CountryDecision) or decision.country_code != code:
                raise ValueError("country_agent must return a matching CountryDecision")
        world_after, action_results = self.services.effect_processor(world, decisions, proposal, event)
        if not isinstance(world_after, WorldState) or world_after.turn != turn:
            raise ValueError("effect_processor must advance WorldState by exactly one turn")
        if not isinstance(action_results, Mapping):
            raise ValueError("effect_processor results must be an object")
        evaluation = dict(self.services.evaluator(world, world_after, decisions, action_results))
        record = TurnRecord(
            turn=turn, world_before=world, perceptions=perceptions,
            coordinator_proposal=proposal, decisions=decisions,
            action_results=dict(action_results), world_after=world_after,
            evaluation=evaluation,
        )
        if self.services.recorder is not None:
            self.services.recorder(record)
        return record
