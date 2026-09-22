"""Pre-run contract for the V5 NORMAL vs NO-DIPLOMACY paired experiment.

This module contains no provider calls. It defines the minimum machinery needed
before running the 20-run experiment: fixed event schedule, condition-specific
schemas, public crisis bulletins, and mechanical validation that the A/B
conditions differ only by autonomous cross-border diplomacy.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import hashlib
import json

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # local preflight fallback; provider runner environments may have jsonschema
    class Draft202012Validator:  # minimal required/additional/type validator for this contract
        def __init__(self, schema):
            self.schema = schema
        def iter_errors(self, instance):
            yield from self._errors(self.schema, instance, '$')
        def _errors(self, schema, value, path):
            typ = schema.get('type')
            if isinstance(typ, list):
                if not any(self._type_ok(t, value) for t in typ):
                    yield f'{path}: type'
                    return
            elif typ and not self._type_ok(typ, value):
                yield f'{path}: type'
                return
            if 'enum' in schema and value not in schema['enum']:
                yield f'{path}: enum'
            if typ == 'object':
                props = schema.get('properties', {})
                for key in schema.get('required', []):
                    if key not in value:
                        yield f'{path}.{key}: required'
                if schema.get('additionalProperties') is False:
                    for key in value:
                        if key not in props:
                            yield f'{path}.{key}: additional'
                for key, subschema in props.items():
                    if key in value:
                        yield from self._errors(subschema, value[key], f'{path}.{key}')
            if typ == 'array':
                if 'maxItems' in schema and len(value) > schema['maxItems']:
                    yield f'{path}: maxItems'
                if schema.get('uniqueItems') and len(value) != len(set(value)):
                    yield f'{path}: uniqueItems'
                for i, item in enumerate(value):
                    yield from self._errors(schema.get('items', {}), item, f'{path}[{i}]')
            if typ == 'string':
                if 'minLength' in schema and len(value) < schema['minLength']:
                    yield f'{path}: minLength'
                if 'maxLength' in schema and len(value) > schema['maxLength']:
                    yield f'{path}: maxLength'
            if typ == 'integer':
                if 'minimum' in schema and value < schema['minimum']:
                    yield f'{path}: minimum'
                if 'maximum' in schema and value > schema['maximum']:
                    yield f'{path}: maximum'
        def _type_ok(self, typ, value):
            return ((typ == 'object' and isinstance(value, dict)) or
                    (typ == 'array' and isinstance(value, list)) or
                    (typ == 'string' and isinstance(value, str)) or
                    (typ == 'integer' and isinstance(value, int) and not isinstance(value, bool)) or
                    (typ == 'boolean' and isinstance(value, bool)) or
                    (typ == 'null' and value is None))



def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class ContractError(ValueError):
    pass

def ensure(condition: bool, code: str):
    if not condition:
        raise ContractError(code)

VERSION = "v5-paired-diplomacy-experiment-contract-1"
DOCUMENT_TYPE = "v5-paired-leader-turn-decision-1"
TURN_MIN = 1
TURN_MAX = 29
NORMAL = "NORMAL"
NO_DIPLOMACY = "NO-DIPLOMACY"
CONDITIONS = (NORMAL, NO_DIPLOMACY)
COMMUNICATION_BUDGET_CHARS = 2000

NORMAL_ACTION_TYPES = (
    "message_only", "information_request", "information_share", "resource_offer",
    "resource_request", "joint_statement", "multilateral_meeting_proposal",
    "other_diplomatic_proposal", "security_assessment", "protective_patrol",
    "route_protection", "border_or_facility_security_reinforcement",
    "sanctions_proposal", "blockade_or_access_restriction_proposal",
    "deterrent_warning", "military_preparedness", "armed_conflict_risk_action",
)

NO_DIPLOMACY_ACTION_TYPES = (
    "domestic_observation", "domestic_information_assessment",
    "domestic_resource_allocation", "domestic_public_health_measure",
    "domestic_infrastructure_repair", "domestic_logistics_adjustment",
    "domestic_security_readiness", "no_external_action",
)

EVENT_SCHEDULE = [
    {
        "turns": [1, 9],
        "event_name": "外部イベントなし",
        "event_text": "外部イベントなし。初期世界における自然な関係形成期間。",
    },
    {
        "turns": [10, 12],
        "event_name": "長雨による野菜不作・生鮮品供給不安・通信障害",
        "event_text": "連日の雨により各地で野菜や生鮮作物の生育不良・収穫遅延が発生し、一部食料品の供給不安と価格上昇リスクが高まっている。同時に、降雨・停電・中継設備障害により通信が不安定化している。",
    },
    {
        "turns": [13, 20],
        "event_name": "長雨危機の継続",
        "event_text": "TURN 10〜12の長雨による野菜不作・生鮮品供給不安・通信障害が継続している。",
    },
    {
        "turns": [21, 23],
        "event_name": "安全保障・制裁・封鎖・警備強化・武力衝突リスク行動空間追加",
        "event_text": "現実に存在し得る安全保障・制裁・封鎖・警備強化・武力衝突リスクに関する行動選択肢が利用可能。ただし強制行動ではなく、Leaderが必要と判断した場合のみ選択可能。",
    },
    {
        "turns": [24, 26],
        "event_name": "水系感染症の流行",
        "event_text": "水系感染症の流行。複数地域で井戸水・河川水の濁りが確認され、腹痛・発熱などを伴う水系感染症が流行し、簡易浄水材、医療相談、衛生用品、患者搬送、通信復旧への需要が増加している。原因・責任・拡大規模・収束は未確定であり、特定国家の責任や意図的行為は確認されていない。",
    },
    {
        "turns": [27, 29],
        "event_name": "水系感染症危機の継続",
        "event_text": "TURN 24〜26の水系感染症危機が継続している。井戸水・河川水の濁り、腹痛・発熱、簡易浄水材、医療相談、衛生用品、患者搬送、通信復旧への需要は引き続き存在する。",
    },
]


def event_for_turn(turn: int) -> dict[str, Any]:
    ensure(TURN_MIN <= turn <= TURN_MAX, "TURN_OUT_OF_RANGE")
    for event in EVENT_SCHEDULE:
        start, end = event["turns"]
        if start <= turn <= end:
            return dict(event)
    raise AssertionError("EVENT_SCHEDULE_GAP")


def public_world_bulletin(turn: int) -> dict[str, Any]:
    event = event_for_turn(turn)
    return {
        "document_type": "v5-public-world-bulletin-1",
        "turn": turn,
        "event_name": event["event_name"],
        "event_text": event["event_text"],
        "observable_by_all_conditions": True,
        "does_not_create_diplomatic_channel": True,
        "does_not_assign_responsibility": True,
        "does_not_script_outcome": True,
    }


def _text(max_length: int | None = None, *, min_length: int = 1) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "string", "minLength": min_length}
    if max_length is not None:
        result["maxLength"] = max_length
    return result


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _target_list(*, allow_external_targets: bool) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "array", "items": _text(128), "uniqueItems": True}
    if not allow_external_targets:
        result["maxItems"] = 0
    return result


def decision_schema(condition: str) -> dict[str, Any]:
    ensure(condition in CONDITIONS, "UNKNOWN_CONDITION")
    normal = condition == NORMAL
    target_list = _target_list(allow_external_targets=normal)
    message = _obj({
        "message_id": _text(128),
        "to_nation_ids": target_list,
        "body": _text(3000),
        "attach_self_introduction": {"type": "boolean"},
    })
    proposal = _obj({
        "proposal_id": _text(128),
        "to_nation_ids": target_list,
        "action_type": {"type": "string", "enum": list(NORMAL_ACTION_TYPES if normal else NO_DIPLOMACY_ACTION_TYPES)},
        "body": _text(3000),
        "requested_world_effect": {"type": ["string", "null"], "minLength": 1},
    })
    schema = _obj({
        "document_type": {"type": "string", "enum": [DOCUMENT_TYPE]},
        "condition": {"type": "string", "enum": [condition]},
        "world_id": _text(128),
        "run_id": _text(128),
        "seed_label": _text(64),
        "turn": {"type": "integer", "minimum": TURN_MIN, "maximum": TURN_MAX},
        "leader_id": _text(128),
        "nation_id": _text(128),
        "observation_summary": _text(2000),
        "contact_selection_reason": _text(2000),
        "outgoing_messages": {"type": "array", "items": message},
        "proposals": {"type": "array", "items": proposal},
        "private_note": {"type": ["string", "null"], "maxLength": 3000},
        "no_direct_world_mutation_ack": {"type": "boolean"},
    })
    if not normal:
        schema["properties"]["outgoing_messages"]["maxItems"] = 0
    return schema


def validate_decision(decision: dict[str, Any], *, condition: str, world_id: str, run_id: str,
                      seed_label: str, turn: int, leader_id: str, nation_id: str,
                      nation_ids: list[str], turn_start_snapshot: dict[str, Any],
                      communication_budget_chars: int = COMMUNICATION_BUDGET_CHARS) -> dict[str, Any]:
    ensure(condition in CONDITIONS, "UNKNOWN_CONDITION")
    errors = list(Draft202012Validator(decision_schema(condition)).iter_errors(decision))
    ensure(not errors, "V5_PAIRED_DECISION_SCHEMA_ERROR")
    ensure(decision["condition"] == condition and decision["world_id"] == world_id
           and decision["run_id"] == run_id and decision["seed_label"] == seed_label
           and decision["turn"] == turn and decision["leader_id"] == leader_id
           and decision["nation_id"] == nation_id, "V5_PAIRED_DECISION_IDENTITY_MISMATCH")
    ensure(decision["no_direct_world_mutation_ack"] is True, "V5_DIRECT_WORLD_MUTATION_NOT_ACKNOWLEDGED")
    known = set(nation_ids)
    ensure(nation_id in known, "V5_ACTOR_NATION_UNKNOWN")
    seen = set(); total_chars = 0; contact_targets = set()
    for section in ("outgoing_messages", "proposals"):
        for item in decision[section]:
            key = item.get("message_id") or item.get("proposal_id")
            ensure(key not in seen, "V5_DUPLICATE_TURN_ITEM_ID")
            seen.add(key)
            targets = set(item["to_nation_ids"])
            if condition == NORMAL:
                ensure(targets and targets <= known and nation_id not in targets,
                       "V5_INVALID_NORMAL_CONTACT_TARGET")
            else:
                ensure(not targets, "V5_NO_DIPLOMACY_EXTERNAL_TARGET_FORBIDDEN")
                ensure(item["action_type"] in NO_DIPLOMACY_ACTION_TYPES,
                       "V5_NO_DIPLOMACY_ACTION_FORBIDDEN")
            contact_targets |= targets
            total_chars += len(item["body"])
            if section == "proposals":
                ensure(item["requested_world_effect"] is None or item["action_type"] != "message_only",
                       "V5_MESSAGE_ONLY_WITH_WORLD_EFFECT")
    ensure(total_chars <= communication_budget_chars, "V5_COMMUNICATION_BUDGET_EXCEEDED")
    if condition == NO_DIPLOMACY:
        ensure(not decision["outgoing_messages"], "V5_NO_DIPLOMACY_MESSAGES_FORBIDDEN")
    return {
        "version": VERSION,
        "valid": True,
        "condition": condition,
        "accepted_world_effects": False,
        "world_state_mutated": False,
        "turn": turn,
        "leader_id": leader_id,
        "nation_id": nation_id,
        "contacted_nation_ids": sorted(contact_targets),
        "message_count": len(decision["outgoing_messages"]),
        "proposal_count": len(decision["proposals"]),
        "communication_chars_used": total_chars,
        "communication_budget_chars": communication_budget_chars,
        "decision_sha256": _digest(decision),
        "turn_start_snapshot_sha256": _digest(turn_start_snapshot),
    }


def build_turn_snapshot(*, source_world: dict[str, Any], condition: str, run_id: str,
                        seed_label: str, turn: int, actor_index: int,
                        message_history: list[dict[str, Any]] | None = None,
                        world_state: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure(condition in CONDITIONS, "UNKNOWN_CONDITION")
    pair = source_world["pairs"][actor_index]
    nation = source_world["nations"][actor_index]["nation"]
    leader = source_world["leaders"][actor_index]
    bulletin = public_world_bulletin(turn)
    messages = []
    if condition == NORMAL:
        messages = [m for m in (message_history or []) if m["turn"] < turn and pair["nation_id"] in m.get("to_nation_ids", [])]
    return {
        "world_id": source_world["world_id"],
        "run_id": run_id,
        "condition": condition,
        "seed_label": seed_label,
        "turn": turn,
        "turn_length_days": 30,
        "actor_nation_id": pair["nation_id"],
        "actor_leader_id": pair["leader_id"],
        "public_world_bulletin": bulletin,
        "public_contact_directory": source_world.get("public_contact_directory", []) if condition == NORMAL else [],
        "known_public_nations": [p["nation_id"] for p in source_world["pairs"]],
        "own_nation": nation,
        "own_leader_private_context": leader,
        "messages_received_before_this_turn": messages,
        "world_state_observation": world_state or {},
        "rules": condition_rules(condition),
    }


def condition_rules(condition: str) -> dict[str, Any]:
    normal = condition == NORMAL
    return {
        "condition": condition,
        "communication_budget_chars": COMMUNICATION_BUDGET_CHARS,
        "cross_border_diplomacy_allowed": normal,
        "direct_diplomatic_messages_allowed": normal,
        "cross_border_proposals_allowed": normal,
        "cross_border_resource_offer_allowed": normal,
        "explicit_acceptance_or_rejection_via_diplomacy_allowed": normal,
        "public_crisis_information_visible": True,
        "world_law_same_as_other_condition": True,
        "speech_only_does_not_change_physical_state": True,
        "do_not_script_outcome": True,
    }


def compare_condition_invariants(normal_snapshot: dict[str, Any], no_diplomacy_snapshot: dict[str, Any]) -> dict[str, Any]:
    same_fields = ["world_id", "seed_label", "turn", "turn_length_days", "actor_nation_id",
                   "actor_leader_id", "public_world_bulletin", "own_nation",
                   "own_leader_private_context", "world_state_observation"]
    mismatches = [field for field in same_fields if normal_snapshot.get(field) != no_diplomacy_snapshot.get(field)]
    allowed_differences = ["condition", "public_contact_directory", "messages_received_before_this_turn", "rules"]
    return {
        "version": VERSION,
        "same_required_fields": not mismatches,
        "mismatches": mismatches,
        "allowed_differences": allowed_differences,
        "normal_condition": normal_snapshot.get("condition"),
        "no_diplomacy_condition": no_diplomacy_snapshot.get("condition"),
    }


@dataclass(frozen=True)
class PreregistrationSeed:
    seed_label: str
    normal_run_id: str
    no_diplomacy_run_id: str


def preregistration_seed_pairs() -> list[dict[str, str]]:
    seeds = ["seed-01", "seed-02", "seed-03", "seed-04", "seed-05", "seed-06", "seed-07", "seed-08", "seed-09", "seed-10"]
    return [asdict(PreregistrationSeed(seed, f"{seed}-A-NORMAL", f"{seed}-B-NO-DIPLOMACY")) for seed in seeds]
