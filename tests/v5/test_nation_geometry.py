"""Synthetic exact-geometry fixtures; never simulation or generated-world data."""
from copy import deepcopy
from fractions import Fraction
import socket
import unittest
from unittest.mock import patch

from homeostasis_v5.nation_generation_contract import record_hash
from homeostasis_v5.nation_geometry import derive_geometry


IDS = [f'nation-{index:03}' for index in range(1, 13)]


def rectangle(x1, y1, x2, y2):
    return {'exterior': [[str(x1), str(y1)], [str(x2), str(y1)], [str(x2), str(y2)], [str(x1), str(y2)]], 'holes': []}


def fixture():
    return {'world_id': 'test-world', 'coordinate_system': 'planar_cartesian_km',
            'extent_km': {'min_x': '0', 'min_y': '0', 'max_x': '100', 'max_y': '100'},
            'regions': [{'region_id': f'r{i}', 'polygons': [rectangle(i * 3, 0, i * 3 + 2, 2)],
                         'surface_description': 'synthetic land', 'terrain_description': 'fixture only',
                         'natural_endowment_notes': [], 'uncertainties': []} for i in range(12)],
            'nation_slots': [{'nation_id': nid, 'territory_region_ids': [f'r{i}'], 'boundary_claims': [],
                              'geography_notes': 'fixture only', 'uncertainties': []} for i, nid in enumerate(IDS)],
            'unresolved': []}


def run(record, **kwargs):
    return derive_geometry(record, expected_world_id='test-world', expected_nation_ids=IDS, **kwargs)


