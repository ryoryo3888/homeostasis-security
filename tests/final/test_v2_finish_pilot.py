from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

import v2_finish_pilot as finish
import v2_continue_pilot as continuation
import v2_paid_pilot as pilot
from v2_autonomous import Journal, SYSTEM_INSTRUCTION
from v2_dialogue import ACTORS, Dialogue, digest, encode


def reply(view):
    actor, number = view["actor"], view["round"]
    return {"outgoing": [{"to": ["B" if actor == "A" else "A"], "body": f"message {actor} {number}"}],
            "activities": [], "private_note": f"private {actor} {number}"}


class FinishPilotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name) / "parent"
        self.seen = []
        pilot.execute(self.parent, "offline-dummy", inner=httpx.MockTransport(self.handler))
        with self.assertRaises(Exception):
            continuation.execute(self.parent, digest(continuation.evidence_identity(self.parent)),
                                 "offline-dummy", inner=httpx.MockTransport(self.handler))
        self.stopped = continuation.output_directory(self.parent)
        self.pin = digest(continuation.evidence_identity(self.stopped))
        self.before = continuation.evidence_identity(self.stopped)
        self.seen.clear()

    def handler(self, request, *, count=None, thoughts=10, stop="STOP"):
        body = json.loads(request.content)
        paid = request.url.path.endswith(":generateContent")
        content = body if paid else body["generateContentRequest"]
        view = json.loads(content["contents"][0]["parts"][0]["text"])
        tokens = count if count is not None else (12242 if view["round"] >= 6 else 1000)
        if not paid:
            return httpx.Response(200, json={"totalTokens": tokens})
        self.seen.append((view, body))
        usage = {"promptTokenCount": tokens, "candidatesTokenCount": 50,
                 "totalTokenCount": tokens + 50 + (thoughts or 0)}
        if thoughts is not None:
            usage["thoughtsTokenCount"] = thoughts
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model",
            "parts": [{"text": encode(reply(view))}]}, "finishReason": stop}], "usageMetadata": usage})

    def execute(self, handler=None, pin=None):
        return finish.execute(self.stopped, pin or self.pin, "offline-dummy", inner=httpx.MockTransport(handler or self.handler))

    def test_only_last_three_rounds_are_generated_and_full_history_matches(self):
        result = self.execute()
        expected, last_views = Dialogue(), []
        for number in range(1, 9):
            views = expected.inputs()
            if number >= 6:
                last_views.extend(views.values())
            expected.commit({a: encode(reply(v)) for a, v in views.items()}, expected_round=number)
        self.assertEqual(result["state"], expected.snapshot())
        self.assertEqual([v for v, _ in self.seen], last_views)
        self.assertEqual((result["model_calls"], result["total_model_calls"]), (12, 32))
        self.assertEqual(continuation.evidence_identity(self.stopped), self.before)
        for view, body in self.seen:
            self.assertEqual(body["systemInstruction"]["parts"][0]["text"], SYSTEM_INSTRUCTION)
            self.assertEqual(body["generationConfig"], {"responseMimeType": "application/json", "maxOutputTokens":8192})
            if view["actor"] in ("C", "COORDINATOR"):
                self.assertNotIn("message A", encode(view))
                self.assertNotIn("private A", encode(view))
        summary = Journal(finish.output_directory(self.stopped)).read("completion-summary.json")
        self.assertLessEqual(Decimal(summary["prior_additional_estimated_usd"]) + Decimal(summary["reserved_usd"]), finish.ORIGINAL_USD_LIMIT)
        self.assertEqual(summary["reserved_usd"], "0.58464")

    def test_wrong_pin_and_forged_paid_stop_are_rejected_before_network(self):
        with self.assertRaises(Exception):
            self.execute(pin="wrong")
        path = self.stopped / "budget-02/count-04.response.json"
        value = json.loads(path.read_text())
        value["payload"]["totalTokens"] = 1000
        value["sha256"] = digest(value["payload"])
        path.write_text(encode(value))
        with self.assertRaisesRegex(pilot.PilotStopped, "NOT_PROVEN"):
            self.execute(pin=digest(continuation.evidence_identity(self.stopped)))
        self.assertEqual(self.seen, [])

    def test_ambiguous_paid_reservation_cannot_be_retried(self):
        Journal(self.stopped / "budget-02").write("paid-04.reservation.json", {"ambiguous": True})
        with self.assertRaisesRegex(pilot.PilotStopped, "AMBIGUOUS"):
            self.execute(pin=digest(continuation.evidence_identity(self.stopped)))
        self.assertEqual(self.seen, [])

    def test_completion_destination_is_one_use(self):
        self.execute()
        with self.assertRaisesRegex(pilot.PilotStopped, "ALREADY_ATTEMPTED"):
            self.execute()
        self.assertEqual(len(self.seen), 12)

    def test_24001_input_tokens_cause_no_paid_generation(self):
        with self.assertRaises(Exception):
            self.execute(lambda r: self.handler(r, count=24001))
        self.assertEqual(self.seen, [])

    def test_missing_usage_stops_after_first_receipt(self):
        with self.assertRaises(Exception):
            self.execute(lambda r: self.handler(r, thoughts=None))
        self.assertEqual(len(self.seen), 1)
        stopped = Journal(finish.output_directory(self.stopped)).read("completion-stopped.json")
        self.assertEqual(stopped["committed_round"], 5)
        self.assertEqual(stopped["paid_attempts"], 1)

    def test_truncated_response_is_not_delivered_or_retried(self):
        with self.assertRaises(Exception):
            self.execute(lambda r: self.handler(r, stop="MAX_TOKENS"))
        self.assertEqual(len(self.seen), 1)
        self.assertTrue((finish.output_directory(self.stopped) / "dialogue/call-00000020.sdk.json").exists())

    def test_timeout_keeps_reservation_and_cannot_restart(self):
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
        stopped = Journal(finish.output_directory(self.stopped)).read("completion-stopped.json")
        self.assertEqual(stopped["reserved_usd"], "0.04872")

    def transport(self, prior=Decimal(0)):
        path = self.parent.parent / "transport"
        path.mkdir()
        return finish.CompletionTransport(httpx.MockTransport(self.handler), Journal(path), prior, finish.sources())

    def request(self):
        body = {"contents": [{"parts": [{"text": encode({"actor":"A", "round":6})}]}],
                "systemInstruction": {}, "generationConfig": {"responseMimeType":"application/json", "maxOutputTokens":8192}}
        return httpx.Request("POST", pilot.ENDPOINT + ":generateContent", json=body, headers={"x-goog-api-key":"offline-dummy"})

    def test_prior_confirmed_spend_counts_against_original_budget(self):
        transport = self.transport(Decimal("0.94"))
        with self.assertRaisesRegex(pilot.PilotStopped, "BUDGET_EXCEEDED"):
            transport.handle_request(self.request())
        self.assertEqual(self.seen, [])

    def test_thirteenth_call_is_blocked(self):
        transport = self.transport()
        for _ in range(12):
            transport.handle_request(self.request())
        with self.assertRaisesRegex(pilot.PilotStopped, "CALL_LIMIT"):
            transport.handle_request(self.request())
        self.assertEqual(len(self.seen), 12)

    def test_source_change_during_count_stops_before_paid_generation(self):
        def handler(request):
            response = self.handler(request)
            change = patch.object(finish, "sources", return_value={"changed":"source"})
            change.start()
            self.addCleanup(change.stop)
            return response
        with self.assertRaises(Exception):
            self.execute(handler)
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
