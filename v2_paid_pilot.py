"""One small, explicitly requested V2 pilot with a wire-level spending guard.

The guard counts the exact generateContent request, including system text,
before forwarding it. It does not change Agent inputs or synthesize decisions.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import stat

import httpx

from homeostasis_core.execution_lock import exclusive_execution
from model_response_json import load_response_object
from v2_autonomous import Journal, run_dialogue, source_identity
from v2_dialogue import digest, encode


MODEL = "gemini-3.6-flash"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/" + MODEL
INPUT_LIMIT = 12000
OUTPUT_LIMIT = 8192
CALL_LIMIT = 8
INPUT_RATE = Decimal("0.75")
OUTPUT_RATE = Decimal("3.75")
USD_LIMIT = Decimal("0.32")


class PilotStopped(RuntimeError):
    pass


def sources():
    return {**source_identity(), Path(__file__).name:
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def profile():
    if date.today() > date(2026, 12, 31):
        raise PilotStopped("PUBLISHED_PRICE_WINDOW_EXPIRED")
    return {"kind": "v2_first_small_live_dialogue_pilot", "model": MODEL,
            "rounds": 2, "max_calls": CALL_LIMIT, "max_input_tokens": INPUT_LIMIT,
            "max_output_tokens_including_thoughts": OUTPUT_LIMIT,
            "input_usd_per_million": str(INPUT_RATE),
            "output_usd_per_million": str(OUTPUT_RATE),
            "usd_reservation_limit": str(USD_LIMIT),
            "source_identity": sources(), "model_defaults_preserved": True,
            "price_source": "https://ai.google.dev/gemini-api/docs/pricing#gemini-3.6-flash",
            "price_valid_through": "2026-12-31", "price_checked_on": "2026-09-20",
            "yen_allowance_basis": "200 JPY per USD plus 10 percent; planning assumption, not an exchange-rate quote",
            "yen_allowance": "70", "account_billing_verified": False,
            "automatic_retries": False, "physical_execution": False}


def cost(input_tokens, output_tokens):
    return (Decimal(input_tokens) * INPUT_RATE + Decimal(output_tokens) * OUTPUT_RATE) / 1000000


class BudgetTransport(httpx.BaseTransport):
    def __init__(self, inner, journal, frozen_profile):
        self.inner = inner
        self.journal = journal
        self.profile_json = encode(frozen_profile)
        self.calls = 0
        self.reserved = Decimal(0)
        self.block_reason = None
        self.usages = []

    def _check_source(self):
        if sources() != json.loads(self.profile_json)["source_identity"]:
            raise PilotStopped("PILOT_SOURCE_CHANGED")

    def handle_request(self, request):
        self._check_source()
        if self.block_reason:
            raise PilotStopped(self.block_reason)
        if request.method != "POST" or str(request.url) != ENDPOINT + ":generateContent":
            raise PilotStopped("UNEXPECTED_PAID_ENDPOINT")
        if self.calls >= CALL_LIMIT:
            raise PilotStopped("PAID_CALL_LIMIT_REACHED")
        body = load_response_object(request.content.decode("utf-8"))
        if set(body) != {"contents", "systemInstruction", "generationConfig"}:
            raise PilotStopped("UNEXPECTED_PAID_REQUEST_FIELDS")
        config = body["generationConfig"]
        if config != {"responseMimeType": "application/json", "maxOutputTokens": OUTPUT_LIMIT}:
            raise PilotStopped("UNEXPECTED_GENERATION_CONFIGURATION")
        index = self.calls
        counted_request = {"generateContentRequest": {"model": "models/" + MODEL, **body}}
        self.journal.write(f"count-{index:02d}.request.json", counted_request)
        count_request = httpx.Request("POST", ENDPOINT + ":countTokens",
            headers={"x-goog-api-key": request.headers["x-goog-api-key"],
                     "content-type": "application/json"},
            json=counted_request, extensions=request.extensions.copy())
        count_response = self.inner.handle_request(count_request)
        try:
            count_response.read()
            if count_response.status_code != 200:
                self.journal.write(f"count-{index:02d}.error.json", {"status": count_response.status_code})
                raise PilotStopped("INPUT_COUNT_FAILED_NO_GENERATION")
            count_data = load_response_object(count_response.text)
            self.journal.write(f"count-{index:02d}.response.json", count_data)
        finally:
            count_response.close()
        input_tokens = count_data.get("totalTokens")
        if type(input_tokens) is not int or not 0 <= input_tokens <= INPUT_LIMIT:
            raise PilotStopped("INPUT_TOKEN_LIMIT_OR_MISSING_COUNT")
        # Reserve the full accepted input allowance, not an optimistic estimate.
        upper = cost(INPUT_LIMIT, OUTPUT_LIMIT)
        if self.reserved + upper > USD_LIMIT:
            raise PilotStopped("USD_RESERVATION_LIMIT_REACHED")
        self._check_source()
        reservation = {"sequence": index, "request": body,
                       "count_response_sha256": digest(count_data), "input_tokens": input_tokens,
                       "maximum_output_tokens": OUTPUT_LIMIT, "reserved_usd": str(upper)}
        self.journal.write(f"paid-{index:02d}.reservation.json", reservation)
        # Consumed before the wire call, including timeouts or an ambiguous crash.
        self.calls += 1
        self.reserved += upper
        self.block_reason = "PREVIOUS_PAID_REQUEST_UNRESOLVED"
        response = self.inner.handle_request(request)
        response.read()
        self.journal.write(f"paid-{index:02d}.wire-response.json", {
            "status": response.status_code, "reservation_sha256": digest(reservation),
            "body_base64": base64.b64encode(response.content).decode("ascii")})
        try:
            response_data = load_response_object(response.text)
            usage = response_data.get("usageMetadata", {})
            counts = [usage.get(name) for name in
                      ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount")]
            known = all(type(value) is int and value >= 0 for value in counts)
            actual = cost(counts[0], counts[1] + counts[2]) if known else None
            within_limits = known and counts[0] <= INPUT_LIMIT and counts[1] + counts[2] <= OUTPUT_LIMIT
            self.usages.append({"sequence": index, "usage": usage,
                                "estimated_usd": str(actual) if actual is not None else None,
                                "within_configured_limits": within_limits,
                                "billing_verified": False})
            self.journal.write(f"paid-{index:02d}.usage.json", self.usages[-1])
            if response.status_code == 200 and within_limits and actual <= upper:
                self.block_reason = None
            else:
                self.block_reason = "USAGE_UNVERIFIED_OR_RESERVATION_EXCEEDED_NO_FURTHER_CALLS"
        except (ValueError, TypeError, KeyError):
            self.block_reason = "UNREADABLE_PAID_RESPONSE_NO_FURTHER_CALLS"
        # Return even malformed output so the runtime can preserve its own receipt.
        return response

    def close(self):
        self.inner.close()


def execute(directory, credential, *, inner=None):
    from google import genai
    from google.genai import types

    if not isinstance(credential, str) or not credential or any(c.isspace() for c in credential):
        raise PilotStopped("CREDENTIAL_MISSING_OR_INVALID")
    frozen = profile()
    directory = Path(directory)
    with exclusive_execution(directory):
        if directory.is_symlink():
            raise PilotStopped("OUTPUT_IS_SYMLINK")
        directory.mkdir(mode=0o700)  # No overwrite, retry or implicit new allowance.
        journal = Journal(directory)
        journal.write("pilot-profile.json", frozen)
        transport = BudgetTransport(inner or httpx.HTTPTransport(retries=0), journal, frozen)
        try:
            with httpx.Client(transport=transport, trust_env=False,
                              follow_redirects=False, timeout=120) as http:
                with genai.Client(vertexai=False, api_key=credential, http_options=types.HttpOptions(
                        base_url="https://generativelanguage.googleapis.com", api_version="v1beta",
                        httpx_client=http, timeout=120000,
                        retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    result = run_dialogue(client, directory / "dialogue", model=MODEL,
                        rounds=2, max_calls=CALL_LIMIT, max_input_bytes=100000,
                        max_output_tokens=OUTPUT_LIMIT)
            journal.write("pilot-summary.json", {
                "status": result["status"], "paid_attempts": transport.calls,
                "reserved_usd": str(transport.reserved), "usage": transport.usages,
                "further_calls_blocked_reason": transport.block_reason,
                "physical_execution": False, "billing_verified": False})
            return result
        except BaseException as error:
            if not journal.exists("pilot-stopped.json"):
                journal.write("pilot-stopped.json", {
                    "status": "technical_stop", "exception_type": type(error).__name__,
                    "paid_attempts": transport.calls, "reserved_usd": str(transport.reserved),
                    "usage": transport.usages, "automatic_retry": False})
            raise


def load_credential(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_uid != os.getuid():
            raise PilotStopped("CREDENTIAL_FILE_NOT_PRIVATE")
        return handle.read().strip()


def main():
    parser = argparse.ArgumentParser(description="V2の初回小規模試運転。最大8回・事前計数・自動再試行なし。")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        execute(args.output_directory, load_credential(args.credential_file))
    except Exception as error:
        # Never display credentials, HTTP headers, raw exceptions or private Agent text.
        raise SystemExit("試運転を停止しました。自動再実行はしません。記録を確認します。種類: "
                         + type(error).__name__) from None
    print("V2の2巡の自由対話を記録しました。使用量と内容を確認してから次へ進みます。")


if __name__ == "__main__":
    main()
