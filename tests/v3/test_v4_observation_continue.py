"""Continue only an evidenced formatting stop; never buy a saved reply twice."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v4 import dialogue
from homeostasis_v4.observation_run import execute, profile
from homeostasis_v4.observation_continue import continue_observation, inspect_parent, parent_digest, SavedThenLive
from tests.v3.test_v4_dialogue import empty, offer
from v2_autonomous import Journal


class ContinueTests(unittest.TestCase):
    def provider(self, seen, fault=False):
        def call(request):
            data = json.loads(request.content)
            if str(request.url).endswith(':countTokens'):
                return httpx.Response(200, json={'totalTokens': 100})
            value = json.loads(data['contents'][0]['parts'][0]['text'])
            view = value['view']; key = view['turn'], view['actor']
            self.assertNotIn(key, seen, 'saved model request was generated again')
            seen.append(key); reply = empty()
            if key == (2, 'NEUTRAL'):
                activity = offer(id='omitted', target='FRAGILE', route='NEUTRAL-reverse')
                activity.pop('body'); reply['activities'] = [activity]
            return httpx.Response(200, json={'candidates': [{'content': {'role': 'model',
                'parts': [{'text': '{' if fault else canonical(reply)}]}, 'finishReason': 'STOP'}],
                'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 120,
                    'thoughtsTokenCount': 30, 'totalTokenCount': 250}})
        return httpx.MockTransport(call)

    def parent(self, path, seen):
        legacy = deepcopy(dialogue.REPLY)
        item = legacy['properties']['activities']['items']
        item['required'] = ['body']; item.pop('anyOf')
        with patch.object(dialogue, 'REPLY', legacy), self.assertRaises(TechnicalFailure):
            execute(path, 'fixture-key', protocol_digest=digest(profile()), inner=self.provider(seen))
        self.assertEqual(len(seen), 14)
        return parent_digest(path)

    def test_reuse_fourteen_and_generate_only_remaining_twenty_six(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'parent'; seen = []; pin = self.parent(path, seen)
            result = continue_observation(path, 'fixture-key', expected_parent_digest=pin,
                protocol_digest=digest(profile()), inner=self.provider(seen))
            self.assertEqual(result['status'], 'observation_period_reached')
            self.assertEqual(result['completed_turns'], 5)
            self.assertEqual(result['new_api_calls'], 26)
            self.assertEqual(result['api_calls'], 40)
            self.assertEqual(result['reserved_usd'], '2.18880')
            self.assertEqual(parent_digest(path), pin)
            child = Journal(path.with_name('parent-completion'))
            first = child.read('turn-001.json'); old = Journal(path).read('turn-001.json')
            self.assertEqual(first['world'], old['world']); self.assertEqual(first['dialogue'], old['dialogue'])
            second = child.read('turn-002.json')
            saved = second['dialogue']['history']['NEUTRAL'][1]['output']['activities'][0]
            self.assertNotIn('body', saved)
            self.assertIsNone(second['dialogue']['offers']['offer:NEUTRAL:omitted']['body'])
            self.assertEqual(len(list(child.directory.glob('reused-*.json'))), 14)
            with self.assertRaisesRegex(TechnicalFailure, 'CONTINUATION_ALREADY_ATTEMPTED'):
                continue_observation(path, 'fixture-key', expected_parent_digest=pin,
                    protocol_digest=digest(profile()), inner=self.provider(seen))
            self.assertEqual(len(seen), 40)

    def test_changed_parent_protocol_or_unresolved_reply_never_spends(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'parent'; seen = []; pin = self.parent(path, seen)
            with self.assertRaisesRegex(TechnicalFailure, 'PARENT_CHANGED'):
                inspect_parent(path, '0' * 64)
            with self.assertRaisesRegex(TechnicalFailure, 'PREPARED_PROTOCOL_CHANGED'):
                continue_observation(path, 'fixture-key', expected_parent_digest=pin,
                    protocol_digest='0' * 64, inner=self.provider(seen))
            # A complete response whose prior usage is unknown cannot be reused.
            p = path / 'stopped.json'; wrapper = json.loads(p.read_text())
            payload = wrapper['payload']; payload['usage'] = []
            wrapper['sha256'] = digest(payload)
            p.write_text(json.dumps(wrapper))
            with self.assertRaisesRegex(TechnicalFailure, 'UNRESOLVED_PAID_USAGE'):
                inspect_parent(path, parent_digest(path))
            self.assertEqual(len(seen), 14)

    def test_changed_saved_input_stops_before_any_new_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'parent'; seen = []; pin = self.parent(path, seen)
            _, _, _, _, cache = inspect_parent(path, pin)
            transport = SimpleNamespace(prepare_round=lambda *a, **k: self.fail('new call after changed input'))
            joined = SavedThenLive(cache, SimpleNamespace(transport=transport), None, path, pin)
            request = deepcopy(cache[2, 'ECON']['request']); request['view']['private_note'] = 'changed'
            with self.assertRaisesRegex(TechnicalFailure, 'SAVED_AGENT_INPUT_CHANGED'):
                joined.prepare_round([canonical(request)])
            self.assertEqual(len(seen), 14)

    def test_new_failure_keeps_paid_count_and_cannot_be_restarted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'parent'; seen = []; pin = self.parent(path, seen)
            result = continue_observation(path, 'fixture-key', expected_parent_digest=pin,
                protocol_digest=digest(profile()), inner=self.provider(seen, fault=True))
            self.assertEqual(result['status'], 'technical_stop')
            self.assertEqual(result['completed_turns'], 1)
            self.assertEqual(result['api_calls'], 15)
            self.assertEqual(result['new_api_calls'], 1)
            self.assertEqual(parent_digest(path), pin)
            with self.assertRaisesRegex(TechnicalFailure, 'CONTINUATION_ALREADY_ATTEMPTED'):
                continue_observation(path, 'fixture-key', expected_parent_digest=pin,
                    protocol_digest=digest(profile()), inner=self.provider(seen))
            self.assertEqual(len(seen), 15)

    def test_missing_description_does_not_allow_empty_or_malformed_activity(self):
        view = {'participants': ['MIL'], 'messages': []}
        reply = empty(); reply['activities'] = [{'operation': 'unknown', 'arguments': {}}]
        self.assertEqual(dialogue.parse_reply(canonical(reply), view), reply)
        for activity in ({}, {'operation': 'unknown'}, {'operation': 'unknown', 'arguments': []}):
            reply['activities'] = [activity]
            with self.assertRaises(TechnicalFailure):
                dialogue.parse_reply(canonical(reply), view)
