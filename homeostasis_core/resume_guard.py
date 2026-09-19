"""Read-only gate: never replay an attempted but uncommitted model decision.

This does not repair checkpoints, invent decisions, migrate old records or
certify an experiment's scientific validity. Ambiguous evidence stays stopped.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class UnsafeResumeError(ValueError):
    """A machine-readable refusal; no raw provider text is disclosed."""


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise UnsafeResumeError(code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "RESUME_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _integer(value: Any, code: str) -> int:
    _require(type(value) is int and value >= 0, code)
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _check_run(record: dict[str, Any], *, number: int, seed: int,
               completed_turn: int, model: str, countries: tuple[str, ...],
               schema_version: int | None = None) -> None:
    _require(type(record) is dict, "RESUME_INVALID_RUN")
    _require(type(record.get("run")) is int and record["run"] == number,
             "RESUME_RUN_MISMATCH")
    _require(type(record.get("seed")) is int and record["seed"] == seed,
             "RESUME_SEED_MISMATCH")
    rows, audit = record.get("turns"), record.get("call_audit")
    _require(type(rows) is list and len(rows) == completed_turn,
             "RESUME_TURN_COUNT_MISMATCH")
    _require(type(audit) is list, "RESUME_MISSING_CALL_AUDIT")
    expected: dict[tuple[int, str, str | None], dict[str, Any]] = {}
    for turn, row in enumerate(rows, 1):
        _require(type(row) is dict and type(row.get("turn")) is int
                 and row["turn"] == turn, "RESUME_TURN_ORDER_MISMATCH")
        responses = row.get("country_responses")
        _require(type(responses) is dict and set(responses) == set(countries),
                 "RESUME_COUNTRY_SET_MISMATCH")
        expected[(turn, "coordinator", None)] = row["proposal"]
        for country in countries:
            expected[(turn, "country", country)] = responses[country]
        expected[(turn, "evaluator", None)] = row["evaluator_commentary"]
    groups: dict[tuple[int, str, str | None], list[dict[str, Any]]] = {}
    for item in audit:
        _require(type(item) is dict, "RESUME_INVALID_AUDIT_ENTRY")
        if schema_version is not None:
            _require(type(item.get("schema_version")) is int
                     and item["schema_version"] == schema_version, "RESUME_PROTOCOL_MISMATCH")
        turn = _integer(item.get("turn"), "RESUME_INVALID_AUDIT_TURN")
        # Even a pre-dispatch journal entry is ambiguous after interruption.
        _require(0 < turn <= completed_turn,
                 "RESUME_UNCOMMITTED_DECISION_REQUIRES_REVIEW")
        _require(type(item.get("run")) is int and item["run"] == number
                 and item.get("model") == model, "RESUME_AUDIT_IDENTITY_MISMATCH")
        role = item.get("agent_type")
        _require(role in ("country", "coordinator", "evaluator"),
                 "RESUME_UNKNOWN_AGENT_TYPE")
        actor = item.get("agent_id") if role == "country" else None
        key = (turn, role, actor)
        _require(key in expected, "RESUME_UNKNOWN_DECISION")
        _require(item.get("snapshot_id") == f"run-{number}-turn-{turn}-start",
                 "RESUME_SNAPSHOT_MISMATCH")
        payload = item.get("public_observation_payload")
        _require(type(payload) is dict and item.get("observation_digest") == _digest(payload),
                 "RESUME_REQUEST_DIGEST_MISMATCH")
        groups.setdefault(key, []).append(item)
    _require(set(groups) == set(expected), "RESUME_MISSING_DECISION_EVIDENCE")
    for key, items in groups.items():
        for attempt, item in enumerate(items, 1):
            _require(type(item.get("attempt")) is int and item["attempt"] == attempt,
                     "RESUME_ATTEMPT_ORDER_MISMATCH")
            _require(item["public_observation_payload"] == items[0]["public_observation_payload"],
                     "RESUME_CHANGED_REQUEST")
            if attempt < len(items):
                _require(item.get("response_status") == "provider_error"
                         and type(item.get("provider_status_code")) is int
                         and item["provider_status_code"] in (429, 503)
                         and item.get("structured_response") is None
                         and "response_sha256" not in item,
                         "RESUME_REGENERATED_OR_AMBIGUOUS_RESPONSE")
            else:
                # A legacy successful record has no response_status. It is
                # accepted only when the committed response is present/matches.
                status = item.get("response_status")
                _require(status in (None, "validated")
                         and type(item.get("structured_response")) is dict
                         and item["structured_response"] == expected[key],
                         "RESUME_RESPONSE_NOT_COMMITTED")


def _check_active_history(active: dict[str, Any], countries: tuple[str, ...]) -> None:
    """Check the runner's existing projections; never repair or replace them.

    These fields become later Agent inputs. Recompute only for comparison
    against committed rows, using the unchanged mappings in run_live. This
    neither approves those world rules nor authenticates the whole checkpoint.
    """
    expected_memories: dict[str, list[dict[str, Any]]] = {c: [] for c in countries}
    for row in active["turns"]:
        state = row["executed_state"]
        _require(type(state) is dict, "RESUME_INCOMPLETE_OR_INVALID_CHECKPOINT")
        for country in countries:
            response = row["country_responses"][country]
            settlements = [x for x in state.get("atomic_settlements", [])
                           if x["agent_id"] == country]
            expected_memories[country].append({
                "response_id": response["response_id"],
                "action_id": response["action"]["action_id"],
                "realized": sum(x["realized"] for x in settlements),
                "unmet": sum(x["unmet"] for x in settlements),
                "event": row["snapshot"]["event"],
                "damage_after": state["reconstruction"]["after"],
            })
    # Canonical JSON distinguishes booleans/numbers/strings and extra fields;
    # Python equality alone would accept True in place of the recorded 1.
    _require(_digest(active["memories"]) == _digest(expected_memories),
             "RESUME_MEMORY_CONTENT_MISMATCH")
    if active["turns"]:
        state = active["turns"][-1]["executed_state"]
        world = state["true_world"]
        expected_history = {
            "economic_loss": max(0, 100 - world["economy"]),
            "reserve_gap": max(0, 100 - world["food"]),
            "trust_loss": max(0, 100 - world["international_trust"]),
            "alertness": world["conflict_load"],
            "unmet_resource_demand": state.get("demand_unmet", 0),
        }
        _require(type(active.get("history_state")) is dict
                 and _digest(active["history_state"]) == _digest(expected_history),
                 "RESUME_HISTORY_STATE_MISMATCH")


def read_resumable_checkpoint(path: Path, *, runs: int, seed: int,
                              turn_count: int, model: str,
                              country_ids: tuple[str, ...],
                              schema_version: int | None = None) -> dict[str, Any]:
    """Validate before client creation/dispatch; return saved data unchanged."""
    _require(path.is_file(), "RESUME_CHECKPOINT_NOT_FOUND")
    _require(type(runs) is int and runs > 0 and type(seed) is int
             and type(turn_count) is int and turn_count > 0,
             "RESUME_INVALID_REQUEST")
    try:
        saved = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        _require(type(saved) is dict, "RESUME_INVALID_CHECKPOINT")
        completed = saved.get("completed_runs")
        _require(type(completed) is list and len(completed) <= runs,
                 "RESUME_COMPLETED_RUN_COUNT_MISMATCH")
        countries = tuple(sorted(country_ids))
        for number, record in enumerate(completed, 1):
            _require(type(record) is dict and record.get("model") == model,
                     "RESUME_MODEL_MISMATCH")
            _check_run(record, number=number, seed=seed + number - 1,
                       completed_turn=turn_count, model=model, countries=countries, schema_version=schema_version)
        active = saved.get("active_run")
        if active is not None:
            _require(type(active) is dict and len(completed) < runs, "RESUME_INVALID_ACTIVE_RUN")
            n = _integer(active.get("completed_turn"), "RESUME_INVALID_COMPLETED_TURN")
            _require(n <= turn_count, "RESUME_INVALID_COMPLETED_TURN")
            _check_run(active, number=len(completed) + 1, seed=seed + len(completed),
                       completed_turn=n, model=model, countries=countries, schema_version=schema_version)
            _require(type(active.get("memories")) is dict
                     and set(active["memories"]) == set(countries)
                     and all(type(v) is list and len(v) == n for v in active["memories"].values()),
                     "RESUME_MEMORY_LENGTH_MISMATCH")
            _check_active_history(active, countries)
            _require(type(active.get("country_states")) is dict
                     and set(active["country_states"]) == set(countries),
                     "RESUME_COUNTRY_STATE_MISMATCH")
            if n:
                last = active["turns"][-1]["executed_state"]
                for current, committed in (("current_world", "true_world"),
                                           ("country_states", "country_states"),
                                           ("world_pool", "world_pool"),
                                           ("network_policy", "network_policy")):
                    _require(active[current] == last[committed], "RESUME_STATE_MISMATCH")
                _require(active["current_damage"] == last["reconstruction"]["after"],
                         "RESUME_DAMAGE_MISMATCH")
        return saved
    except UnsafeResumeError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError):
        raise UnsafeResumeError("RESUME_INCOMPLETE_OR_INVALID_CHECKPOINT") from None
