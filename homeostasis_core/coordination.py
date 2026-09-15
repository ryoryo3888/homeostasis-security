"""Deterministic, non-coercive proposal coordination for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping, Protocol

from .metrics import clamp, global_homeostasis, sovereignty_summary
from .models import (
    CountryProfile, CountryState, JsonModel, WorldState,
    _freeze, _integer, _nonempty, _score, _strings,
)
from .resources import ResourceNetwork, SupplyLink, TransferRecord, process_resource_network


PROPOSAL_TYPES = (
    "食料援助",
    "仲裁",
    "制裁提案",
    "資源再配分",
    "緊急協定",
    "停戦提案",
    "復興支援",
)
RESPONSE_TYPES = ("受け入れる", "拒否する", "条件付きで応じる")
OUTCOME_TYPES = ("成立", "部分成立", "不成立")


@dataclass(frozen=True)
class ProposedResourceTransfer(JsonModel):
    source: str
    target: str
    resource: str
    amount: float

    def __post_init__(self) -> None:
        for name in ("source", "target", "resource"):
            _nonempty(name, getattr(self, name))
        if self.source == self.target:
            raise ValueError("resource transfer source and target must differ")
        _score("amount", self.amount)


@dataclass(frozen=True)
class ResponseConditions(JsonModel):
    required_countries: tuple[str, ...] = ()
    minimum_aid_amount: float | None = None
    maximum_sovereignty_burden: float | None = None
    mutual_performance: bool = False
    deadline_turn: int | None = None

    def __post_init__(self) -> None:
        _strings("required_countries", self.required_countries)
        if self.minimum_aid_amount is not None:
            _score("minimum_aid_amount", self.minimum_aid_amount)
        if self.maximum_sovereignty_burden is not None:
            _score("maximum_sovereignty_burden", self.maximum_sovereignty_burden)
        if not isinstance(self.mutual_performance, bool):
            raise ValueError("mutual_performance must be boolean")
        if self.deadline_turn is not None:
            _integer("deadline_turn", self.deadline_turn)
        object.__setattr__(self, "required_countries", tuple(sorted(self.required_countries)))


@dataclass(frozen=True)
class GlobalProposal(JsonModel):
    proposal_id: str
    proposal_type: str
    reason: str
    target_countries: tuple[str, ...]
    requested_participants: tuple[str, ...]
    resource_transfers: tuple[ProposedResourceTransfer, ...]
    requested_actions: Mapping[str, str]
    predicted_global_effect: float
    predicted_sovereignty_burden: Mapping[str, float]
    valid_turns: int
    issued_turn: int = 0

    def __post_init__(self) -> None:
        _nonempty("proposal_id", self.proposal_id)
        if self.proposal_type not in PROPOSAL_TYPES:
            raise ValueError(f"unsupported proposal_type: {self.proposal_type}")
        _nonempty("reason", self.reason)
        _strings("target_countries", self.target_countries, required=True)
        _strings("requested_participants", self.requested_participants, required=True)
        participants = set(self.requested_participants)
        if any(not isinstance(item, ProposedResourceTransfer) for item in self.resource_transfers):
            raise ValueError("resource_transfers must contain ProposedResourceTransfer objects")
        endpoints = {code for item in self.resource_transfers for code in (item.source, item.target)}
        if not endpoints <= participants:
            raise ValueError("resource transfer countries must be requested participants")
        route_keys = [(item.source, item.target, item.resource) for item in self.resource_transfers]
        if len(set(route_keys)) != len(route_keys):
            raise ValueError("proposal resource routes must be unique")
        if not isinstance(self.requested_actions, Mapping):
            raise ValueError("requested_actions must be an object")
        if set(self.requested_actions) != participants:
            raise ValueError("requested_actions must cover every requested participant")
        for country, action in self.requested_actions.items():
            _nonempty(f"requested_actions[{country}]", action)
        _score("predicted_global_effect", self.predicted_global_effect)
        if not isinstance(self.predicted_sovereignty_burden, Mapping):
            raise ValueError("predicted_sovereignty_burden must be an object")
        if set(self.predicted_sovereignty_burden) != participants:
            raise ValueError("sovereignty burdens must cover every requested participant")
        for country, burden in self.predicted_sovereignty_burden.items():
            _score(f"predicted_sovereignty_burden[{country}]", burden)
        _integer("valid_turns", self.valid_turns, minimum=1)
        _integer("issued_turn", self.issued_turn)
        object.__setattr__(self, "target_countries", tuple(sorted(self.target_countries)))
        object.__setattr__(self, "requested_participants", tuple(sorted(self.requested_participants)))
        object.__setattr__(self, "resource_transfers", tuple(sorted(
            self.resource_transfers, key=lambda item: (item.source, item.target, item.resource)
        )))
        object.__setattr__(self, "requested_actions", _freeze(self.requested_actions))
        object.__setattr__(self, "predicted_sovereignty_burden", _freeze(self.predicted_sovereignty_burden))


@dataclass(frozen=True)
class CountryResponse(JsonModel):
    country_id: str
    proposal_id: str
    response: str
    reason: str
    conditions: ResponseConditions | None
    self_interest_score: float
    sovereignty_burden_score: float
    perceived_global_effect: float

    def __post_init__(self) -> None:
        _nonempty("country_id", self.country_id)
        _nonempty("proposal_id", self.proposal_id)
        if self.response not in RESPONSE_TYPES:
            raise ValueError(f"unsupported response: {self.response}")
        _nonempty("reason", self.reason)
        if self.response == "条件付きで応じる" and not isinstance(self.conditions, ResponseConditions):
            raise ValueError("conditional response requires structured conditions")
        if self.response != "条件付きで応じる" and self.conditions is not None:
            raise ValueError("only conditional responses may contain conditions")
        for name in ("self_interest_score", "sovereignty_burden_score", "perceived_global_effect"):
            _score(name, getattr(self, name))


class CountryResponsePolicy(Protocol):
    def decide(
        self, profile: CountryProfile, state: CountryState,
        proposal: GlobalProposal, current_turn: int,
    ) -> CountryResponse: ...


@dataclass(frozen=True)
class ConfiguredProposalCoordinator:
    """Non-coercive coordinator that only selects validated configured proposals."""

    proposals: Mapping[str, GlobalProposal]

    def __post_init__(self) -> None:
        if not isinstance(self.proposals, Mapping) or not self.proposals:
            raise ValueError("proposals must be a non-empty object")
        for proposal_id, proposal in self.proposals.items():
            if not isinstance(proposal, GlobalProposal) or proposal.proposal_id != proposal_id:
                raise ValueError("proposal keys and IDs must match")
        object.__setattr__(self, "proposals", _freeze(self.proposals))

    def propose(self, proposal_id: str, world: WorldState) -> GlobalProposal:
        if proposal_id not in self.proposals:
            raise ValueError(f"unknown proposal_id: {proposal_id}")
        proposal = self.proposals[proposal_id]
        if not set(proposal.requested_participants) <= set(world.countries):
            raise ValueError("proposal references countries outside the world")
        return proposal


def build_proposal_catalog(proposals: Iterable[GlobalProposal]) -> Mapping[str, GlobalProposal]:
    """Validate proposal IDs before converting a sequence to an immutable mapping."""
    items = tuple(proposals)
    if not items or any(not isinstance(item, GlobalProposal) for item in items):
        raise ValueError("proposals must contain GlobalProposal objects")
    ids = [item.proposal_id for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("proposal_id values must be unique")
    return _freeze({item.proposal_id: item for item in items})


def build_response_map(
    responses: Iterable[CountryResponse], proposal: GlobalProposal,
) -> Mapping[str, CountryResponse]:
    """Validate duplicate submissions and proposal IDs before mapping by country."""
    items = tuple(responses)
    if any(not isinstance(item, CountryResponse) for item in items):
        raise ValueError("responses must contain CountryResponse objects")
    country_ids = [item.country_id for item in items]
    if len(set(country_ids)) != len(country_ids):
        raise ValueError("each country may answer a proposal only once")
    if any(item.proposal_id != proposal.proposal_id for item in items):
        raise ValueError("response proposal_id does not match proposal")
    if set(country_ids) != set(proposal.requested_participants):
        raise ValueError("responses must cover every requested participant exactly once")
    return _freeze({item.country_id: item for item in items})


@dataclass(frozen=True)
class DeterministicResponsePolicy:
    """One replaceable policy shared by every country; it contains no country-specific rules."""

    accept_threshold: float = 58
    conditional_threshold: float = 38

    def __post_init__(self) -> None:
        _score("accept_threshold", self.accept_threshold)
        _score("conditional_threshold", self.conditional_threshold)
        if self.conditional_threshold > self.accept_threshold:
            raise ValueError("conditional_threshold cannot exceed accept_threshold")

    def decide(
        self, profile: CountryProfile, state: CountryState,
        proposal: GlobalProposal, current_turn: int,
    ) -> CountryResponse:
        if profile.code != state.code or state.code not in proposal.requested_participants:
            raise ValueError("profile, state and proposal country IDs must match")
        _integer("current_turn", current_turn)
        burden = proposal.predicted_sovereignty_burden[state.code]
        diplomacy = state.indicators.get("diplomatic_posture", 50)
        stability = state.indicators.get("domestic_stability", 50)
        targeted_bonus = 15 if state.code in proposal.target_countries else 0
        self_interest = clamp(0.35 * stability + 0.35 * diplomacy + targeted_bonus)
        perceived = clamp(0.65 * proposal.predicted_global_effect + 0.35 * diplomacy)
        decision_score = clamp(0.45 * self_interest + 0.40 * perceived + 0.15 * (100 - burden))
        if decision_score >= self.accept_threshold:
            response = "受け入れる"
            conditions = None
        elif decision_score >= self.conditional_threshold:
            response = "条件付きで応じる"
            conditions = ResponseConditions(
                required_countries=proposal.target_countries,
                minimum_aid_amount=0,
                maximum_sovereignty_burden=clamp(0.6 * state.sovereignty + 0.4 * diplomacy),
                mutual_performance=True,
                deadline_turn=current_turn + proposal.valid_turns - 1,
            )
        else:
            response = "拒否する"
            conditions = None
        return CountryResponse(
            country_id=state.code,
            proposal_id=proposal.proposal_id,
            response=response,
            reason=f"common deterministic policy score={decision_score:.2f}",
            conditions=conditions,
            self_interest_score=self_interest,
            sovereignty_burden_score=burden,
            perceived_global_effect=perceived,
        )


@dataclass(frozen=True)
class ProposalExecutionResult(JsonModel):
    proposal_id: str
    status: str
    participating_countries: tuple[str, ...]
    rejected_countries: tuple[str, ...]
    condition_unmet_countries: tuple[str, ...]
    actual_transfers: tuple[TransferRecord, ...]
    world_before: WorldState
    world_after: WorldState
    country_state_changes: Mapping[str, Mapping[str, object]]
    world_state_changes: Mapping[str, float]
    sovereignty_burden: Mapping[str, float]
    global_homeostasis_effect: float
    logs: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty("proposal_id", self.proposal_id)
        if self.status not in OUTCOME_TYPES:
            raise ValueError(f"unsupported outcome status: {self.status}")
        for name in ("participating_countries", "rejected_countries", "condition_unmet_countries", "logs"):
            _strings(name, getattr(self, name))
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if any(not isinstance(item, TransferRecord) for item in self.actual_transfers):
            raise ValueError("actual_transfers must contain TransferRecord objects")
        _score("global_homeostasis_effect", self.global_homeostasis_effect)
        for burden in self.sovereignty_burden.values():
            _score("sovereignty_burden", burden)
        object.__setattr__(self, "actual_transfers", tuple(self.actual_transfers))
        for name in ("country_state_changes", "world_state_changes", "sovereignty_burden"):
            object.__setattr__(self, name, _freeze(getattr(self, name)))


def _conditions_met(
    country: str, response: CountryResponse, proposal: GlobalProposal,
    consenting: set[str], deliverable_aid: Mapping[str, float],
    performed_countries: set[str], current_turn: int,
) -> bool:
    conditions = response.conditions
    if conditions is None:
        return True
    aid = deliverable_aid.get(country, 0)
    counterparts = {
        code for transfer in proposal.resource_transfers
        if country in (transfer.source, transfer.target)
        for code in (transfer.source, transfer.target)
        if code != country
    }
    checks = (
        set(conditions.required_countries) <= consenting,
        conditions.minimum_aid_amount is None or aid >= conditions.minimum_aid_amount,
        conditions.maximum_sovereignty_burden is None
        or proposal.predicted_sovereignty_burden[country] <= conditions.maximum_sovereignty_burden,
        not conditions.mutual_performance
        or (set(conditions.required_countries) | counterparts) <= performed_countries,
        conditions.deadline_turn is None or current_turn <= conditions.deadline_turn,
    )
    return all(checks)


def _execute_resource_portion(
    world: WorldState, proposal: GlobalProposal, participants: set[str]
) -> tuple[dict[str, CountryState], tuple[TransferRecord, ...]]:
    eligible = tuple(
        transfer for transfer in proposal.resource_transfers
        if transfer.source in participants and transfer.target in participants
    )
    if not eligible:
        return dict(world.countries), ()
    links = tuple(
        SupplyLink(
            f"{proposal.proposal_id}:{transfer.source}:{transfer.target}:{transfer.resource}",
            transfer.source, transfer.target, transfer.resource, transfer.amount, 100, 100, True,
        )
        for transfer in eligible
    )
    resource_types = tuple(sorted({
        resource for state in world.countries.values() for resource in state.resources.levels
    }))
    result = process_resource_network(
        world.countries, ResourceNetwork(1, links, {}, resource_types)
    )
    return dict(result.countries), result.transfers


def execute_proposal(
    world: WorldState, proposal: GlobalProposal,
    responses: Mapping[str, CountryResponse], current_turn: int,
) -> ProposalExecutionResult:
    """Apply only voluntary, condition-satisfying portions of a proposal."""
    _integer("current_turn", current_turn)
    if proposal.proposal_id in world.executed_proposal_ids:
        raise ValueError(f"proposal already executed: {proposal.proposal_id}")
    requested = set(proposal.requested_participants)
    referenced = requested | set(proposal.target_countries)
    if not referenced <= set(world.countries):
        raise ValueError("proposal references unknown countries")
    if set(responses) != requested:
        raise ValueError("responses must cover every requested participant exactly once")
    for code, response in responses.items():
        if not isinstance(response, CountryResponse) or response.country_id != code:
            raise ValueError("response keys and country IDs must match")
        if response.proposal_id != proposal.proposal_id:
            raise ValueError("response proposal_id does not match proposal")
        if response.conditions is not None:
            unknown_required = set(response.conditions.required_countries) - requested
            if unknown_required:
                raise ValueError(f"conditions reference unknown countries: {sorted(unknown_required)}")
    ordered_responses = {code: responses[code] for code in sorted(responses)}
    rejected = {code for code, response in ordered_responses.items() if response.response == "拒否する"}
    expired = current_turn > proposal.issued_turn + proposal.valid_turns
    unconditional = {
        code for code, response in ordered_responses.items()
        if response.response == "受け入れる"
    }
    conditional = {
        code for code, response in ordered_responses.items()
        if response.response == "条件付きで応じる"
    }
    consenting = unconditional | conditional
    participants = set() if expired else set(unconditional)
    if not expired:
        while True:
            additions: set[str] = set()
            for code in sorted(conditional - participants):
                candidate = participants | {code}
                _, preview_transfers = _execute_resource_portion(world, proposal, candidate)
                deliverable_aid: dict[str, float] = {}
                performed = {
                    participant for participant in candidate
                    if not any(item.source == participant for item in proposal.resource_transfers)
                }
                for transfer in preview_transfers:
                    deliverable_aid[transfer.target] = deliverable_aid.get(transfer.target, 0) + transfer.delivered
                    if transfer.delivered > 0:
                        performed.add(transfer.source)
                if _conditions_met(
                    code, ordered_responses[code], proposal, candidate,
                    deliverable_aid, performed, current_turn,
                ):
                    additions.add(code)
            if not additions:
                break
            participants |= additions
    unmet = consenting - participants
    status = (
        "成立" if participants == requested
        else "部分成立" if participants
        else "不成立"
    )
    countries_after_resources, actual_transfers = _execute_resource_portion(
        world, proposal, participants
    )

    countries_after: dict[str, CountryState] = {}
    burdens: dict[str, float] = {}
    for code in sorted(world.countries):
        state = countries_after_resources[code]
        burden = proposal.predicted_sovereignty_burden.get(code, 0) if code in participants else 0
        burdens[code] = burden
        sovereignty = clamp(state.sovereignty - 0.10 * burden)
        countries_after[code] = CountryState(
            state.code, sovereignty, state.indicators, state.energy_portfolio,
            state.attributes, state.resources,
        )

    participation_ratio = len(participants) / len(requested)
    potential = (proposal.predicted_global_effect - 50) * 0.10
    if not participants:
        realized_delta = -abs(potential) if potential >= 0 else 0
    elif proposal.resource_transfers:
        requested_amount = math.fsum(item.amount for item in proposal.resource_transfers)
        delivered_amount = math.fsum(item.delivered for item in actual_transfers)
        realization_ratio = min(1.0, delivered_amount / requested_amount) if requested_amount else 0
        realized_delta = potential * realization_ratio
    else:
        realized_delta = potential * participation_ratio
    indicators = dict(world.indicators)
    for name in ("food", "energy", "economy", "environment", "international_trust"):
        if name in indicators:
            indicators[name] = clamp(indicators[name] + realized_delta)
    if "conflict_load" in indicators:
        indicators["conflict_load"] = clamp(indicators["conflict_load"] - realized_delta)
    homeostasis = global_homeostasis(indicators)
    world_after = WorldState(
        turn=world.turn + 1, indicators=indicators, countries=countries_after,
        damages=world.damages, global_homeostasis=homeostasis,
        executed_proposal_ids=world.executed_proposal_ids + (proposal.proposal_id,),
    )
    country_changes = {
        code: {
            "sovereignty_before": world.countries[code].sovereignty,
            "sovereignty_after": world_after.countries[code].sovereignty,
            "resources_before": world.countries[code].resources.to_dict()["levels"],
            "resources_after": world_after.countries[code].resources.to_dict()["levels"],
        }
        for code in sorted(world.countries)
    }
    world_changes = {
        name: world_after.indicators[name] - value for name, value in world.indicators.items()
    }
    before_homeostasis = world.global_homeostasis
    if before_homeostasis is None:
        before_homeostasis = global_homeostasis(world.indicators)
    effect_score = clamp(50 + 5 * (homeostasis - before_homeostasis))
    logs = (
        f"proposal={proposal.proposal_id}",
        f"status={status}",
        f"participants={','.join(sorted(participants))}",
        f"rejected={','.join(sorted(rejected))}",
        f"conditions_unmet={','.join(sorted(unmet))}",
        f"expired={str(expired).lower()}",
        f"transferred={math.fsum(item.delivered for item in actual_transfers):.6f}",
    ) + tuple(
        f"action={code}:{proposal.requested_actions[code]}" for code in sorted(participants)
    )
    return ProposalExecutionResult(
        proposal.proposal_id, status, tuple(sorted(participants)), tuple(sorted(rejected)),
        tuple(sorted(unmet)), actual_transfers, world, world_after, country_changes,
        world_changes, burdens, effect_score, logs,
    )


@dataclass(frozen=True)
class GovernanceEvaluation(JsonModel):
    national_sovereignty_maintenance: float
    global_homeostasis: float
    sovereignty_burden: float
    overall_improvement_effect: float
    sovereignty_homeostasis_conflict: float

    def __post_init__(self) -> None:
        for name in (
            "national_sovereignty_maintenance", "global_homeostasis", "sovereignty_burden",
            "overall_improvement_effect", "sovereignty_homeostasis_conflict",
        ):
            _score(name, getattr(self, name))


class GovernanceEvaluator(Protocol):
    def evaluate(self, result: ProposalExecutionResult) -> GovernanceEvaluation: ...


@dataclass(frozen=True)
class IndependentGovernanceEvaluator:
    """Evaluator with no coordinator or proposal-generation dependency."""

    def evaluate(self, result: ProposalExecutionResult) -> GovernanceEvaluation:
        before_sovereignty = sovereignty_summary(result.world_before.countries)["average"]
        after_sovereignty = sovereignty_summary(result.world_after.countries)["average"]
        before_homeostasis = result.world_before.global_homeostasis
        if before_homeostasis is None:
            before_homeostasis = global_homeostasis(result.world_before.indicators)
        after_homeostasis = result.world_after.global_homeostasis
        sovereignty_delta = after_sovereignty - before_sovereignty
        homeostasis_delta = after_homeostasis - before_homeostasis
        burden = sum(result.sovereignty_burden.values()) / len(result.sovereignty_burden)
        improvement = clamp(50 + 5 * homeostasis_delta)
        conflict = clamp(
            4 * abs(homeostasis_delta - sovereignty_delta)
            + 3 * max(0, -homeostasis_delta)
            + 3 * max(0, -sovereignty_delta)
        )
        return GovernanceEvaluation(
            after_sovereignty, after_homeostasis, burden, improvement, conflict
        )


@dataclass(frozen=True)
class CoordinationTurnResult(JsonModel):
    proposal: GlobalProposal
    responses: Mapping[str, CountryResponse]
    execution: ProposalExecutionResult
    evaluation: GovernanceEvaluation

    def __post_init__(self) -> None:
        object.__setattr__(self, "responses", _freeze(self.responses))


@dataclass(frozen=True)
class CoordinationPipeline:
    response_policy: CountryResponsePolicy
    evaluator: GovernanceEvaluator

    def process_turn(
        self, world: WorldState, profiles: Mapping[str, CountryProfile],
        proposal: GlobalProposal,
    ) -> CoordinationTurnResult:
        if set(profiles) != set(world.countries):
            raise ValueError("profile and world country sets must match")
        responses = {
            code: self.response_policy.decide(
                profiles[code], world.countries[code], proposal, world.turn + 1
            )
            for code in sorted(proposal.requested_participants)
        }
        execution = execute_proposal(world, proposal, responses, world.turn + 1)
        evaluation = self.evaluator.evaluate(execution)
        return CoordinationTurnResult(proposal, responses, execution, evaluation)

    def process_configured_turn(
        self, world: WorldState, profiles: Mapping[str, CountryProfile],
        coordinator: ConfiguredProposalCoordinator, proposal_id: str,
    ) -> CoordinationTurnResult:
        """Optional full sequence: observe world, select proposal, respond, execute, evaluate."""
        proposal = coordinator.propose(proposal_id, world)
        return self.process_turn(world, profiles, proposal)
