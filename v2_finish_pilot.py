"""Finish the approved pilot after a proven, pre-generation input-limit stop.

Only the remaining three rounds are generated. Prior confirmed spend plus all
new reservations must stay within the originally approved $0.95328 allowance.
"""
from __future__ import annotations

import argparse
import base64
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import uuid

import httpx

from homeostasis_core.execution_lock import exclusive_execution
from v2_autonomous import Journal, configuration, _request, _response_text
from v2_dialogue import ACTORS, digest, encode
import v2_continue_pilot as continuation
import v2_paid_pilot as pilot

require = continuation.require
INPUT_LIMIT = 24000
CALL_LIMIT = 12
ORIGINAL_USD_LIMIT = Decimal("0.95328")


def sources():
    return {**continuation.sources(), Path(__file__).name:
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def wire_request(request, manifest):
    return {"contents": [{"parts": [{"text": request["kwargs"]["contents"]}], "role": "user"}],
            "systemInstruction": {"parts": [{"text": manifest["system_instruction"]}], "role": "user"},
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": pilot.OUTPUT_LIMIT}}


def verify_stopped(directory, expected_sha256):
    """Accept only a complete fifth round followed by one unpaid oversized count."""
    directory = Path(directory)
    identity = continuation.evidence_identity(directory)
    require(digest(identity) == expected_sha256, "STOPPED_EVIDENCE_CHANGED")
    runtime, journal = Journal(directory / "dialogue"), Journal(directory)
    manifest = runtime.read("manifest.json")
    require(manifest["continuation_source_identity"] == continuation.sources(), "CONTINUATION_SOURCE_MISMATCH")
    dialogue, parent_manifest, parent_identity = continuation.verify_parent(
        Path(manifest["parent_directory"]), manifest["parent_evidence_sha256"])
    require(manifest["parent_evidence"] == parent_identity
            and manifest["parent_run_id"] == parent_manifest["run_id"], "PARENT_BINDING_MISMATCH")
    expected = configuration(model=pilot.MODEL, rounds=8, max_calls=24,
                             max_input_bytes=100000, max_output_tokens=pilot.OUTPUT_LIMIT)
    require(all(manifest.get(key) == value for key, value in expected.items()), "CONTINUATION_CONFIG_MISMATCH")
    stopped = journal.read("continuation-stopped.json")
    require(stopped["status"] == "technical_stop" and stopped["exception_type"] == "PilotStopped"
            and stopped["committed_round"] == 5 and stopped["paid_attempts"] == 12
            and not stopped["unresolved"] and len(stopped["usage"]) == 12, "UNSAFE_STOP_STATE")
    require(not runtime.exists("result.json"), "CONTINUATION_ALREADY_COMPLETE")
    require(len(list((directory / "dialogue").glob("call-*.request.json"))) == 13
            and len(list((directory / "dialogue").glob("call-*.sdk.json"))) == 12
            and len(list(directory.glob("budget-*/paid-*.reservation.json"))) == 12
            and len(list(directory.glob("budget-*/paid-*.wire-response.json"))) == 12
            and len(list(directory.glob("budget-*/paid-*.usage.json"))) == 12,
            "UNEXPECTED_OR_AMBIGUOUS_ATTEMPTS")
    spent = Decimal(0)
    sequence = 8
    for number in range(3, 6):
        views, replies = dialogue.inputs(), {}
        for actor in ACTORS:
            request = {"run_id": manifest["run_id"], "sequence": sequence, "round": number,
                       "actor": actor, "kwargs": _request(views[actor], manifest)}
            replies[actor] = _response_text(runtime, sequence, request, None, manifest)
            budget, index = divmod(sequence - 8, 8)
            guard = Journal(directory / f"budget-{budget+1:02d}")
            reservation = guard.read(f"paid-{index:02d}.reservation.json")
            require(reservation["request"] == wire_request(request, manifest), "PAID_INPUT_MISMATCH")
            require(guard.read(f"count-{index:02d}.request.json") == {
                "generateContentRequest": {"model": "models/" + pilot.MODEL, **reservation["request"]}},
                "COUNT_REQUEST_MISMATCH")
            count = guard.read(f"count-{index:02d}.response.json")
            require(digest(count) == reservation["count_response_sha256"]
                    and count["totalTokens"] == reservation["input_tokens"], "COUNT_MISMATCH")
            wire = guard.read(f"paid-{index:02d}.wire-response.json")
            require(wire["status"] == 200 and wire["reservation_sha256"] == digest(reservation), "WIRE_MISMATCH")
            raw = json.loads(base64.b64decode(wire["body_base64"], validate=True))
            candidates = raw["candidates"]
            require(len(candidates) == 1 and candidates[0]["finishReason"] == "STOP", "INCOMPLETE_PARENT_REPLY")
            require("".join(p["text"] for p in candidates[0]["content"]["parts"] if not p.get("thought"))
                    == replies[actor], "WIRE_TEXT_MISMATCH")
            usage = guard.read(f"paid-{index:02d}.usage.json")
            require(usage["usage"] == raw["usageMetadata"] and usage["within_configured_limits"]
                    and stopped["usage"][sequence-8] == {"budget": budget+1, **usage}, "USAGE_MISMATCH")
            counts = [raw["usageMetadata"].get(k) for k in
                      ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount")]
            require(all(type(c) is int and c >= 0 for c in counts)
                    and counts[0] <= pilot.INPUT_LIMIT and counts[1] + counts[2] <= pilot.OUTPUT_LIMIT,
                    "UNKNOWN_PRIOR_SPEND")
            actual = pilot.cost(counts[0], counts[1] + counts[2])
            require(Decimal(usage["estimated_usd"]) == actual, "PRIOR_SPEND_MISMATCH")
            spent += actual
            sequence += 1
        state = dialogue.commit(replies, expected_round=number)
        require(runtime.read(f"round-{number:08d}.json") == {"round": number,
            "inputs_sha256": digest(views), "state_sha256": digest(state),
            "call_sequences": list(range(sequence-4, sequence))}, "REPLAY_MISMATCH")
    require(dialogue.snapshot() == stopped["delivery_state"], "STOP_STATE_MISMATCH")
    pending = {"run_id": manifest["run_id"], "sequence": 20, "round": 6, "actor": ACTORS[0],
               "kwargs": _request(dialogue.inputs()[ACTORS[0]], manifest)}
    require(runtime.read("call-00000020.request.json") == pending
            and not runtime.exists("call-00000020.sdk.json"), "PENDING_REQUEST_MISMATCH")
    guard = Journal(directory / "budget-02")
    require(guard.read("count-04.request.json") == {"generateContentRequest": {
        "model": "models/" + pilot.MODEL, **wire_request(pending, manifest)}}, "PENDING_COUNT_MISMATCH")
    count = guard.read("count-04.response.json")["totalTokens"]
    require(type(count) is int and count > pilot.INPUT_LIMIT
            and not guard.exists("paid-04.reservation.json") and not guard.exists("paid-04.wire-response.json"),
            "STOP_NOT_PROVEN_BEFORE_PAID_GENERATION")
    require(spent + CALL_LIMIT * pilot.cost(INPUT_LIMIT, pilot.OUTPUT_LIMIT) <= ORIGINAL_USD_LIMIT,
            "ORIGINAL_TOTAL_BUDGET_EXCEEDED")
    require(identity == continuation.evidence_identity(directory), "EVIDENCE_CHANGED_DURING_REPLAY")
    return dialogue, manifest, identity, spent


class CompletionTransport(httpx.BaseTransport):
    """Wider input only; fixed output, remaining call count and original total spend."""

    def __init__(self, inner, journal, prior_spend, source_identity):
        self.inner, self.journal = inner, journal
        self.prior_spend, self.source_identity = prior_spend, source_identity.copy()
        self.calls, self.reserved, self.block_reason, self.usages = 0, Decimal(0), None, []

    def check(self):
        require(sources() == self.source_identity, "COMPLETION_SOURCE_CHANGED")
        require(self.block_reason is None, "UNRESOLVED_PAID_REQUEST")

    def handle_request(self, request):
        self.check()
        require(request.method == "POST" and str(request.url) == pilot.ENDPOINT + ":generateContent",
                "UNEXPECTED_PAID_ENDPOINT")
        require(self.calls < CALL_LIMIT, "REMAINING_CALL_LIMIT")
        body = json.loads(request.content)
        require(set(body) == {"contents", "systemInstruction", "generationConfig"}
                and body["generationConfig"] == {"responseMimeType": "application/json", "maxOutputTokens": pilot.OUTPUT_LIMIT},
                "UNEXPECTED_GENERATION_SETTINGS")
        index = self.calls
        counted = {"generateContentRequest": {"model": "models/" + pilot.MODEL, **body}}
        self.journal.write(f"count-{index:02d}.request.json", counted)
        count_request = httpx.Request("POST", pilot.ENDPOINT + ":countTokens", json=counted,
            headers={"x-goog-api-key": request.headers["x-goog-api-key"], "content-type": "application/json"},
            extensions=request.extensions.copy())
        response = self.inner.handle_request(count_request)
        try:
            response.read()
            require(response.status_code == 200, "COUNT_FAILED_NO_GENERATION")
            count = response.json()
            self.journal.write(f"count-{index:02d}.response.json", count)
        finally:
            response.close()
        input_tokens = count.get("totalTokens")
        require(type(input_tokens) is int and 0 <= input_tokens <= INPUT_LIMIT, "INPUT_LIMIT_NO_GENERATION")
        upper = pilot.cost(INPUT_LIMIT, pilot.OUTPUT_LIMIT)
        require(self.prior_spend + self.reserved + upper <= ORIGINAL_USD_LIMIT, "ORIGINAL_TOTAL_BUDGET_EXCEEDED")
        self.check()
        reservation = {"sequence": index, "request": body, "input_tokens": input_tokens,
                       "count_response_sha256": digest(count), "maximum_output_tokens": pilot.OUTPUT_LIMIT,
                       "reserved_usd": str(upper)}
        self.journal.write(f"paid-{index:02d}.reservation.json", reservation)
        self.calls += 1
        self.reserved += upper
        self.block_reason = "PREVIOUS_PAID_REQUEST_UNRESOLVED"
        response = self.inner.handle_request(request)
        response.read()
        self.journal.write(f"paid-{index:02d}.wire-response.json", {"status": response.status_code,
            "reservation_sha256": digest(reservation), "body_base64": base64.b64encode(response.content).decode("ascii")})
        try:
            usage = response.json().get("usageMetadata", {})
            counts = [usage.get(k) for k in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount")]
            known = all(type(c) is int and c >= 0 for c in counts)
            actual = pilot.cost(counts[0], counts[1] + counts[2]) if known else None
            within = known and counts[0] <= INPUT_LIMIT and counts[1] + counts[2] <= pilot.OUTPUT_LIMIT
            record = {"sequence": index, "usage": usage, "estimated_usd": str(actual) if actual is not None else None,
                      "within_configured_limits": within, "billing_verified": False}
            self.usages.append(record)
            self.journal.write(f"paid-{index:02d}.usage.json", record)
            if response.status_code == 200 and within and actual <= upper:
                self.block_reason = None
        except (ValueError, TypeError, KeyError, AttributeError):
            pass  # The raw receipt remains; unresolved usage prevents all further calls.
        return response

    def summary(self):
        return {"paid_attempts": self.calls, "prior_additional_estimated_usd": str(self.prior_spend),
                "reserved_usd": str(self.reserved), "usage": self.usages,
                "unresolved": self.block_reason, "automatic_retry": False, "billing_verified": False}

    def close(self):
        self.inner.close()


def output_directory(stopped):
    require(not Path(stopped).is_symlink(), "STOPPED_DIRECTORY_SYMLINK")
    stopped = Path(stopped).resolve()
    return stopped.with_name(stopped.name + "-completion")


def execute(stopped, expected_sha256, credential, *, inner=None):
    from google import genai
    from google.genai import types

    require(isinstance(credential, str) and credential and not any(c.isspace() for c in credential), "INVALID_CREDENTIAL")
    destination = output_directory(stopped)
    stopped = Path(stopped).resolve()
    with exclusive_execution(destination):
        require(not destination.exists() and not destination.is_symlink(), "COMPLETION_ALREADY_ATTEMPTED")
        dialogue, previous, identity, spent = verify_stopped(stopped, expected_sha256)
        pilot.profile()  # Retain the published-price expiry guard.
        frozen = sources()
        manifest = configuration(model=pilot.MODEL, rounds=8, max_calls=12,
                                 max_input_bytes=200000, max_output_tokens=pilot.OUTPUT_LIMIT)
        manifest.update({"run_id": str(uuid.uuid4()), "first_new_round": 6,
            "previous_directory": str(stopped), "previous_evidence": identity,
            "previous_evidence_sha256": expected_sha256, "source_chain": frozen,
            "prior_additional_estimated_usd": str(spent), "original_additional_usd_limit": str(ORIGINAL_USD_LIMIT),
            "max_input_tokens": INPUT_LIMIT, "automatic_retries": False,
            "maximum_remaining_usd": str(CALL_LIMIT * pilot.cost(INPUT_LIMIT, pilot.OUTPUT_LIMIT))})
        destination.mkdir(mode=0o700)
        journal, runtime = Journal(destination), Journal(destination / "dialogue")
        runtime.prepare(manifest, resume=False)
        transport = CompletionTransport(inner or httpx.HTTPTransport(retries=0), journal, spent, frozen)
        sequence = 20
        status = "observation_period_reached"
        try:
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=120) as http:
                with genai.Client(vertexai=False, api_key=credential, http_options=types.HttpOptions(
                        base_url="https://generativelanguage.googleapis.com", api_version="v1beta",
                        httpx_client=http, timeout=120000,
                        retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    for number in range(6, 9):
                        transport.check()
                        views, replies = dialogue.inputs(), {}
                        requests = {a: {"run_id": manifest["run_id"], "sequence": sequence+i,
                            "round": number, "actor": a, "kwargs": _request(views[a], manifest)} for i, a in enumerate(ACTORS)}
                        if any(len(encode(r["kwargs"]).encode("utf-8")) > manifest["max_input_bytes"] for r in requests.values()):
                            status = "input_limit_reached_no_history_truncated"
                            break
                        for actor, request in requests.items():
                            replies[actor] = _response_text(runtime, sequence, request, client, manifest)
                            sequence += 1
                            transport.check()
                        state = dialogue.commit(replies, expected_round=number)
                        runtime.write(f"round-{number:08d}.json", {"round": number, "inputs_sha256": digest(views),
                            "state_sha256": digest(state), "call_sequences": list(range(sequence-4, sequence))})
            require(identity == continuation.evidence_identity(stopped), "PREVIOUS_EVIDENCE_CHANGED")
            transport.check()
            result = {"kind": "v2_completed_dialogue_private_audit", "status": status,
                "physical_execution": False, "program_execution": False, "model_calls": sequence-20,
                "total_model_calls": sequence, "manifest_sha256": digest(manifest), "state": dialogue.snapshot()}
            runtime.write("result.json", result)
            journal.write("completion-summary.json", {"status": status, **transport.summary()})
            return result
        except BaseException as error:
            journal.write("completion-stopped.json", {"status": "technical_stop", "exception_type": type(error).__name__,
                "committed_round": dialogue.snapshot()["round"], "delivery_state": dialogue.snapshot(),
                "not_an_agent_decision": True, **transport.summary()})
            raise


def main():
    parser = argparse.ArgumentParser(description="課金前の入力上限停止を検証し、残る3ターンだけ完了する。")
    parser.add_argument("--stopped-directory", type=Path, required=True)
    parser.add_argument("--expected-stopped-sha256", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.stopped_directory, args.expected_stopped_sha256, pilot.load_credential(args.credential_file))
    except Exception as error:
        raise SystemExit("停止しました。自動再実行はしません。種類: " + type(error).__name__) from None
    print(f"V2を{result['state']['round']}ターンまで記録しました。今回の追加生成: {result['model_calls']}回。")


if __name__ == "__main__":
    main()
