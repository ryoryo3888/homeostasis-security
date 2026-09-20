"""Four fresh eight-round trials, sharing the V2 allowance with the first trial.

The existing Agent protocol is unchanged. Reservations are released only after
durable, bounded provider usage, never after a timeout or an uncertain receipt.
"""
from __future__ import annotations

import argparse
import base64
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import httpx

from homeostasis_core.execution_lock import exclusive_execution
from v2_autonomous import Journal, configuration, run_dialogue, _request, _response_text
from v2_dialogue import ACTORS, digest
import v2_continue_pilot as continuation
import v2_finish_pilot as finish
import v2_paid_pilot as pilot

require = continuation.require
INPUT_LIMIT = 24000
NEW_TRIALS = 4
ROUNDS = 8
CALL_LIMIT = NEW_TRIALS * ROUNDS * len(ACTORS)
# 2.27 * 200 JPY/USD * 1.10 = 499.40 planning yen, including the first trial.
TOTAL_USD_LIMIT = Decimal("2.27")


def sources():
    return {**finish.sources(), Path(__file__).name:
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def usage_cost(usage, input_limit=INPUT_LIMIT):
    counts = [usage.get(k) for k in
              ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount")]
    require(all(type(c) is int and c >= 0 for c in counts)
            and counts[0] <= input_limit and counts[1] + counts[2] <= pilot.OUTPUT_LIMIT,
            "UNKNOWN_OR_UNBOUNDED_USAGE")
    return pilot.cost(counts[0], counts[1] + counts[2])


def verify_wire(journal, index, request, manifest, text):
    reservation = journal.read(f"paid-{index:02d}.reservation.json")
    require(reservation["request"] == finish.wire_request(request, manifest), "WIRE_INPUT_MISMATCH")
    require(journal.read(f"count-{index:02d}.request.json") == {
        "generateContentRequest": {"model": "models/" + pilot.MODEL, **reservation["request"]}}, "COUNT_INPUT_MISMATCH")
    count = journal.read(f"count-{index:02d}.response.json")
    require(digest(count) == reservation["count_response_sha256"]
            and count["totalTokens"] == reservation["input_tokens"]
            and type(count["totalTokens"]) is int and 0 <= count["totalTokens"] <= INPUT_LIMIT,
            "COUNT_RECEIPT_MISMATCH")
    wire = journal.read(f"paid-{index:02d}.wire-response.json")
    require(wire["status"] == 200 and wire["reservation_sha256"] == digest(reservation), "WIRE_RECEIPT_MISMATCH")
    raw = json.loads(base64.b64decode(wire["body_base64"], validate=True))
    candidates = raw["candidates"]
    require(len(candidates) == 1 and candidates[0]["finishReason"] == "STOP"
            and "".join(p["text"] for p in candidates[0]["content"]["parts"] if not p.get("thought")) == text,
            "WIRE_TEXT_MISMATCH")
    usage = journal.read(f"paid-{index:02d}.usage.json")
    actual = usage_cost(raw["usageMetadata"])
    require(usage["usage"] == raw["usageMetadata"] and usage["within_configured_limits"]
            and Decimal(usage["estimated_usd"]) == actual, "USAGE_MISMATCH")
    return actual


def verify_first_trial(directory, expected_sha256):
    """Replay the completed, three-part first trial and recompute all its spend."""
    directory = Path(directory)
    identity = continuation.evidence_identity(directory)
    require(digest(identity) == expected_sha256, "FIRST_TRIAL_EVIDENCE_CHANGED")
    runtime, journal = Journal(directory / "dialogue"), Journal(directory)
    manifest = runtime.read("manifest.json")
    require(manifest["source_chain"] == finish.sources(), "FIRST_TRIAL_SOURCE_CHANGED")
    dialogue, previous, previous_identity, spent = finish.verify_stopped(
        Path(manifest["previous_directory"]), manifest["previous_evidence_sha256"])
    require(manifest["previous_evidence"] == previous_identity, "FIRST_TRIAL_PARENT_CHANGED")
    expected = configuration(model=pilot.MODEL, rounds=8, max_calls=12,
                             max_input_bytes=200000, max_output_tokens=pilot.OUTPUT_LIMIT)
    require(all(manifest.get(k) == v for k, v in expected.items()), "FIRST_TRIAL_CONFIGURATION_CHANGED")
    original = Journal(Path(previous["parent_directory"]))
    for index in range(8):
        usage = original.read(f"paid-{index:02d}.usage.json")
        actual = usage_cost(usage["usage"], pilot.INPUT_LIMIT)
        require(Decimal(usage["estimated_usd"]) == actual, "FIRST_TRIAL_SPEND_CHANGED")
        spent += actual
    summary, result = journal.read("completion-summary.json"), runtime.read("result.json")
    require(summary["status"] == result["status"] == "observation_period_reached"
            and summary["paid_attempts"] == result["model_calls"] == 12
            and result["total_model_calls"] == 32 and summary["unresolved"] is None
            and len(summary["usage"]) == 12 and result["manifest_sha256"] == digest(manifest),
            "FIRST_TRIAL_NOT_COMPLETE")
    for pattern in ("paid-*.reservation.json", "paid-*.wire-response.json", "paid-*.usage.json"):
        require(len(list(directory.glob(pattern))) == 12, "FIRST_TRIAL_EXTRA_ATTEMPT")
    sequence = 20
    for number in range(6, 9):
        views, replies = dialogue.inputs(), {}
        for actor in ACTORS:
            request = {"run_id": manifest["run_id"], "sequence": sequence, "round": number,
                       "actor": actor, "kwargs": _request(views[actor], manifest)}
            require(runtime.exists(f"call-{sequence:08d}.request.json")
                    and runtime.exists(f"call-{sequence:08d}.sdk.json"), "FIRST_TRIAL_RECEIPT_MISSING")
            replies[actor] = _response_text(runtime, sequence, request, None, manifest)
            spent += verify_wire(journal, sequence - 20, request, manifest, replies[actor])
            require(journal.read(f"paid-{sequence-20:02d}.usage.json") == summary["usage"][sequence-20],
                    "FIRST_TRIAL_SUMMARY_MISMATCH")
            sequence += 1
        state = dialogue.commit(replies, expected_round=number)
        require(runtime.read(f"round-{number:08d}.json") == {"round": number,
            "inputs_sha256": digest(views), "state_sha256": digest(state),
            "call_sequences": list(range(sequence-4, sequence))}, "FIRST_TRIAL_REPLAY_MISMATCH")
    require(result["state"] == dialogue.snapshot(), "FIRST_TRIAL_RESULT_MISMATCH")
    require(identity == continuation.evidence_identity(directory), "FIRST_TRIAL_CHANGED_DURING_REPLAY")
    return spent, identity


class RepetitionTransport(httpx.BaseTransport):
    """One ledger for all four trials; reserve a full round before its first call."""

    def __init__(self, inner, journal, prior_spend, source_identity):
        require(prior_spend.is_finite() and 0 <= prior_spend <= TOTAL_USD_LIMIT, "INVALID_PRIOR_SPEND")
        self.inner, self.journal = inner, journal
        self.source_identity = source_identity.copy()
        self.prior_spend, self.spent = prior_spend, prior_spend
        self.calls, self.pending, self.block_reason = 0, Decimal(0), None
        self.usages = []

    def check(self):
        require(sources() == self.source_identity, "REPETITION_SOURCE_CHANGED")
        pilot.profile()
        require(self.block_reason is None and self.pending == 0, "UNRESOLVED_PAID_REQUEST")

    def handle_request(self, request):
        self.check()
        require(request.method == "POST" and str(request.url) == pilot.ENDPOINT + ":generateContent",
                "UNEXPECTED_PAID_ENDPOINT")
        require(self.calls < CALL_LIMIT, "FOUR_TRIAL_CALL_LIMIT")
        body = json.loads(request.content)
        require(set(body) == {"contents", "systemInstruction", "generationConfig"}
                and body["generationConfig"] == {"responseMimeType": "application/json", "maxOutputTokens": pilot.OUTPUT_LIMIT},
                "UNEXPECTED_GENERATION_SETTINGS")
        view = json.loads(body["contents"][0]["parts"][0]["text"])
        require(view["actor"] == ACTORS[self.calls % 4] and view["round"] == (self.calls // 4) % ROUNDS + 1,
                "UNEXPECTED_TRIAL_SEQUENCE")
        upper = pilot.cost(INPUT_LIMIT, pilot.OUTPUT_LIMIT)
        remaining_in_round = len(ACTORS) - self.calls % len(ACTORS)
        require(self.spent + remaining_in_round * upper <= TOTAL_USD_LIMIT, "TOTAL_BUDGET_BEFORE_NEXT_ROUND")
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
        tokens = count.get("totalTokens")
        require(type(tokens) is int and 0 <= tokens <= INPUT_LIMIT, "INPUT_LIMIT_NO_GENERATION")
        self.check()
        reservation = {"sequence": index, "trial": 2 + index // 32, "request": body,
            "input_tokens": tokens, "count_response_sha256": digest(count),
            "maximum_output_tokens": pilot.OUTPUT_LIMIT, "reserved_usd": str(upper),
            "confirmed_total_usd_before_call": str(self.spent),
            "remaining_round_reservation_usd": str(remaining_in_round * upper),
            "total_usd_limit": str(TOTAL_USD_LIMIT)}
        self.journal.write(f"paid-{index:02d}.reservation.json", reservation)
        self.calls += 1
        self.pending, self.block_reason = upper, "PAID_REQUEST_UNRESOLVED"
        response = self.inner.handle_request(request)
        response.read()
        self.journal.write(f"paid-{index:02d}.wire-response.json", {"status": response.status_code,
            "reservation_sha256": digest(reservation), "body_base64": base64.b64encode(response.content).decode("ascii")})
        try:
            usage = response.json().get("usageMetadata", {})
            actual = usage_cost(usage)
            require(response.status_code == 200 and actual <= upper, "UNRESOLVED_USAGE")
            record = {"sequence": index, "usage": usage, "estimated_usd": str(actual),
                      "within_configured_limits": True, "billing_verified": False}
            self.journal.write(f"paid-{index:02d}.usage.json", record)
            self.usages.append(record)
            self.spent += actual
            self.pending, self.block_reason = Decimal(0), None
        except (pilot.PilotStopped, ValueError, TypeError, KeyError, AttributeError):
            pass  # Keep the reservation and raw receipt, then forbid further calls.
        return response

    def summary(self):
        return {"paid_attempts": self.calls, "prior_estimated_usd": str(self.prior_spend),
                "confirmed_total_estimated_usd": str(self.spent), "unresolved_reserved_usd": str(self.pending),
                "total_usd_limit": str(TOTAL_USD_LIMIT), "unresolved": self.block_reason,
                "usage": self.usages, "automatic_retry": False, "billing_verified": False}

    def close(self):
        self.inner.close()


def output_directory(first_trial):
    require(not Path(first_trial).is_symlink(), "FIRST_TRIAL_SYMLINK")
    first_trial = Path(first_trial).resolve()
    return first_trial.with_name(first_trial.name + "-five-runs")


def execute(first_trial, expected_sha256, credential, *, inner=None):
    from google import genai
    from google.genai import types

    require(isinstance(credential, str) and credential and not any(c.isspace() for c in credential), "INVALID_CREDENTIAL")
    destination = output_directory(first_trial)
    with exclusive_execution(destination):
        require(not destination.exists() and not destination.is_symlink(), "REPETITION_ALREADY_ATTEMPTED")
        spent, identity = verify_first_trial(first_trial, expected_sha256)
        pilot.profile()
        frozen = sources()
        destination.mkdir(mode=0o700)
        journal = Journal(destination)
        journal.write("batch-profile.json", {"first_trial_directory": str(Path(first_trial).resolve()),
            "first_trial_sha256": expected_sha256, "first_trial_identity": identity,
            "source_identity": frozen, "prior_estimated_usd": str(spent),
            "total_usd_limit": str(TOTAL_USD_LIMIT), "planning_yen_per_usd": "220",
            "planning_yen_ceiling": "499.40", "new_trials": NEW_TRIALS, "rounds_each": ROUNDS,
            "max_input_tokens": INPUT_LIMIT, "max_output_tokens": pilot.OUTPUT_LIMIT,
            "max_paid_calls": CALL_LIMIT, "automatic_retry": False,
            "condition_changes": False, "fresh_memory_each_trial": True,
            "input_limit_note": "First trial used 12000 through round 5 then 24000; all new trials use 24000. No truncation.",
            "price_profile": pilot.profile()})
        transport = RepetitionTransport(inner or httpx.HTTPTransport(retries=0), journal, spent, frozen)
        completed = []
        try:
            with httpx.Client(transport=transport, trust_env=False, follow_redirects=False, timeout=120) as http:
                with genai.Client(vertexai=False, api_key=credential, http_options=types.HttpOptions(
                        base_url="https://generativelanguage.googleapis.com", api_version="v1beta",
                        httpx_client=http, timeout=120000,
                        retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    for number in range(2, NEW_TRIALS + 2):
                        transport.check()
                        result = run_dialogue(client, destination / f"trial-{number:02d}", model=pilot.MODEL,
                            rounds=ROUNDS, max_calls=ROUNDS * len(ACTORS), max_input_bytes=200000,
                            max_output_tokens=pilot.OUTPUT_LIMIT)
                        transport.check()
                        require(result["status"] == "observation_period_reached" and result["state"]["round"] == ROUNDS,
                                "TRIAL_INCOMPLETE")
                        completed.append(number)
                        journal.write(f"trial-{number:02d}-summary.json", {"trial": number,
                            "result_sha256": digest(result), "completed_new_trials": completed.copy(), **transport.summary()})
                        print(f"Trial {number}/5 complete; total estimated USD {transport.spent}.", flush=True)
            require(verify_first_trial(first_trial, expected_sha256)[1] == identity, "FIRST_TRIAL_CHANGED")
            summary = {"status": "five_trials_completed", "completed_new_trials": completed,
                       "physical_execution": False, **transport.summary()}
            journal.write("batch-summary.json", summary)
            return summary
        except BaseException as error:
            journal.write("batch-stopped.json", {"status": "technical_stop", "exception_type": type(error).__name__,
                "completed_new_trials": completed, "not_an_agent_decision": True, **transport.summary()})
            raise


def main():
    parser = argparse.ArgumentParser(description="既存1回を含めV2を合計5回。全体の費用上限を共有し自動再実行しない。")
    parser.add_argument("--first-trial-directory", type=Path, required=True)
    parser.add_argument("--expected-first-trial-sha256", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        execute(args.first_trial_directory, args.expected_first_trial_sha256, pilot.load_credential(args.credential_file))
    except Exception as error:
        raise SystemExit("停止しました。自動再実行しません。種類: " + type(error).__name__) from None


if __name__ == "__main__":
    main()
