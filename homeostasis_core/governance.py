"""Versioned, voluntary governance-rule evolution."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping
from .models import JsonModel,_freeze,_integer,_nonempty,_score,_strings

CHANGE_TYPES=("international_law","voting_rule","emergency_authority","resource_sharing","international_agreement","veto_structure")
VOTES=("accept","reject","conditional")

@dataclass(frozen=True)
class GovernanceRuleSet(JsonModel):
    version:int; effective_turn:int; rules:Mapping[str,object]; applied_change_ids:tuple[str,...]=()
    def __post_init__(self):
        _integer("version",self.version,minimum=1); _integer("effective_turn",self.effective_turn); _strings("applied_change_ids",self.applied_change_ids)
        if not isinstance(self.rules,Mapping): raise ValueError("rules must be an object")
        threshold=self.rules.get("approval_threshold",50); _score("approval_threshold",threshold)
        object.__setattr__(self,"rules",_freeze(self.rules)); object.__setattr__(self,"applied_change_ids",tuple(sorted(self.applied_change_ids)))

@dataclass(frozen=True)
class RuleChangeProposal(JsonModel):
    change_id:str; change_type:str; reason:str; requested_countries:tuple[str,...]; changes:Mapping[str,object]; proposed_turn:int; duration_turns:int|None=None; expiry_condition:str|None=None; sovereignty_burden:float=0
    def __post_init__(self):
        _nonempty("change_id",self.change_id); _nonempty("reason",self.reason)
        if self.change_type not in CHANGE_TYPES: raise ValueError("unsupported rule change type")
        _strings("requested_countries",self.requested_countries,required=True); _integer("proposed_turn",self.proposed_turn)
        if not isinstance(self.changes,Mapping) or not self.changes: raise ValueError("changes cannot be empty")
        if self.change_type=="emergency_authority" and self.duration_turns is None: raise ValueError("emergency authority requires a duration")
        if self.duration_turns is not None: _integer("duration_turns",self.duration_turns,minimum=1)
        if self.expiry_condition is not None:_nonempty("expiry_condition",self.expiry_condition)
        _score("sovereignty_burden",self.sovereignty_burden)
        object.__setattr__(self,"requested_countries",tuple(sorted(self.requested_countries))); object.__setattr__(self,"changes",_freeze(self.changes))

@dataclass(frozen=True)
class GovernanceVote(JsonModel):
    country_id:str; change_id:str; vote:str; conditions_met:bool=True
    def __post_init__(self):
        _nonempty("country_id",self.country_id); _nonempty("change_id",self.change_id)
        if self.vote not in VOTES: raise ValueError("unsupported vote")
        if not isinstance(self.conditions_met,bool): raise ValueError("conditions_met must be boolean")

@dataclass(frozen=True)
class GovernanceChangeRecord(JsonModel):
    proposal:RuleChangeProposal; votes:Mapping[str,GovernanceVote]; status:str; basis_version:int; before:Mapping[str,object]; after:Mapping[str,object]
    def __post_init__(self):
        if self.status not in ("established","rejected"):raise ValueError("invalid change status")
        object.__setattr__(self,"votes",_freeze(self.votes)); object.__setattr__(self,"before",_freeze(self.before)); object.__setattr__(self,"after",_freeze(self.after))

def decide_rule_change(current:GovernanceRuleSet,proposal:RuleChangeProposal,votes:Mapping[str,GovernanceVote],current_turn:int)->tuple[GovernanceRuleSet,GovernanceChangeRecord]:
    _integer("current_turn",current_turn)
    if proposal.change_id in current.applied_change_ids: raise ValueError("rule change already applied")
    requested=set(proposal.requested_countries)
    if set(votes)!=requested: raise ValueError("votes must cover requested countries exactly")
    for code,vote in votes.items():
        if vote.country_id!=code or vote.change_id!=proposal.change_id:raise ValueError("vote identity mismatch")
    accepting=sum(v.vote=="accept" or (v.vote=="conditional" and v.conditions_met) for v in votes.values())
    threshold=float(current.rules.get("approval_threshold",50))
    established=100*accepting/len(requested)>=threshold
    before=dict(current.rules); after=dict(before)
    if established: after.update(proposal.changes)
    updated=GovernanceRuleSet(current.version+1,current_turn+1,after,current.applied_change_ids+(proposal.change_id,)) if established else current
    record=GovernanceChangeRecord(proposal,votes,"established" if established else "rejected",current.version,before,after)
    return updated,record

def expire_emergency_rules(ruleset:GovernanceRuleSet,proposal:RuleChangeProposal,current_turn:int,condition_met:bool=False)->GovernanceRuleSet:
    if proposal.change_type!="emergency_authority":return ruleset
    expired=current_turn>=proposal.proposed_turn+(proposal.duration_turns or 0) or condition_met
    if not expired:return ruleset
    rules={k:v for k,v in ruleset.rules.items() if k not in proposal.changes}
    return GovernanceRuleSet(ruleset.version+1,current_turn,rules,ruleset.applied_change_ids)

def governance_sovereignty_maintenance(proposal:RuleChangeProposal,established:bool)->float:
    return 100-proposal.sovereignty_burden if established else 100
