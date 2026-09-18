"""Regression rejection tests for the user-approved visual frame."""
import json
from copy import deepcopy
from pathlib import Path
import unittest
from tools.v3_visual_contract import compare_layout,verify_sources
ROOT=Path(__file__).resolve().parents[2]
class ApprovedVisualTests(unittest.TestCase):
    def setUp(self):
        self.baseline=json.loads((ROOT/'tests/layout/v3-public-baseline.json').read_text())
        self.record=self.baseline['records'][0]
    def test_approved_source(self):
        self.assertEqual(self.baseline['status'],'approved')
        verify_sources(self.baseline['protected_sources'])
    def test_same_frame(self):compare_layout(self.record,deepcopy(self.record))
    def test_relocation_rejected(self):
        changed=deepcopy(self.record);changed['parents']['v3-earth']='body'
        with self.assertRaises(ValueError):compare_layout(self.record,changed)
    def test_position_and_size_rejected(self):
        for node in ('v3-earth','v3-control','v3-canvas'):
            for field in ('x','y','width','height'):
                changed=deepcopy(self.record);changed['bounds'][node][field]+=8
                with self.assertRaises(ValueError):compare_layout(self.record,changed)
    def test_state_movement_rejected(self):
        changed=deepcopy(self.record);changed['nodes'][0]['x']+=8
        with self.assertRaises(ValueError):compare_layout(self.record,changed)
    def test_detached_aurora_rejected(self):
        changed=deepcopy(self.record);changed['earthLayers'][1]['y']+=8
        with self.assertRaises(ValueError):compare_layout(self.record,changed)
    def test_source_drift_rejected(self):
        with self.assertRaises(ValueError):verify_sources({'ui/v3/observatory.css':'0'*64})
    def test_all_viewports_and_slots(self):
        c=json.loads((ROOT/'ui/v3/frame.json').read_text())
        self.assertEqual(c['viewports'],[r['viewport'] for r in self.baseline['records']])
        self.assertEqual(set(c['slots']),{'STATE_DETAIL','NETWORK_DETAIL','METRICS_EVIDENCE'})

    def test_mobile_relative_world_still_rejects_movement(self):
        r=self.baseline['records'][-1];changed=deepcopy(r);changed['nodes'][0]['y']+=8
        with self.assertRaises(ValueError):compare_layout(r,changed)
