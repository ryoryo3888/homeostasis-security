"""File integrity is necessary, but does not independently prove a model run."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from homeostasis_core.gemini_agents import eligible_result_paths,pilot_is_eligible


class ResultEvidenceBindingTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.result=Path(self.directory.name)/'gemini-run-fixture.json'
        self.result.write_text('{"metadata":{"mode":"gemini"},"value":1}\n')
        self.manifest=self.result.with_suffix('.audit.json')
        self.audit={'result_file':self.result.name,'status':'accepted',
                    'include_in_research_aggregation':True,
                    'result_sha256':hashlib.sha256(self.result.read_bytes()).hexdigest()}
        self.save_audit()

    def save_audit(self):self.manifest.write_text(json.dumps(self.audit))

    def test_matching_bytes_retain_existing_eligibility(self):
        self.assertTrue(pilot_is_eligible(self.result,self.manifest))
        self.assertEqual(eligible_result_paths(self.result.parent),(self.result,))

    def test_changed_result_is_rejected_without_repairing_evidence(self):
        self.result.write_text('{"metadata":{"mode":"gemini"},"value":2}\n')
        before=(self.result.read_bytes(),self.manifest.read_bytes())
        self.assertFalse(pilot_is_eligible(self.result,self.manifest))
        self.assertEqual(eligible_result_paths(self.result.parent),())
        self.assertEqual((self.result.read_bytes(),self.manifest.read_bytes()),before)

    def test_byte_change_is_not_hidden_by_json_normalization(self):
        data=json.loads(self.result.read_bytes())
        self.result.write_text(json.dumps(data,indent=2))
        self.assertFalse(pilot_is_eligible(self.result,self.manifest))

    def test_missing_or_invalid_hash_is_not_inferred(self):
        for value in (None,'','0'*64,0,True,[],{}):
            with self.subTest(value=value):
                self.audit['result_sha256']=value;self.save_audit()
                self.assertFalse(pilot_is_eligible(self.result,self.manifest))
        del self.audit['result_sha256'];self.save_audit()
        self.assertFalse(pilot_is_eligible(self.result,self.manifest))

    def test_correct_hash_does_not_override_rejection(self):
        self.audit['status']='rejected';self.save_audit()
        self.assertFalse(pilot_is_eligible(self.result,self.manifest))
