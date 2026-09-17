"""Published analysis is independently replayable without original private runs."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
from tools.analyze_worldline import validate_timeline, ROOT

class WorldlineAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT/'results/status/analyses/20260917T075421Z-11147417/timeline.json').read_text())

    def test_all_eight_turns_choice_settlement_evaluator_and_reconstruction(self):
        self.assertTrue(validate_timeline(self.data))
        self.assertEqual(self.data['run']['api_calls'],80)
        self.assertEqual(self.data['run']['retry_count'],0)
        self.assertTrue(self.data['validation']['research_eligible'])

    def test_tampered_choice_is_rejected(self):
        d=copy.deepcopy(self.data);d['turns'][0]['decisions'][0]['model_response']['choice_id']='NOT_IN_CATALOG'
        with self.assertRaises(ValueError):validate_timeline(d)

    def test_tampered_world_or_derived_resource_delta_rejected(self):
        for field in ('world','delta'):
            d=copy.deepcopy(self.data)
            if field=='world':d['turns'][3]['executed_state']['true_world']['food']+=1
            else:d['turns'][3]['derived']['resource_delta']['ECON']['food']+=1
            with self.assertRaises(ValueError):validate_timeline(d)

    def test_tampered_event_priority_or_evaluator_input_rejected(self):
        for field in ('event','evaluator'):
            d=copy.deepcopy(self.data)
            if field=='event':d['turns'][5]['event_derivation']['candidates'][0]['priority']+=1
            else:d['turns'][5]['evaluator_input_sha256']='0'*64
            with self.assertRaises(ValueError):validate_timeline(d)

    def test_check_fingerprint_covers_protected_readme(self):
        from homeostasis_core.observability import source_digest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'README.md').write_text('protected historical prefix')
            before=source_digest(root)
            (root/'README.md').write_text('changed prefix')
            self.assertNotEqual(source_digest(root),before)

    def test_original_run_unchanged_when_available(self):
        path=ROOT/'results/research'/self.data['run_id']
        for filename,expected in self.data['source_hashes'].items():
            if (path/filename).exists():self.assertEqual(hashlib.sha256((path/filename).read_bytes()).hexdigest(),expected)
