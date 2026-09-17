"""Offline replay of immutable country answers; never constructs a client."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from homeostasis_core.gemini_agents import apply_structured_actions, resolve_conditional_participants
from homeostasis_core.resources import ResourceNetwork, SupplyLink
from homeostasis_core.emergent_dynamics import reconstruction_step

FIXTURE = Path(__file__).parents[1] / 'fixtures/settlement_20260916T233557Z.json'

class SimultaneousConditionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = json.loads(FIXTURE.read_text())
        cls.answers = cls.f['turn']['country_responses']
        n = cls.f['network']
        cls.network = ResourceNetwork(n['schema_version'], tuple(SupplyLink.from_dict(x) for x in n['links']), n['demands'], tuple(n['resource_types']))

    def replay(self, answers):
        s = self.f['turn']['snapshot']
        return apply_structured_actions(self.f['initial_states'], answers, s['world'], s['damage'], 1,
            world_pool=s['world_pool'], resource_network=self.network, network_policy=s['network_policy'])

    def test_all_40320_answer_orders_same_full_atomic_state(self):
        expected = self.replay(self.answers)
        self.assertEqual(expected['participants'], sorted(self.answers))
        self.assertEqual(expected['world_pool']['food'], 30)
        self.assertEqual(expected['world_pool']['logistics'], 50)
        self.assertEqual(expected['demand_unmet'], 0)
        for order in itertools.permutations(self.answers):
            self.assertEqual(self.replay({c:self.answers[c] for c in order}), expected)

    def test_saved_state_and_evaluator_exactly_match_legacy_execution(self):
        # Explicitly replay the historical erroneous singleton, not rewrite it.
        with patch('homeostasis_core.gemini_agents.resolve_conditional_participants', return_value={'NEUTRAL'}):
            replay = self.replay(self.answers)
        replay['causal_record']['event'] = self.f['turn']['snapshot']['event']
        saved = copy.deepcopy(self.f['turn']['executed_state'])
        saved.pop('reconstruction', None)
        saved['causal_record'].pop('farmland_reconstruction', None)
        self.assertEqual(reconstruction_step(8000, replay, replay['country_states']), self.f['turn']['executed_state']['reconstruction'])
        self.assertEqual(replay, saved)
        self.assertEqual(self.f['evaluator_input'], saved)
        self.assertEqual(saved['world_pool']['food'], 20)
        self.assertEqual(saved['demand_unmet'], 0)

    def test_failed_dependency_cascades_without_partial_effects(self):
        answers = copy.deepcopy(self.answers)
        answers['RES']['response_id'] = 'REJECT'
        answers['RES']['conditions'] = {}
        self.assertEqual(resolve_conditional_participants(answers, 1), {'NEUTRAL'})
        out = self.replay(answers)
        baseline = {c:copy.deepcopy(a) for c,a in answers.items()}
        for c in baseline:
            if c != 'NEUTRAL':
                baseline[c]['action'] = {'action_id':'NO_ACTION','parameters':{'amount':0,'recipient_type':'none','target_country':None,'resource':None},'description':'offline counterfactual'}
        other = self.replay(baseline)
        self.assertEqual(out, other)
        self.assertEqual(out['participants'], ['NEUTRAL'])

    def test_static_constraints_eliminate_cycle_and_dependents(self):
        for condition in ({'deadline_turn':1}, {'maximum_sovereignty_burden':19}, {'minimum_aid_amount':21}):
            answers = copy.deepcopy(self.answers)
            answers['FOOD']['conditions'].update(condition)
            turn = 2 if 'deadline_turn' in condition else 1
            self.assertEqual(resolve_conditional_participants(answers, turn), {'NEUTRAL'})

    def test_mutual_means_one_other_participant_and_never_self(self):
        a = copy.deepcopy(self.answers['ECON'])
        a['conditions'] = {'mutual_performance':True}
        self.assertEqual(resolve_conditional_participants({'ECON':a}, 1), set())
        self.assertEqual(resolve_conditional_participants({'ECON':a,'NEUTRAL':self.answers['NEUTRAL']}, 1), {'ECON','NEUTRAL'})

    def test_fixed_point_is_greatest_among_all_256_subsets(self):
        countries = list(self.answers)
        valid = []
        for flags in itertools.product((False,True), repeat=8):
            group = {c for c,flag in zip(countries,flags) if flag}
            if 'NEUTRAL' not in group: continue
            # Independent oracle for this fixture: all scalar limits pass.
            if all(set(self.answers[c]['conditions'].get('required_countries', [])) <= group
                   and (not self.answers[c]['conditions'].get('mutual_performance') or len(group)>1) for c in group):
                valid.append(group)
        self.assertEqual(len(valid), 17)
        self.assertIn({'NEUTRAL'}, valid)
        self.assertIn({'NEUTRAL','ECON','FOOD','RES'}, valid)
        self.assertEqual(resolve_conditional_participants(self.answers, 1), set.union(*valid))

    def test_source_artifacts_unchanged_when_available(self):
        for filename, expected in self.f['source_hashes'].items():
            path = Path(filename)
            if path.exists(): self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
