"""Synthetic offline accounting fixtures; not generated national evidence."""
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import json
import socket
import unittest
from unittest.mock import patch

from homeostasis_v5.nation_valuation import evaluate_initial_holdings


def reference():
    return {'record_id': 'synthetic-offline-test', 'sha256': 'a' * 64}


def catalog():
    return {'version': 'synthetic-test-only', 'status': 'approved_for_nation_generation',
            'reference_year': 2024, 'usd_per_point': '10000000', 'points_per_nation': '1000',
            'approval_ref': reference(), 'coverage_review': {'review_ref': reference(), 'known_gaps': []},
            'specifications': [{'spec_id': 'fixture', 'name': 'synthetic asset', 'asset_kind': 'inventory',
                'unit': 'test_unit', 'definition': 'synthetic specification', 'acquisition_scope': 'test only',
                'quantity_rules': 'nonnegative_decimal', 'operating_requirements': 'not evaluated',
                'state_valuation_rules': 'new equivalent full acquisition',
                'points_per_unit': {'numerator': '1', 'denominator': '3'},
                'source_refs': [reference()], 'adoption_ref': reference()}],
            'free_proposal_policy': 'preserve_and_stop_if_unresolved'}


def holding():
    return {'holding_id': 'h1', 'source_id': 's1', 'name': 'synthetic item', 'spec_id': 'fixture',
            'asset_kind': 'inventory', 'quantity': {'value': '1', 'unit': 'test_unit'}, 'region_ids': ['region1'],
            'state_description': 'existing', 'capability_claim': 'unverified claim', 'dependencies': [],
            'proposal_id': None}


def nation():
    return {'world_id': 'world-test', 'nation_id': 'nation-test',
            'geography_ref': {'map_sha256': 'b' * 64, 'territory_region_ids': ['region1']},
            'name': 'synthetic country', 'population': {'count': 1, 'description': 'test only'},
            'society': {k: 'test only' for k in ('social_structure', 'economy', 'institutions', 'technology',
                                               'strengths', 'weaknesses', 'other_notes')},
            'natural_resources': [], 'holdings': [], 'free_asset_proposals': [],
            'external_relation_claims': [], 'reported_retained_points': '1000', 'unresolved': []}