def ratio(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


class NationGeometryTests(unittest.TestCase):
    def setUp(self):
        blocker = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_NETWORK'))
        blocker.start()
        self.addCleanup(blocker.stop)

    def assertStops(self, record, code):
        before = deepcopy(record)
        result = run(record)
        self.assertFalse(result['accepted_for_nation_context'])
        self.assertFalse(result['simulation_physical_approval'])
        self.assertIn(code, {reason['code'] for reason in result['stop_reasons']})
        self.assertEqual(record, before)
        return result

    def test_disconnected_world_is_accepted_without_routes_and_has_66_nation_pairs(self):
        record = fixture()
        before = deepcopy(record)
        result = run(record, expected_map_hash=record_hash(record))
        self.assertTrue(result['accepted_for_nation_context'])
        self.assertFalse(result['simulation_physical_approval'])
        self.assertEqual(len(result['nation_pairs']), 66)
        self.assertEqual(ratio(result['regions'][0]['area_km2']), 4)
        self.assertEqual(ratio(result['nation_pairs'][0]['squared_distance_km2']), 1)
        self.assertTrue(all(pair['adjacency'] == 'disjoint' for pair in result['nation_pairs']))
        self.assertEqual(record, before)

    def test_common_edge_is_distinguished_from_point_contact(self):
        record = fixture()
        record['regions'][1]['polygons'] = [rectangle(2, 0, 4, 2)]
        record['regions'][2]['polygons'] = [rectangle(4, 2, 6, 4)]
        result = run(record)
        self.assertTrue(result['accepted_for_nation_context'])
        pair = {(p['first_id'], p['second_id']): p for p in result['region_pairs']}
        self.assertEqual(pair['r0', 'r1']['adjacency'], 'shared_boundary_segment')
        self.assertEqual(pair['r1', 'r2']['adjacency'], 'point_contact_only')
        self.assertEqual(ratio(pair['r0', 'r1']['squared_distance_km2']), 0)

    def test_holes_islands_and_unowned_sea_keep_exact_areas(self):
        record = fixture()
        outer = rectangle(50, 50, 60, 60)
        outer['holes'] = [rectangle(52, 52, 58, 58)['exterior']]
        record['regions'][0]['polygons'] = [outer, rectangle(70, 70, 71, 71)]
        sea = deepcopy(record['regions'][0])
        sea.update(region_id='unowned-water', polygons=[rectangle(53, 53, 57, 57)], surface_description='water')
        record['regions'].append(sea)
        result = run(record)
        self.assertTrue(result['accepted_for_nation_context'])
        self.assertEqual(ratio(result['regions'][0]['area_km2']), 65)
        self.assertEqual(len(result['nation_territories']), 12)

    def test_concavity_and_reversed_ring_orientation_do_not_change_area(self):
        record = fixture()
        shape = [['50','50'], ['54','50'], ['54','51'], ['51','51'], ['51','54'], ['50','54']]
        record['regions'][0]['polygons'] = [{'exterior': shape, 'holes': []}]
        first = run(record)
        record['regions'][0]['polygons'][0]['exterior'].reverse()
        second = run(record)
        self.assertTrue(first['accepted_for_nation_context'])
        self.assertTrue(second['accepted_for_nation_context'])
        self.assertEqual(ratio(first['regions'][0]['area_km2']), 7)
        self.assertEqual(first['regions'][0]['area_km2'], second['regions'][0]['area_km2'])

    def test_self_crossing_backtracking_and_zero_area_stop_without_repair(self):
        for ring in ([['0','0'], ['2','2'], ['0','2'], ['2','0']],
                     [['0','0'], ['2','0'], ['1','0'], ['0','2']],
                     [['0','0'], ['1','0'], ['2','0']]):
            record = fixture()
            record['regions'][0]['polygons'] = [{'exterior': ring, 'holes': []}]
            self.assertStops(record, 'SELF_INTERSECTING_RING')

    def test_hole_outside_touching_crossing_and_nested_holes_stop(self):
        cases = [([rectangle(3, 3, 4, 4)['exterior']], 'HOLE_OUTSIDE_EXTERIOR'),
                 ([rectangle(0, 0, 1, 1)['exterior']], 'HOLE_BOUNDARY_CONTACT_UNSUPPORTED'),
                 ([rectangle('0.2','0.2','1.8','1.8')['exterior'], rectangle('0.5','0.5','1','1')['exterior']],
                  'HOLES_OVERLAP_OR_NESTED')]
        for holes, code in cases:
            record = fixture()
            record['regions'][0]['polygons'][0]['holes'] = holes
            self.assertStops(record, code)

    def test_interiors_overlapping_with_crossings_shared_edges_or_containment_stop(self):
        for shape in (rectangle(1, 1, 3, 3), rectangle(1, 0, 3, 2), rectangle(0, 0, 2, 2),
                      rectangle('0.2','0.2','1.8','1.8')):
            record = fixture()
            record['regions'][1]['polygons'] = [shape]
            self.assertStops(record, 'REGIONS_INTERIOR_OVERLAP')

    def test_overlapping_parts_and_shared_assignment_stop_but_claims_do_not_reassign(self):
        record = fixture()
        record['regions'][0]['polygons'].append(rectangle(1, 0, 2, 2))
        self.assertStops(record, 'REGION_PARTS_INTERIOR_OVERLAP')
        record = fixture()
        record['nation_slots'][1]['territory_region_ids'].append('r0')
        self.assertStops(record, 'SHARED_TERRITORY_UNRESOLVED')
        record = fixture()
        record['nation_slots'][1]['boundary_claims'] = [{'region_id': 'r0', 'claim': 'unilateral claim, not adjudicated'}]
        result = run(record)
        self.assertTrue(result['accepted_for_nation_context'])
        self.assertEqual(result['boundary_claims'][0]['claims'], record['nation_slots'][1]['boundary_claims'])
        self.assertEqual(result['nation_territories'][0]['region_ids'], ['r0'])

    def test_sub_float_gap_is_not_snapped_to_adjacency(self):
        record = fixture()
        record['regions'][1]['polygons'] = [rectangle('2.000000000000000000000000000001', 0, 4, 2)]
        result = run(record)
        self.assertTrue(result['accepted_for_nation_context'])
        pair = result['nation_pairs'][0]
        self.assertEqual(pair['adjacency'], 'disjoint')
        self.assertEqual(ratio(pair['squared_distance_km2']), Fraction(1, 10**60))

    def test_extent_references_hash_and_complexity_fail_explicitly(self):
        record = fixture()
        record['regions'][0]['polygons'][0]['exterior'][0] = ['-1','0']
        self.assertStops(record, 'COORDINATE_OUTSIDE_EXTENT')
        record = fixture()
        record['nation_slots'][0]['territory_region_ids'] = ['missing']
        self.assertStops(record, 'UNKNOWN_REGION_REFERENCE')
        result = run(fixture(), expected_map_hash='0' * 64)
        self.assertEqual(result['stop_reasons'][0]['code'], 'MAP_HASH_MISMATCH')
        with patch('homeostasis_v5.nation_geometry.MAX_TOTAL_VERTICES', 4):
            self.assertStops(fixture(), 'GEOMETRY_COMPLEXITY_UNSUPPORTED')

    def test_uncertainties_are_preserved_without_claiming_truth(self):
        record = fixture()
        record['unresolved'] = ['geological composition not established']
        result = run(record)
        self.assertEqual(result['declared_uncertainties'][0]['items'], record['unresolved'])
        self.assertIn('geographic_prose_truth', result['unperformed_checks'])
        self.assertFalse(result['simulation_physical_approval'])

    def test_single_argument_api_and_optional_identity_pins(self):
        self.assertTrue(derive_geometry(fixture())['accepted_for_nation_context'])
        result = derive_geometry(fixture(), expected_world_id='other-world')
        self.assertFalse(result['accepted_for_nation_context'])
        self.assertIn('WORLD_ID_MISMATCH', {reason['code'] for reason in result['stop_reasons']})

    def test_empty_territory_preserves_nation_and_records_undefined_distance_for_review(self):
        record = fixture()
        record['nation_slots'][0]['territory_region_ids'] = []
        result = self.assertStops(record, 'EMPTY_TERRITORY_REQUIRES_CONTENT_REVIEW')
        self.assertEqual(result['status'], 'needs_content_review')
        self.assertEqual(len(result['nation_territories']), 12)
        self.assertEqual(ratio(result['nation_territories'][0]['area_km2']), 0)
        self.assertEqual(result['nation_territories'][0]['region_ids'], [])
        first_pairs = [pair for pair in result['nation_pairs'] if pair['first_id'] == IDS[0]]
        self.assertEqual(len(first_pairs), 11)
        self.assertTrue(all(pair['adjacency'] == 'undefined_empty_territory' for pair in first_pairs))
        self.assertTrue(all(pair['distance_km'] is None for pair in first_pairs))


if __name__ == '__main__':
    unittest.main()
