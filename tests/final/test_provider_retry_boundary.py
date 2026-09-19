"""Provider exceptions are not proof that no Agent decision was generated."""
import json
from types import SimpleNamespace
import unittest
from test_simulation import sdk_reply

import httpx
from google import genai
from google.genai import types, errors

from homeostasis_core.gemini_agents import GeminiGateway


class ProviderRetryBoundaryTests(unittest.TestCase):
    def test_ambiguous_exceptions_stop_before_replacement_answer(self):
        for error in (TimeoutError('synthetic timeout'), ValueError('SDK response decode'),
                      json.JSONDecodeError('synthetic','',0), RuntimeError('503 UNAVAILABLE')):
            with self.subTest(error=type(error).__name__):
                requests=[]
                def generate(**kwargs):
                    requests.append(kwargs)
                    if len(requests)==1: raise error
                    return sdk_reply('{"replacement":true}')
                gateway=GeminiGateway(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                                      sleep_fn=lambda _:None)
                with self.assertRaises(RuntimeError): gateway.call('A',1,1,{},json.loads)
                self.assertEqual(len(requests),1)
                self.assertIsNone(gateway.calls[0]['structured_response'])
                self.assertEqual(gateway.calls[0]['response_status'],'provider_failure_no_retry')
                self.assertIs(gateway.calls[0]['automatic_regeneration'],False)

    def test_only_explicit_retryable_api_errors_keep_bounded_retry(self):
        for code,status in ((429,'RESOURCE_EXHAUSTED'),(503,'UNAVAILABLE')):
            requests=[]
            def generate(**kwargs):
                requests.append(kwargs)
                if len(requests)==1:
                    raise errors.APIError(code,{'error':{'code':code,'status':status,'message':'fixture'}})
                return sdk_reply('{"answer":"unchanged"}')
            gateway=GeminiGateway(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                                  sleep_fn=lambda _:None)
            self.assertEqual(gateway.call('A',1,1,{'fixed':'input'},json.loads),{'answer':'unchanged'})
            self.assertEqual(len(requests),2)
            self.assertEqual(requests[0],requests[1])
            self.assertEqual(gateway.calls[0]['provider_status_code'],code)

    def test_permanent_or_inconsistent_provider_errors_do_not_retry(self):
        for error in (
            errors.APIError(400,{'error':{'code':400,'status':'INVALID_ARGUMENT'}}),
            errors.APIError(503,{'error':{'code':400,'status':'UNAVAILABLE'}}),
            errors.APIError(503,{'error':{'code':503,'status':'UNKNOWN'}}),
        ):
            calls=[]
            def generate(**kwargs): calls.append(kwargs); raise error
            gateway=GeminiGateway(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                                  sleep_fn=lambda _:None)
            with self.assertRaises(RuntimeError): gateway.call('A',1,1,{},json.loads)
            self.assertEqual(len(calls),1)

    def test_real_sdk_parse_failures_are_not_new_model_calls(self):
        for payload in (b'not JSON', b'{"candidates":[{"index":"not-an-integer"}]}'):
            sent=[]
            def handler(request):
                sent.append(request)
                return httpx.Response(200,content=payload,headers={'Content-Type':'application/json'})
            with httpx.Client(transport=httpx.MockTransport(handler),trust_env=False) as http:
                with genai.Client(vertexai=False,api_key='offline-dummy',http_options=types.HttpOptions(
                    base_url='https://retry-fixture.invalid',httpx_client=http,
                    retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    gateway=GeminiGateway(client,model='offline-model',sleep_fn=lambda _:None)
                    with self.assertRaises(RuntimeError): gateway.call('A',1,1,{},json.loads)
                    self.assertEqual(len(sent),1)
                    self.assertIsNone(gateway.calls[0]['structured_response'])

    def test_real_sdk_explicit_rejection_retries_identical_request(self):
        for code,status in ((429,'RESOURCE_EXHAUSTED'),(503,'UNAVAILABLE')):
            sent=[]
            def handler(request):
                sent.append(request.content)
                if len(sent)==1:
                    return httpx.Response(code,json={'error':{'code':code,'status':status,'message':'fixture'}})
                return httpx.Response(200,json={'candidates':[{'finishReason':'STOP',
                    'content':{'parts':[{'text':'{"answer":"unchanged"}'}]}}]})
            with httpx.Client(transport=httpx.MockTransport(handler),trust_env=False) as http:
                with genai.Client(vertexai=False,api_key='offline-dummy',http_options=types.HttpOptions(
                    base_url='https://retry-fixture.invalid',httpx_client=http,
                    retry_options=types.HttpRetryOptions(attempts=1))) as client:
                    gateway=GeminiGateway(client,model='offline-model',sleep_fn=lambda _:None)
                    self.assertEqual(gateway.call('A',1,1,{'fixed':'input'},json.loads),{'answer':'unchanged'})
                    self.assertEqual(len(sent),2)
                    self.assertEqual(sent[0],sent[1])
                    self.assertEqual(gateway.calls[0]['provider_status_code'],code)

    def test_known_rejections_still_obey_attempt_and_call_limits(self):
        for max_calls,retry_limit,expected in ((10,3,3),(2,3,2)):
            sent=[]
            def generate(**kwargs):
                sent.append(kwargs)
                raise errors.APIError(503,{'error':{'code':503,'status':'UNAVAILABLE','message':'fixture'}})
            gateway=GeminiGateway(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                                  max_calls=max_calls,retry_limit=retry_limit,sleep_fn=lambda _:None)
            with self.assertRaises(RuntimeError): gateway.call('A',1,1,{},json.loads)
            self.assertEqual(len(sent),expected)
            self.assertTrue(all(request==sent[0] for request in sent))
            self.assertTrue(all(record['structured_response'] is None for record in gateway.calls))


if __name__ == '__main__': unittest.main()
