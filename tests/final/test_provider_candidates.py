"""Do not pick an SDK candidate or accept a stopped/incomplete generation."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from google.genai import types
import simulation
import simulation_v2
from homeostasis_core.gemini_agents import GeminiGateway
from provider_response import complete_response_text
from response_receipts import ResponseReceipts

AGENT_TEXT = '現在認識: 観測。\n懸念: なし。\n行動: 何もしない。\n理由: 自分の判断。'


def reply(text, *, count=1, finish='STOP'):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(parts=[types.Part(text=text)]), finish_reason=finish)
        for _ in range(count)])


class ProviderCandidateTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_NETWORK'))
        network.start(); self.addCleanup(network.stop)

    def call(self, route, client):
        if route == 'v1_agent':
            return simulation.call_agent(client, SimpleNamespace(name='fixture', context=lambda:'synthetic'),
                'synthetic', 'synthetic', SimpleNamespace(context=lambda:'synthetic'))
        if route == 'v1_evaluator':
            return simulation.call_evaluator(client, simulation.EXTERNAL_EVENTS[0], 'synthetic',
                'a', 'r', 'b', 'a', 'r', 'b', simulation.INTERNATIONAL_LAW)
        if route == 'v2_json': return simulation_v2.call_json(client, 'synthetic')
        return GeminiGateway(client).call('A', 1, 1, {}, json.loads)

    def test_missing_multiple_incomplete_or_blocked_candidates_stop_every_parser(self):
        evaluation = json.dumps({field:50 for field in simulation.EVALUATION_FIELDS})
        for route in ('v1_agent', 'v1_evaluator', 'v2_json', 'gateway'):
            raw = AGENT_TEXT if route == 'v1_agent' else evaluation
            for count, finish in ((0,'STOP'), (2,'STOP'), (1,None), (1,'MAX_TOKENS'), (1,'SAFETY')):
                with self.subTest(route=route, count=count, finish=finish):
                    generate = Mock(return_value=reply(raw, count=count, finish=finish))
                    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
                    with self.assertRaises((ValueError, RuntimeError)): self.call(route, client)
                    self.assertEqual(generate.call_count, 1)

    def test_single_complete_response_is_not_rewritten(self):
        raw = ' \n'+AGENT_TEXT+'\t'
        self.assertEqual(complete_response_text(reply(raw)), raw)
        for route in ('v1_agent','v1_evaluator','v2_json','gateway'):
            evaluation = {field:50 for field in simulation.EVALUATION_FIELDS}
            raw = AGENT_TEXT if route == 'v1_agent' else json.dumps(evaluation)
            client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock(return_value=reply(raw))))
            result = self.call(route, client)
            expected = raw if route in ('v1_agent','v2_json') else evaluation
            self.assertEqual(result, expected)

    def test_text_property_is_never_read_to_select_an_ambiguous_candidate(self):
        class Ambiguous:
            candidates = [SimpleNamespace(finish_reason='STOP')] * 2
            @property
            def text(self): raise AssertionError('candidate selection must not happen')
        with self.assertRaisesRegex(ValueError, 'AMBIGUOUS'):
            complete_response_text(Ambiguous())

    def test_gateway_keeps_all_candidates_before_rejecting(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResponseReceipts.for_output(Path(directory)/'synthetic.json'); store.prepare()
            response = reply('{"first":true}',count=2)
            response.candidates[1].content.parts[0].text = '{"second":true}'
            generate = Mock(return_value=response); parser = Mock()
            gateway = GeminiGateway(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                                    response_hook=store.record)
            with self.assertRaises(RuntimeError): gateway.call('A', 1, 1, {}, parser)
            saved = json.loads(next(store.directory.glob('*.json')).read_text())
            self.assertEqual([c['content']['parts'][0]['text'] for c in saved['sdk_response']['candidates']],
                             ['{"first":true}','{"second":true}'])
            parser.assert_not_called()
            self.assertEqual(generate.call_count, 1)
            self.assertIsNone(gateway.calls[0]['structured_response'])

    def test_v1_keeps_all_candidates_and_does_not_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd(); os.chdir(directory)
            try:
                generate = Mock(return_value=reply(AGENT_TEXT,count=2))
                client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
                with patch.object(simulation, 'USE_GEMINI', True), \
                        patch.object(simulation, 'getpass', return_value='offline-dummy'), \
                        patch.object(simulation.genai, 'Client', return_value=client), redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(ValueError,'AMBIGUOUS'): simulation.main()
                output = Path(f'simulation_result_independent_agents_{simulation.EXPERIMENT_CONDITION}.json')
                self.assertFalse(output.exists())
                store = ResponseReceipts.for_output(output)
                saved = json.loads(next(store.directory.glob('*.json')).read_text())
                self.assertEqual(len(saved['sdk_response']['candidates']),2)
                self.assertEqual(generate.call_count,1)
            finally:
                os.chdir(previous)


if __name__ == '__main__': unittest.main()
