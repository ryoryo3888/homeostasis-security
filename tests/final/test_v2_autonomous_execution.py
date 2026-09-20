import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from google.genai.types import GenerateContentResponse

import v2_autonomous as runtime
from v2_dialogue import ACTORS, encode


SETTINGS = dict(model="offline-model", rounds=2, max_calls=8,
                max_input_bytes=100000, max_output_tokens=4096)


def output(messages=(), note="", activities=()):
    return {"outgoing": list(messages), "activities": list(activities), "private_note": note}


def sdk_response(value, finish="STOP"):
    return GenerateContentResponse.model_validate({
        "candidates": [{"content": {"role": "model", "parts": [{"text": encode(value)}]},
                        "finishReason": finish}],
        "modelVersion": "offline-model-1", "usageMetadata": {"totalTokenCount": 21},
    })


class ScriptedClient:
    def __init__(self, script=None):
        self.models = self
        self.seen = []
        self.script = script or (lambda view: output())

    def generate_content(self, **kwargs):
        view = json.loads(kwargs["contents"])
        self.seen.append(view)
        return sdk_response(self.script(view))


class AutonomousExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "run"

    def run_dialogue(self, client=None, **changes):
        return runtime.run_dialogue(client or ScriptedClient(), self.directory,
                                    **{**SETTINGS, **changes})

    def test_direct_conversation_runs_through_frozen_rounds_and_private_memory(self):
        def script(view):
            if view["actor"] == "A" and view["round"] == 1:
                return output([{"to": ["B"], "body": "secret proposal"}], "A-only")
            if view["actor"] == "B" and view["round"] == 2:
                self.assertEqual(view["messages"][0]["body"], "secret proposal")
                return output([{"to": ["A"], "body": "different reply"}])
            return output()
        client = ScriptedClient(script)
        result = self.run_dialogue(client)
        self.assertEqual(len(client.seen), 8)
        self.assertEqual(result["state"]["round"], 2)
        self.assertFalse(result["physical_execution"])
        for view in client.seen:
            if view["round"] == 1:
                self.assertEqual(view["messages"], [])
            if view["actor"] in ("C", "COORDINATOR"):
                self.assertNotIn("secret proposal", encode(view))
                self.assertNotIn("A-only", encode(view))
        journal = runtime.Journal(self.directory)
        self.assertEqual(journal.read("result.json"), result)
        self.assertEqual(journal.read("call-00000000.sdk.json")["sdk_response"]["model_version"],
                         "offline-model-1")
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in self.directory.iterdir()))

    def test_unknown_activities_remain_requests_and_silence_has_no_forced_reply(self):
        client = ScriptedClient(lambda view: output(activities=[{"body": "未実装の新活動"}])
                                if view["actor"] == "A" else output())
        result = self.run_dialogue(client)
        self.assertEqual(len(client.seen), 8)
        self.assertEqual(result["state"]["messages"], [])
        self.assertFalse(result["state"]["activity_results"]["A"][0]["executed"])

    def test_budgets_stop_before_partial_round_or_truncation(self):
        for limits, calls, status in [
            ({"max_calls": 6}, 4, "call_budget_reached_before_next_round"),
            ({"max_input_bytes": 10}, 0, "input_limit_reached_no_history_truncated"),
        ]:
            with self.subTest(limits=limits), tempfile.TemporaryDirectory() as temporary:
                client = ScriptedClient()
                result = runtime.run_dialogue(client, Path(temporary) / "run", **{**SETTINGS, **limits})
                self.assertEqual((len(client.seen), result["status"]), (calls, status))

    def test_malformed_and_truncated_sdk_responses_are_saved_but_never_delivered(self):
        for response in (sdk_response({}), sdk_response(output(), "MAX_TOKENS")):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as temporary:
                client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: response))
                directory = Path(temporary) / "run"
                with self.assertRaises(runtime.ExecutionStopped):
                    runtime.run_dialogue(client, directory, **SETTINGS)
                journal = runtime.Journal(directory)
                self.assertTrue(journal.exists("call-00000000.sdk.json"))
                stopped = journal.read("stopped.json")
                self.assertEqual(stopped["delivery_state"]["messages"], [])
                self.assertTrue(stopped["not_an_agent_decision"])

    def test_ambiguous_provider_failure_is_not_retried_or_resumed(self):
        calls = []
        def fail(**kwargs):
            calls.append(kwargs)
            raise TimeoutError("ambiguous")
        client = SimpleNamespace(models=SimpleNamespace(generate_content=fail))
        with self.assertRaises(runtime.ExecutionStopped):
            self.run_dialogue(client)
        with self.assertRaises(runtime.ExecutionStopped):
            self.run_dialogue(client, resume=True)
        self.assertEqual(len(calls), 1)
        self.assertTrue((self.directory / "call-00000000.request.json").exists())
        self.assertFalse((self.directory / "call-00000000.sdk.json").exists())

    def test_crash_after_receipt_resumes_without_recalling_or_duplicate_delivery(self):
        class PowerLoss(BaseException):
            pass
        original = runtime.Journal.write
        def crashing_write(journal, name, payload):
            original(journal, name, payload)
            if name == "call-00000000.sdk.json":
                raise PowerLoss()
        client = ScriptedClient(lambda view: output([{"to": ["B"], "body": "once"}])
                                if view["actor"] == "A" and view["round"] == 1 else output())
        with patch.object(runtime.Journal, "write", crashing_write):
            with self.assertRaises(PowerLoss):
                self.run_dialogue(client)
        result = self.run_dialogue(client, resume=True)
        self.assertEqual(len(client.seen), 8)
        self.assertEqual(len(result["state"]["messages"]), 1)

    def test_crash_after_checkpoint_replays_without_redelivery(self):
        class PowerLoss(BaseException):
            pass
        original = runtime.Journal.write
        def crashing_write(journal, name, payload):
            original(journal, name, payload)
            if name == "round-00000001.json":
                raise PowerLoss()
        client = ScriptedClient()
        with patch.object(runtime.Journal, "write", crashing_write):
            with self.assertRaises(PowerLoss):
                self.run_dialogue(client)
        result = self.run_dialogue(client, resume=True)
        self.assertEqual(len(client.seen), 8)
        self.assertEqual(len(result["state"]["history"]["A"]), 2)

    def test_missing_receipt_after_process_death_blocks_before_any_new_call(self):
        class PowerLoss(BaseException):
            pass
        client = SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda **kwargs: (_ for _ in ()).throw(PowerLoss())))
        with self.assertRaises(PowerLoss):
            self.run_dialogue(client)
        resumed = ScriptedClient()
        with self.assertRaisesRegex(runtime.ExecutionStopped, "AMBIGUOUS"):
            self.run_dialogue(resumed, resume=True)
        self.assertEqual(resumed.seen, [])

    def test_completed_run_is_never_overwritten(self):
        self.run_dialogue()
        before = {path.name: path.read_bytes() for path in self.directory.iterdir()}
        client = ScriptedClient()
        with self.assertRaises(FileExistsError):
            self.run_dialogue(client)
        with self.assertRaises(runtime.ExecutionStopped):
            self.run_dialogue(client, resume=True)
        self.assertEqual(client.seen, [])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.directory.iterdir()})

    def test_configuration_mismatch_and_invalid_budgets_do_not_call_model(self):
        client = ScriptedClient()
        for limits in ({"rounds": True}, {"max_calls": 0}, {"model": ""}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.run_dialogue(client, **limits)
        self.run_dialogue()
        with self.assertRaisesRegex(runtime.ExecutionStopped, "CONFIGURATION"):
            self.run_dialogue(client, resume=True, model="different-model")
        self.assertEqual(client.seen, [])

    def test_real_sdk_transport_stays_offline_and_records_exact_inputs(self):
        import httpx
        from google import genai
        from google.genai import types
        calls = []
        def handler(request):
            payload = json.loads(request.content)
            view = json.loads(payload["contents"][0]["parts"][0]["text"])
            calls.append(view)
            self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 4096)
            self.assertNotIn("協力せよ", json.dumps(payload, ensure_ascii=False))
            return httpx.Response(200, json={"candidates": [{"content": {
                "role": "model", "parts": [{"text": encode(output())}]}, "finishReason": "STOP"}]})
        with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http:
            with genai.Client(vertexai=False, api_key="offline-dummy", http_options=types.HttpOptions(
                    base_url="https://v2-dialogue.invalid", httpx_client=http,
                    retry_options=types.HttpRetryOptions(attempts=1))) as client:
                result = self.run_dialogue(client)
        self.assertEqual([view["actor"] for view in calls], list(ACTORS) * 2)
        self.assertEqual(result["model_calls"], 8)

    def test_concurrent_execution_cannot_share_a_journal(self):
        client = ScriptedClient()
        with runtime.exclusive_execution(self.directory):
            with self.assertRaises(FileExistsError):
                self.run_dialogue(client)
        self.assertEqual(client.seen, [])

    def test_source_drift_stops_after_saving_response_before_delivery(self):
        original = runtime.source_identity()
        identities = [original, original, {"changed": "source"}]
        client = ScriptedClient()
        with patch.object(runtime, "source_identity", side_effect=identities):
            with self.assertRaises(runtime.ExecutionStopped):
                self.run_dialogue(client)
        journal = runtime.Journal(self.directory)
        self.assertTrue(journal.exists("call-00000000.sdk.json"))
        self.assertEqual(journal.read("stopped.json")["committed_round"], 0)
        self.assertEqual(len(client.seen), 1)

    def test_distinct_runs_cannot_exchange_receipts(self):
        class PowerLoss(BaseException):
            pass
        original = runtime.Journal.write
        def crashing_write(journal, name, payload):
            original(journal, name, payload)
            if name == "call-00000000.sdk.json":
                raise PowerLoss()
        directories = [self.directory, Path(self.temporary.name) / "other"]
        with patch.object(runtime.Journal, "write", crashing_write):
            for directory in directories:
                with self.assertRaises(PowerLoss):
                    runtime.run_dialogue(ScriptedClient(), directory, **SETTINGS)
        name = "call-00000000.sdk.json"
        (directories[0] / name).write_bytes((directories[1] / name).read_bytes())
        client = ScriptedClient()
        with self.assertRaises(runtime.ExecutionStopped):
            self.run_dialogue(client, resume=True)
        self.assertEqual(client.seen, [])


if __name__ == "__main__":
    unittest.main()
