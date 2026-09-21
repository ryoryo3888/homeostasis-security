"""Synthetic offline records; none are generated nations or adopted asset prices."""
from copy import deepcopy
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from homeostasis_v5 import nation_generation_contract as contract


IDS = [f'nation-{index:03}' for index in range(1, 13)]


def geography():
    return {'world_id': 'world-test', 'coordinate_system': 'planar_cartesian_km',
            'extent_km': {'min_x': '0', 'min_y': '0', 'max_x': '20', 'max_y': '20'},
            'regions': [{'region_id': f'region-{i}',
                         'polygons': [{'exterior': [[str(i), '0'], [str(i + 1), '0'], [str(i), '1']], 'holes': []}],
                         'surface_description': 'synthetic land', 'terrain_description': 'test only',
                         'natural_endowment_notes': [], 'uncertainties': []} for i in range(12)],
            'nation_slots': [{'nation_id': nid, 'territory_region_ids': [f'region-{i}'],
                              'boundary_claims': [], 'geography_notes': 'test only', 'uncertainties': []}
                             for i, nid in enumerate(IDS)], 'unresolved': []}


def reference():
    return {'record_id': 'synthetic-not-real-approval', 'sha256': 'a' * 64}


def catalog():
    return {'version': 'synthetic-only-v1', 'status': 'approved_for_nation_generation',
            'reference_year': 2024, 'usd_per_point': '10000000', 'points_per_nation': '1000',
            'approval_ref': reference(), 'coverage_review': {'review_ref': reference(), 'known_gaps': []},
            'specifications': [{'spec_id': 'synthetic-stock', 'name': 'test item', 'asset_kind': 'inventory',
                                'unit': 'test_unit', 'definition': 'synthetic, not a real V5 capability',
                                'acquisition_scope': 'fixture only', 'quantity_rules': 'fixture only',
                                'operating_requirements': 'fixture only', 'state_valuation_rules': 'fixture only',
                                'points_per_unit': {'numerator': '1', 'denominator': '3'},
                                'source_refs': [reference()], 'adoption_ref': reference()}],
            'free_proposal_policy': 'preserve_and_stop_if_unresolved'}


def request(nid=IDS[0], map_record=None, catalog_record=None):
    m = geography() if map_record is None else map_record
    c = catalog() if catalog_record is None else catalog_record
    return contract.build_nation_request(m, nid, c, expected_map_hash=contract.record_hash(m),
                                        expected_catalog_hash=contract.record_hash(c))


def nation():
    return {'world_id': 'world-test', 'nation_id': IDS[0],
            'geography_ref': {'map_sha256': contract.record_hash(geography()), 'territory_region_ids': ['region-0']},
            'name': 'synthetic nation', 'population': {'count': 123, 'description': 'fixture only'},
            'society': {key: 'test only' for key in ('social_structure', 'economy', 'institutions', 'technology',
                                                   'strengths', 'weaknesses', 'other_notes')},
            'natural_resources': [], 'holdings': [], 'free_asset_proposals': [],
            'external_relation_claims': [], 'reported_retained_points': '1000', 'unresolved': []}


