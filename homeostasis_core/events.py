"""Deterministic causal event generation and bounded closed-loop progression."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .metrics import clamp
from .models import JsonModel, _freeze, _integer, _nonempty, _score, _strings


@dataclass(frozen=True)
class CausalEvent(JsonModel):
    event_id: str
    event_type: str
    turn_created: int
    duration_turns: int
    remaining_damage: float
    recovery_per_turn: float
    cause_event_ids: tuple[str, ...] = ()
    affected_countries: tuple[str, ...] = ()
    effects: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self):
        _nonempty("event_id", self.event_id); _nonempty("event_type", self.event_type)
        _integer("turn_created", self.turn_created); _integer("duration_turns", self.duration_turns, minimum=1)
        _score("remaining_damage", self.remaining_damage); _score("recovery_per_turn", self.recovery_per_turn)
        _strings("cause_event_ids", self.cause_event_ids); _strings("affected_countries", self.affected_countries, required=True)
        if self.event_id in self.cause_event_ids: raise ValueError("event cannot cause itself")
        for key, value in self.effects.items(): _nonempty("effect", key); _score(f"effects[{key}]", value)
        object.__setattr__(self, "cause_event_ids", tuple(sorted(self.cause_event_ids)))
        object.__setattr__(self, "affected_countries", tuple(sorted(self.affected_countries)))
        object.__setattr__(self, "effects", _freeze(self.effects))


@dataclass(frozen=True)
class EventRule(JsonModel):
    rule_id: str
    source_type: str
    generated_type: str
    threshold_damage: float
    cooldown_turns: int
    max_occurrences: int
    effect_scale: float

    def __post_init__(self):
        for name in ("rule_id", "source_type", "generated_type"): _nonempty(name, getattr(self, name))
        _score("threshold_damage", self.threshold_damage); _integer("cooldown_turns", self.cooldown_turns)
        _integer("max_occurrences", self.max_occurrences, minimum=1); _score("effect_scale", self.effect_scale)
        if self.source_type == self.generated_type: raise ValueError("event rule cannot directly self-reference")


@dataclass(frozen=True)
class EventLedger(JsonModel):
    turn: int
    active_events: tuple[CausalEvent, ...] = ()
    history: tuple[CausalEvent, ...] = ()
    generated_keys: tuple[str, ...] = ()

    def __post_init__(self):
        _integer("turn", self.turn)
        events = self.active_events + self.history
        ids = [e.event_id for e in events]
        if any(not isinstance(e, CausalEvent) for e in events) or len(ids) != len(set(ids)): raise ValueError("event IDs must be unique")
        _strings("generated_keys", self.generated_keys)
        object.__setattr__(self, "active_events", tuple(sorted(self.active_events, key=lambda e:e.event_id)))
        object.__setattr__(self, "history", tuple(sorted(self.history, key=lambda e:(e.turn_created,e.event_id))))
        object.__setattr__(self, "generated_keys", tuple(sorted(self.generated_keys)))


def advance_events(ledger: EventLedger, rules: tuple[EventRule, ...], *, max_generated_per_turn: int = 3) -> EventLedger:
    """Recover active damage and generate a bounded next causal layer."""
    _integer("max_generated_per_turn", max_generated_per_turn, minimum=1)
    if len({r.rule_id for r in rules}) != len(rules): raise ValueError("rule IDs must be unique")
    next_turn = ledger.turn + 1
    recovered=[]; active=[]
    for event in ledger.active_events:
        remaining = clamp(event.remaining_damage - event.recovery_per_turn)
        updated = CausalEvent(event.event_id,event.event_type,event.turn_created,event.duration_turns,remaining,event.recovery_per_turn,event.cause_event_ids,event.affected_countries,event.effects)
        (active if remaining > 0 and next_turn-event.turn_created < event.duration_turns else recovered).append(updated)
    candidates=[]; keys=set(ledger.generated_keys)
    counts={r.rule_id:sum(k.startswith(r.rule_id+":") for k in keys) for r in rules}
    last={r.rule_id:max([int(k.rsplit(":",1)[1]) for k in keys if k.startswith(r.rule_id+":")], default=-10**9) for r in rules}
    for source in sorted(active, key=lambda e:e.event_id):
        for rule in sorted(rules, key=lambda r:r.rule_id):
            key=f"{rule.rule_id}:{source.event_id}:{next_turn}"
            if (source.event_type==rule.source_type and source.remaining_damage>=rule.threshold_damage
                and counts[rule.rule_id] < rule.max_occurrences and next_turn-last[rule.rule_id] > rule.cooldown_turns and key not in keys):
                candidates.append((key, source, rule))
    for key, source, rule in candidates[:max_generated_per_turn]:
        eid=f"auto-{rule.rule_id}-{next_turn}-{source.event_id}"
        damage=clamp(source.remaining_damage*rule.effect_scale/100)
        active.append(CausalEvent(eid,rule.generated_type,next_turn,2,damage,damage,(source.event_id,),source.affected_countries,{"magnitude":damage}))
        keys.add(key); counts[rule.rule_id]+=1; last[rule.rule_id]=next_turn
    return EventLedger(next_turn,tuple(active),ledger.history+tuple(recovered),tuple(keys))


def farmland_recovery_history(initial_damage: float = 8000, recovery_per_turn: float = 2000, turns: int = 5) -> tuple[float, ...]:
    """Scenario-unit recovery helper; unlike scores, physical tonnes are not clamped."""
    if isinstance(initial_damage,bool) or initial_damage < 0 or isinstance(recovery_per_turn,bool) or recovery_per_turn <= 0: raise ValueError("damage values must be positive numbers")
    _integer("turns", turns, minimum=1)
    return tuple(max(0, initial_damage-recovery_per_turn*i) for i in range(turns))
