from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

import v2_repeat_pilot as repeat
import v2_finish_pilot as finish
import v2_continue_pilot as continuation
import v2_paid_pilot as pilot
from v2_autonomous import Journal, SYSTEM_INSTRUCTION
from v2_dialogue import ACTORS, Dialogue, digest, encode


def reply(view):
    actor, number = view["actor"], view["round"]
    return {"outgoing": [{"to": ["B" if actor == "A" else "A"], "body": f"message {actor} {number}"}],
            "activities": [], "private_note": f"private {actor} {number}"}


class RepeatPilotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name) / "parent"
        self.seen = []
        pilot.execute(self.parent, "offline-dummy", inner=httpx.MockTransport(self.handler))
        with self.assertRaises(Exception):
            continuation.execute(self.parent, digest(continuation.evidence_identity(self.parent)),
                                 "offline-dummy", inner=httpx.MockTransport(self.handler))
        stopped = continuation.output_directory(self.parent)
        finish.execute(stopped, digest(continuation.evidence_identity(stopped)), "offline-dummy",
                       inner=httpx.MockTransport(self.handler))
        self.first = finish.output_directory(stopped)
        self.before = continuation.evidence_identity(self.first)
        self.pin = digest(self.before)
        self.original_seen = self.seen.copy()
        self.seen.clear()

    def handler(self, request, *, count=None, thoughts=10, output=50, stop="STOP"):
        body = json.loads(request.content)
        paid = request.url.path.endswith(":generateContent")
        content = body if paid else body["generateContentRequest"]
        view = json.loads(content["contents"][0]["parts"][0]["text"])
        tokens = count if count is not None else (12242 if view["round"] >= 6 else 1000)
        if not paid:
            return httpx.Response(200, json={"totalTokens": tokens})
        self.seen.append((view, body))
        usage = {"promptTokenCount": tokens, "candidatesTokenCount": output,
                 "totalTokenCount": tokens + output + (thoughts or 0)}
        if thoughts is not None:
            usage["thoughtsTokenCount"] = thoughts
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model",
            "parts": [{"text": encode(reply(view))}]}, "finishReason": stop}], "usageMetadata": usage})

    def execute(self, handler=None, pin=None):
        return repeat.execute(self.first, pin or self.pin, "offline-dummy", inner=httpx.MockTransport(handler or self.handler))

    def test_four_fresh_trials_match_original_inputs_and_share_ledger(self):
        summary = self.execute()
        self.assertEqual(summary["completed_new_trials"], [2, 3, 4, 5])
        self.assertEqual(summary["paid_attempts"], 128)
        self.assertEqual(self.seen, self.original_seen * 4)
        self.assertEqual(continuation.evidence_identity(self.first), self.before)
        first_cost, _ = repeat.verify_first_trial(self.first, self.pin)
        self.assertEqual(Decimal(summary["confirmed_total_estimated_usd"]), first_cost * 5)
        self.assertLessEqual(Decimal(summary["confirmed_total_estimated_usd"]), repeat.TOTAL_USD_LIMIT)
        directory = repeat.output_directory(self.first)
        expected = Journal(self.first / "dialogue").read("result.json")["state"]
        for number in range(2, 6):
            runtime = Journal(directory / f"trial-{number:02d}")
            self.assertEqual(runtime.read("result.json")["state"], expected)
            manifest = runtime.read("manifest.json")
            for sequence in range(32):
                request = runtime.read(f"call-{sequence:08d}.request.json")
                sdk = runtime.read(f"call-{sequence:08d}.sdk.json")["sdk_response"]
                repeat.verify_wire(Journal(directory), (number-2)*32+sequence, request, manifest,
                                   sdk["candidates"][0]["content"]["parts"][0]["text"])
        for view, body in self.seen:
            self.assertEqual(body["systemInstruction"]["parts"][0]["text"], SYSTEM_INSTRUCTION)
            if view["actor"] in ("C", "COORDINATOR"):
                self.assertNotIn("message A", encode(view))
                self.assertNotIn("private A", encode(view))

    def test_destination_cannot_reset_budget_or_repeat_paid_calls(self):
        self.execute()
        with self.assertRaisesRegex(pilot.PilotStopped, "ALREADY_ATTEMPTED"):
            self.execute()
        self.assertEqual(len(self.seen), 128)

    def test_wrong_first_trial_pin_prevents_network(self):
        with self.assertRaisesRegex(pilot.PilotStopped, "EVIDENCE_CHANGED"):
            self.execute(pin="wrong")
        self.assertEqual(self.seen, [])

    def test_forged_prior_cost_rejected_even_with_new_digest(self):
        path = self.first / "paid-00.usage.json"
        wrapped = json.loads(path.read_text())
        wrapped["payload"]["estimated_usd"] = "0"
        wrapped["sha256"] = digest(wrapped["payload"])
        path.write_text(encode(wrapped))
        with self.assertRaisesRegex(pilot.PilotStopped, "USAGE_MISMATCH"):
            self.execute(pin=digest(continuation.evidence_identity(self.first)))
        self.assertEqual(self.seen, [])

    def test_oversized_input_never_generates(self):
        with self.assertRaises(Exception):
            self.execute(lambda r: self.handler(r, count=24001))
        self.assertEqual(self.seen, [])

    def test_missing_prior_receipt_is_read_only_and_never_regenerated(self):
        path = self.first / "dialogue/call-00000020.request.json"
        path.unlink()
        before = continuation.evidence_identity(self.first)
        with self.assertRaisesRegex(pilot.PilotStopped, "RECEIPT_MISSING"):
            self.execute(pin=digest(before))
        self.assertEqual(continuation.evidence_identity(self.first), before)
        self.assertEqual(self.seen, [])

    def test_unknown_usage_blocks_all_subsequent_calls_and_retains_reservation(self):
        with self.assertRaises(Exception):
            self.execute(lambda r: self.handler(r, thoughts=None))
        self.assertEqual(len(self.seen), 1)
        stopped = Journal(repeat.output_directory(self.first)).read("batch-stopped.json")
        self.assertEqual(stopped["unresolved_reserved_usd"], "0.04872")
        self.assertEqual(stopped["completed_new_trials"], [])

    def test_timeout_never_retries_and_cannot_restart(self):
        attempts = []
        def handler(request):
            if request.url.path.endswith(":countTokens"):
                return self.handler(request)
            attempts.append(request)
            raise httpx.ReadTimeout("offline timeout")
        with self.assertRaises(Exception):
            self.execute(handler)
        with self.assertRaises(pilot.PilotStopped):
            self.execute()
        self.assertEqual(len(attempts), 1)

    def test_incomplete_response_preserved_without_retry_or_next_trial(self):
        with self.assertRaises(Exception):
            self.execute(lambda r: self.handler(r, stop="MAX_TOKENS"))
        self.assertEqual(len(self.seen), 1)
        self.assertTrue((repeat.output_directory(self.first) / "trial-02/call-00000000.sdk.json").exists())

    def transport(self, prior=Decimal(0), handler=None):
        directory = self.parent.parent / "transport"
        directory.mkdir()
        return repeat.RepetitionTransport(httpx.MockTransport(handler or self.handler), Journal(directory), prior, repeat.sources())

    def request(self, sequence=0):
        view = {"actor": ACTORS[sequence % 4], "round": (sequence // 4) % 8 + 1}
        body = {"contents": [{"parts": [{"text": encode(view)}]}], "systemInstruction": {},
                "generationConfig": {"responseMimeType":"application/json", "maxOutputTokens":8192}}
        return httpx.Request("POST", pilot.ENDPOINT + ":generateContent", json=body, headers={"x-goog-api-key":"offline-dummy"})

    def test_reserve_full_round_including_prior_spend_before_any_network(self):
        calls = []
        transport = self.transport(prior=repeat.TOTAL_USD_LIMIT - Decimal("0.19"), handler=lambda r: calls.append(r))
        with self.assertRaisesRegex(pilot.PilotStopped, "TOTAL_BUDGET"):
            transport.handle_request(self.request())
        self.assertEqual(calls, [])

    def test_exact_budget_boundary_and_no_reset_on_next_round(self):
        upper = pilot.cost(24000,8192)
        transport = self.transport(repeat.TOTAL_USD_LIMIT - upper * 4,
                                   lambda r: self.handler(r, count=24000, output=8192, thoughts=0))
        for sequence in range(4):
            transport.handle_request(self.request(sequence))
        self.assertEqual(transport.spent, repeat.TOTAL_USD_LIMIT)
        with self.assertRaisesRegex(pilot.PilotStopped, "TOTAL_BUDGET"):
            transport.handle_request(self.request(4))
        self.assertEqual(len(self.seen), 4)

    def test_source_change_before_or_after_count_blocks_generation(self):
        transport = self.transport()
        original = repeat.sources()
        with patch.object(repeat, "sources", return_value={}):
            with self.assertRaisesRegex(pilot.PilotStopped, "SOURCE_CHANGED"):
                transport.handle_request(self.request())
        with patch.object(repeat, "sources", side_effect=[original, {}]):
            with self.assertRaisesRegex(pilot.PilotStopped, "SOURCE_CHANGED"):
                transport.handle_request(self.request())
        self.assertEqual(self.seen, [])

    def test_call_limit_and_unexpected_endpoint_are_blocked(self):
        transport = self.transport()
        transport.calls = 128
        with self.assertRaisesRegex(pilot.PilotStopped, "CALL_LIMIT"):
            transport.handle_request(self.request())
        transport.calls = 0
        with self.assertRaisesRegex(pilot.PilotStopped, "ENDPOINT"):
            transport.handle_request(httpx.Request("POST", "https://example.invalid"))
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
