"""Reading or editing a V2 observation must not rewrite the source event."""
from copy import deepcopy
import unittest

import simulation_v2 as v2


class V2ObservationIsolationTests(unittest.TestCase):
    def setUp(self):
        self.event = deepcopy(v2.SOURCE_EVENT)
        self.state = deepcopy(v2.INITIAL_WORLD_STATE)

    def tearDown(self):
        v2.SOURCE_EVENT.clear()
        v2.SOURCE_EVENT.update(self.event)

    def observe(self, turn=1):
        return v2.public_observation(turn, self.state,
                                     self.event['lost_annual_rice_capacity_tons'])

    def test_editing_observation_cannot_change_initial_event(self):
        observation = self.observe()
        self.assertEqual(observation['source_event'], self.event)
        observation['source_event']['origin'] = 'observer annotation'
        observation['source_event']['lost_annual_rice_capacity_tons'] = 1
        observation['source_event']['recovery_turns'] = 99
        self.assertEqual(v2.SOURCE_EVENT, self.event)
        self.assertEqual(self.state, v2.INITIAL_WORLD_STATE)

    def test_one_observation_cannot_rewrite_other_or_future_observations(self):
        first = self.observe()
        second = self.observe()
        expected = deepcopy(second)
        first['source_event']['event'] = 'observer replacement event'
        self.assertEqual(second, expected)
        self.assertEqual(self.observe(), expected)

    def test_later_source_changes_cannot_relabel_an_existing_observation(self):
        first = self.observe()
        expected = deepcopy(first)
        v2.SOURCE_EVENT['origin'] = 'different scenario source'
        v2.SOURCE_EVENT['lost_annual_rice_capacity_tons'] = 123
        self.assertEqual(first, expected)
        self.assertEqual(self.observe()['source_event'], v2.SOURCE_EVENT)


if __name__ == '__main__':
    unittest.main()
