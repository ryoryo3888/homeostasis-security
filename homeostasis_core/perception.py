"""Asymmetric observations, persistent memory and replaceable decisions."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence
from .metrics import clamp
from .models import CountryProfile, CountryState, JsonModel, WorldState, _freeze, _integer, _nonempty, _score, _strings

@dataclass(frozen=True)
class InformationPolicy(JsonModel):
    country_id: str
    delay_turns: int = 0
    freshness: float = 100
    observable_indicators: tuple[str,...] = ()
    perception_bias: Mapping[str,float] = field(default_factory=dict)
    def __post_init__(self):
        _nonempty("country_id",self.country_id); _integer("delay_turns",self.delay_turns); _score("freshness",self.freshness)
        _strings("observable_indicators",self.observable_indicators,required=True)
        for k,v in self.perception_bias.items(): _nonempty("bias",k); _score(f"bias[{k}]",v)
        object.__setattr__(self,"observable_indicators",tuple(sorted(self.observable_indicators))); object.__setattr__(self,"perception_bias",_freeze(self.perception_bias))

@dataclass(frozen=True)
class CountryMemory(JsonModel):
    country_id: str
    observed_turn: int
    observed_world: Mapping[str,float]
    perception_error: Mapping[str,float]
    freshness: float
    damage_history: tuple[str,...]=()
    decision_history: tuple[str,...]=()
    def __post_init__(self):
        _nonempty("country_id",self.country_id); _integer("observed_turn",self.observed_turn); _score("freshness",self.freshness)
        for values in (self.observed_world,self.perception_error):
            for k,v in values.items(): _nonempty("indicator",k); _score(f"value[{k}]",v)
        _strings("damage_history",self.damage_history); _strings("decision_history",self.decision_history)
        object.__setattr__(self,"observed_world",_freeze(self.observed_world)); object.__setattr__(self,"perception_error",_freeze(self.perception_error))

class DecisionProvider(Protocol):
    def decide(self, profile:CountryProfile, state:CountryState, memory:CountryMemory)->str: ...

@dataclass(frozen=True)
class DeterministicDecisionProvider:
    threshold: float = 50
    def __post_init__(self): _score("threshold",self.threshold)
    def decide(self, profile, state, memory):
        # Deliberately consumes only country state and its observation, never a true WorldState.
        observed=sum(memory.observed_world.values())/len(memory.observed_world)
        resilience=(state.indicators.get("domestic_stability",50)+state.indicators.get("recovery_capacity",50))/2
        return "cooperate" if (observed+resilience)/2 >= self.threshold else "protect"

def observe_world(history:Sequence[WorldState], policies:Mapping[str,InformationPolicy], previous:Mapping[str,CountryMemory]|None=None)->Mapping[str,CountryMemory]:
    if not history: raise ValueError("world history cannot be empty")
    current=history[-1]; previous=previous or {}
    if set(policies)!=set(current.countries): raise ValueError("information policies must match countries")
    result={}
    for code in sorted(policies):
        policy=policies[code]; index=max(0,len(history)-1-policy.delay_turns); source=history[index]
        visible={}; errors={}
        for key in policy.observable_indicators:
            if key not in source.indicators: raise ValueError(f"unknown observable indicator: {key}")
            bias=policy.perception_bias.get(key,50)-50
            visible[key]=clamp(source.indicators[key]+bias); errors[key]=abs(visible[key]-source.indicators[key])
        prior=previous.get(code)
        damage=tuple(sorted(set((prior.damage_history if prior else ())+tuple(d.damage_id for d in source.damages if d.target_country==code))))
        decisions=prior.decision_history if prior else ()
        result[code]=CountryMemory(code,source.turn,visible,errors,policy.freshness,damage,decisions)
    return _freeze(result)

def recover_country(state:CountryState, support:float=0)->CountryState:
    _score("support",support); indicators=dict(state.indicators)
    capacity=indicators.get("recovery_capacity",0)
    step=(capacity+support)/200
    for key in ("food_reserves","economy","domestic_stability","international_trust"):
        if key in indicators: indicators[key]=clamp(indicators[key]+step)
    return CountryState(state.code,state.sovereignty,indicators,state.energy_portfolio,state.attributes,state.resources)
