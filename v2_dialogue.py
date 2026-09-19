"""V2 addressed dialogue: deterministic transport, not a world simulator.

All inputs in one round precede that round's outputs. No Observer, evaluator,
model callback or political action classifier participates in delivery.
"""
from __future__ import annotations

import hashlib
import json

from model_response_json import load_response_object
from simulation_v2 import AGENTS, INITIAL_WORLD_STATE, SOURCE_EVENT


PROTOCOL_VERSION = "v2-addressed-dialogue-1"
ACTORS = ("A", "B", "C", "COORDINATOR")


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def clone(value):
    return json.loads(encode(value))


def digest(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def _keys(value, required, optional=()):
    if (not isinstance(value, dict) or not set(required) <= value.keys()
            or value.keys() - set(required) - set(optional)):
        raise ValueError("invalid transport fields")


def _text(value):
    if not isinstance(value, str):
        raise ValueError("transport text must be a string")


def recipients(value):
    if (not isinstance(value, list) or not value
            or any(not isinstance(item, str) for item in value)
            or len(set(value)) != len(value)
            or not set(value) <= set(ACTORS)):
        raise ValueError("invalid recipients")
    return value


def parse_reply(raw):
    """Validate the envelope only; preserve all free content verbatim."""
    value = load_response_object(raw)
    _keys(value, ("outgoing", "activities", "private_note"))
    _text(value["private_note"])
    for key in ("outgoing", "activities"):
        if not isinstance(value[key], list):
            raise ValueError(f"{key} must be an array")
    for message in value["outgoing"]:
        _keys(message, ("to", "body"), ("reply_to",))
        recipients(message["to"])
        _text(message["body"])
        if "reply_to" in message:
            refs = message["reply_to"]
            if (not isinstance(refs, list)
                    or any(not isinstance(ref, str) for ref in refs)
                    or len(set(refs)) != len(refs)):
                raise ValueError("invalid reply references")
    for request in value["activities"]:
        _keys(request, ("body",), ("operation", "arguments"))
        _text(request["body"])
        if "operation" in request:
            _text(request["operation"])
        if "arguments" in request and not isinstance(request["arguments"], dict):
            raise ValueError("activity arguments must be an object")
    return value


def initial_conditions():
    # Old recovery_turns is not an implemented forecast or automatic recovery.
    return {
        "roles": {**{code: agent.role for code, agent in AGENTS.items()},
                  "COORDINATOR": "強制権を持たない地球調整機関"},
        "event": {key: SOURCE_EVENT[key] for key in
                  ("origin", "event", "lost_annual_rice_capacity_tons")},
        "legacy_initial_indicators": clone(INITIAL_WORLD_STATE),
        "indicator_status": "historical_initial_conditions_not_live_measurements",
    }


class Dialogue:
    """Own state as serialized JSON; returned views cannot mutate live state."""

    def __init__(self):
        initial = initial_conditions()
        self._state_json = encode({
            "protocol": PROTOCOL_VERSION,
            "round": 0,
            "initial": initial,
            "events": [{"id": "initial:0", "kind": "initial_condition",
                        "round": 0, "cause": None, "visible_to": list(ACTORS),
                        "facts": initial["event"]}],
            "messages": [],
            "history": {actor: [] for actor in ACTORS},
            "notes": {actor: "" for actor in ACTORS},
            "activity_results": {actor: [] for actor in ACTORS},
        })

    def snapshot(self):
        """Private audit copy. Contains all actors' private data; not a broadcast."""
        return json.loads(self._state_json)

    def inputs(self):
        state = self.snapshot()
        result = {}
        for actor in ACTORS:
            result[actor] = {
                "actor": actor, "participants": list(ACTORS),
                "round": state["round"] + 1,
                "role": state["initial"]["roles"][actor],
                "initial_conditions": state["initial"],
                "events": [event for event in state["events"]
                           if actor in event["visible_to"]],
                "messages": [message for message in state["messages"]
                             if actor == message["sender"] or actor in message["to"]],
                "own_outputs": state["history"][actor],
                "private_note": state["notes"][actor],
                "activity_results": state["activity_results"][actor],
                "capabilities": {
                    "addressed_messages": True,
                    "private_memory": True,
                    "activity_execution": [],
                    "physical_execution": False,
                    "program_execution": False,
                },
            }
        return clone(result)

    def commit(self, raw_replies, *, expected_round):
        """Apply one complete round atomically. Reapplication fails, never resends."""
        state = self.snapshot()
        round_number = state["round"] + 1
        if type(expected_round) is not int or expected_round != round_number:
            raise ValueError("stale or duplicate round")
        if not isinstance(raw_replies, dict) or set(raw_replies) != set(ACTORS):
            raise ValueError("one response is required from every participant")
        replies = {actor: parse_reply(raw_replies[actor]) for actor in ACTORS}
        before_inputs = self.inputs()
        # No delivery occurs until *all* envelopes/references have been checked.
        for actor, reply in replies.items():
            visible_ids = {message["id"] for message in before_inputs[actor]["messages"]}
            for message in reply["outgoing"]:
                if not set(message.get("reply_to", [])) <= visible_ids:
                    raise ValueError("reply references a message unavailable to its author")
        for actor in ACTORS:
            reply = replies[actor]
            response_id = f"response:{round_number}:{actor}"
            state["history"][actor].append({"id": response_id,
                                           "round": round_number, "output": reply})
            state["notes"][actor] = reply["private_note"]
            for index, message in enumerate(reply["outgoing"]):
                message_id = f"message:{round_number}:{actor}:{index}"
                delivered = {**message, "id": message_id, "sender": actor,
                             "sent_round": round_number,
                             "available_round": round_number + 1,
                             "cause": response_id}
                state["messages"].append(delivered)
                state["events"].append({
                    "id": f"event:{message_id}", "kind": "message_delivered",
                    "round": round_number, "cause": response_id,
                    "message_id": message_id,
                    "visible_to": list(dict.fromkeys([actor, *message["to"]])),
                })
            for index, request in enumerate(reply["activities"]):
                request_id = f"activity:{round_number}:{actor}:{index}"
                # A request is retained even when its execution mechanism is absent.
                receipt = {"id": request_id, "cause": response_id,
                           "request": request, "executed": False,
                           "status": "environment_unsupported",
                           "reason": "No execution capability is connected for this request.",
                           "physical_change": None}
                state["activity_results"][actor].append(receipt)
                state["events"].append({
                    "id": f"event:{request_id}", "kind": "activity_not_executed",
                    "round": round_number, "cause": response_id,
                    "request_id": request_id, "visible_to": [actor],
                })
        state["round"] = round_number
        self._state_json = encode(state)
        return self.snapshot()
