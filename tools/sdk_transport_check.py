"""Actual pinned SDK through a mock HTTP boundary. Never contacts Gemini."""
import copy
import json
import os
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

class SDKTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('HOMEOSTASIS_OFFLINE')!='1':
            raise RuntimeError('Offline guard required')
        # Verify the process-level guard, independent of MockTransport.
        with socket.socket() as sock:
            try:sock.connect(('127.0.0.1',9))
            except RuntimeError:pass
            else:raise AssertionError('Network guard missing')
        cls.fixture=json.loads((ROOT/'tests/fixtures/transport_failure.json').read_text(encoding='utf-8'))

    def sdk_call(self, *, bad_header=False, status=200, hostile_environment=False):
        import httpx
        from google import genai
        from homeostasis_core.transport_safety import client_settings
        seen=[]
        request=copy.deepcopy(self.fixture['request'])
        request['config']['automatic_function_calling']={'disable':True}
        def handle(request):
            seen.append(request)
            if status!=200:return httpx.Response(status,json={'error':{'code':status,'message':'synthetic'}})
            return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[{
                'text':json.dumps(self.fixture['successful_response'],ensure_ascii=False)}]},'finishReason':'STOP'}]})
        from homeostasis_core.gemini_agents import coordinator_response_schema
        self.assertEqual(request['config']['response_json_schema'],coordinator_response_schema())
        options=client_settings('offline-synthetic-not-a-real-key')
        if bad_header:options['api_key']='offline-合成-not-a-real-key'
        options['http_options']['httpx_client']=httpx.Client(transport=httpx.MockTransport(handle),trust_env=False)
        env={'HOMEOSTASIS_OFFLINE':'1'}
        if hostile_environment:env.update(GOOGLE_GENAI_USE_VERTEXAI='true',GOOGLE_GENAI_USE_ENTERPRISE='true',GOOGLE_GEMINI_BASE_URL='https://invalid.example',HTTPS_PROXY='http://invalid.example:9',SSL_CERT_FILE='/nonexistent/synthetic.pem',SSL_CERT_DIR='/nonexistent/synthetic-certs')
        with patch.dict(os.environ,env,clear=True):
            client=genai.Client(**options)
            try:
                if bad_header:
                    with self.assertRaises(UnicodeEncodeError):client.models.generate_content(**request)
                    self.assertEqual(seen,[])
                elif status!=200:
                    with self.assertRaises(Exception):client.models.generate_content(**request)
                    self.assertEqual(len(seen),1)
                else:
                    response=client.models.generate_content(**request)
                    self.assertEqual(json.loads(response.text),self.fixture['successful_response'])
                    self.assertEqual(len(seen),1)
                    self.assertEqual(seen[0].url.host,'generativelanguage.googleapis.com')
                    body=json.loads(seen[0].content)
                    self.assertEqual(body['contents'][0]['parts'][0]['text'],self.fixture['request']['contents'])
                    self.assertIn('A国ミサイル',body['contents'][0]['parts'][0]['text'])
            finally:client.close();options['http_options']['httpx_client'].close()

    def test_japanese_coordinator_round_trip(self):self.sdk_call()
    def test_legacy_non_ascii_header_fails_before_mock_dispatch(self):self.sdk_call(bad_header=True)
    def test_http_503_has_no_retry(self):self.sdk_call(status=503)
    def test_environment_does_not_redirect_backend(self):self.sdk_call(hostile_environment=True)

if __name__=='__main__':
    unittest.main()
