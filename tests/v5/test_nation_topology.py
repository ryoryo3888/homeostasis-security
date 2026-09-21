"""Independent shared-boundary regression checks; all worlds are synthetic."""
from copy import deepcopy
from fractions import Fraction
import socket
import unittest
from unittest.mock import patch

from homeostasis_v5.nation_generation_contract import record_hash
from homeostasis_v5 import nation_topology as topology

IDS = [f'nation-{i:03d}' for i in range(1, 13)]


def edge_ref(edge_id, direction='forward'):
    return {'edge_id': edge_id, 'direction': direction}


def fixture():
    # Two adjacent boxes share one edge ID; ten other islands are disconnected.
    vertices = [
        {'vertex_id': 'a', 'position_km': ['0', '0']},
        {'vertex_id': 'b', 'position_km': ['2', '0']},
        {'vertex_id': 'c', 'position_km': ['2', '2']},
        {'vertex_id': 'd', 'position_km': ['0', '2']},
        {'vertex_id': 'e', 'position_km': ['4', '0']},
        {'vertex_id': 'f', 'position_km': ['4', '2']},
    ]
    edges = [{'edge_id': name, 'start_vertex_id': start, 'end_vertex_id': end}
             for name, start, end in [('ab', 'a', 'b'), ('bc', 'b', 'c'), ('cd', 'c', 'd'), ('da', 'd', 'a'),
                                      ('be', 'b', 'e'), ('ef', 'e', 'f'), ('fc', 'f', 'c')]]
    loops = [[edge_ref(e) for e in ('ab', 'bc', 'cd', 'da')],
             [edge_ref('be'), edge_ref('ef'), edge_ref('fc'), edge_ref('bc', 'reverse')]]
    for i in range(2, 12):
        x = 6 + i * 3
        names = [f'p{i}-{j}' for j in range(4)]
        for name, position in zip(names, [(x, 0), (x + 2, 0), (x + 2, 2), (x, 2)]):
            vertices.append({'vertex_id': name, 'position_km': list(map(str, position))})
        loop = []
        for j in range(4):
            name = f'e{i}-{j}'
            edges.append({'edge_id': name, 'start_vertex_id': names[j], 'end_vertex_id': names[(j + 1) % 4]})
            loop.append(edge_ref(name))
        loops.append(loop)
    return {'world_id': 'synthetic-topology', 'coordinate_system': 'planar_cartesian_km',
            'extent_km': {'min_x': '0', 'min_y': '0', 'max_x': '100', 'max_y': '100'},
            'vertices': vertices, 'edges': edges,
            'regions': [{'region_id': f'r{i}', 'polygons': [{'exterior': loop, 'holes': []}],
                         'surface_description': 'synthetic land', 'terrain_description': 'fixture only',
                         'natural_endowment_notes': [], 'uncertainties': []}
                        for i, loop in enumerate(loops)],
            'nation_slots': [{'nation_id': nid, 'territory_region_ids': [f'r{i}'], 'boundary_claims': [],
                              'geography_notes': 'fixture only', 'uncertainties': []} for i, nid in enumerate(IDS)],
            'unresolved': []}


def from_map_fixture(map_record):
    """Synthetic adapter for transport fixtures only, never applied to RAW."""
    result = deepcopy(map_record)
    vertices, edges, vertex_ids, edge_ids = [], [], {}, {}
    def loop(ring):
        ids = []
        for xy in ring:
            key = tuple(Fraction(value) for value in xy)
            if key not in vertex_ids:
                vid = 'v' + str(len(vertices))
                vertex_ids[key] = vid
                vertices.append({'vertex_id': vid, 'position_km': deepcopy(xy)})
            ids.append(vertex_ids[key])
        references = []
        for start, end in zip(ids, ids[1:] + ids[:1]):
            key = frozenset((start, end))
            if key not in edge_ids:
                eid = 'e' + str(len(edges))
                edge_ids[key] = (eid, start, end)
                edges.append({'edge_id': eid, 'start_vertex_id': start, 'end_vertex_id': end})
            eid, original_start, original_end = edge_ids[key]
            references.append(edge_ref(eid, 'forward' if start == original_start else 'reverse'))
        return references
    for region in result['regions']:
        for polygon in region['polygons']:
            polygon['exterior'] = loop(polygon['exterior'])
            polygon['holes'] = [loop(hole) for hole in polygon['holes']]
    result['vertices'], result['edges'] = vertices, edges
    return result


