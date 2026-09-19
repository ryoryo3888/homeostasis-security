"""A frozen protocol must match the parameters actually used by the runner."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from homeostasis_v3 import turn
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.network import load_network
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.settlement import Policy
from homeostasis_v3.turn import CountryInput, TurnFailure, TurnRunner

ROOT = Path(__file__).resolve().parents[2]


class TurnConfigurationTests(unittest.TestCase):
    def runner(self):
        baseline = load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
        network = load_network(ROOT/'scenarios/v3/synthetic_network.json', baseline)
        return TurnRunner(baseline, network, pool_location='MIL', context_id='configuration-fixture')

    def changes(self):
        return {
            'policy': lambda r: setattr(r, 'policy', Policy('baseline', reserve_essential=False)),
            'pool': lambda r: setattr(r, 'pool_location', 'RES'),
            'context': lambda r: setattr(r, 'context_id', 'changed-context'),
            'budget': lambda r: setattr(r, 'search_budget', r.search_budget+1),
            'baseline': lambda r: r.baseline['world']['accounts'][0].update(balance=1),
            'network': lambda r: r.network['routes'][0].update(capacity=1),
            'record': lambda r: r.config['policy'].update(reserve_essential=False),
        }

    def test_changed_parameters_stop_before_callbacks_and_preserve_opening(self):
        for name, change in self.changes().items():
            with self.subTest(name=name):
                runner = self.runner(); opening = runner.genesis(); before = deepcopy(opening)
                change(runner); callback = Mock(return_value=None)
                with self.assertRaises(TurnFailure) as caught:
                    runner.run(opening, coordinator=callback)
                self.assertEqual(caught.exception.code, 'TURN_CONFIGURATION_CHANGED')
                self.assertEqual(caught.exception.record['phase'], 'TURN_OPEN')
                callback.assert_not_called()
                self.assertEqual(opening, before)

    def test_genesis_and_replay_cannot_use_a_changed_configuration(self):
        for name, change in self.changes().items():
            with self.subTest(name=name):
                runner = self.runner(); opening = runner.genesis(); recorded = runner.run(opening)
                change(runner)
                with self.assertRaisesRegex(TechnicalFailure, 'TURN_CONFIGURATION_CHANGED'):
                    runner.genesis()
                with self.assertRaisesRegex(TechnicalFailure, 'TURN_CONFIGURATION_CHANGED'):
                    runner.replay(opening, recorded['input'])

    def test_module_rule_drift_does_not_rewrite_the_frozen_record(self):
        runner = self.runner(); opening = runner.genesis(); before = deepcopy(runner.config)
        with patch.dict(turn.RULES, {'version': 'unapproved-change'}):
            self.assertEqual(runner.config, before)
            with self.assertRaisesRegex(TurnFailure, 'TURN_CONFIGURATION_CHANGED'):
                runner.run(opening)

    def test_callback_drift_stops_before_another_callback_or_completed_turn(self):
        for boundary in ('coordinator', 'catalogue', 'choose', 'consent', 'pool'):
            with self.subTest(boundary=boundary):
                runner = self.runner(); opening = runner.genesis(); before = deepcopy(opening)
                calls = []
                def callback(phase, result):
                    def invoke(*_args):
                        calls.append(phase)
                        if phase == boundary:
                            runner.policy = Policy('baseline', reserve_essential=False)
                        return result
                    return invoke
                countries = {c['state_id']: CountryInput(callback('choose', []), callback('consent', {}))
                             for c in runner.baseline['world']['countries']}
                with self.assertRaisesRegex(TurnFailure, 'TURN_CONFIGURATION_CHANGED'):
                    runner.run(opening, coordinator=callback('coordinator', None),
                               catalogue=callback('catalogue', []), countries=countries,
                               pool_consent=callback('pool', {}))
                self.assertEqual(calls[-1], boundary)
                self.assertEqual(calls.count(boundary), 1)
                self.assertEqual(opening, before)

    def test_change_between_turns_does_not_extend_the_original_protocol(self):
        runner = self.runner(); completed = runner.run(runner.genesis()); before = deepcopy(completed)
        runner.policy = Policy('baseline', reserve_essential=False)
        callback = Mock(return_value=None)
        with self.assertRaisesRegex(TurnFailure, 'TURN_CONFIGURATION_CHANGED'):
            runner.run(completed, coordinator=callback)
        callback.assert_not_called()
        self.assertEqual(completed, before)


if __name__ == '__main__':
    unittest.main()
