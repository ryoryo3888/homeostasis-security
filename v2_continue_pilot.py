"""Continue one verified two-round pilot through round eight, exactly once.

Old requests and replies are replayed locally. The parent remains read-only;
new paid requests use the original per-call budget guard and Agent protocol.
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
from v2_dialogue import ACTORS, Dialogue, digest, encode
import v2_paid_pilot as pilot


ADDITIONAL_CALLS = 24
FINAL_ROUND = 8


def require(condition, reason):
    if not condition:
        raise pilot.PilotStopped(reason)


def sources():
    return {**pilot.sources(), Path(__file__).name:
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def evidence_identity(parent):
    """Pin all private JSON evidence, including the exact HTTP responses."""
    parent = Path(parent)
    require(not parent.is_symlink(), "PARENT_SYMLINK")
    records = {}
    for path in sorted(parent.rglob("*.json")):
        payload = Journal(path.parent).read(path.name)
        records[str(path.relative_to(parent))] = digest(payload)
    require(bool(records), "PARENT_EVIDENCE_MISSING")
    return records


def verify_parent(parent, expected_sha256):
    """Rebuild the original state from bound receipts, without a model client."""
    parent = Path(parent)
    identity = evidence_identity(parent)
    require(digest(identity) == expected_sha256, "PARENT_EVIDENCE_CHANGED")
    journal, runtime = Journal(parent), Journal(parent / "dialogue")
    require(not list(parent.rglob("*stopped*")), "PARENT_PREVIOUSLY_STOPPED")
    require(journal.read("pilot-profile.json") == pilot.profile(), "PARENT_PROFILE_CHANGED")
    manifest = runtime.read("manifest.json")
    expected = configuration(model=pilot.MODEL, rounds=2, max_calls=8,
                             max_input_bytes=100000, max_output_tokens=pilot.OUTPUT_LIMIT)
    expected["run_id"] = manifest["run_id"]
    require(manifest == expected, "PARENT_CONFIGURATION_CHANGED")
    result, summary = runtime.read("result.json"), journal.read("pilot-summary.json")
    require(result["manifest_sha256"] == digest(manifest), "PARENT_MANIFEST_MISMATCH")
    require(result["status"] == summary["status"] == "observation_period_reached"
            and result["model_calls"] == summary["paid_attempts"] == 8
            and summary["further_calls_blocked_reason"] is None, "PARENT_NOT_COMPLETE")
    require(len(summary["usage"]) == 8, "PARENT_USAGE_INCOMPLETE")
    dialogue = Dialogue()
    sequence = 0
    for number in (1, 2):
        inputs, replies = dialogue.inputs(), {}
        for actor in ACTORS:
            request = {"run_id": manifest["run_id"], "sequence": sequence,
                       "round": number, "actor": actor, "kwargs": _request(inputs[actor], manifest)}
            require(runtime.exists(f"call-{sequence:08d}.request.json")
                    and runtime.exists(f"call-{sequence:08d}.sdk.json"), "PARENT_RECEIPT_MISSING")
            replies[actor] = _response_text(runtime, sequence, request, None, manifest)
            reservation = journal.read(f"paid-{sequence:02d}.reservation.json")
            counted = journal.read(f"count-{sequence:02d}.request.json")["generateContentRequest"].copy()
            require(counted.pop("model") == "models/" + pilot.MODEL
                    and counted == reservation["request"], "PARENT_WIRE_REQUEST_MISMATCH")
            expected_wire = {"contents": [{"parts": [{"text": request["kwargs"]["contents"]}], "role": "user"}],
                "systemInstruction": {"parts": [{"text": manifest["system_instruction"]}], "role": "user"},
                "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": pilot.OUTPUT_LIMIT}}
            require(counted == expected_wire, "PARENT_WIRE_INPUT_MISMATCH")
            count = journal.read(f"count-{sequence:02d}.response.json")
            require(digest(count) == reservation["count_response_sha256"]
                    and count["totalTokens"] == reservation["input_tokens"]
                    and type(count["totalTokens"]) is int and 0 <= count["totalTokens"] <= pilot.INPUT_LIMIT
                    and reservation["sequence"] == sequence
                    and reservation["maximum_output_tokens"] == pilot.OUTPUT_LIMIT
                    and Decimal(reservation["reserved_usd"]) == pilot.cost(pilot.INPUT_LIMIT, pilot.OUTPUT_LIMIT),
                    "PARENT_COUNT_MISMATCH")
            wire = journal.read(f"paid-{sequence:02d}.wire-response.json")
            require(wire["status"] == 200 and wire["reservation_sha256"] == digest(reservation),
                    "PARENT_WIRE_RECEIPT_MISMATCH")
            raw = json.loads(base64.b64decode(wire["body_base64"], validate=True))
            candidates = raw["candidates"]
            require(len(candidates) == 1 and candidates[0]["finishReason"] == "STOP",
                    "PARENT_INCOMPLETE_RESPONSE")
            text = "".join(part["text"] for part in candidates[0]["content"]["parts"]
                           if not part.get("thought"))
            require(text == replies[actor], "PARENT_WIRE_TEXT_MISMATCH")
            usage = journal.read(f"paid-{sequence:02d}.usage.json")
            require(usage == summary["usage"][sequence] and usage["usage"] == raw["usageMetadata"]
                    and usage["within_configured_limits"], "PARENT_USAGE_MISMATCH")
            sequence += 1
        state = dialogue.commit(replies, expected_round=number)
        checkpoint = runtime.read(f"round-{number:08d}.json")
        require(checkpoint == {"round": number, "state_sha256": digest(state),
                "inputs_sha256": digest(inputs), "call_sequences": list(range(sequence - 4, sequence))},
                "PARENT_REPLAY_MISMATCH")
    require(dialogue.snapshot() == result["state"], "PARENT_RESULT_MISMATCH")
    require(identity == evidence_identity(parent), "PARENT_CHANGED_DURING_REPLAY")
    return dialogue, manifest, identity


class SourceCheckedTransport(httpx.BaseTransport):
    """Check continuation code immediately before both count and paid I/O."""

    def __init__(self, inner, source_identity):
        self.inner, self.source_identity = inner, source_identity.copy()

    def handle_request(self, request):
        require(sources() == self.source_identity, "CONTINUATION_SOURCE_CHANGED")
        return self.inner.handle_request(request)

    def close(self):
        self.inner.close()


class ContinuationTransport(httpx.BaseTransport):
    """At most three original eight-call guards; no reset after an error."""

    def __init__(self, inner, directory, source_identity):
        self.inner = SourceCheckedTransport(inner, source_identity)
        self.directory = Path(directory)
        self.source_identity = source_identity.copy()
        self.guards = []

    @property
    def calls(self):
        return sum(guard.calls for guard in self.guards)

    def check(self):
        require(sources() == self.source_identity, "CONTINUATION_SOURCE_CHANGED")
        for guard in self.guards:
            require(guard.block_reason is None, "UNRESOLVED_PAID_REQUEST_NO_CONTINUATION")

    def handle_request(self, request):
        self.check()
        require(self.calls < ADDITIONAL_CALLS, "ADDITIONAL_CALL_LIMIT_REACHED")
        if not self.guards or self.guards[-1].calls == pilot.CALL_LIMIT:
            directory = self.directory / f"budget-{len(self.guards) + 1:02d}"
            directory.mkdir(mode=0o700)
            self.guards.append(pilot.BudgetTransport(self.inner, Journal(directory), pilot.profile()))
        return self.guards[-1].handle_request(request)

    def summary(self):
        return {"paid_attempts": self.calls,
                "reserved_usd": str(sum((guard.reserved for guard in self.guards), Decimal(0))),
                "usage": [{"budget": number, **usage}
                          for number, guard in enumerate(self.guards, 1) for usage in guard.usages],
                "unresolved": [guard.block_reason for guard in self.guards if guard.block_reason],
                "automatic_retry": False, "billing_verified": False}

    def close(self):
        self.inner.close()


def output_directory(parent):
    require(not Path(parent).is_symlink(), "PARENT_SYMLINK")
    parent = Path(parent).resolve()
    return parent.with_name(parent.name + "-through-round-8")


def execute(parent, expected_parent_sha256, credential, *, inner=None):
    """One continuation destination per parent; no paid retry or overwrite."""
    from google import genai
    from google.genai import types

    require(isinstance(credential, str) and credential and not any(c.isspace() for c in credential),
            "CREDENTIAL_MISSING_OR_INVALID")
    directory = output_directory(parent)
    parent = Path(parent).resolve()
    with exclusive_execution(directory):
        require(not directory.exists() and not directory.is_symlink(), "CONTINUATION_ALREADY_ATTEMPTED")
        dialogue, parent_manifest, identity = verify_parent(parent, expected_parent_sha256)
        frozen_sources = sources()
        manifest = configuration(model=pilot.MODEL, rounds=FINAL_ROUND, max_calls=ADDITIONAL_CALLS,
                                 max_input_bytes=100000, max_output_tokens=pilot.OUTPUT_LIMIT)
        manifest.update({"run_id": str(uuid.uuid4()), "parent_run_id": parent_manifest["run_id"],
                         "parent_directory": str(parent), "parent_evidence": identity,
                         "parent_evidence_sha256": expected_parent_sha256,
                         "continuation_source_identity": frozen_sources, "first_new_round": 3,
                         "additional_calls": ADDITIONAL_CALLS,
                         "maximum_additional_usd": str(ADDITIONAL_CALLS * pilot.cost(pilot.INPUT_LIMIT, pilot.OUTPUT_LIMIT)),
                         "pilot_budget_profile": pilot.profile()})
        directory.mkdir(mode=0o700)
        journal, runtime = Journal(directory), Journal(directory / "dialogue")
        runtime.prepare(manifest, resume=False)
        transport = ContinuationTransport(inner or httpx.HTTPTransport(retries=0), directory, frozen_sources)
        sequence = 8
        status = "observation_period_reached"
        try:
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=120) as http:
                with genai.Client(vertexai=False, api_key=credential, http_options=types.HttpOptions(
                        base_url="https://generativelanguage.googleapis.com", api_version="v1beta",
                        httpx_client=http, timeout=120000,
                        retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    for number in range(3, FINAL_ROUND + 1):
                        transport.check()
                        views = dialogue.inputs()
                        requests = {actor: {"run_id": manifest["run_id"], "sequence": sequence + index,
                                    "round": number, "actor": actor, "kwargs": _request(views[actor], manifest)}
                                    for index, actor in enumerate(ACTORS)}
                        if any(len(encode(request["kwargs"]).encode("utf-8")) > manifest["max_input_bytes"]
                               for request in requests.values()):
                            status = "input_limit_reached_no_history_truncated"
                            break
                        replies = {}
                        for actor, request in requests.items():
                            replies[actor] = _response_text(runtime, sequence, request, client, manifest)
                            sequence += 1
                            transport.check()
                        state = dialogue.commit(replies, expected_round=number)
                        runtime.write(f"round-{number:08d}.json", {"round": number,
                            "inputs_sha256": digest(views), "state_sha256": digest(state),
                            "call_sequences": list(range(sequence - 4, sequence))})
            require(identity == evidence_identity(parent), "PARENT_CHANGED_DURING_CONTINUATION")
            transport.check()
            result = {"kind": "v2_continued_dialogue_private_audit", "status": status,
                      "physical_execution": False, "program_execution": False,
                      "model_calls": sequence - 8, "parent_model_calls": 8,
                      "total_model_calls": sequence, "manifest_sha256": digest(manifest),
                      "parent_evidence_sha256": expected_parent_sha256, "state": dialogue.snapshot()}
            runtime.write("result.json", result)
            journal.write("continuation-summary.json", {"status": status, **transport.summary()})
            return result
        except BaseException as error:
            journal.write("continuation-stopped.json", {
                "status": "technical_stop", "exception_type": type(error).__name__,
                "committed_round": dialogue.snapshot()["round"], "delivery_state": dialogue.snapshot(),
                "not_an_agent_decision": True, **transport.summary()})
            raise


def main():
    parser = argparse.ArgumentParser(description="保存済みV2の2巡を検証し、最大24生成で8巡目まで続行。")
    parser.add_argument("--parent-directory", type=Path, required=True)
    parser.add_argument("--expected-parent-sha256", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.parent_directory, args.expected_parent_sha256,
                         pilot.load_credential(args.credential_file))
    except Exception as error:
        raise SystemExit("続行を停止しました。自動再実行はしません。種類: " + type(error).__name__) from None
    print(f"V2を{result['state']['round']}巡目まで記録しました。追加生成: {result['model_calls']}回。")


if __name__ == "__main__":
    main()