def add_box(record, name, x1, y1, x2, y2):
    names = [name + str(i) for i in range(4)]
    for vertex, xy in zip(names, [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]):
        record['vertices'].append({'vertex_id': vertex, 'position_km': list(map(str, xy))})
    loop = []
    for i in range(4):
        eid = name + '-edge-' + str(i)
        record['edges'].append({'edge_id': eid, 'start_vertex_id': names[i], 'end_vertex_id': names[(i + 1) % 4]})
        loop.append(edge_ref(eid))
    return loop


def compile_record(record):
    return topology.compile_topology(record, expected_world_id='synthetic-topology', expected_nation_ids=IDS)


class NationTopologyTests(unittest.TestCase):
    def setUp(self):
        blocker = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_NETWORK'))
        blocker.start(); self.addCleanup(blocker.stop)

    def assertRejected(self, record):
        before = deepcopy(record)
        with self.assertRaises(topology.TopologyError) as captured:
            compile_record(record)
        self.assertEqual(record, before)
        self.assertFalse(captured.exception.report.get('accepted_for_nation_context', False))
        return captured.exception

    def test_shared_edge_compiles_exactly_without_input_mutation(self):
        record = fixture(); before = deepcopy(record)
        result = compile_record(record)
        m = result['map']
        self.assertEqual(m['regions'][0]['polygons'][0]['exterior'], [['0','0'], ['2','0'], ['2','2'], ['0','2']])
        self.assertEqual(m['regions'][1]['polygons'][0]['exterior'], [['2','0'], ['4','0'], ['4','2'], ['2','2']])
        self.assertNotIn('vertices', m); self.assertNotIn('edges', m)
        self.assertEqual(record, before)
        self.assertEqual(record_hash(result), record_hash(compile_record(record)))
        report = result['report']
        self.assertEqual(report['raw_topology_sha256'], record_hash(record))
        self.assertEqual(report['compiled_map_sha256'], record_hash(m))
        self.assertFalse(report['simulation_physical_approval'])
        self.assertIn('bc', report['graph']['shared_edges'])
        self.assertEqual(len(report['geometry']['nation_pairs']), 66)
        pair = report['geometry']['nation_pairs'][0]
        self.assertEqual(pair['adjacency'], 'shared_boundary_segment')

    def test_shared_edge_orientation_can_reverse_without_rewriting_original(self):
        record = fixture()
        record['edges'][1]['start_vertex_id'], record['edges'][1]['end_vertex_id'] = 'c', 'b'
        record['regions'][0]['polygons'][0]['exterior'][1]['direction'] = 'reverse'
        record['regions'][1]['polygons'][0]['exterior'][3]['direction'] = 'forward'
        self.assertEqual(compile_record(record)['map'], compile_record(fixture())['map'])

    def test_unknown_edges_vertices_nonclosed_and_direction_errors_stop(self):
        record = fixture(); record['regions'][0]['polygons'][0]['exterior'][1]['edge_id'] = 'missing'; self.assertRejected(record)
        record = fixture(); record['edges'][0]['start_vertex_id'] = 'missing'; self.assertRejected(record)
        record = fixture(); record['regions'][0]['polygons'][0]['exterior'].pop(); self.assertRejected(record)
        record = fixture(); record['regions'][0]['polygons'][0]['exterior'][1]['direction'] = 'reverse'; self.assertRejected(record)

    def test_duplicate_identifiers_coordinates_and_geometric_edge_stop(self):
        record = fixture(); record['vertices'].append(deepcopy(record['vertices'][0])); self.assertRejected(record)
        record = fixture(); record['vertices'].append({'vertex_id': 'alias', 'position_km': ['0.0', '0e0']}); self.assertRejected(record)
        record = fixture(); record['edges'].append({'edge_id': 'bc-alias', 'start_vertex_id': 'c', 'end_vertex_id': 'b'}); self.assertRejected(record)
        record = fixture(); record['edges'][1]['edge_id'] = 'ab'; self.assertRejected(record)

    def test_unresolved_t_junction_and_crossing_do_not_get_automatically_split(self):
        record = fixture()
        record['vertices'].extend([{'vertex_id': 't', 'position_km': ['1', '0']}, {'vertex_id': 'u', 'position_km': ['1','1']}])
        record['edges'].append({'edge_id': 'tu', 'start_vertex_id': 't', 'end_vertex_id': 'u'})
        self.assertIn(self.assertRejected(record).code, ('EDGE_CONTACT_WITHOUT_SHARED_VERTEX', 'VERTEX_IN_EDGE_INTERIOR'))
        record = fixture()
        record['edges'].extend([{'edge_id': 'diagonal-ac', 'start_vertex_id': 'a', 'end_vertex_id': 'c'},
                                {'edge_id': 'diagonal-db', 'start_vertex_id': 'd', 'end_vertex_id': 'b'}])
        self.assertEqual(self.assertRejected(record).code, 'EDGE_CROSSING_WITHOUT_SHARED_VERTEX')

    def test_shared_graph_does_not_excuse_overlapping_polygon_interiors(self):
        record = fixture()
        # Disconnected purported island sits fully inside another nation's land,
        # reproducing the important prior failure without crossing boundary edges.
        loop = add_box(record, 'overlap', '0.25', '0.25', '1.75', '1.75')
        record['regions'][1]['polygons'].append({'exterior': loop, 'holes': []})
        error = self.assertRejected(record)
        self.assertEqual(error.code, 'COMPILED_MAP_GEOMETRY_REJECTED')
        self.assertIn('REGIONS_INTERIOR_OVERLAP', {row['code'] for row in error.report['stop_reasons']})

    def test_claims_are_preserved_without_changing_territory_assignment(self):
        record = fixture()
        record['nation_slots'][1]['boundary_claims'] = [{'region_id': 'r0', 'claim': 'unilateral synthetic claim'}]
        m = compile_record(record)['map']
        self.assertEqual(m['nation_slots'], record['nation_slots'])
        self.assertEqual(m['nation_slots'][1]['territory_region_ids'], ['r1'])
        record['nation_slots'][1]['territory_region_ids'].append('r0')
        self.assertRejected(record)

    def test_empty_territory_is_retained_but_not_approved(self):
        record = fixture(); record['nation_slots'][0]['territory_region_ids'] = []
        self.assertRejected(record)
        self.assertEqual(record['nation_slots'][0]['territory_region_ids'], [])

    def test_holes_and_disconnected_parts_remain_possible(self):
        record = fixture()
        exterior = add_box(record, 'island', 50, 50, 60, 60)
        hole = add_box(record, 'lake', 52, 52, 58, 58)
        record['regions'][0]['polygons'].append({'exterior': exterior, 'holes': [hole]})
        m = compile_record(record)['map']
        self.assertEqual(len(m['regions'][0]['polygons']), 2)
        self.assertEqual(m['regions'][0]['polygons'][1]['holes'][0], [['52','52'], ['58','52'], ['58','58'], ['52','58']])

    def test_coordinate_precision_is_preserved_without_rounding_or_snapping(self):
        record = fixture()
        for vertex in record['vertices']:
            if vertex['vertex_id'] == 'p2-0':
                vertex['position_km'][0] = '12.000000000000000000000000000001'
        compiled = compile_record(record)['map']
        self.assertEqual(compiled['regions'][2]['polygons'][0]['exterior'][0][0], '12.000000000000000000000000000001')

    def test_world_id_nation_id_and_extent_remain_pinned(self):
        record = fixture(); record['world_id'] = 'other'; self.assertRejected(record)
        record = fixture(); record['nation_slots'][0]['nation_id'] = 'nation-013'; self.assertRejected(record)
        record = fixture(); record['vertices'][0]['position_km'] = ['-0.1', '0']; self.assertRejected(record)

    def test_package_has_no_persona_context_or_world_scenario(self):
        package = topology.build_topology_request('synthetic-topology', IDS)
        self.assertEqual(package['stage'], 'map')
        self.assertEqual(package['context']['world_id'], 'synthetic-topology')
        self.assertEqual(package['context']['nation_ids'], IDS)
        self.assertFalse(package['executable'])
        for key in ('leaders', 'personas', 'previous_nations', 'turn_events', 'required_contacts'):
            self.assertNotIn(key, package['context'])
        schema = topology.topology_schema()
        self.assertIn('vertices', schema['properties'])
        self.assertIn('edges', schema['properties'])
        self.assertNotIn('default', str(schema))


if __name__ == '__main__': unittest.main()
