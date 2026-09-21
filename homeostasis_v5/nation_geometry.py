"""Exact planar-map checks and DERIVED geometry; no map repair or simulation.

Shapely is absent from the existing execution environment. Decimal input strings
are therefore converted losslessly to Fraction for segment predicates, areas,
and squared minimum separations. Irrational distances remain square-root
expressions, not rounded input coordinates or fictional route lengths.

Accepted means geometric suitability for nation-generation context only. This
module does not adjudicate territorial claims, classify terrain prose, approve
transport/physical capabilities, or certify the truth of geographic descriptions.
Touching holes are an unsupported ambiguity and stop, rather than being repaired.
The vertex limit below is an explicit computational limit, not a world-size rule.
"""
from copy import deepcopy
from fractions import Fraction
from itertools import combinations

from homeostasis_v5.nation_generation_contract import (
    NationContractError, inspect_map_output, record_hash,
)


GEOMETRY_VERSION = 'exact-planar-nation-geometry-1'
MAX_TOTAL_VERTICES = 768


class _Stop(Exception):
    def __init__(self, code, **details):
        self.code, self.details = code, details


def _require(value, code, **details):
    if not value:
        raise _Stop(code, **details)


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _orientation(a, b, c):
    return _cross(_sub(b, a), _sub(c, a))


