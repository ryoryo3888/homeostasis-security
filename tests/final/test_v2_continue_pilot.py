import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

import v2_continue_pilot as continuation
import v2_paid_pilot as pilot
from v2_autonomous import Journal, SYSTEM_INSTRUCTION
from v2_dialogue import ACTORS, Dialogue, digest, encode


def reply(view):
    actor, number = view["actor"], view["round"]
    return {"outgoing": [{"to": ["B" if actor == "A" else "A"],
                          "body": f"free message {actor} {number}"}],
            "activities": [{"body": "unlisted activity"}] if actor == "B" and number == 3 else [],
            "private_note": f"private note {actor} {number}"}


class ContinuePilotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name) / "parent"
        self.seen = []
        pilot.execute(self.parent, "offline-dummy", inner=httpx.MockTransport(self.handler))
        self.identity = continuation.evidence_identity(self.parent)
        self.pin = digest(self.identity)
        self.before = {str(p.relative_to(self.parent)): p.read_bytes() for p in self.parent.rglob("*.json")}
        self.seen.clear()

    def handler(self, request, *, count=1000, thoughts=10, finish="STOP"):
        body = json.loads(request.content)
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": count})
        view = json.loads(body["contents"][0]["parts"][0]["text"])
        self.seen.append((view, body))
        usage = {"promptTokenCount": count, "candidatesTokenCount": 60,
                 "totalTokenCount": count + 60 + (thoughts or 0)}
        if thoughts is not None:
            usage["thoughtsTokenCount"] = thoughts
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model",
            "parts": [{"text": encode(reply(view))}]}, "finishReason": finish}], "usageMetadata": usage})

    def execute(self, handler=None, pin=None, parent=None):
        return continuation.execute(parent or self.parent, pin or self.pin, "offline-dummy",
                                    inner=httpx.MockTransport(handler or self.handler))

    def test_continuation_matches_uninterrupted_eight_rounds_without_recalling_parent(self):
        result = self.execute()
        baseline = Dialogue()
        baseline_views = []
        for number in range(1, 9):
            inputs = baseline.inputs()
            if number > 2:
                baseline_views.extend(inputs.values())
            baseline.commit({actor: encode(reply(view)) for actor, view in inputs.items()}, expected_round=number)
        self.assertEqual(result["state"], baseline.snapshot())
        self.assertEqual([view for view, _ in self.seen], baseline_views)
        self.assertEqual((result["model_calls"], result["total_model_calls"]), (24, 32))
        self.assertEqual([v["round"] for v, _ in self.seen], [n for n in range(3, 9) for _ in ACTORS])
        for view, body in self.seen:
            self.assertEqual(body["systemInstruction"]["parts"][0]["text"], SYSTEM_INSTRUCTION)
            self.assertEqual(body["generationConfig"], {"responseMimeType": "application/json", "maxOutputTokens": 8192})
            if view["actor"] in ("C", "COORDINATOR"):
                self.assertNotIn("free message A", encode(view))
                self.assertNotIn("private note A", encode(view))
            self.assertTrue(all(m["sent_round"] < view["round"] for m in view["messages"]))
        self.assertEqual(self.before, {str(p.relative_to(self.parent)): p.read_bytes() for p in self.parent.rglob("*.json")})
        self.assertEqual(len([e for e in result["state"]["events"] if e["kind"] == "initial_condition"]), 1)
        self.assertFalse(result["state"]["activity_results"]["B"][0]["executed"])
        directory = continuation.output_directory(self.parent)
        summary = Journal(directory).read("continuation-summary.json")
        self.assertEqual(summary["reserved_usd"], "0.95328")
        self.assertEqual(summary["paid_attempts"], 24)
        self.assertEqual(len(list(directory.glob("budget-*"))), 3)
        self.assertTrue(all(p.stat().st_mode & 0o077 == 0 for p in directory.rglob("*.json")))

    def test_parent_pin_or_missing_receipt_blocks_all_network_calls(self):
        with self.assertRaisesRegex(pilot.PilotStopped, "EVIDENCE_CHANGED"):
            self.execute(pin="wrong")
        path = self.parent / "dialogue/call-00000000.sdk.json"
        path.unlink()
        with self.assertRaises(Exception):
            self.execute(pin=digest(continuation.evidence_identity(self.parent)))
        self.assertEqual(self.seen, [])

    def test_forged_parent_state_is_rejected_by_replay_even_with_updated_hash(self):
        path = self.parent / "dialogue/result.json"
        saved = json.loads(path.read_text())
        saved["payload"]["state"]["notes"]["A"] = "invented history"
        saved["sha256"] = digest(saved["payload"])
        path.write_text(encode(saved))
        with self.assertRaisesRegex(pilot.PilotStopped, "RESULT_MISMATCH"):
            self.execute(pin=digest(continuation.evidence_identity(self.parent)))
        self.assertEqual(self.seen, [])

    def test_complete_continuation_cannot_be_called_again_or_through_alias(self):
        self.execute()
        alias = self.parent.parent / "alias"
        alias.symlink_to(self.parent, target_is_directory=True)
        for parent in (self.parent, alias):
            with self.subTest(parent=parent), self.assertRaises(pilot.PilotStopped):
                self.execute(parent=parent)
        self.assertEqual(len(self.seen), 24)

    def test_timeout_reserves_once_and_refuses_a_new_attempt(self):
        attempts = []
        def fail(request):
            if request.url.path.endswith(":countTokens"):
                return self.handler(request)
            attempts.append(request)
            raise httpx.ReadTimeout("offline timeout")
        with self.assertRaises(Exception):
            self.execute(fail)
        with self.assertRaises(pilot.PilotStopped):
            self.execute()
        stopped = Journal(continuation.output_directory(self.parent)).read("continuation-stopped.json")
        self.assertEqual(stopped["paid_attempts"], 1)
        self.assertEqual(stopped["committed_round"], 2)
        self.assertEqual(len(attempts), 1)

    def test_input_count_limit_stops_before_paid_call_without_truncating_parent(self):
        with self.assertRaises(Exception):
            self.execute(lambda r: self.handler(r, count=12001))
        self.assertEqual(self.seen, [])
        self.assertEqual(self.identity, continuation.evidence_identity(self.parent))

    def test_missing_usage_at_budget_boundary_cannot_start_a_new_allowance(self):
        def handler(request):
            return self.handler(request, thoughts=None if len(self.seen) == 7 else 10)
        with self.assertRaises(Exception):
            self.execute(handler)
        directory = continuation.output_directory(self.parent)
        stopped = Journal(directory).read("continuation-stopped.json")
        self.assertEqual(len(self.seen), 8)
        self.assertEqual(stopped["committed_round"], 3)
        self.assertFalse((directory / "budget-02").exists())
        self.assertTrue((directory / "dialogue/call-00000015.sdk.json").exists())

    def test_incomplete_response_stops_before_other_agents_and_keeps_original_receipt(self):
        with self.assertRaises(Exception):
            self.execute(lambda r: self.handler(r, finish="MAX_TOKENS"))
        self.assertEqual(len(self.seen), 1)
        directory = continuation.output_directory(self.parent)
        self.assertTrue((directory / "dialogue/call-00000008.sdk.json").exists())
        self.assertEqual(Journal(directory).read("continuation-stopped.json")["committed_round"], 2)

    def test_source_change_during_response_stops_before_delivery(self):
        def handler(request):
            response = self.handler(request)
            if request.url.path.endswith(":generateContent"):
                change = patch.object(continuation, "sources", return_value={"changed": "source"})
                change.start()
                self.addCleanup(change.stop)
            return response
        with self.assertRaisesRegex(pilot.PilotStopped, "SOURCE_CHANGED"):
            self.execute(handler)
        self.assertEqual(len(self.seen), 1)

    def test_source_change_during_free_count_prevents_the_paid_request(self):
        def handler(request):
            response = self.handler(request)
            change = patch.object(continuation, "sources", return_value={"changed": "source"})
            change.start()
            self.addCleanup(change.stop)
            return response
        with self.assertRaises(Exception):
            self.execute(handler)
        self.assertEqual(self.seen, [])

    def test_twenty_fifth_paid_call_is_refused_without_network(self):
        destination = self.parent.parent / "transport"
        destination.mkdir()
        transport = continuation.ContinuationTransport(httpx.MockTransport(self.handler), destination, continuation.sources())
        body = {"contents": [{"parts": [{"text": encode({"actor": "C", "round": 3})}]}],
                "systemInstruction": {}, "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 8192}}
        request = httpx.Request("POST", pilot.ENDPOINT + ":generateContent", json=body,
                                headers={"x-goog-api-key": "offline-dummy"})
        for _ in range(24):
            transport.handle_request(request)
        with self.assertRaisesRegex(pilot.PilotStopped, "CALL_LIMIT"):
            transport.handle_request(request)
        self.assertEqual(len(self.seen), 24)


if __name__ == "__main__":
    unittest.main()
