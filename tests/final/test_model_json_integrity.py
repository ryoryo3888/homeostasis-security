"""Received model answers must not be silently selected or coerced by JSON decoding."""
import json
from types import SimpleNamespace
import unittest
from test_simulation import sdk_reply

import simulation
import simulation_v2
from homeostasis_core.gemini_agents import (
    GeminiGateway, parse_country_json, parse_coordinator_json, parse_evaluator_json,
)


class ModelJsonIntegrityTests(unittest.TestCase):
    def country(self):
        return dict(country_id='MIL', proposal_id='p', response_id='REJECT',
                    response_label='拒否する', reason='Agent自身の理由', conditions={},
                    self_interest=50, sovereignty_burden=10, perceived_global_effect=50,
                    action_requires_participation=False,
                    action=dict(action_id='NO_ACTION', description='明示した不作為',
                                parameters=dict(recipient_type='none', target_country=None, resource=None, amount=0)))

    def cases(self):
        return [
            (simulation.parse_evaluator_response, {key:50 for key in simulation.EVALUATION_FIELDS}),
            (simulation_v2.parse_evaluator_response,
             {**{key:50 for key in simulation_v2.EVALUATOR_FIELDS}, 'assessment':'観測'}),
            (simulation_v2.parse_coordinator_response,
             dict(proposal=simulation_v2.COORDINATOR_PROPOSALS[0], reason='提案理由')),
            (lambda text: simulation_v2.parse_country_response(text,'A'),
             dict(observation='観測', action=simulation_v2.AGENTS['A'].actions[0],
                  proposal_response=simulation_v2.PROPOSAL_RESPONSES[0], reason='判断理由')),
            (parse_country_json, self.country()),
            (parse_coordinator_json, dict(proposal_id='p', proposal_type='食料援助', reason='提案理由',
                                         predicted_global_effect=50, predicted_sovereignty_burden=10, requested_action='提案')),
            (parse_evaluator_json, dict(national_sovereignty=50, global_homeostasis=50, resource_stability=50,
                                       resilience=50, conflict_load=50, history_effect=50, assessment='観測')),
        ]

    def test_duplicate_fields_never_select_the_last_value(self):
        for parser, answer in self.cases():
            text = json.dumps(answer,ensure_ascii=False)
            for key in answer:
                for earlier in ('"contradictory value"', json.dumps(answer[key],ensure_ascii=False)):
                    with self.subTest(parser=parser, key=key, earlier=earlier):
                        raw = '{' + json.dumps(key) + ':' + earlier + ',' + text[1:]
                        with self.assertRaises(ValueError): parser(raw)

    def test_nested_and_escaped_duplicate_keys_are_rejected(self):
        raw = json.dumps(self.country(),ensure_ascii=False)
        for malformed in (
            raw.replace('"amount": 0','"amount": 99, "amount": 0'),
            raw.replace('"action_requires_participation": false',
                        '"action_requires_participation": true, "action_requires_participation": false'),
            '{"country_\\u0069d":"OTHER",' + raw[1:],
        ):
            with self.subTest(raw=malformed):
                with self.assertRaises(ValueError): parse_country_json(malformed)

    def test_nonfinite_json_is_rejected_even_in_ignored_fields(self):
        for parser, answer in self.cases():
            text = json.dumps(answer,ensure_ascii=False)
            for invalid in ('NaN','Infinity','-Infinity','1e999'):
                with self.subTest(parser=parser, invalid=invalid):
                    with self.assertRaises(ValueError):
                        parser('{"unused_value":' + invalid + ',' + text[1:])

    def test_valid_answers_and_explicit_no_action_are_unchanged(self):
        for parser, answer in self.cases():
            with self.subTest(parser=parser):
                self.assertEqual(parser(json.dumps(answer,ensure_ascii=False)),answer)

    def test_ambiguous_answer_stops_gateway_without_regeneration(self):
        valid = json.dumps(self.country(),ensure_ascii=False)
        ambiguous = '{"action_requires_participation":true,' + valid[1:]
        calls = []
        def generate(**kwargs):
            calls.append(kwargs)
            return sdk_reply(ambiguous if len(calls)==1 else valid)
        gateway = GeminiGateway(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                                retry_limit=3,sleep_fn=lambda _:None)
        with self.assertRaises(RuntimeError):
            gateway.call('MIL',1,1,{},parse_country_json)
        self.assertEqual(len(calls),1)
        self.assertEqual(gateway.calls[0]['response_status'],'validation_failed')
        self.assertIsNone(gateway.calls[0]['structured_response'])


if __name__ == '__main__': unittest.main()
