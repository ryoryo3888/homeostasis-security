import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from homeostasis_core.api_budget import BoundedClient
from homeostasis_core.observability import (inspect_run,validate_bundle,prepare,validate_publication,secret_scan,source_digest)
from homeostasis_core.transport_safety import (validate_credential,client_settings,request_fingerprint,exception_evidence,LocalTransportConfigurationError)
import research_workflow as workflow

FIXTURE=Path(__file__).parents[1]/'fixtures/transport_failure.json'

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

class TransportSafetyTests(unittest.TestCase):
    def test_credential_preflight_rejects_bad_values_without_echo(self):
        for value in ('', 'fake-日本語', 'fake\r\nheader', 'fake token', 'fake\x00', 'fake\x7f', ' fake'):
            with self.assertRaises(LocalTransportConfigurationError) as cm:validate_credential(value)
            if value:self.assertNotIn(value,str(cm.exception))
        validate_credential('synthetic-ASCII_123')

    def test_client_policy_pins_backend_and_disables_environment_transport(self):
        options=client_settings('synthetic')
        self.assertIs(options['vertexai'],False)
        self.assertEqual(options['http_options']['retry_options']['attempts'],1)
        self.assertFalse(options['http_options']['client_args']['trust_env'])
        self.assertFalse(options['http_options']['async_client_args']['trust_env'])
        self.assertEqual(options['http_options']['base_url'],'https://generativelanguage.googleapis.com')

    def test_invalid_credential_stops_cli_before_client_and_budget(self):
        with tempfile.TemporaryDirectory() as d, patch.object(workflow,'ROOT',Path(d)), patch.object(workflow.os,'chdir'), \
             patch.dict(os.environ,{'HOMEOSTASIS_OFFLINE':'0','GEMINI_API_KEY':'synthetic-日本語'}), \
             patch.object(workflow.subprocess,'run'), patch('homeostasis_core.gemini_agents.create_gemini_client') as factory:
            with self.assertRaises(LocalTransportConfigurationError):workflow.main(['experiment','--execute','--confirm','YES'])
            factory.assert_not_called();self.assertFalse((Path(d)/'results').exists())

    def test_request_encoding_preserves_japanese_rejects_surrogates_and_nan(self):
        self.assertEqual(request_fingerprint({'x':'日本語'}),request_fingerprint({'x':'日本語'}))
        for value in ('\ud800',float('nan')):
            with self.assertRaises(LocalTransportConfigurationError):request_fingerprint({'x':value})

    def test_exception_evidence_never_contains_text_objects_or_key_fragments(self):
        exc=UnicodeEncodeError('ascii','synthetic-秘密-token',0,4,'sensitive reason')
        evidence=exception_evidence(exc,'sdk_entered');raw=json.dumps(evidence)
        self.assertEqual(evidence['encoding'],'ascii')
        for x in ('synthetic','秘密','sensitive','reason','object'):self.assertNotIn(x,raw)
        secret_scan(evidence)

    def test_failed_transport_counts_attempt_not_provider_receipt_and_never_retries(self):
        calls=[]
        def fail(**kwargs):
            calls.append(kwargs);raise UnicodeEncodeError('ascii','秘密',0,1,'synthetic')
        with tempfile.TemporaryDirectory() as d:
            bounded=BoundedClient(SimpleNamespace(models=SimpleNamespace(generate_content=fail)),1,Path(d)/'audit.json')
            with self.assertRaises(UnicodeEncodeError):bounded.generate_content(contents='日本語')
            with self.assertRaisesRegex(RuntimeError,'limit'):bounded.generate_content(contents='日本語')
            self.assertEqual(len(calls),1);r=bounded.attempts[0]
            self.assertEqual(r['dispatch_stage'],'sdk_entered');self.assertEqual(r['provider_acceptance'],'unknown')
            self.assertEqual(r['failure_evidence']['encoding'],'ascii');self.assertEqual(len(r['request_sha256']),64)
            self.assertNotIn('秘密',(Path(d)/'audit.json').read_text())

    def test_local_request_failure_has_no_sdk_entry(self):
        invoked=[]
        with tempfile.TemporaryDirectory() as d:
            bounded=BoundedClient(SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw:invoked.append(kw))),1,Path(d)/'audit.json')
            with self.assertRaises(LocalTransportConfigurationError):bounded.generate_content(contents='\ud800')
            self.assertEqual(invoked,[]);self.assertEqual(bounded.attempts[0]['dispatch_stage'],'local_request_validation')

    def test_saved_null_response_failure_roundtrips_and_publishes_without_changes(self):
        f=json.loads(FIXTURE.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'results/rejected'/f['failed_run']
            save(p/'failure.json',f['failure']);save(p/'transport.audit.json',f['transport'])
            save(p/'result.json.checkpoint',{'active_run':{'completed_turn':0,'turns':[],'call_audit':[f['failed_decision']]}})
            before={x:x.read_bytes() for x in p.iterdir()}
            b=inspect_run(p);self.assertTrue(validate_bundle(b));self.assertIsNone(b['decisions'][0]['model_response'])
            self.assertEqual(b['failure']['error_type'],'UnicodeEncodeError');self.assertFalse(b['validation']['research_eligible'])
            save(root/'results/debug/check.json',{'status':'PASS','source_digest':source_digest(root)})
            with patch('homeostasis_core.observability.subprocess.check_output',return_value='test\n'):
                s=prepare(root);self.assertEqual(s['latest_run']['status'],'failed')
                self.assertEqual(validate_publication(root),s)
            self.assertEqual(before,{x:x.read_bytes() for x in p.iterdir()})

    def test_client_initialization_failure_has_zero_attempt_publication(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(workflow,'ROOT',root),patch.object(workflow.os,'chdir'), \
                 patch.dict(os.environ,{'HOMEOSTASIS_OFFLINE':'0','GEMINI_API_KEY':'synthetic'}), \
                 patch.object(workflow.subprocess,'run'),patch('homeostasis_core.transport_safety.runtime_manifest',return_value={'runtime_version':1}), \
                 patch('homeostasis_core.gemini_agents.create_gemini_client',side_effect=ValueError('synthetic')), \
                 patch('homeostasis_core.observability.subprocess.check_output',return_value='test\n'):
                with self.assertRaisesRegex(RuntimeError,'sanitized failure'):workflow.main(['experiment','--execute','--confirm','YES'])
            state=validate_publication(root)
            self.assertEqual(state['latest_run']['api_calls'],0)
            self.assertEqual(state['latest_run']['status'],'failed')
            b=json.loads((root/state['latest']['experiment']).read_text())
            self.assertTrue(validate_bundle(b));self.assertEqual(b['failure']['validation'],'NOT_STARTED')
            self.assertFalse(b['validation']['research_eligible'])

    def test_development_state_update_can_be_republished_without_manual_pointer_patch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save(root/'results/status/development.json',{'next_step':'first'})
            with patch('homeostasis_core.observability.subprocess.check_output',return_value='test\n'):
                prepare(root)
                save(root/'results/status/development.json',{'next_step':'second'})
                s=prepare(root)
            self.assertEqual(s['development_status']['next_step'],'second')
            self.assertEqual(validate_publication(root),s)
