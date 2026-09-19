"""No remote calls: exercise both retry helpers with explicit SDK fixtures."""
from contextlib import redirect_stdout
import io
import json
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from google import genai
from google.genai import errors, types
import simulation
import simulation_v2


class V1V2RetryBoundaryTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_NETWORK'))
        network.start(); self.addCleanup(network.stop)

    def call(self, module, client):
        with redirect_stdout(io.StringIO()), patch.object(simulation.time, 'sleep'):
            options = {} if module is simulation else {'sleep_fn': lambda _: None, 'jitter_fn': lambda *_: 0}
            return module.generate_content_with_retry(client, model='offline-model', contents='fixed input',
                                                      config={'seed': 17}, **options)

    def test_error_text_and_attributes_cannot_authorize_regeneration(self):
        class PretendRejection(Exception):
            code = 503
            status = 'UNAVAILABLE'
        for module in (simulation, simulation_v2):
            for failure in (RuntimeError('429 RESOURCE_EXHAUSTED'),
                            ValueError('503 UNAVAILABLE while decoding response'),
                            TimeoutError('429 request state unknown'),
                            PretendRejection('synthetic'),
                            errors.APIError(400, {'error': {'code': 400, 'status': 'INVALID_ARGUMENT',
                                                          'message': 'contains 429 503 UNAVAILABLE'}}),
                            errors.APIError(503, {'error': {'code': 400, 'status': 'UNAVAILABLE'}})):
                with self.subTest(module=module.__name__, failure=type(failure).__name__):
                    generate = Mock(side_effect=[failure, SimpleNamespace(text='replacement')])
                    with self.assertRaises(type(failure)):
                        self.call(module, SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
                    self.assertEqual(generate.call_count, 1)

    def test_explicit_rejections_preserve_request_and_existing_attempt_limits(self):
        for module in (simulation, simulation_v2):
            for code, status, limit in ((429, 'RESOURCE_EXHAUSTED', 2), (503, 'UNAVAILABLE', 3)):
                for succeeds in (True, False):
                    with self.subTest(module=module.__name__, code=code, succeeds=succeeds):
                        failure = errors.APIError(code, {'error': {'code': code, 'status': status}})
                        answer = SimpleNamespace(text='original')
                        outcomes = [failure] * (limit - 1) + [answer if succeeds else failure]
                        generate = Mock(side_effect=outcomes)
                        client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
                        if succeeds: self.assertIs(self.call(module, client), answer)
                        else:
                            with self.assertRaises(errors.APIError): self.call(module, client)
                        self.assertEqual(generate.call_count, limit)
                        self.assertTrue(all(c == generate.call_args_list[0] for c in generate.call_args_list))

    def test_sdk_parsing_failures_do_not_retry_and_explicit_http_rejections_do(self):
        for module in (simulation, simulation_v2):
            for scenario in ('malformed', 'invalid_field', '429', '503'):
                with self.subTest(module=module.__name__, scenario=scenario):
                    sent = []
                    def handler(request):
                        sent.append(request.content)
                        if scenario == 'malformed':
                            return httpx.Response(200, content=b'not json')
                        if scenario == 'invalid_field':
                            return httpx.Response(200, json={'candidates': [{'index': '429 RESOURCE_EXHAUSTED'}]})
                        if len(sent) == 1:
                            code = int(scenario)
                            return httpx.Response(code, json={'error': {'code': code,
                                'status': {429: 'RESOURCE_EXHAUSTED', 503: 'UNAVAILABLE'}[code]}})
                        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': 'original'}]}}]})
                    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http:
                        with genai.Client(vertexai=False, api_key='offline-dummy', http_options=types.HttpOptions(
                            base_url='https://retry-fixture.invalid', httpx_client=http,
                            retry_options=types.HttpRetryOptions(attempts=1))) as client:
                            if scenario in ('malformed', 'invalid_field'):
                                with self.assertRaises((ValueError, json.JSONDecodeError)):
                                    self.call(module, client)
                                self.assertEqual(len(sent), 1)
                            else:
                                self.assertEqual(self.call(module, client).text, 'original')
                                self.assertEqual(len(sent), 2)
                                self.assertEqual(sent[0], sent[1])

    def test_daily_limit_still_stops_without_retry(self):
        for module in (simulation, simulation_v2):
            failure = errors.APIError(429, {'error': {'code': 429, 'status': 'RESOURCE_EXHAUSTED',
                                                    'message': 'GenerateRequestsPerDayPerProjectPerModel'}})
            generate = Mock(side_effect=failure)
            with self.assertRaises(errors.APIError):
                self.call(module, SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
            self.assertEqual(generate.call_count, 1)


if __name__ == '__main__': unittest.main()