def rational(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


class NationValuationTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_NETWORK'))
        p.start(); self.addCleanup(p.stop)

    def test_all_retained_and_json_safe_without_physical_approval(self):
        r = evaluate_initial_holdings(nation(), catalog())
        self.assertTrue(r['accepted_initial_accounting'])
        self.assertEqual(rational(r['exact_retained_points']), 1000)
        self.assertTrue(r['reported_balance_matches'])
        self.assertFalse(r['requires_manual_balance_review'])
        self.assertTrue(r['manual_spec_review_required'])
        self.assertFalse(r['world_physics_approved'])
        json.dumps(r, allow_nan=False)

    def test_recurring_balance_keeps_raw_and_never_rounds_to_match(self):
        n, c = nation(), catalog()
        n['holdings'] = [holding()]
        n['reported_retained_points'] = '999.6666666666666666666666667'
        before = deepcopy((n, c))
        with localcontext() as ctx:
            ctx.prec = 2
            r = evaluate_initial_holdings(n, c)
        self.assertTrue(r['accepted_initial_accounting'])
        self.assertEqual(rational(r['total_acquisition_points']), Fraction(1, 3))
        self.assertEqual(rational(r['exact_retained_points']), Fraction(2999, 3))
        self.assertFalse(r['reported_balance_matches'])
        self.assertTrue(r['requires_manual_balance_review'])
        self.assertNotEqual(rational(r['reported_minus_exact_points']), 0)
        self.assertEqual((n, c), before)

    def test_jpy_fraction_price_is_not_decimal_rounded(self):
        n, c = nation(), catalog()
        n['holdings'] = [holding()]
        n['holdings'][0]['quantity']['value'] = '7'
        # Synthetic exact price representation exercises nonterminating FX ratios.
        c['specifications'][0]['points_per_unit'] = {'numerator': '17', 'denominator': '1514551000'}
        r = evaluate_initial_holdings(n, c)
        self.assertEqual(rational(r['total_acquisition_points']), Fraction(119, 1514551000))
        self.assertEqual(rational(r['exact_retained_points']), 1000 - Fraction(119, 1514551000))

    def test_all_operating_states_receive_same_whole_new_price(self):
        totals = []
        for state in ('existing operational', 'stopped', 'under construction 20 percent'):
            n = nation(); n['holdings'] = [holding()]
            n['holdings'][0]['state_description'] = state
            r = evaluate_initial_holdings(n, catalog())
            totals.append(r['total_acquisition_points'])
            self.assertFalse(r['priced_holdings'][0]['state_discount_applied'])
            self.assertFalse(r['priced_holdings'][0]['operating_status_inferred'])
        self.assertTrue(all(total == totals[0] for total in totals))

    def test_unknown_proposal_is_unresolved_not_free_with_no_remaining_balance(self):
        n = nation(); n['holdings'] = [holding()]
        n['holdings'][0]['spec_id'] = None
        n['holdings'][0]['proposal_id'] = 'proposal1'
        n['free_asset_proposals'] = [{'proposal_id': 'proposal1', 'original_text': 'ORIGINAL TEST CLAIM',
            'specification_claim': 'unpriced capability', 'quantity': {'value': '1', 'unit': 'item'},
            'related_holding_ids': ['h1'], 'unresolved_fields': ['price']}]
        before = deepcopy(n)
        r = evaluate_initial_holdings(n, catalog())
        self.assertEqual(r['status'], 'unresolved')
        self.assertFalse(r['accepted_initial_accounting'])
        self.assertIsNone(r['total_acquisition_points'])
        self.assertIsNone(r['exact_retained_points'])
        self.assertIn('UNMAPPED_ASSET_SPECIFICATION', [e['code'] for e in r['unresolved']])
        self.assertEqual(n, before)

    def test_duplicate_identity_and_units_reject(self):
        for kind in ('source', 'holding', 'unit', 'spec'):
            n, c = nation(), catalog(); n['holdings'] = [holding()]
            if kind == 'unit':
                n['holdings'][0]['quantity']['unit'] = 'wrong'
            elif kind == 'spec':
                c['specifications'].append(deepcopy(c['specifications'][0]))
            else:
                other = holding()
                other['holding_id' if kind == 'source' else 'source_id'] += '2'
                n['holdings'].append(other)
            with self.subTest(kind=kind):
                r = evaluate_initial_holdings(n, c)
                self.assertEqual(r['status'], 'invalid')
                self.assertFalse(r['accepted_initial_accounting'])
                self.assertIsNone(r['exact_retained_points'])

    def test_integer_units_and_uninterpreted_rules(self):
        n, c = nation(), catalog(); n['holdings'] = [holding()]
        n['holdings'][0]['quantity']['value'] = '1.5'
        c['specifications'][0]['quantity_rules'] = 'nonnegative_integer'
        r = evaluate_initial_holdings(n, c)
        self.assertIn('INTEGER_QUANTITY_REQUIRED', [e['code'] for e in r['errors']])
        c['specifications'][0]['quantity_rules'] = 'the quantities should probably be whole'
        r = evaluate_initial_holdings(n, c)
        self.assertEqual(r['status'], 'unresolved')
        c['specifications'][0]['quantity_rules'] = 'nonnegative_decimal'
        self.assertTrue(evaluate_initial_holdings(n, c)['accepted_initial_accounting'])

    def test_tiny_overrun_is_not_rounded_away(self):
        n, c = nation(), catalog(); n['holdings'] = [holding()]
        c['specifications'][0]['points_per_unit'] = {'numerator': '1', 'denominator': '1'}
        n['holdings'][0]['quantity']['value'] = '1000.0000000000000000000000000000000000000001'
        r = evaluate_initial_holdings(n, c)
        self.assertEqual(r['status'], 'over_budget')
        self.assertFalse(r['accepted_initial_accounting'])
        self.assertGreater(rational(r['over_budget_points']), 0)
        self.assertIsNone(r['exact_retained_points'])

    def test_missing_and_obviously_wrong_claim_require_review(self):
        for claim in (None, '1'):
            n = nation(); n['reported_retained_points'] = claim
            r = evaluate_initial_holdings(n, catalog())
            self.assertTrue(r['accepted_initial_accounting'])
            self.assertTrue(r['requires_manual_balance_review'])
            self.assertEqual(rational(r['exact_retained_points']), 1000)
            self.assertNotEqual(r['reported_balance_matches'], True)

    def test_general_uncertainties_are_preserved_for_semantic_review(self):
        n = nation(); n['unresolved'] = ['Geological details are unknown.']
        before = deepcopy(n)
        r = evaluate_initial_holdings(n, catalog())
        self.assertTrue(r['accepted_initial_accounting'])
        self.assertEqual(r['nation_uncertainties'], n['unresolved'])
        self.assertEqual(r['unresolved'], [])
        self.assertTrue(r['manual_spec_review_required'])
        self.assertFalse(r['world_physics_approved'])
        r['nation_uncertainties'].append('Independent DERIVED mutation')
        self.assertEqual(n, before)

    def test_invalid_or_pathological_numeric_and_draft_catalog_stop(self):
        for value in ('-1', 'NaN', '1e999999999', True, 1.2):
            n = nation(); n['holdings'] = [holding()]
            n['holdings'][0]['quantity']['value'] = value
            with self.subTest(value=value):
                r = evaluate_initial_holdings(n, catalog())
                self.assertFalse(r['accepted_initial_accounting'])
                self.assertTrue(r['errors'])
        c = catalog(); c['status'] = 'draft'
        self.assertEqual(evaluate_initial_holdings(nation(), c)['status'], 'invalid')


if __name__ == '__main__':
    unittest.main()
