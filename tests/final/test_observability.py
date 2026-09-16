import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from final_experiment_runner import run_live, _checkpoint
from research_workflow import probe
from homeostasis_core.api_budget import BoundedClient
from homeostasis_core.research_validation import research_manifest
from homeostasis_core.observability import (prepare, validate_publication, validate_bundle, inspect_run,
    source_digest, secret_scan, public_decision, PublicationError, encoded)
from tests.final.test_decision_audit import SelectionModels
from tests.final.test_workflow_safety import VariedModels
from tests.final.test_phase9_gemini_final import Response

PROBE='20260916T210000Z-aaaaaaaa'
TURN='20260916T220000Z-bbbbbbbb'
FULL='20260916T230000Z-cccccccc'
FAILED='20260916T235000Z-dddddddd'


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encoded(value))


class ObservabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive=tempfile.TemporaryDirectory();root=Path(cls.archive.name)
        for mode,run_id,category in (('probe',PROBE,'probe'),('turn',TURN,'probe'),('experiment',FULL,'research')):
            path=root/'results'/category/run_id;path.mkdir(parents=True)
            fake=SimpleNamespace(models=SelectionModels() if mode=='probe' else VariedModels())
            maximum={'probe':1,'turn':10,'experiment':80}[mode]
            client=BoundedClient(fake,maximum,path/'transport.audit.json')
            if mode=='probe':
                result=probe(client,audit_hook=lambda calls:_checkpoint(path/'decision.audit.json',{'run_id':run_id,'calls':calls}))
                save(path/'result.json',result)
            else:
                run_live(client,path/'result.json',1,7,turns=1 if mode=='turn' else 8,max_calls=maximum,retry_limit=1)
            save(path/'result.audit.json',research_manifest(path/'result.json',[] if mode=='experiment' else ['not research']))
        class InvalidConditional(VariedModels):
            def generate_content(self,**kwargs):
                response=super().generate_content(**kwargs);payload=json.loads(kwargs['contents'])
                if 'turn_start_observation' in payload:
                    d=json.loads(response.text);d.update(response_id='CONDITIONAL',response_label='条件付きで応じる',conditions={})
                    return Response(json.dumps(d))
                return response
        path=root/'results/rejected'/FAILED;path.mkdir(parents=True)
        client=BoundedClient(SimpleNamespace(models=InvalidConditional()),10,path/'transport.audit.json')
        try:run_live(client,path/'result.json',1,7,turns=1,max_calls=10,retry_limit=1)
        except RuntimeError:pass
        save(path/'failure.json',{'mode':'turn','status':'rejected','error_type':'RuntimeError',
                                 'api_calls':len(client.attempts),'include_in_research_aggregation':False})

    @classmethod
    def tearDownClass(cls):cls.archive.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        shutil.copytree(Path(self.archive.name)/'results',self.root/'results')
        (self.root/'RESEARCH_STATE.md').write_text('Historical research notes; preserve me.\n')
        save(self.root/'results/debug/check.json',{'status':'PASS','api_calls':0,'source_digest':source_digest(self.root)})

    def publish(self):
        with patch('homeostasis_core.observability.subprocess.check_output',side_effect=lambda args,**_: 'test-branch\n' if 'branch' in args else 'a'*40+'\n'):
            return prepare(self.root)

    def test_status_latest_history_and_human_state(self):
        state=self.publish();self.assertEqual(validate_publication(self.root),state)
        self.assertEqual(state['latest_run']['run_id'],FAILED)
        self.assertEqual(state['latest_run']['api_calls'],2)
        self.assertEqual(state['validation']['preflight'],'PASS')
        self.assertIn(PROBE,state['latest']['probe']);self.assertIn(FULL,state['latest']['successful_research'])
        self.assertIn('Historical research notes; preserve me.',(self.root/'RESEARCH_STATE.md').read_text())

    def test_probe_original_choice_and_trace_export(self):
        b=inspect_run(self.root/'results/probe'/PROBE)
        self.assertTrue(validate_bundle(b));r=b['decisions'][0]
        self.assertEqual(r['choice_id'],r['choice_response']['choice_id'])
        self.assertEqual(r['reason'],r['materialized_action']['description'])
        self.assertEqual(b['worlds'],[])
        self.assertFalse(b['validation']['research_eligible'])

    def test_one_turn_exports_actual_world_values_and_all_agents(self):
        path=self.root/'results/probe'/TURN;b=inspect_run(path)
        original=json.loads((path/'result.json').read_text())['runs'][0]['details']['turns'][0]
        self.assertTrue(validate_bundle(b));self.assertEqual(len(b['decisions']),10)
        self.assertEqual(b['worlds'][0]['world'],original['executed_state']['true_world'])
        self.assertEqual(b['worlds'][0]['reconstruction'],original['executed_state']['reconstruction'])
        self.assertEqual(b['worlds'][0]['established_actions'],original['executed_state']['causal_record']['accepted_actions'])

    def test_eight_turn_research_requires_real_admission(self):
        b=inspect_run(self.root/'results/research'/FULL)
        self.assertTrue(validate_bundle(b));self.assertTrue(b['validation']['research_eligible'])
        self.assertEqual(len(b['worlds']),8)
        path=self.root/'results/research'/FULL
        manifest=json.loads((path/'result.audit.json').read_text());manifest['include_in_research_aggregation']=False
        save(path/'result.audit.json',manifest)
        with self.assertRaises(PublicationError):inspect_run(path)

    def test_failure_is_observable_but_not_research(self):
        b=inspect_run(self.root/'results/rejected'/FAILED)
        self.assertTrue(validate_bundle(b));self.assertEqual(b['run']['status'],'failed')
        self.assertEqual(b['failure']['agent_id'],'ECON');self.assertEqual(b['failure']['api_call_number'],2)
        self.assertEqual(b['failure']['derived_diagnosis'],'CONDITIONAL_REQUIRES_EXECUTABLE_CONDITIONS')
        self.assertEqual(b['validation']['decision_audit'],'PASS');self.assertEqual(b['validation']['contracts'],'FAIL')
        self.assertFalse(b['validation']['research_eligible'])

    def test_credentials_block_log_export_and_mark_newest_blocked(self):
        path=self.root/'results/rejected'/FAILED/'failure.json';d=json.loads(path.read_text())
        d['GEMINI_API_KEY']='AIza'+'A'*35;save(path,d)
        state=self.publish()
        self.assertEqual(state['latest_blocked_run']['code'],'SECRET_SCAN_FAILED')
        self.assertFalse((self.root/'results/status/runs'/FAILED).exists())
        for p in (self.root/'results/status').rglob('*.json'):self.assertNotIn('AIza'+'A'*35,p.read_text())

    def test_secret_scan_detects_embedded_keys_and_environment_secret(self):
        for item in ({'reason':'token '+'AIza'+'A'*35},{'authorization':'Bearer abc'}, {'password':'secret'}):
            with self.assertRaises(PublicationError):secret_scan(item)
        with patch.dict('os.environ',{'GEMINI_API_KEY':'synthetic-secret-credential'}):
            with self.assertRaises(PublicationError):secret_scan({'reason':'synthetic-secret-credential'})

    def test_projection_omits_private_payload_and_internal_reasoning(self):
        path=self.root/'results/probe'/PROBE
        row=json.loads((path/'result.json').read_text())['call_audit'][0]
        row['sdk_object']={'thoughts':'hidden-contents'}
        row['model_response']['thoughts']='hidden-contents'
        row['public_observation_payload']['private_observation']['password']='hidden-contents'
        out=public_decision(row)
        self.assertNotIn('hidden-contents',json.dumps(out));self.assertNotIn('private_observation',json.dumps(out))

    def test_missing_pointer_and_wrong_latest_rejected(self):
        state=self.publish();state['latest']['probe']='results/status/runs/missing.json';save(self.root/'results/status/latest.json',state)
        with self.assertRaises(PublicationError):validate_publication(self.root,check_human=False)

    def test_broken_transport_and_choice_audit_block_export(self):
        path=self.root/'results/probe'/PROBE
        audit=json.loads((path/'transport.audit.json').read_text());audit['attempts'][0]['agent_id']='WRONG'
        save(path/'transport.audit.json',audit)
        with self.assertRaises(PublicationError):inspect_run(path)
        b=inspect_run(self.root/'results/probe'/TURN);b['decisions'][1]['choice_response']['choice_id']='WRONG'
        with self.assertRaises(ValueError):validate_bundle(b)

    def test_raw_results_never_modified_and_clone_preserves_history(self):
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root/'results').rglob('*') if p.is_file()}
        first=self.publish()
        for filename,d in before.items():self.assertEqual(hashlib.sha256(Path(filename).read_bytes()).hexdigest(),d)
        # Fresh GitHub clones have public projections but no private source runs.
        for category in ('probe','research','rejected'):shutil.rmtree(self.root/'results'/category)
        second=self.publish();self.assertEqual(first['latest'],second['latest'])

    def test_stale_preflight_is_not_reported_as_pass(self):
        save(self.root/'results/debug/check.json',{'status':'PASS','source_digest':'old'})
        self.assertEqual(self.publish()['validation']['preflight'],'UNKNOWN')

    def test_public_hash_tamper_and_human_state_mismatch_rejected(self):
        state=self.publish();p=self.root/state['latest']['probe'];b=json.loads(p.read_text());b['decisions'][0]['amount']=999
        save(p,b)
        with self.assertRaises(PublicationError):validate_publication(self.root)

    def test_status_schema_and_human_sync_are_enforced(self):
        state=self.publish()
        (self.root/'RESEARCH_STATE.md').write_text('out of sync')
        with self.assertRaises(PublicationError):validate_publication(self.root)
        state['status_version']=True;save(self.root/'results/status/latest.json',state)
        with self.assertRaises(PublicationError):validate_publication(self.root,check_human=False)

    def test_world_metric_corruption_is_not_exported(self):
        path=self.root/'results/probe'/TURN
        r=json.loads((path/'result.json').read_text())
        r['runs'][0]['details']['turns'][0]['executed_state']['true_world']['food']=999
        save(path/'result.json',r)
        save(path/'result.audit.json',research_manifest(path/'result.json',['not research']))
        with self.assertRaises(PublicationError):inspect_run(path)

    def test_transport_count_boolean_is_not_a_valid_call_count(self):
        path=self.root/'results/probe'/PROBE
        audit=json.loads((path/'transport.audit.json').read_text());audit['api_calls']=True
        save(path/'transport.audit.json',audit)
        with self.assertRaises(PublicationError):inspect_run(path)

    def test_push_guard_refuses_main_before_any_git_operation(self):
        from tools.publication_gate import verify_commit
        with patch('tools.publication_gate.subprocess.check_output',side_effect=AssertionError('git invoked')):
            with self.assertRaisesRegex(PublicationError,'MAIN_PUSH'):
                verify_commit('a'*40,'refs/heads/main')

    def test_legacy_missing_trace_is_blocked_not_reverse_inferred(self):
        path=self.root/'results/probe'/PROBE;r=json.loads((path/'result.json').read_text());r.pop('run_id');save(path/'result.json',r)
        save(path/'result.audit.json',research_manifest(path/'result.json',['legacy']))
        with self.assertRaisesRegex(PublicationError,'MISSING_ORIGINAL'):inspect_run(path)
