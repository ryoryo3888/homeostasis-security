"""Turn 5 is inherited, not replayed against the provider or reset to genesis."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v4.observation_run import execute, profile
from homeostasis_v4.observation_continue import parent_digest, continue_observation
from homeostasis_v4.observation_extend import prepare_extension, extend_observation, extension_profile
from tests.v3.test_v4_dialogue import empty, offer, respond
from v2_autonomous import Journal


class ExtensionTests(unittest.TestCase):
    def provider(self, seen, *, fault=None, next_turn=False):
        def call(request):
            data = json.loads(request.content)
            if str(request.url).endswith(':countTokens'):
                return httpx.Response(200, json={'totalTokens': 32001 if fault == 'oversize' else 100})
            v = json.loads(data['contents'][0]['parts'][0]['text'])['view']
            key = v['turn'], v['actor']
            self.assertNotIn(key, seen)
            if next_turn: self.assertGreaterEqual(v['turn'], 6)
            seen[key] = v; reply = empty()
            if key == (4, 'MIL'):
                reply['activities'] = [offer(id='z-first')]
            if key == (5, 'MIL'):
                reply.update(activities=[offer(id='a-next')], outgoing=[{'to': ['RES'], 'body': 'message saved at turn 5'}],
                             private_note='private note from turn 5')
            if v['turn'] in (5, 6) and v['actor'] == 'RES' and any(o['status'] == 'pending' for o in v['offers']):
                reply['activities'] = [respond(v)]
            return httpx.Response(200, json={'candidates': [{'content': {'role': 'model',
                'parts': [{'text': '{' if fault == 'bad_json' else canonical(reply)}]}, 'finishReason': 'STOP'}],
                'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 120,
                                  'thoughtsTokenCount': 30, 'totalTokenCount': 250}})
        return httpx.MockTransport(call)

    def parent(self, p, seen):
        execute(p, 'fixture-key', protocol_digest=digest(profile()), inner=self.provider(seen))
        return parent_digest(p)

    def test_exact_three_turn_extension_preserves_memory_offers_and_transit(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'parent'; seen={}; pin=self.parent(p,seen)
            plan, runner, opening=prepare_extension(p,pin)
            self.assertEqual(opening,Journal(p).read('turn-005.json'))
            self.assertEqual(len(seen),40)
            result=extend_observation(p,'fixture-key',expected_parent_digest=pin,
                protocol_digest=plan['protocol_digest'],inner=self.provider(seen,next_turn=True))
            self.assertEqual(result['status'],'observation_period_reached')
            self.assertEqual(result['completed_turns'],8)
            self.assertEqual(result['additional_api_calls'],24)
            self.assertEqual(result['cumulative_api_calls'],64)
            self.assertEqual(result['reserved_usd'],'1.31328')
            self.assertEqual(len(seen),64);self.assertEqual(parent_digest(p),pin)
            self.assertEqual(seen[6,'MIL']['private_note'],'private note from turn 5')
            for (turn,actor),v in seen.items():
                if turn==6:
                    if actor not in ('MIL','RES'):self.assertNotIn('message saved at turn 5',canonical(v))
                    if actor!='MIL':self.assertNotIn('private note from turn 5',canonical(v))
            child=Journal(Path(plan['output_directory']))
            shipments=child.read('turn-008.json')['world']['world_state']['shipments']
            self.assertEqual({s['choice_id']:s['arrival_turn'] for s in shipments},
                {'offer:MIL:z-first':6,'offer:MIL:a-next':7})
            for turn in range(6,9):opening=runner.replay(opening,child.read(f'turn-{turn:03d}.json'))
            with self.assertRaisesRegex(TechnicalFailure,'EXTENSION_ALREADY_ATTEMPTED'):
                extend_observation(p,'fixture-key',expected_parent_digest=pin,
                    protocol_digest=plan['protocol_digest'],inner=self.provider(seen,next_turn=True))
            self.assertEqual(len(seen),64)

    def test_prepaid_limits_and_unresolved_output_never_retry(self):
        for fault in ('oversize','bad_json'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as temp:
                p=Path(temp)/'parent';seen={};pin=self.parent(p,seen)
                plan,_,_=prepare_extension(p,pin)
                result=extend_observation(p,'fixture-key',expected_parent_digest=pin,
                    protocol_digest=plan['protocol_digest'],inner=self.provider(seen,fault=fault,next_turn=True))
                self.assertEqual(result['status'],'technical_stop')
                self.assertEqual(result['completed_turns'],5)
                self.assertEqual(result['additional_api_calls'],0 if fault=='oversize' else 1)
                self.assertEqual(parent_digest(p),pin)
                with self.assertRaisesRegex(TechnicalFailure,'EXTENSION_ALREADY_ATTEMPTED'):
                    extend_observation(p,'fixture-key',expected_parent_digest=pin,
                        protocol_digest=plan['protocol_digest'],inner=self.provider(seen,next_turn=True))

    def test_changed_parent_or_model_conditions_stop_before_network(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'parent';seen={};pin=self.parent(p,seen)
            with self.assertRaisesRegex(TechnicalFailure,'PARENT_CHANGED'):
                prepare_extension(p,'0'*64)
            modified=deepcopy(profile());modified['source_hashes']['homeostasis_v4/dialogue.py']='0'*64
            with patch('homeostasis_v4.observation_extend.profile',return_value=modified):
                with self.assertRaisesRegex(TechnicalFailure,'UNRELATED_SOURCE_CHANGED'):
                    prepare_extension(p,pin)
            with self.assertRaisesRegex(TechnicalFailure,'PREPARED_PROTOCOL_CHANGED'):
                extend_observation(p,'fixture-key',expected_parent_digest=pin,protocol_digest='0'*64,
                    inner=self.provider(seen,next_turn=True))
            self.assertEqual(len(seen),40)

    def test_completed_formatting_continuation_keeps_original_call_provenance(self):
        from tests.v3.test_v4_observation_continue import ContinueTests
        helper=ContinueTests()
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'original';old_seen=[];pin=helper.parent(p,old_seen)
            result=continue_observation(p,'fixture-key',expected_parent_digest=pin,
                protocol_digest=digest(profile()),inner=helper.provider(old_seen))
            self.assertEqual(result['api_calls'],40)
            parent=p.with_name('original-completion');parent_pin=parent_digest(parent)
            plan,_,_=prepare_extension(parent,parent_pin)
            self.assertEqual(len(plan['parent_pins']),2)
            seen={}
            result=extend_observation(parent,'fixture-key',expected_parent_digest=parent_pin,
                protocol_digest=plan['protocol_digest'],inner=self.provider(seen,next_turn=True))
            self.assertEqual(result['completed_turns'],8)
            self.assertEqual(len(seen),24)
            self.assertEqual(parent_digest(p),pin);self.assertEqual(parent_digest(parent),parent_pin)

    def test_extension_budget_is_fixed_to_twenty_four_generations(self):
        settings=extension_profile()
        self.assertEqual(settings['turns'],3);self.assertEqual(settings['max_calls'],24)
        self.assertEqual(settings['usd_reservation_limit'],'1.31328')
        self.assertEqual(settings['max_input_tokens'],profile()['max_input_tokens'])
