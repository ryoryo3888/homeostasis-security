"""Real SDK over mock HTTP: paid bounds, complete-round preflight and receipts."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v4.observation_run import execute, profile
from v2_autonomous import Journal
from tests.v3.test_v4_dialogue import empty, offer, respond


class ObservationRunTests(unittest.TestCase):
    def simulated_provider(self, fault=None):
        self.counts = 0; self.paid = 0; self.operations = []
        def handler(request):
            data = json.loads(request.content)
            if str(request.url).endswith(':countTokens'):
                self.counts += 1; self.operations.append('count')
                return httpx.Response(200, json={'totalTokens': 32001 if fault == 'oversize' and self.counts == 8 else 100})
            self.paid += 1; self.operations.append('generate')
            value = json.loads(data['contents'][0]['parts'][0]['text'])
            view = value['view']; reply = empty()
            if view['turn'] == 1 and view['actor'] == 'MIL':
                reply.update(outgoing=[{'to': ['RES'], 'body': '秘密の提案'}], activities=[offer()], private_note='秘密の自分用記録')
            if view['turn'] == 2 and view['actor'] == 'RES':
                reply['activities'] = [respond(view)]
            usage = {'promptTokenCount': 100, 'candidatesTokenCount': 120, 'thoughtsTokenCount': 30, 'totalTokenCount': 250}
            if fault == 'missing_usage': usage.pop('thoughtsTokenCount')
            if fault == 'excess_usage': usage['candidatesTokenCount'] = 9000
            if fault == 'timeout': raise httpx.ReadTimeout('synthetic timeout')
            if fault == 'bad_json': text = '{'
            else: text = canonical(reply)
            return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [{'text': text}]},
                'finishReason': 'MAX_TOKENS' if fault == 'truncated' else 'STOP'}], 'usageMetadata': usage})
        return httpx.MockTransport(handler)

    def test_five_turns_real_sdk_no_network_exact_replay_and_private_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            result = execute(output, 'unused-fixture-credential', protocol_digest=digest(profile()), inner=self.simulated_provider())
            self.assertEqual(result['completed_turns'], 5)
            self.assertEqual(self.paid, 40); self.assertEqual(self.counts, 40)
            self.assertEqual(self.operations[:8], ['count'] * 8)
            self.assertEqual(self.operations[8:16], ['generate'] * 8)
            journal = Journal(output)
            first = journal.read('turn-001.json')
            second = journal.read('turn-002.json')
            third = journal.read('turn-003.json')
            self.assertFalse(first['world']['world_state']['shipments'])
            self.assertEqual(second['world']['world_state']['shipments'][0]['dispatched_amount'], 2)
            self.assertEqual(third['world']['world_state']['shipments'][0]['arrived_amount'], 2)
            for actor, request in second['input']['requests'].items():
                if actor not in ('MIL', 'RES'): self.assertNotIn('秘密の提案', canonical(request))
                if actor != 'MIL': self.assertNotIn('秘密の自分用記録', canonical(request))
            self.assertEqual(result['reserved_usd'], '2.18880')
            self.assertFalse(result['formal_research_eligibility'])
            self.assertEqual(result['kind'], 'v4_transport_validation')
            self.assertEqual(result['provider_mode'], 'injected_transport_not_certified_live')
            self.assertIn('not live Agent evidence', journal.read('protocol.json')['dialogue_configuration']['source'])
            for path in output.glob('*.json'):
                self.assertEqual(path.stat().st_mode & 0o077, 0)
                self.assertNotIn('unused-fixture-credential', path.read_text())
            before = self.paid
            with self.assertRaises(FileExistsError):
                execute(output, 'unused-fixture-credential', protocol_digest=digest(profile()), inner=self.simulated_provider())
            self.assertEqual(before, 40)
            self.assertEqual(self.paid, 0)

    def test_oversize_eighth_actor_stops_before_any_paid_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            with self.assertRaises(TechnicalFailure):
                execute(output, 'unused-fixture-credential', protocol_digest=digest(profile()), inner=self.simulated_provider('oversize'))
            self.assertEqual(self.counts, 8); self.assertEqual(self.paid, 0)
            stopped = Journal(output).read('stopped.json')
            self.assertEqual(stopped['completed_turns'], 0)
            self.assertTrue(stopped['not_an_agent_decision'])
            self.assertFalse((output / 'turn-001.json').exists())

    def test_unknown_or_excess_usage_and_incomplete_reply_do_not_retry(self):
        for fault in ('missing_usage', 'excess_usage', 'truncated', 'bad_json', 'timeout'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'run'
                with self.assertRaises(TechnicalFailure):
                    execute(output, 'unused-fixture-credential', protocol_digest=digest(profile()), inner=self.simulated_provider(fault))
                self.assertEqual(self.paid, 1)
                journal = Journal(output)
                stopped = journal.read('stopped.json')
                self.assertEqual(stopped['completed_turns'], 0)
                self.assertEqual(stopped['api_calls'], 1)
                self.assertFalse(stopped['automatic_retry'])
                self.assertTrue((output / 'paid-000.reservation.json').exists())
                if fault != 'timeout':
                    wire = journal.read('paid-000.wire.json')
                    self.assertTrue(base64.b64decode(wire['body_base64']))
                    self.assertTrue((output / 'agent-000.sdk.json').exists())

    def test_changed_protocol_never_constructs_a_paid_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            inner = self.simulated_provider()
            with self.assertRaisesRegex(TechnicalFailure, 'PREPARED_PROTOCOL_CHANGED'):
                execute(Path(directory) / 'run', 'unused-fixture-credential', protocol_digest='0' * 64, inner=inner)
            self.assertEqual(self.counts, 0); self.assertEqual(self.paid, 0)
