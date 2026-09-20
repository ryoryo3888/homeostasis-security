import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from v2_autonomous import Journal
import v2_paid_pilot as pilot


class PaidPilotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "pilot"
        self.requests = []

    def handler(self, request, *, input_count=1000, thoughts=10):
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        if request.url.path.endswith(":countTokens"):
            self.assertIn("systemInstruction", body["generateContentRequest"])
            return httpx.Response(200, json={"totalTokens": input_count})
        view = json.loads(body["contents"][0]["parts"][0]["text"])
        outgoing = []
        if view["actor"] == "A" and view["round"] == 1:
            outgoing = [{"to": ["B"], "body": "Private unlisted proposal."}]
        if view["actor"] == "B" and view["round"] == 2:
            self.assertEqual(view["messages"][0]["body"], "Private unlisted proposal.")
        if view["actor"] in ("C", "COORDINATOR"):
            self.assertNotIn("Private unlisted proposal.", json.dumps(view))
        usage = {"promptTokenCount": input_count, "candidatesTokenCount": 50,
                 "totalTokenCount": input_count + 50 + (thoughts or 0)}
        if thoughts is not None:
            usage["thoughtsTokenCount"] = thoughts
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
            {"text": json.dumps({"outgoing": outgoing, "activities": [], "private_note": ""})}]},
            "finishReason": "STOP"}], "usageMetadata": usage})

    def execute(self, handler=None):
        return pilot.execute(self.directory, "offline-dummy", inner=httpx.MockTransport(handler or self.handler))

    def paid_count(self):
        return sum(path.endswith(":generateContent") for path, _ in self.requests)

    def test_exact_wire_input_count_precedes_each_of_eight_paid_calls(self):
        result = self.execute()
        self.assertEqual(result["state"]["round"], 2)
        self.assertEqual(self.paid_count(), 8)
        self.assertEqual(len(self.requests), 16)
        for count, generate in zip(self.requests[::2], self.requests[1::2]):
            counted = dict(count[1]["generateContentRequest"])
            self.assertEqual(counted.pop("model"), "models/" + pilot.MODEL)
            self.assertEqual(counted, generate[1])
        summary = Journal(self.directory).read("pilot-summary.json")
        self.assertLessEqual(pilot.Decimal(summary["reserved_usd"]), pilot.USD_LIMIT)
        self.assertTrue(all(item["estimated_usd"] is not None for item in summary["usage"]))
        self.assertFalse(summary["billing_verified"])

    def test_input_count_over_limit_causes_zero_paid_calls(self):
        with self.assertRaises(Exception):
            self.execute(lambda request: self.handler(request, input_count=12001))
        self.assertEqual(self.paid_count(), 0)
        self.assertEqual(Journal(self.directory).read("pilot-stopped.json")["paid_attempts"], 0)

    def test_missing_usage_stops_before_next_paid_call_but_keeps_receipt(self):
        with self.assertRaises(Exception):
            self.execute(lambda request: self.handler(request, thoughts=None))
        self.assertEqual(self.paid_count(), 1)
        self.assertTrue((self.directory / "paid-00.wire-response.json").is_file())
        self.assertTrue((self.directory / "dialogue/call-00000000.sdk.json").is_file())

    def test_timeout_reserves_the_call_and_never_retries(self):
        def handler(request):
            if request.url.path.endswith(":countTokens"):
                return self.handler(request)
            self.requests.append((request.url.path, {}))
            self.assertTrue((self.directory / "paid-00.reservation.json").is_file())
            raise httpx.ReadTimeout("offline timeout")
        with self.assertRaises(Exception):
            self.execute(handler)
        self.assertEqual(self.paid_count(), 1)
        self.assertEqual(Journal(self.directory).read("pilot-stopped.json")["paid_attempts"], 1)
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(self.paid_count(), 1)

    def test_count_failure_never_reaches_paid_endpoint(self):
        requests = []
        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(403, json={"error": "offline denied"})
        with self.assertRaises(Exception):
            self.execute(handler)
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0].endswith(":countTokens"))

    def test_unknown_tools_model_and_larger_output_limit_are_blocked(self):
        for change in ("tools", "model", "output"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                journal = Journal(directory)
                transport = pilot.BudgetTransport(httpx.MockTransport(self.handler), journal, pilot.profile())
                body = {"contents": [], "systemInstruction": {}, "generationConfig": {
                    "responseMimeType": "application/json", "maxOutputTokens": 8192}}
                url = pilot.ENDPOINT + ":generateContent"
                if change == "tools":
                    body["tools"] = [{"googleSearch": {}}]
                if change == "model":
                    url = url.replace(pilot.MODEL, "another-model")
                if change == "output":
                    body["generationConfig"]["maxOutputTokens"] = 8193
                with self.assertRaises(pilot.PilotStopped):
                    transport.handle_request(httpx.Request("POST", url, json=body))
        self.assertEqual(self.requests, [])

    def test_pilot_directory_cannot_be_reused(self):
        self.execute()
        before = len(self.requests)
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(len(self.requests), before)

    def test_private_credential_file_is_read_without_copying_it(self):
        path = Path(self.temporary.name) / "key"
        path.write_text("offline-dummy")
        path.chmod(0o600)
        self.assertEqual(pilot.load_credential(path), "offline-dummy")
        path.chmod(0o644)
        with self.assertRaises(pilot.PilotStopped):
            pilot.load_credential(path)

    def test_ninth_wire_call_is_refused_before_counting_or_generation(self):
        self.directory.mkdir(mode=0o700)
        transport = pilot.BudgetTransport(httpx.MockTransport(self.handler),
                                         Journal(self.directory), pilot.profile())
        body = {"contents": [{"parts": [{"text": json.dumps({"actor": "C", "round": 1})}]}],
                "systemInstruction": {}, "generationConfig": {
                    "responseMimeType": "application/json", "maxOutputTokens": 8192}}
        def request():
            return httpx.Request("POST", pilot.ENDPOINT + ":generateContent", json=body,
                                 headers={"x-goog-api-key": "offline-dummy"})
        for _ in range(8):
            transport.handle_request(request())
        with self.assertRaisesRegex(pilot.PilotStopped, "CALL_LIMIT"):
            transport.handle_request(request())
        self.assertEqual((self.paid_count(), len(self.requests)), (8, 16))

    def test_source_change_during_counting_prevents_paid_call(self):
        original = pilot.sources()
        def handler(request):
            result = self.handler(request)
            source_patch = patch.object(pilot, "sources", return_value={"changed": "source"})
            source_patch.start()
            self.addCleanup(source_patch.stop)
            return result
        with self.assertRaises(Exception):
            self.execute(handler)
        self.assertEqual(self.paid_count(), 0)


if __name__ == "__main__":
    unittest.main()