class NationGenerationContractTests(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_NETWORK'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_map_is_12_slots_without_persona_assets_or_runtime_settings(self):
        result = contract.build_map_request('world-test', IDS)
        self.assertEqual(set(result['context']), {'world_id', 'nation_ids', 'coordinate_system'})
        self.assertEqual(result['context']['nation_ids'], IDS)
        self.assertIsNone(result['runtime_settings'])
        self.assertFalse(result['executable'])
        for key in ('model', 'temperature', 'seed', 'generationConfig', 'maxOutputTokens', 'defaults', 'examples'):
            self.assertNotIn(f'"{key}"', contract.record_bytes(result).decode())
        with self.assertRaises(TypeError):
            contract.build_map_request('world-test', IDS, personas={'secret': 'PERSONA_SENTINEL'})

    def test_all_nations_share_full_geography_and_only_own_id_changes(self):
        packages = [request(nid) for nid in IDS]
        for package in packages:
            self.assertEqual(package['context']['common_geography'], geography())
            self.assertEqual(len(package['context']['common_geography']['nation_slots']), 12)
        contexts = [deepcopy(package['context']) for package in packages]
        for context in contexts:
            context.pop('own_nation_id')
        self.assertTrue(all(context == contexts[0] for context in contexts))

    def test_extra_context_records_are_rejected_even_if_rehashed(self):
        for key in ('personas', 'leaders', 'previous_nations', 'messages', 'assets'):
            with self.subTest(key=key):
                m = geography()
                m[key] = 'DO_NOT_SEND'
                with self.assertRaisesRegex(contract.NationContractError, 'MAP_SCHEMA_ERROR'):
                    request(map_record=m)
        c = catalog()
        c['other_nations'] = 'DO_NOT_SEND'
        with self.assertRaisesRegex(contract.NationContractError, 'CATALOG_SCHEMA_ERROR'):
            request(catalog_record=c)

    def test_draft_reference_catalog_is_not_a_generation_menu(self):
        path = Path(__file__).resolve().parents[2] / 'docs/design/v5/NATION_ASSET_CATALOG.proposed.json'
        draft = json.loads(path.read_text())
        with self.assertRaisesRegex(contract.NationContractError, 'CATALOG_SCHEMA_ERROR'):
            request(catalog_record=draft)

    def test_input_output_mutation_does_not_change_later_builds_or_schema_order(self):
        m, c = geography(), catalog()
        before = deepcopy((m, c))
        first = request(map_record=m, catalog_record=c)
        self.assertEqual((m, c), before)
        original = contract.record_bytes(first)
        first['context']['common_geography']['regions'].clear()
        first['response_schema']['properties'].clear()
        self.assertEqual(contract.record_bytes(request(map_record=m, catalog_record=c)), original)
        self.assertEqual(list(contract.schema_for('nation')['properties'])[:3], ['world_id', 'nation_id', 'geography_ref'])

    def test_hash_pin_identity_reference_and_slot_checks(self):
        with self.assertRaisesRegex(contract.NationContractError, 'MAP_HASH_MISMATCH'):
            contract.build_nation_request(geography(), IDS[0], catalog(), expected_map_hash='0'*64,
                                         expected_catalog_hash=contract.record_hash(catalog()))
        with self.assertRaisesRegex(contract.NationContractError, 'CATALOG_HASH_MISMATCH'):
            contract.build_nation_request(geography(), IDS[0], catalog(), expected_map_hash=contract.record_hash(geography()),
                                         expected_catalog_hash='0'*64)
        for ids in (IDS[:11], IDS + ['nation-013'], [IDS[0]] * 12):
            with self.assertRaisesRegex(contract.NationContractError, 'NATION_IDS_MUST_BE_12_UNIQUE'):
                contract.build_map_request('world-test', ids)
        with self.assertRaisesRegex(contract.NationContractError, 'UNKNOWN_OWN_NATION'):
            request('missing')
        changed = nation()
        changed['geography_ref']['territory_region_ids'] = ['region-1']
        with self.assertRaisesRegex(contract.NationContractError, 'TERRITORY_REFERENCE_MISMATCH'):
            contract.inspect_nation_output(changed, request())

    def test_all_points_can_be_reported_retained_without_inventing_assets(self):
        record = nation()
        before = deepcopy(record)
        report = contract.inspect_nation_output(record, request())
        self.assertTrue(report['structurally_valid'])
        self.assertFalse(report['accepted_initial_nation'])
        self.assertIsNone(report['accepted_retained_points'])
        self.assertEqual(record, before)
        self.assertEqual(record['reported_retained_points'], '1000')
        self.assertEqual(record['holdings'], [])

    def test_unknown_asset_proposal_is_preserved_and_not_priced_as_zero(self):
        record = nation()
        record['holdings'] = [{'holding_id': 'h1', 'source_id': 's1', 'name': 'unlisted asset', 'spec_id': None,
                               'asset_kind': 'novel', 'quantity': {'value': '1', 'unit': 'item'}, 'region_ids': ['region-0'],
                               'state_description': 'unknown', 'capability_claim': 'original capability claim',
                               'dependencies': [], 'proposal_id': 'p1'}]
        record['free_asset_proposals'] = [{'proposal_id': 'p1', 'original_text': 'ORIGINAL_UNKNOWN_PROPOSAL',
                                          'specification_claim': 'not a mapped capability',
                                          'quantity': {'value': None, 'unit': None},
                                          'related_holding_ids': ['h1'], 'unresolved_fields': ['price']}]
        before = deepcopy(record)
        report = contract.inspect_nation_output(record, request())
        self.assertIn('UNMAPPED_ASSET_SPECIFICATION', report['unresolved'])
        self.assertIn('FREE_PROPOSAL_REQUIRES_REVIEW', report['unresolved'])
        self.assertIsNone(report['accepted_retained_points'])
        self.assertTrue(report['requires_stop_before_acceptance'])
        self.assertEqual(record, before)

    def test_multiple_islands_holes_and_unowned_regions_are_not_forbidden(self):
        m = geography()
        m['regions'][0]['polygons'].append({'exterior': [['15','15'], ['19','15'], ['19','19'], ['15','19']],
                                           'holes': [[['16','16'], ['17','16'], ['16','17']]]})
        unused = deepcopy(m['regions'][1])
        unused['region_id'] = 'unowned-sea'
        unused['surface_description'] = 'sea'
        m['regions'].append(unused)
        report = contract.inspect_map_output(m, expected_world_id='world-test', expected_nation_ids=IDS)
        self.assertTrue(report['structurally_valid'])
        self.assertIn('polygon_topology', report['unperformed_checks'])
        self.assertFalse(report['accepted_initial_world'])

    def test_no_geometry_or_relation_or_free_text_becomes_physical_effect(self):
        record = nation()
        record['external_relation_claims'] = [{'nation_ids': [IDS[1]], 'claim_text': 'Unilateral claim of alliance.'}]
        record['society']['technology'] = 'A free text claim of limitless capacity.'
        report = contract.inspect_nation_output(record, request())
        self.assertFalse(report['accepted_initial_nation'])
        self.assertIn('physical_feasibility', report['unperformed_checks'])
        changed = deepcopy(record)
        changed['area_km2'] = '100'
        with self.assertRaisesRegex(contract.NationContractError, 'NATION_SCHEMA_ERROR'):
            contract.inspect_nation_output(changed, request())

    def test_request_package_changes_cannot_bypass_hash_or_context_boundaries(self):
        changed = request()
        changed['context']['previous_nations'] = 'OTHER_NATION_SENTINEL'
        with self.assertRaisesRegex(contract.NationContractError, 'REQUEST_PACKAGE_MUTATED'):
            contract.inspect_nation_output(nation(), changed)
        changed = request()
        changed['context']['common_geography']['regions'][0]['terrain_description'] = 'changed'
        with self.assertRaisesRegex(contract.NationContractError, 'MAP_HASH_MISMATCH'):
            contract.inspect_nation_output(nation(), changed)

    def test_known_spec_units_and_duplicate_capacity_claims_are_checked(self):
        base = {'holding_id': 'h1', 'source_id': 's1', 'name': 'known test holding',
                'spec_id': 'synthetic-stock', 'asset_kind': 'inventory',
                'quantity': {'value': '1', 'unit': 'test_unit'}, 'region_ids': ['region-0'],
                'state_description': 'test only', 'capability_claim': 'test only',
                'dependencies': [], 'proposal_id': None}
        record = nation()
        record['holdings'] = [base]
        self.assertTrue(contract.inspect_nation_output(record, request())['structurally_valid'])
        changed = deepcopy(record)
        changed['holdings'][0]['quantity']['unit'] = 'other_unit'
        with self.assertRaisesRegex(contract.NationContractError, 'HOLDING_UNIT_MISMATCH'):
            contract.inspect_nation_output(changed, request())
        changed = deepcopy(record)
        second = dict(deepcopy(base), holding_id='h2')
        changed['holdings'].append(second)
        with self.assertRaisesRegex(contract.NationContractError, 'DUPLICATE_SOURCE_CLAIM'):
            contract.inspect_nation_output(changed, request())

    def test_bad_coordinates_and_extra_fields_are_rejected_without_correction(self):
        for mutation in ('nonfinite', 'extreme', 'outside', 'missing-region', 'leader-field'):
            m = geography()
            if mutation == 'nonfinite':
                m['regions'][0]['polygons'][0]['exterior'][0][0] = 'NaN'
            elif mutation == 'extreme':
                m['extent_km']['max_x'] = '1e1000000000'
            elif mutation == 'outside':
                m['regions'][0]['polygons'][0]['exterior'][0][0] = '21'
            elif mutation == 'missing-region':
                m['nation_slots'][0]['territory_region_ids'] = ['missing']
            else:
                m['nation_slots'][0]['leader'] = 'SECRET'
            before = deepcopy(m)
            with self.subTest(mutation=mutation), self.assertRaises(contract.NationContractError):
                request(map_record=m)
            self.assertEqual(m, before)


if __name__ == '__main__':
    unittest.main()
