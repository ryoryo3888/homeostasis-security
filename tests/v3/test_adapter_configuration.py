"""The fixed-catalogue adapter cannot adopt replies under changed conditions."""
import json
from copy import deepcopy
import unittest
from unittest.mock import patch

from homeostasis_v3 import agent_adapter
from homeostasis_v3.agent_adapter import ExchangeBudget, JsonCountryAdapter
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical
from homeostasis_v3.turn import Snapshot
from tests.v3 import test_agent_preflight as fixtures


class AdapterConfigurationTests(unittest.TestCase):
    def fixture(self, mutate=None):
        case = fixtures.PreflightTests(); case.setUp()
        requests = []
        def exchange(raw):
            request = json.loads(raw); requests.append(request)
            answer = case.response(raw)
            if mutate:
                mutate(adapter, request)
            return canonical(answer)
        adapter = JsonCountryAdapter('MIL', catalogue=case.catalogue, exchange=exchange,
                                     budget=case.budget, source='synthetic fixture')
        return case, adapter, requests

    def changes(self):
        return {
            'actor': lambda a: setattr(a, 'state_id', 'RES'),
            'source': lambda a: setattr(a, 'source', 'replacement source'),
            'budget_limit': lambda a: setattr(a.budget, 'limit', 99),
            'budget': lambda a: setattr(a, 'budget', ExchangeBudget(16)),
            'exchange': lambda a: setattr(a, 'exchange', lambda _: '{}'),
            'catalogue': lambda a: setattr(a, 'catalogue', lambda _: []),
        }

    def test_setting_changes_stop_before_any_request(self):
        for name, change in self.changes().items():
            with self.subTest(change=name):
                case, adapter, requests = self.fixture()
                callbacks = adapter.callbacks()
                change(adapter)
                with self.assertRaisesRegex(TechnicalFailure, 'ADAPTER_CONFIGURATION_CHANGED'):
                    case.run_fixture({'MIL': callbacks})
                self.assertEqual(requests, [])

    def test_reply_cannot_relabel_source_or_change_next_phase_conditions(self):
        for phase in ('choice', 'consent'):
            for name, change in self.changes().items():
                with self.subTest(phase=phase, change=name):
                    def mutate(adapter, request):
                        if request['phase'] == phase:
                            change(adapter)
                    case, adapter, requests = self.fixture(mutate)
                    opening = deepcopy(case.genesis)
                    with self.assertRaisesRegex(TechnicalFailure, 'ADAPTER_CONFIGURATION_CHANGED'):
                        case.run_fixture({'MIL': adapter.callbacks()})
                    self.assertEqual(len(requests), 1 if phase == 'choice' else 2)
                    self.assertEqual(case.genesis, opening)

    def test_catalogue_callback_drift_stops_before_reservation(self):
        case = fixtures.PreflightTests(); case.setUp()
        requests = []
        def catalogue(view):
            adapter.source = 'replacement source'
            return case.catalogue(view)
        adapter = JsonCountryAdapter('MIL', catalogue=catalogue,
                                     exchange=lambda raw: requests.append(raw),
                                     budget=case.budget, source='synthetic fixture')
        with self.assertRaisesRegex(TechnicalFailure, 'ADAPTER_CONFIGURATION_CHANGED'):
            case.run_fixture({'MIL': adapter.callbacks()})
        self.assertEqual(requests, [])
        self.assertEqual(case.budget.attempts, [])

    def test_budget_callback_drift_stops_before_dispatch(self):
        case, adapter, requests = self.fixture()
        reserve = case.budget.reserve
        def changed(request):
            key = reserve(request)
            adapter.source = 'replacement source'
            return key
        with patch.object(case.budget, 'reserve', side_effect=changed):
            with self.assertRaisesRegex(TechnicalFailure, 'ADAPTER_CONFIGURATION_CHANGED'):
                case.run_fixture({'MIL': adapter.callbacks()})
        self.assertEqual(requests, [])
        self.assertEqual(len(case.budget.attempts), 1)

    def test_schema_change_stops_even_when_consent_would_be_empty(self):
        for operation in ('choose', 'consent', 'callbacks'):
            with self.subTest(operation=operation):
                case, adapter, requests = self.fixture()
                callbacks = adapter.callbacks()
                with patch.dict(agent_adapter.RESPONSE, {'title': 'replacement contract'}):
                    with self.assertRaisesRegex(TechnicalFailure, 'ADAPTER_CONFIGURATION_CHANGED'):
                        if operation == 'choose':
                            case.run_fixture({'MIL': callbacks})
                        elif operation == 'consent':
                            adapter.consent(Snapshot.of({}), Snapshot.of([]))
                        else:
                            adapter.callbacks()
                self.assertEqual(requests, [])

    def test_restoring_settings_cannot_reuse_adapter_after_detected_drift(self):
        def mutate(adapter, request):
            adapter.source = 'replacement source'
        case, adapter, requests = self.fixture(mutate)
        with self.assertRaises(TechnicalFailure):
            case.run_fixture({'MIL': adapter.callbacks()})
        adapter.source = 'synthetic fixture'
        view = Snapshot.of(requests[0]['observation'])
        for operation in (adapter.callbacks,
                          lambda: adapter.choose(view, Snapshot.of(None)),
                          lambda: adapter.consent(view, Snapshot.of([]))):
            with self.assertRaisesRegex(TechnicalFailure, 'ADAPTER_CONFIGURATION_FAILED'):
                operation()
        self.assertEqual(len(requests), 1)


if __name__ == '__main__':
    unittest.main()
