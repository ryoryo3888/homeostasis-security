"""Compare decomposed allocation to the original full Cartesian search."""
from collections import defaultdict
from fractions import Fraction
import hashlib
from itertools import product
import random
import unittest
from unittest.mock import patch

from tests.v3 import test_settlement as fixtures
from homeostasis_v3.settlement import SettlementEngine
from homeostasis_v3.choices import TechnicalFailure


def exhaustive(engine, state, choices, prepared, policy):
    domains = []
    for choice, feasible in zip(choices, prepared):
        maximum = feasible['feasible_amount']
        domains.append([0] if not maximum else
                       [0, *range(choice['minimum_amount'], maximum + 1)]
                       if choice['allow_partial'] else [0, choice['requested_amount']])
    order = sorted(range(len(choices)), key=lambda i: (
        hashlib.sha256((policy.tie_seed + ':' + choices[i]['choice_id']).encode()).hexdigest(),
        choices[i]['choice_id']))
    def score(quantities):
        requested = defaultdict(int); allocated = defaultdict(int)
        for choice, quantity in zip(choices, quantities):
            key = choice['actor_state_id'], choice['resource']
            requested[key] += choice['requested_amount']; allocated[key] += quantity
        actors = defaultdict(list)
        for key in requested:
            actors[key[0]].append(Fraction(allocated[key], requested[key]))
        fulfillment = tuple(sorted(sum(values) / len(values) for values in actors.values()))
        tie = tuple(quantities[i] for i in order)
        return (fulfillment, tie) if policy.allocation == 'leximin_actor_fulfillment' else (tie,)
    return max((q for q in product(*domains)
                if not engine._constraints(state, choices, prepared, q, policy)[0]), key=score)


class ComponentSearchTests(unittest.TestCase):
    def fixture(self):
        fixture = fixtures.SettlementTests()
        fixture.setUp()
        return fixture

    def test_matches_exhaustive_audit_across_constraints_and_policies(self):
        rng = random.Random(20260920)
        for case in range(120):
            f = self.fixture()
            for group in f.n['shared_capacities']:
                group['capacity'] = rng.randint(1, 6)
            for account in f.b['world']['accounts']:
                account['balance'] = rng.randint(0, 30)
            f.build(pool={'food': 6, 'energy': 6})
            choices = []
            count = rng.randint(1, 5)
            for i in range(count):
                route = rng.choice(f.n['routes'])
                amount = rng.randint(1, 4)
                conditions = []
                if count > 1 and rng.random() < .4:
                    other = rng.choice([j for j in range(count) if j != i])
                    kind = rng.choice(['participation', 'settled_amount', 'arrived_amount'])
                    conditions = [{'kind': kind, 'choice_id': f'c{other}',
                                   'minimum_amount': 0 if kind == 'participation' else rng.randint(1, 4)}]
                choices.append(f.choice(f'c{i}', route['source'], route['destination'], route['route_id'],
                    amount, rng.choice([True, False]), rng.randint(1, amount), conditions,
                    resource=rng.choice(['food', 'energy'])))
            for policy in ('baseline', 'no-reserve', 'priority'):
                with self.subTest(case=case, policy=policy):
                    f.build(pool={'food': 6, 'energy': 6})
                    actual = f.e.read(f.run_batch(choices, policy=policy))
                    f.build(pool={'food': 6, 'energy': 6})
                    with patch.object(SettlementEngine, '_allocate', exhaustive):
                        expected = f.e.read(f.run_batch(choices, policy=policy))
                    self.assertEqual(actual, expected)

    def test_eight_partial_transfers_fit_without_changing_allocations(self):
        f = self.fixture()
        choices = [f.choice(f'c{i}', r['source'], r['destination'], r['route_id'], 100)
                   for i, r in enumerate(f.n['routes']) if r['route_id'].endswith('-forward')]
        self.assertEqual(len(choices), 8)
        actual = f.e.read(f.run_batch(choices))
        self.assertEqual(len(actual['shipments']), 8)
        self.assertEqual(f.e._totals(actual), f.e._totals(f.e.read(f.s)))
        self.assertTrue(all(row['settled_amount'] <= row['individual']['feasible_amount']
                            for row in actual['audits'][-1]['choices']))

    def test_pool_and_domestic_requests_match_exhaustive(self):
        f = self.fixture()
        f.build(pool={'food': 5, 'energy': 5})
        choices = [f.choice('a', amount=3, action='pool_withdraw'),
                   f.choice('b', 'RES', 'RES', 'MIL-forward', 3, action='pool_withdraw'),
                   f.choice('c', 'MIL', 'NEUTRAL', 'MIL-reverse', 3, resource='energy'),
                   f.choice('d', 'FOOD', 'SMALL', 'FOOD-forward', 3)]
        actual = f.e.read(f.run_batch(choices))
        f.build(pool={'food': 5, 'energy': 5})
        with patch.object(SettlementEngine, '_allocate', exhaustive):
            self.assertEqual(actual, f.e.read(f.run_batch(choices)))

    def test_cross_component_conditions_remain_atomic(self):
        f = self.fixture()
        choices = [f.choice('a', amount=3, conditions=[
            {'kind': 'settled_amount', 'choice_id': 'b', 'minimum_amount': 2}]),
            f.choice('b', 'FOOD', 'SMALL', 'FOOD-forward', 3, conditions=[
                {'kind': 'participation', 'choice_id': 'a', 'minimum_amount': 0}])]
        actual = f.e.read(f.run_batch(choices))
        f.build()
        with patch.object(SettlementEngine, '_allocate', exhaustive):
            self.assertEqual(actual, f.e.read(f.run_batch(choices)))
        f.build(budget=2)
        with self.assertRaisesRegex(TechnicalFailure, 'SEARCH_BUDGET_EXCEEDED'):
            f.run_batch(choices)
        self.assertEqual(f.e.read(f.s)['shipments'], [])
