"""F06: agent-authored action dependency, using synthetic responses only."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from test_simulation import sdk_reply

from homeostasis_core.gemini_agents import (
    GeminiGateway, SCHEMA_VERSION, apply_structured_actions,
    country_response_schema, parse_country_json, run_gemini_turn,
)


class ActionParticipationTests(unittest.TestCase):
    def setUp(self):
        state = {'archetype': 'synthetic', 'sovereignty': 80,
                 'indicators': {k: 50 for k in ('food_reserves', 'energy_stability',
                     'economy', 'military_security', 'domestic_stability',
                     'recovery_capacity', 'international_trust', 'diplomatic_posture')},
                 'resources': {k: 50 for k in ('food', 'fossil_fuel', 'renewable_energy',
                     'nuclear', 'grid_storage_resilience', 'funds_economy', 'logistics')},
                 'energy_portfolio': {'sources': {'fossil_fuel': 34, 'renewable_energy': 33,
                     'nuclear': 33}, 'import_dependency': 50}}
        self.states = {c: deepcopy(state) for c in ('A', 'B')}
        self.world = {k: 50 for k in ('food', 'energy', 'economy', 'environment',
                                      'international_trust', 'conflict_load')}

    def answer(self, country='A', response='REJECT', dependent=False, action='PROTECT_RESERVES'):
        return dict(country_id=country, proposal_id='p', response_id=response,
                    response_label={'ACCEPT': '受け入れる', 'REJECT': '拒否する',
                                    'CONDITIONAL': '条件付きで応じる'}[response],
                    reason='synthetic', conditions=({'required_countries': ['B']}
                        if response == 'CONDITIONAL' else {}),
                    self_interest=50, sovereignty_burden=5, perceived_global_effect=50,
                    action_requires_participation=dependent,
                    action=dict(action_id=action, description='synthetic',
                                parameters=dict(recipient_type='none', target_country=None,
                                                resource=None, amount=0)))

    def execute(self, answer, other=None):
        return apply_structured_actions(self.states,
            {'A': answer, 'B': other or self.answer('B', dependent=True, action='NO_ACTION')},
            self.world, 0)

    def test_reject_does_not_discard_independent_action(self):
        result = self.execute(self.answer())
        self.assertEqual(result['participants'], [])
        self.assertEqual(result['action_executors'], ['A'])
        self.assertIn('A', result['rejected'])
        self.assertEqual(result['action_counts']['PROTECT_RESERVES'], 1)

    def test_reject_does_not_execute_participation_dependent_action(self):
        result = self.execute(self.answer(dependent=True))
        self.assertEqual(result['action_executors'], [])
        self.assertEqual(result['action_counts']['PROTECT_RESERVES'], 0)
        self.assertIn('A', result['causal_record']['participation_blocked_actions'])

    def test_unmet_participation_conditions_leave_independent_action(self):
        result = self.execute(self.answer(response='CONDITIONAL'))
        self.assertEqual(result['participants'], [])
        self.assertIn('A', result['condition_unmet'])
        self.assertEqual(result['action_executors'], ['A'])

    def test_unmet_participation_conditions_block_dependent_action(self):
        result = self.execute(self.answer(response='CONDITIONAL', dependent=True))
        self.assertEqual(result['action_executors'], [])

    def test_satisfied_conditions_allow_dependent_action(self):
        result = self.execute(self.answer(response='CONDITIONAL', dependent=True),
                              self.answer('B', response='ACCEPT', dependent=True))
        self.assertEqual(result['participants'], ['A', 'B'])
        self.assertEqual(result['action_executors'], ['A', 'B'])

    def test_accept_keeps_both_dependency_choices(self):
        for dependent in (False, True):
            with self.subTest(dependent=dependent):
                result = self.execute(self.answer(response='ACCEPT', dependent=dependent))
                self.assertEqual(result['participants'], ['A'])
                self.assertEqual(result['action_executors'], ['A'])

    def test_independent_transfer_still_conserves_resources(self):
        answer = self.answer(action='PROVIDE_RESOURCE')
        answer['action']['parameters'] = dict(recipient_type='country', target_country='B',
                                               resource='food', amount=5)
        result = self.execute(answer)
        self.assertEqual(result['country_states']['A']['resources']['food'], 45)
        self.assertEqual(result['country_states']['B']['resources']['food'], 55)
        self.assertEqual(result['participants'], [])

    def test_independence_does_not_bypass_feasibility(self):
        answer = self.answer(action='PROVIDE_RESOURCE')
        answer['action']['parameters'] = dict(recipient_type='country', target_country='B',
                                               resource='food', amount=99)
        before = deepcopy(self.states)
        with self.assertRaises(ValueError):
            self.execute(answer)
        self.assertEqual(self.states, before)

    def test_absent_or_nonboolean_dependency_is_not_inferred(self):
        for value in (None, 0, 1, 'false', {}, []):
            with self.subTest(value=value):
                answer = self.answer(); answer['action_requires_participation'] = value
                with self.assertRaises(ValueError): parse_country_json(json.dumps(answer))
                with self.assertRaises(ValueError): self.execute(answer)
        answer = self.answer(); del answer['action_requires_participation']
        with self.assertRaises(ValueError): parse_country_json(json.dumps(answer))
        with self.assertRaises(ValueError): self.execute(answer)

    def test_schema_and_parser_keep_agent_dependency(self):
        schema = country_response_schema(('A', 'B'))
        self.assertIn('action_requires_participation', schema['required'])
        self.assertEqual(schema['properties']['action_requires_participation'], {'type': 'boolean'})
        for dependent in (False, True):
            answer = self.answer(dependent=dependent)
            self.assertEqual(parse_country_json(json.dumps(answer)), answer)
        self.assertEqual(SCHEMA_VERSION, 3)

    def test_order_independence_and_input_preservation(self):
        answers = {'A': self.answer(), 'B': self.answer('B', dependent=True)}
        before = deepcopy((self.states, answers, self.world))
        one = apply_structured_actions(self.states, answers, self.world, 0)
        two = apply_structured_actions(self.states, dict(reversed(list(answers.items()))), self.world, 0)
        self.assertEqual(one, two)
        self.assertEqual((self.states, answers, self.world), before)

    def test_real_turn_passes_independent_rejection_through_to_world(self):
        requests = []

        def generate(**kw):
            request = json.loads(kw['contents']); requests.append(request)
            if 'observable_world' in request:
                answer = dict(proposal_id='p', proposal_type='食料援助', reason='synthetic',
                              predicted_global_effect=50, predicted_sovereignty_burden=5,
                              requested_action='synthetic')
            elif 'executed_true_state' in request:
                answer = {k: 50 for k in ('national_sovereignty', 'global_homeostasis',
                    'resource_stability', 'resilience', 'conflict_load', 'history_effect')}
                answer['assessment'] = 'synthetic'
            else:
                country = request['turn_start_observation']['own_country']
                answer = self.answer(country, dependent=(country == 'B'))
            return sdk_reply(json.dumps(answer))

        gateway = GeminiGateway(SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        views = {c: dict(own_country=c, observed_world=self.world, own_state=self.states[c])
                 for c in self.states}
        result = run_gemini_turn(gateway, 1, 1, dict(snapshot_id='s', world=self.world,
                                damage=0, event='synthetic'), views, {}, ('A', 'B'),
                                country_states=self.states)
        self.assertEqual(len(requests), 4)
        self.assertEqual(result['executed_state']['action_executors'], ['A'])
        self.assertEqual(result['executed_state']['participants'], [])
        self.assertFalse(result['country_responses']['A']['action_requires_participation'])
        self.assertIn('action_requires_participation', requests[1]['response_contract']['exact_fields'])


if __name__ == '__main__':
    unittest.main()
