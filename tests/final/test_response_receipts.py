"""Synthetic SDK replies only; no network or model decisions are generated."""
from copy import deepcopy
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from google import genai
from google.genai import types

import final_experiment_runner as runner
from homeostasis_core.gemini_agents import GeminiGateway
from response_receipts import ResponseReceipts


def response(text):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(parts=[types.Part(text=text)]), finish_reason="STOP")])


class ResponseReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "synthetic.json"
        self.store = ResponseReceipts.for_output(self.output)
        self.store.prepare()
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("NO_NETWORK"))
        network.start(); self.addCleanup(network.stop)

    def gateway(self, reply, hook=None):
        generate = Mock(return_value=reply)
        gateway = GeminiGateway(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                                response_hook=hook or self.store.record)
        return gateway, generate

    def saved(self, audit):
        path = self.store.directory / (audit["response_receipt"]["id"] + ".json")
        return json.loads(path.read_bytes())

    def test_original_spacing_unicode_and_rejected_json_survive(self):
        raw = ' \n{"reason":"拒否する","reason":"secret-fixture"}\t'
        gateway, generate = self.gateway(response(raw))
        from model_response_json import load_response_object
        with self.assertRaises(RuntimeError):
            gateway.call("A", 1, 1, {}, load_response_object)
        audit = gateway.calls[0]
        self.assertEqual(self.saved(audit)["sdk_response"]["candidates"][0]["content"]["parts"][0]["text"], raw)
        self.assertEqual(audit["response_status"], "validation_failed")
        self.assertNotIn("secret-fixture", json.dumps(gateway.calls))
        self.assertEqual(generate.call_count, 1)
        self.assertIsNone(audit["structured_response"])

    def test_full_sdk_reply_saved_before_text_or_usage_access(self):
        for field in ("text", "usage_metadata"):
            class BrokenResponse:
                candidates = response('synthetic').candidates
                def model_dump_json(self, **kwargs):
                    return response('{"raw":"preserved"}').model_dump_json(**kwargs)
                @property
                def text(self):
                    if field == "text": raise ValueError("synthetic text extraction error")
                    return '{"raw":"preserved"}'
                @property
                def usage_metadata(self):
                    if field == "usage_metadata": raise ValueError("synthetic usage error")
                    return None
            gateway, generate = self.gateway(BrokenResponse())
            with self.assertRaises(RuntimeError):
                gateway.call(field, 1, 1, {}, json.loads)
            self.assertTrue(self.saved(gateway.calls[0])["sdk_response"]["candidates"])
            self.assertEqual(generate.call_count, 1)

    def test_disk_failure_never_parses_or_reissues(self):
        gateway, generate = self.gateway(response('{"valid":true}'),
                                         Mock(side_effect=OSError("synthetic full disk")))
        parser = Mock()
        with self.assertRaisesRegex(RuntimeError, "could not be preserved"):
            gateway.call("A", 1, 1, {}, parser)
        parser.assert_not_called()
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(gateway.calls[0]["response_status"], "receipt_failed")

    def test_receipt_cannot_be_overwritten_and_is_private(self):
        gateway, _ = self.gateway(response('{"valid":true}'))
        gateway.call("A", 1, 1, {}, json.loads)
        audit = gateway.calls[0]
        path = self.store.directory / (audit["response_receipt"]["id"] + ".json")
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.store.record(audit, response('{"replacement":true}'))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(list(self.store.directory.glob(".receipt-*")), [])

    def test_resume_verifies_missing_changed_and_mismatched_receipts(self):
        gateway, _ = self.gateway(response('{"valid":true}'))
        gateway.call("A", 1, 1, {}, json.loads)
        audit = gateway.calls[0]
        self.store.verify([audit])
        for field, value in (("response_sha256", "wrong"), ("structured_response", {"valid": False}),
                             ("observation_digest", "wrong"), ("response_receipt", None)):
            changed = deepcopy(audit); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.store.verify([changed])
        path = self.store.directory / (audit["response_receipt"]["id"] + ".json")
        raw = path.read_bytes(); path.write_bytes(raw + b" ")
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            self.store.verify([audit])
        path.unlink()
        with self.assertRaisesRegex(ValueError, "MISSING"):
            self.store.verify([audit])
        self.store.verify([{"response_status": "validated"}])  # No legacy backfill.
        self.assertEqual(list(self.store.directory.iterdir()), [])

    def test_real_sdk_safety_and_truncation_evidence_excludes_headers(self):
        payloads = [
            {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": '{"broken":'}]}}]},
            {"promptFeedback": {"blockReason": "SAFETY"}},
        ]
        for index, payload in enumerate(payloads):
            sent = []
            def handler(request):
                sent.append(request)
                return httpx.Response(200, json=payload, headers={"x-private-fixture": "never-publish-header"})
            with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http:
                with genai.Client(vertexai=False, api_key="offline-dummy", http_options=types.HttpOptions(
                    base_url="https://receipt-fixture.invalid", httpx_client=http,
                    retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    gateway = GeminiGateway(client, response_hook=self.store.record)
                    with self.assertRaises(RuntimeError):
                        gateway.call("A", 1, index + 1, {}, json.loads)
                    saved = self.saved(gateway.calls[0])
                    self.assertNotIn("sdk_http_response", saved["sdk_response"])
                    self.assertNotIn("never-publish-header", json.dumps(saved))
                    if index == 0:
                        self.assertEqual(saved["sdk_response"]["candidates"][0]["finish_reason"], "MAX_TOKENS")
                    else:
                        self.assertEqual(saved["sdk_response"]["prompt_feedback"]["block_reason"], "SAFETY")
                    self.assertEqual(len(sent), 1)

    def test_runner_failure_preserves_reply_and_does_not_advance(self):
        destination = self.output.parent / "failure.json"
        generate = Mock(return_value=response(' {"unreadable": '))
        client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        with self.assertRaises(RuntimeError): runner.run_live(client, destination, 1, 7)
        checkpoint = destination.with_suffix(".json.checkpoint")
        saved = json.loads(checkpoint.read_bytes())
        self.assertEqual(saved["active_run"]["completed_turn"], 0)
        self.assertEqual(saved["active_run"]["turns"], [])
        receipt_store = ResponseReceipts.for_output(destination)
        receipt_store.verify(saved["active_run"]["call_audit"])
        self.assertEqual(len(list(receipt_store.directory.glob("*.json"))), 1)
        before = checkpoint.read_bytes()
        with self.assertRaises(ValueError): runner.run_live(client, destination, 1, 7, True)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(checkpoint.read_bytes(), before)
        self.assertFalse(destination.exists())

    def test_fresh_execution_cannot_reuse_private_archive(self):
        client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock()))
        with self.assertRaises(FileExistsError): runner.run_live(client, self.output, 1, 7)
        client.models.generate_content.assert_not_called()


if __name__ == "__main__": unittest.main()
