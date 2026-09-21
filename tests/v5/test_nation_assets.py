"""Synthetic offline prices test arithmetic only; these are not adopted V5 prices."""
import copy
from decimal import Decimal, InvalidOperation, Overflow, localcontext
import unittest
from unittest.mock import patch

from homeostasis_v5.nation_assets import estimate_assets


def table(rate='2.5'):
    return {'version': 'synthetic-test-only-v1', 'entries': [
        {'spec_id': 'synthetic/capacity-v1', 'unit': 'test-unit', 'points_per_unit': rate},
    ]}


def holding(hid='asset-1', source='capacity-1', quantity='4', **overrides):
    return dict({'holding_id': hid, 'source_id': source, 'name': 'synthetic asset',
                 'spec_id': 'synthetic/capacity-v1', 'unit': 'test-unit', 'quantity': quantity}, **overrides)


class NationAssetAccountingTests(unittest.TestCase):
    def test_names_do_not_change_price_and_inputs_are_unchanged(self):
        assets, prices = [holding()], table()
        before = copy.deepcopy((assets, prices))
        first = estimate_assets(assets, prices)
        self.assertEqual((assets, prices), before)
        renamed = estimate_assets([holding(name='a free-form AI-proposed name')], prices)
        self.assertEqual(first, renamed)
        self.assertEqual(first.status, 'within_budget')
        self.assertEqual(first.total_points, Decimal('10'))
        self.assertEqual(first.unused_points, Decimal('990'))
        self.assertEqual(first.overage_points, Decimal('0'))

    def test_shared_atomic_component_in_two_display_groups_is_charged_once(self):
        groups = [{'group_id': 'port', 'holding_ids': ['asset-1']},
                  {'group_id': 'logistics', 'holding_ids': ['asset-1']}]
        result = estimate_assets([holding()], table(), groups=groups)
        self.assertEqual(result.total_points, Decimal('10'))
        self.assertEqual(len(result.priced_holdings), 1)

    def test_unknown_or_explicitly_unpriced_spec_prevents_complete_total(self):
        for prices in (table(), {'version': 'test-v2', 'entries': table()['entries'] + [
            {'spec_id': 'unknown-v1', 'unit': 'test-unit', 'points_per_unit': None},
        ]}):
            with self.subTest(prices=prices):
                result = estimate_assets([holding(), holding('asset-2', 'capacity-2', spec_id='unknown-v1')], prices)
                self.assertEqual(result.status, 'unpriced')
                self.assertEqual(result.known_subtotal_points, Decimal('10'))
                self.assertIsNone(result.total_points)
                self.assertIsNone(result.unused_points)
                self.assertIsNone(result.overage_points)
                self.assertEqual(len(result.unresolved), 1)

    def test_duplicate_ownership_or_physical_source_is_invalid(self):
        for second, expected in ((holding(source='different'), 'duplicate_holding_id'),
                                 (holding(hid='renamed-copy'), 'duplicate_source_claim')):
            result = estimate_assets([holding(), second], table())
            self.assertEqual(result.status, 'invalid')
            self.assertIn(expected, {issue.code for issue in result.errors})
            self.assertIsNone(result.total_points)

    def test_distinct_owned_capacities_with_same_spec_are_both_charged(self):
        result = estimate_assets([holding(), holding('asset-2', 'capacity-2')], table())
        self.assertEqual(result.total_points, Decimal('20'))

    def test_negative_nonfinite_float_boolean_and_malformed_numbers_are_invalid(self):
        for bad in ('-1', 'NaN', 'sNaN', 'Infinity', '-Infinity', 'not-number', 0.1, True, None):
            for location in ('quantity', 'rate', 'budget'):
                if bad is None and location == 'rate':
                    continue  # Explicitly unresolved prices are tested separately.
                with self.subTest(value=bad, location=location):
                    result = estimate_assets([holding(quantity=bad if location == 'quantity' else '4')],
                                             table(bad if location == 'rate' else '2.5'),
                                             budget_points=bad if location == 'budget' else '1000')
                    self.assertEqual(result.status, 'invalid')
                    self.assertIsNone(result.total_points)

    def test_no_zero_price_or_implicit_unit_conversion(self):
        self.assertEqual(estimate_assets([holding()], table('0')).status, 'invalid')
        mismatch = estimate_assets([holding(unit='other-unit')], table())
        self.assertEqual(mismatch.status, 'invalid')
        self.assertIn('unit_mismatch', {issue.code for issue in mismatch.errors})

    def test_overrun_smaller_than_decimal_context_precision_is_not_rounded_away(self):
        prices = table('1')
        assets = [holding(quantity='1000'), holding('asset-2', 'capacity-2', quantity='1e-30')]
        with localcontext() as context:
            context.prec = 5
            result = estimate_assets(assets, prices)
        self.assertEqual(result.status, 'over_budget')
        self.assertEqual(result.total_points, Decimal('1000.000000000000000000000000000001'))
        self.assertEqual(result.overage_points, Decimal('1e-30'))
        self.assertEqual(result.unused_points, Decimal('0'))

    def test_multiplication_and_remaining_budget_are_exact(self):
        with localcontext() as context:
            context.prec = 5
            over = estimate_assets([holding(quantity='1000')], table('1.000000000000000000000000000001'))
            under = estimate_assets([holding(quantity='999.999999999999999999999999999999')], table('1'))
        self.assertEqual(over.status, 'over_budget')
        self.assertEqual(over.overage_points, Decimal('1e-27'))
        self.assertEqual(under.status, 'within_budget')
        self.assertEqual(under.unused_points, Decimal('1e-30'))

    def test_exact_budget_boundary_and_empty_inventory_do_not_invent_purchases(self):
        full = estimate_assets([holding(quantity=Decimal('1000'))], table(1))
        self.assertEqual(full.status, 'within_budget')
        self.assertEqual(full.unused_points, Decimal('0'))
        empty = estimate_assets([], {'version': 'empty-test-table-v1', 'entries': []})
        self.assertEqual(empty.total_points, Decimal('0'))
        self.assertEqual(empty.unused_points, Decimal('1000'))

    def test_invalid_structure_takes_priority_over_unpriced_items(self):
        result = estimate_assets([holding(spec_id='unknown-v1', quantity='-1')], table())
        self.assertEqual(result.status, 'invalid')
        self.assertIsNone(result.total_points)
        self.assertIsNone(result.known_subtotal_points)
        self.assertTrue(result.errors)
        self.assertTrue(result.unresolved)

    def test_extreme_decimal_representations_are_rejected_before_arithmetic(self):
        for bad in ('1e1000000000', '1e-1000000000', Decimal('1e1000000000'),
                    '1' * 257, '0' * 1025, 10 ** 1000):
            with self.subTest(value_type=type(bad).__name__):
                with patch('homeostasis_v5.nation_assets._multiply', side_effect=AssertionError('must not multiply')):
                    result = estimate_assets([holding(quantity=bad)], table())
                self.assertEqual(result.status, 'invalid')
                self.assertIn('numeric_range_unsupported', {issue.code for issue in result.errors})
                self.assertIsNone(result.total_points)

    def test_unexpected_decimal_arithmetic_failure_returns_invalid_not_a_partial_total(self):
        for operation, error in (('_multiply', Overflow), ('_multiply', InvalidOperation), ('_sum', Overflow)):
            with self.subTest(operation=operation, error=error):
                with patch(f'homeostasis_v5.nation_assets.{operation}', side_effect=error):
                    result = estimate_assets([holding()], table())
                self.assertEqual(result.status, 'invalid')
                self.assertIn('numeric_range_unsupported', {issue.code for issue in result.errors})
                self.assertIsNone(result.known_subtotal_points)
                self.assertIsNone(result.total_points)

    def test_bad_structure_and_group_references_are_invalid(self):
        bad_cases = [
            ([dict(holding(), population=1000000)], table(), ()),
            ([holding()], {'entries': table()['entries']}, ()),
            ([holding()], {'version': 'v', 'entries': table()['entries'] * 2}, ()),
            ([holding()], table(), [{'group_id': 'g', 'holding_ids': ['missing']}]),
            ([holding()], table(), [{'group_id': 'g', 'holding_ids': ['asset-1', 'asset-1']}]),
            ([holding()], table(), [{'group_id': 'asset-1', 'holding_ids': []}]),
            ([holding()], table(), [{'group_id': 'g', 'holding_ids': [], 'quantity': 100}]),
            (None, table(), ()),
            ([holding()], None, ()),
        ]
        for assets, prices, groups in bad_cases:
            with self.subTest(assets=assets, prices=prices, groups=groups):
                result = estimate_assets(assets, prices, groups=groups)
                self.assertEqual(result.status, 'invalid')
                self.assertIsNone(result.known_subtotal_points)


if __name__ == '__main__':
    unittest.main()
