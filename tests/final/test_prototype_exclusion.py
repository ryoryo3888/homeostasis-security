"""Offline classification checks; never reclassify or rewrite historical files."""
import json
from pathlib import Path
import tempfile
import unittest

from homeostasis_core.gemini_agents import eligible_result_paths, pilot_is_eligible
from simulation_final import run_final_simulation

ROOT=Path(__file__).resolve().parents[2]


class PrototypeExclusionTests(unittest.TestCase):
    def eligible(self, value):
        with tempfile.TemporaryDirectory() as directory:
            result=Path(directory)/'gemini-run-fixture.json'
            result.write_text(json.dumps(value),encoding='utf-8')
            manifest=result.with_suffix('.audit.json')
            manifest.write_text(json.dumps({'result_file':result.name,'status':'accepted',
                                            'include_in_research_aggregation':True}))
            return pilot_is_eligible(result,manifest),eligible_result_paths(result.parent)

    def test_saved_prototypes_cannot_be_promoted_by_acceptance_label(self):
        for name in ('deterministic_prototype.json','deterministic_prototype_8turn.json'):
            with self.subTest(name=name):
                path=ROOT/'results/final'/name; before=path.read_bytes()
                self.assertEqual(self.eligible(json.loads(before)),(False,()))
                self.assertEqual(path.read_bytes(),before)

    def test_new_prototype_is_explicitly_not_agent_research(self):
        result=run_final_simulation()
        self.assertEqual(result['decision_origin'],'deterministic_policy')
        self.assertEqual(result['artifact_class'],'deterministic_prototype')
        self.assertEqual(result['api_calls'],0)
        self.assertFalse(result['research_eligible'])
        self.assertEqual(result['publication_status'],'withheld')
        self.assertEqual(self.eligible(result),(False,()))

    def test_negative_classification_in_result_or_metadata_is_binding(self):
        markers=({'research_eligible':False},{'gemini_executed':False},
                 {'mode':'deterministic_prototype'},{'mode':'development'},
                 {'artifact_class':'validation_run'},{'artifact_class':'synthetic_validation'},
                 {'decision_origin':'synthetic_fixture'},{'decision_origin':'deterministic_policy'})
        for marker in markers:
            for value in (marker,{'metadata':marker}):
                with self.subTest(value=value):self.assertEqual(self.eligible(value),(False,()))

    def test_api_free_aggregation_does_not_reclassify_model_results(self):
        eligible,paths=self.eligible({'metadata':{'mode':'gemini'},'api_used':False,'api_calls':0})
        self.assertTrue(eligible)
        self.assertEqual(len(paths),1)

    def test_non_object_cannot_be_research_result(self):
        self.assertEqual(self.eligible([]),(False,()))