def _on_segment(p, a, b):
    return (_orientation(a, b, p) == 0
            and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _edges(ring):
    return list(zip(ring, ring[1:] + ring[:1]))


def _segment_relation(a, b, c, d):
    """none, point, overlap_segment, or proper_cross; no tolerance/snap."""
    abc, abd, cda, cdb = (_orientation(a, b, c), _orientation(a, b, d),
                          _orientation(c, d, a), _orientation(c, d, b))
    if abc == abd == cda == cdb == 0:
        start, end = max(min(a, b), min(c, d)), min(max(a, b), max(c, d))
        return 'none' if start > end else ('point' if start == end else 'overlap_segment')
    if abc * abd < 0 and cda * cdb < 0:
        return 'proper_cross'
    if any((_on_segment(c, a, b), _on_segment(d, a, b),
            _on_segment(a, c, d), _on_segment(b, c, d))):
        return 'point'
    return 'none'


def _signed_area(ring):
    return sum((_cross(a, b) for a, b in _edges(ring)), Fraction(0)) / 2


def _ring(raw, location):
    ring = [tuple(Fraction(value) for value in point) for point in raw]
    _require(len(set(ring)) == len(ring), 'REPEATED_RING_VERTEX', location=location)
    edges = _edges(ring)
    for i, (a, b) in enumerate(edges):
        _require(a != b, 'ZERO_LENGTH_EDGE', location=location)
        for j in range(i + 1, len(edges)):
            c, d = edges[j]
            relation = _segment_relation(a, b, c, d)
            adjacent = j == i + 1 or (i == 0 and j == len(edges) - 1)
            _require(relation == ('point' if adjacent else 'none'),
                     'SELF_INTERSECTING_RING', location=location, edges=[i, j])
    _require(_signed_area(ring) != 0, 'NON_POSITIVE_RING_AREA', location=location)
    return ring


def _in_ring(point, ring):
    """-1 outside, 0 boundary, 1 inside by exact even-odd ray intersections."""
    inside = False
    x, y = point
    for a, b in _edges(ring):
        if _on_segment(point, a, b):
            return 0
        if (a[1] > y) != (b[1] > y):
            crossing_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if crossing_x > x:
                inside = not inside
    return 1 if inside else -1


def _rings_contact(first, second):
    return any(_segment_relation(a, b, c, d) != 'none'
               for a, b in _edges(first) for c, d in _edges(second))


def _polygon(raw, location):
    exterior = _ring(raw['exterior'], location + '.exterior')
    holes = [_ring(hole, f'{location}.holes[{i}]') for i, hole in enumerate(raw['holes'])]
    for i, hole in enumerate(holes):
        _require(not _rings_contact(exterior, hole), 'HOLE_BOUNDARY_CONTACT_UNSUPPORTED', location=location, hole=i)
        _require(_in_ring(hole[0], exterior) == 1, 'HOLE_OUTSIDE_EXTERIOR', location=location, hole=i)
        for j, previous in enumerate(holes[:i]):
            _require(not _rings_contact(hole, previous), 'HOLES_CONTACT_OR_CROSS', location=location, holes=[j, i])
            _require(_in_ring(hole[0], previous) == -1 and _in_ring(previous[0], hole) == -1,
                     'HOLES_OVERLAP_OR_NESTED', location=location, holes=[j, i])
    area = abs(_signed_area(exterior)) - sum((abs(_signed_area(hole)) for hole in holes), Fraction(0))
    _require(area > 0, 'NON_POSITIVE_POLYGON_AREA', location=location)
    boundaries = []
    for is_hole, ring in [(False, exterior), *((True, hole) for hole in holes)]:
        sign = (1 if _signed_area(ring) > 0 else -1) * (-1 if is_hole else 1)
        # sign=1: polygon interior lies left of this directed boundary segment.
        boundaries.extend((a, b, sign) for a, b in _edges(ring))
    return {'exterior': exterior, 'holes': holes, 'boundaries': boundaries, 'area': area}


def _in_polygon(point, polygon):
    position = _in_ring(point, polygon['exterior'])
    if position != 1:
        return position
    for hole in polygon['holes']:
        hole_position = _in_ring(point, hole)
        if hole_position == 0:
            return 0
        if hole_position == 1:
            return -1
    return 1


def _interior_sample(polygon):
    """Move halfway to the next exact boundary along an inward normal ray."""
    a, b = polygon['exterior'][:2]
    midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    direction = _sub(b, a)
    sign = 1 if _signed_area(polygon['exterior']) > 0 else -1
    normal = (-direction[1] * sign, direction[0] * sign)
    crossings = []
    for c, d, _ in polygon['boundaries']:
        segment = _sub(d, c)
        denominator = _cross(normal, segment)
        offset = _sub(c, midpoint)
        if denominator:
            t, u = _cross(offset, segment) / denominator, _cross(offset, normal) / denominator
            if t > 0 and 0 <= u <= 1:
                crossings.append(t)
        elif _cross(offset, normal) == 0:
            for endpoint in (c, d):
                t = _dot(_sub(endpoint, midpoint), normal) / _dot(normal, normal)
                if t > 0:
                    crossings.append(t)
    _require(bool(crossings), 'INTERIOR_SAMPLE_UNRESOLVED')
    distance = min(crossings) / 2
    sample = (midpoint[0] + distance * normal[0], midpoint[1] + distance * normal[1])
    _require(_in_polygon(sample, polygon) == 1, 'INTERIOR_SAMPLE_UNRESOLVED')
    return sample


def _point_segment_squared(point, a, b):
    edge, offset = _sub(b, a), _sub(point, a)
    t = _dot(offset, edge) / _dot(edge, edge)
    if t <= 0:
        return _dot(offset, offset)
    if t >= 1:
        offset = _sub(point, b)
        return _dot(offset, offset)
    return _cross(offset, edge) ** 2 / _dot(edge, edge)


def _relation(first, second):
    shared_edge, point_touch, minimum = False, False, None
    for a, b, side_first in first['boundaries']:
        for c, d, side_second in second['boundaries']:
            contact = _segment_relation(a, b, c, d)
            if contact == 'proper_cross':
                return {'overlap': True}
            if contact == 'overlap_segment':
                same_direction = _dot(_sub(b, a), _sub(d, c)) > 0
                if side_first == side_second * (1 if same_direction else -1):
                    return {'overlap': True}
                shared_edge = True
            if contact == 'point':
                point_touch = True
            distances = [Fraction(0)] if contact != 'none' else [
                _point_segment_squared(a, c, d), _point_segment_squared(b, c, d),
                _point_segment_squared(c, a, b), _point_segment_squared(d, a, b),
            ]
            value = min(distances)
            minimum = value if minimum is None else min(minimum, value)
    for polygon, other in ((first, second), (second, first)):
        samples = [_interior_sample(polygon)]
        for a, b, _ in polygon['boundaries']:
            # A boundary can cross at the other ring's vertex, without a proper
            # segment crossing. Split there before testing open subsegments;
            # one midpoint for the entire edge could miss a short intersection.
            cuts = {a, b}
            for c, d, _ in other['boundaries']:
                cuts.update(point for point in (c, d) if _on_segment(point, a, b))
            cuts = sorted(cuts)
            samples.extend(cuts)
            samples.extend(((c[0] + d[0]) / 2, (c[1] + d[1]) / 2)
                           for c, d in zip(cuts, cuts[1:]))
        if any(_in_polygon(point, other) == 1 for point in samples):
            return {'overlap': True}
    return {'overlap': False, 'shared_boundary_segment': shared_edge, 'point_touch': point_touch,
            'squared_distance': minimum}


def _ratio(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def _pair_metric(first_id, second_id, relations):
    if not relations:
        return {'first_id': first_id, 'second_id': second_id,
                'shares_boundary_segment': None, 'point_contact': None,
                'adjacency': 'undefined_empty_territory', 'squared_distance_km2': None,
                'distance_km': None}
    minimum = min(relation['squared_distance'] for relation in relations)
    shared = any(relation['shared_boundary_segment'] for relation in relations)
    touching = any(relation['point_touch'] for relation in relations)
    return {'first_id': first_id, 'second_id': second_id,
            'shares_boundary_segment': shared, 'point_contact': touching,
            'adjacency': 'shared_boundary_segment' if shared else ('point_contact_only' if touching else 'disjoint'),
            'squared_distance_km2': _ratio(minimum),
            'distance_km': {'square_root_of': _ratio(minimum)}}


def derive_geometry(map_record, *, expected_world_id=None, expected_nation_ids=None, expected_map_hash=None):
    """Return an immutable-input DERIVED report, stopping on unresolved geometry.

    Territory names/claims are preserved but never adjudicated. Free-text
    uncertainties require separate content review and are not silently filled.
    Whole-map coverage and nation interconnection are not requirements. An empty
    territory list retains the nation with zero area and undefined separation,
    while requiring content review; it is not repaired into a land allocation.
    Optional expected values pin identity to the caller's frozen configuration.
    """
    report = {'geometry_version': GEOMETRY_VERSION, 'status': 'stopped',
              'accepted_for_nation_context': False, 'simulation_physical_approval': False,
              'input_map_sha256': None, 'arithmetic': 'exact rational coordinates and predicates',
              'distance_definition': 'minimum separation of declared territory geometries; not route length or travel time',
              'computational_limit': {'max_total_vertices': MAX_TOTAL_VERTICES},
              'stop_reasons': [], 'regions': [], 'nation_territories': [], 'region_pairs': [], 'nation_pairs': [],
              'boundary_claims': [], 'declared_uncertainties': [],
              'unperformed_checks': ['geographic_prose_truth', 'political_claim_adjudication',
                                    'terrain_semantics', 'physical_capabilities', 'transport_routes']}
    try:
        report['input_map_sha256'] = record_hash(map_record)
        if expected_map_hash is not None:
            _require(report['input_map_sha256'] == expected_map_hash, 'MAP_HASH_MISMATCH')
        if expected_world_id is None and isinstance(map_record, dict):
            expected_world_id = map_record.get('world_id')
        if expected_nation_ids is None:
            slots = map_record.get('nation_slots', []) if isinstance(map_record, dict) else []
            expected_nation_ids = [slot.get('nation_id') if isinstance(slot, dict) else None
                                   for slot in slots] if isinstance(slots, list) else []
        inspect_map_output(map_record, expected_world_id=expected_world_id, expected_nation_ids=expected_nation_ids)
        total_vertices = sum(len(ring) for region in map_record['regions'] for polygon in region['polygons']
                             for ring in (polygon['exterior'], *polygon['holes']))
        _require(total_vertices <= MAX_TOTAL_VERTICES, 'GEOMETRY_COMPLEXITY_UNSUPPORTED', vertices=total_vertices)
        report['boundary_claims'] = [
            {'nation_id': slot['nation_id'], 'claims': deepcopy(slot['boundary_claims'])}
            for slot in map_record['nation_slots'] if slot['boundary_claims']]
        report['declared_uncertainties'] = (
            [{'scope': 'world', 'items': deepcopy(map_record['unresolved'])}]
            + [{'scope': region['region_id'], 'items': deepcopy(region['uncertainties'])} for region in map_record['regions']]
            + [{'scope': slot['nation_id'], 'items': deepcopy(slot['uncertainties'])} for slot in map_record['nation_slots']])
        polygons, areas, owners = {}, {}, {}
        for region in map_record['regions']:
            rid = region['region_id']
            _require(bool(region['polygons']), 'REGION_WITHOUT_GEOMETRY', region_id=rid)
            polygons[rid] = [_polygon(polygon, f'{rid}.polygons[{i}]') for i, polygon in enumerate(region['polygons'])]
            for first, second in combinations(polygons[rid], 2):
                _require(not _relation(first, second)['overlap'], 'REGION_PARTS_INTERIOR_OVERLAP', region_id=rid)
            areas[rid] = sum((polygon['area'] for polygon in polygons[rid]), Fraction(0))
        for slot in map_record['nation_slots']:
            nid = slot['nation_id']
            if not slot['territory_region_ids']:
                report['stop_reasons'].append({'code': 'EMPTY_TERRITORY_REQUIRES_CONTENT_REVIEW',
                                               'layer': 'content_review', 'nation_id': nid})
            for rid in slot['territory_region_ids']:
                _require(rid not in owners, 'SHARED_TERRITORY_UNRESOLVED', region_id=rid,
                         nation_ids=[owners.get(rid), nid])
                owners[rid] = nid
        region_relations = {}
        for first_id, second_id in combinations(polygons, 2):
            relations = [_relation(first, second) for first in polygons[first_id] for second in polygons[second_id]]
            _require(not any(relation['overlap'] for relation in relations), 'REGIONS_INTERIOR_OVERLAP',
                     region_ids=[first_id, second_id])
            region_relations[frozenset((first_id, second_id))] = relations
            report['region_pairs'].append(_pair_metric(first_id, second_id, relations))
        for first, second in combinations(map_record['nation_slots'], 2):
            relations = [relation for rid in first['territory_region_ids'] for other in second['territory_region_ids']
                         for relation in region_relations[frozenset((rid, other))]]
            report['nation_pairs'].append(_pair_metric(first['nation_id'], second['nation_id'], relations))
        report['regions'] = [{'region_id': rid, 'area_km2': _ratio(area)} for rid, area in areas.items()]
        report['nation_territories'] = [
            {'nation_id': slot['nation_id'], 'region_ids': deepcopy(slot['territory_region_ids']),
             'area_km2': _ratio(sum((areas[rid] for rid in slot['territory_region_ids']), Fraction(0)))}
            for slot in map_record['nation_slots']]
        if report['stop_reasons']:
            report['status'] = 'needs_content_review'
        else:
            report.update(status='accepted', accepted_for_nation_context=True)
    except NationContractError as exc:
        report['stop_reasons'].append({'code': str(exc), 'layer': 'map_contract'})
    except _Stop as exc:
        report['stop_reasons'].append({'code': exc.code, 'layer': 'geometry', **exc.details})
    except (ArithmeticError, ValueError, OverflowError) as exc:
        report['stop_reasons'].append({'code': 'GEOMETRY_NUMERIC_REPRESENTATION_UNSUPPORTED', 'layer': 'geometry',
                                       'exception_type': type(exc).__name__})
    return report
