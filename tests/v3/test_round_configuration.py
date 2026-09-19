"""Every country in a planning round must receive one frozen protocol."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from homeostasis_v3 import autonomous
from homeostasis_v3.agent_adapter import ExchangeBudget
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.turn import Snapshot
from tests.v3 import test_autonomous_gemini as fixtures


class RoundConfigurationTests(unittest.TestCase):
    def case(self):
        case = fixtures.AutonomousTests(); case.setUp()
        return case

    def changes(self):
        return {
            'initiative_limit': lambda r: setattr(r, 'max_initiatives', 99),
            'amount_limit': lambda r: setattr(r, 'maximum_amount', 999),
            'source': lambda r: setattr(r, 'source', 'replacement source'),
            'states': lambda r: setattr(r, 'state_ids', r.state_ids[:-1]),
            'budget_limit': lambda r: setattr(r.budget, 'limit', 999),
            'budget_object': lambda r: setattr(r, 'budget', ExchangeBudget(16)),
            'exchange': lambda r: setattr(r, 'exchange', lambda _raw: '{}'),
        }

    def test_changed_settings_stop_before_any_country_request(self):
        for name, change in self.changes().items():
            with self.subTest(name=name):
                case = self.case(); round = case.make_round(); change(round)
                with self.assertRaisesRegex(TechnicalFailure, 'PLANNING_CONFIGURATION_CHANGED'):
                    case.run_round(round)
                self.assertEqual(case.requests, [])
                self.assertTrue(round.failed)

    def test_drift_in_a_reply_stops_before_another_country(self):
        for phase in ('initiative', 'consent'):
            with self.subTest(phase=phase):
                case = self.case(); holder = {}; changed = []
                def mutate(_answer, request):
                    if request['phase'] == phase and not changed:
                        changed.append(True)
                        holder['round'].max_initiatives = 99
                round = case.make_round(mutate); holder['round'] = round
                before = deepcopy(case.opening)
                with self.assertRaisesRegex(TechnicalFailure, 'PLANNING_CONFIGURATION_CHANGED'):
                    case.run_round(round)
                self.assertEqual(len(case.requests), 1 if phase == 'initiative' else 9)
                self.assertTrue(all(r['payload']['max_initiatives'] == 4 for r in case.requests
                                    if r['phase'] == 'initiative'))
                self.assertEqual(case.opening, before)
                self.assertTrue(round.failed)

    def test_restoring_settings_cannot_reuse_a_failed_round(self):
        case = self.case(); holder = {}
        def mutate(_answer, _request): holder['round'].max_initiatives = 99
        round = case.make_round(mutate); holder['round'] = round
        with self.assertRaises(TechnicalFailure): case.run_round(round)
        view = Snapshot.of(case.requests[0]['observation'])
        round.max_initiatives = 4
        for operation in (lambda: round.catalogue(view), round.countries, round.record):
            with self.assertRaises(TechnicalFailure): operation()
        self.assertEqual(len(case.requests), 1)

    def test_drift_during_budget_reservation_stops_before_dispatch(self):
        case = self.case(); round = case.make_round(); reserve = round.budget.reserve
        def changed(request):
            key = reserve(request)
            round.max_initiatives = 99
            return key
        with patch.object(round.budget, 'reserve', side_effect=changed):
            with self.assertRaisesRegex(TechnicalFailure, 'PLANNING_CONFIGURATION_CHANGED'):
                case.run_round(round)
        self.assertEqual(case.requests, [])
        self.assertEqual(len(round.budget.attempts), 1)
        self.assertTrue(round.failed)

    def test_completed_round_cannot_relabel_its_source_or_limits(self):
        for field, value in (('source', 'new source'), ('max_initiatives', 99), ('maximum_amount', 999)):
            with self.subTest(field=field):
                case = self.case(); round = case.make_round(); result = case.run_round(round)
                before = deepcopy(result); sent = deepcopy(case.requests)
                setattr(round, field, value)
                with self.assertRaisesRegex(TechnicalFailure, 'PLANNING_CONFIGURATION_CHANGED'):
                    round.record()
                self.assertEqual(result, before)
                self.assertEqual(case.requests, sent)

    def test_schema_change_requires_a_new_round(self):
        for schema in (autonomous.INITIATIVE_RESPONSE, autonomous.RESPONSE):
            with self.subTest(schema=id(schema)):
                case = self.case(); round = case.make_round()
                with patch.dict(schema, {'title': 'changed response contract'}):
                    with self.assertRaisesRegex(TechnicalFailure, 'PLANNING_CONFIGURATION_CHANGED'):
                        case.run_round(round)
                self.assertEqual(case.requests, [])


if __name__ == '__main__':
    unittest.main()
