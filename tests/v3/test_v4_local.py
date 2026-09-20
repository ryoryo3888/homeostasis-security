import base64
from copy import deepcopy
import contextlib
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from homeostasis_v3.contracts import canonical, digest
from homeostasis_v4.dialogue import SYSTEM_INSTRUCTION, REPLY, parse_reply
from homeostasis_v4.evidence import EvidenceRun, read_record, verify
from homeostasis_v4.local_observation import execute, prepare, replay, same_identity, LocalExchange, local_reply_format
from tests.v3.test_v4_dialogue import empty, offer, respond


class LocalPilotTests(unittest.TestCase):
    def test_thinking_uses_chat_and_only_final_answer_drives_world(self):
        with tempfile.TemporaryDirectory() as tmp, self.provider() as client:
            settings = prepare(client, model='qwen3:1.7b', seed=73, turns=2,
                               synthetic=True, structured_output=True, thinking=True)
            path = Path(tmp) / 'run'
            result = execute(path, settings, protocol_digest=digest(settings), client=client,
                             telemetry=lambda c, m: {})
            self.assertEqual(result['status'], 'success')
            self.assertEqual(replay(path)['replayed_turns'], 2)
            self.assertEqual(settings['api_endpoint'], '/api/chat')
            self.assertTrue(all(c['think'] for c in self.calls))
            self.assertTrue(all('prompt' not in c and 'system' not in c for c in self.calls))
            for call in self.calls[8:]:
                text = call['messages'][1]['content']; view = json.loads(text)['view']
                self.assertEqual(call['messages'][0], {'role': 'system', 'content': SYSTEM_INSTRUCTION})
                self.assertNotIn('THINKING_MUST_NOT_BE_AN_AGENT_ANSWER', text)
                if view['actor'] not in ('MIL', 'RES'):
                    self.assertNotIn('private offer', text)
                if view['actor'] != 'MIL':
                    self.assertNotIn('private memory', text)
            wire = read_record(path / 'RAW/call-000.wire.json')
            data = json.loads(base64.b64decode(wire['body_base64']))
            self.assertEqual(data['message']['thinking'], 'THINKING_MUST_NOT_BE_AN_AGENT_ANSWER')
            self.assertIn('think=true', read_record(path / 'DERIVED/execution-summary.json')['report']['model_mode'])
            # Even a valid final-answer-shaped thinking field cannot replace empty content.
            with self.provider('thinking_only') as empty_client:
                failed = Path(tmp) / 'thinking-only'
                result = execute(failed, settings, protocol_digest=digest(settings), client=empty_client,
                                 telemetry=lambda c, m: {})
                self.assertEqual(result['status'], 'failure')
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(replay(failed)['replayed_turns'], 0)
                self.assertEqual(read_record(failed / 'terminal.json')['error']['code'], 'LOCAL_RESPONSE_TEXT_REQUIRED')

    def test_legacy_generate_protocol_and_records_still_replay(self):
        with tempfile.TemporaryDirectory() as tmp, self.provider() as client:
            settings = prepare(client, model='qwen3:1.7b', seed=73, turns=2, synthetic=True)
            settings.pop('api_endpoint')
            original = Path(tmp) / 'original'
            execute(original, settings, protocol_digest=digest(settings), client=client, telemetry=lambda c,m: {})
            legacy = Path(tmp) / 'legacy'
            evidence = EvidenceRun(legacy, read_record(original / 'manifest.json'))
            for raw in sorted((original / 'RAW').iterdir()):
                value = read_record(raw)
                if raw.name.endswith('.request.json'):
                    value.pop('endpoint')
                evidence.write(raw.name, value)
            evidence.finish('success', completed_turns=2)
            self.assertEqual(replay(legacy)['replayed_turns'], 2)

    def test_local_grammar_preserves_activity_alternatives_and_arbitrary_arguments(self):
        from jsonschema import Draft202012Validator
        original = deepcopy(REPLY)
        converted = local_reply_format()
        old = Draft202012Validator(REPLY['properties']['activities']['items'])
        item = converted['properties']['activities']['items']
        new = Draft202012Validator(item)
        self.assertEqual(set(item), {'anyOf'})
        for branch in item['anyOf']:
            self.assertTrue(branch['properties']['arguments']['additionalProperties'])
            self.assertFalse(branch['additionalProperties'])
        absent = object()
        for body, operation, arguments, extra in itertools.product(
                (absent, '', 'Unlisted idea', 7), (absent, 'novel_operation', None),
                (absent, {}, {'arbitrary': [1, 'x', {'new': True}]}, 'invalid'), (False, True)):
            value = {k: v for k, v in [('body', body), ('operation', operation), ('arguments', arguments)]
                     if v is not absent}
            if extra:value['unexpected'] = 'invalid protocol field'
            self.assertEqual(old.is_valid(value), new.is_valid(value), value)
        for value in (None, [], 'not an object'):
            self.assertEqual(old.is_valid(value), new.is_valid(value))
        self.assertEqual(REPLY, original)

    def test_prepared_runtime_limits_drive_cli_and_stop_new_calls(self):
        from tools import run_v4_local as cli
        with tempfile.TemporaryDirectory() as tmp, self.provider() as client:
            settings = prepare(client, model='qwen3:1.7b', seed=73, turns=2, synthetic=True,
                               request_timeout_seconds=300, run_deadline_seconds=3600)
            prepared = Path(tmp) / 'prepared.json'
            prepared.write_text(json.dumps({'protocol': settings, 'protocol_digest': digest(settings)}))
            with patch.object(cli.httpx, 'Client') as factory, patch.object(cli, 'execute', return_value={
                    'status': 'success'}) as run, patch('sys.argv', ['run_v4_local', '--execute',
                    '--prepared', str(prepared), '--output', str(Path(tmp)/'run'),
                    '--request-timeout', '1', '--run-deadline', '1']), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 0)
                self.assertEqual(factory.call_args.kwargs['timeout'], 300)
                self.assertEqual(run.call_args.args[1], settings)
            with patch('homeostasis_v4.local_observation.time.monotonic', return_value=0):
                exchange = LocalExchange(client, None, settings)
            with patch('homeostasis_v4.local_observation.time.monotonic', return_value=3601):
                with self.assertRaisesRegex(Exception, 'PILOT_DEADLINE_REACHED'):
                    exchange('{}')
            self.assertEqual(self.calls, [])
            for timeout, deadline in ((0, 1200), (601, 1200), (180, 0), (180, 7201), (True, 1200)):
                with self.subTest(timeout=timeout, deadline=deadline), self.assertRaises(Exception):
                    prepare(client, model='qwen3:1.7b', seed=73, turns=2,
                            request_timeout_seconds=timeout, run_deadline_seconds=deadline)

    def test_structured_format_is_existing_contract_and_keeps_free_requests(self):
        with tempfile.TemporaryDirectory() as tmp, self.provider() as client:
            settings = prepare(client, model='qwen3:1.7b', seed=73, turns=2,
                               synthetic=True, structured_output=True)
            self.assertEqual(settings['generation_config']['format'], local_reply_format())
            self.assertIsNot(settings['generation_config']['format'], REPLY)
            path = Path(tmp) / 'run'
            result = execute(path, settings, protocol_digest=digest(settings), client=client,
                             telemetry=lambda c, m: {'timestamp': 'fixture', 'measurements': {}})
            self.assertEqual(result['status'], 'success')
            self.assertEqual(replay(path)['replayed_turns'], 2)
            self.assertTrue(all(c['format'] == local_reply_format() for c in self.calls))
            view = json.loads(self.calls[0]['prompt'])['view']
            proposals = {'outgoing': [], 'private_note': 'A freely chosen note', 'activities': [
                {'body': 'An institution not defined by the environment',
                 'operation': 'invented_institution', 'arguments': {'proposal': ['free', 7]}},
                {'body': 'A free-text activity without a known operation'}]}
            from jsonschema import Draft202012Validator
            Draft202012Validator(settings['generation_config']['format']).validate(proposals)
            self.assertEqual(parse_reply(canonical(proposals), view), proposals)
            Draft202012Validator(settings['generation_config']['format']).validate(empty())

    def test_parameter_display_order_does_not_change_identity_or_raw_metadata(self):
        expected = {'digest': 'a' * 64, 'details': {
            'parameters': 'temperature 0.6\nstop "first"\ntop_p 0.95\nstop "second"',
            'template': 'original'}}
        actual = deepcopy(expected)
        actual['details']['parameters'] = 'top_p 0.95\nstop "first"\nstop "second"\ntemperature 0.6'
        originals = deepcopy((actual, expected))
        self.assertTrue(same_identity(actual, expected))
        self.assertEqual((actual, expected), originals)
        for field, value in (
            ('parameters', 'top_p 0.94\nstop "first"\nstop "second"\ntemperature 0.6'),
            ('parameters', 'top_p 0.95\nstop "second"\nstop "first"\ntemperature 0.6'),
            ('parameters', 'top_p 0.95\nstop "first"\ntemperature 0.6'),
            ('template', 'changed'),
        ):
            changed = deepcopy(actual); changed['details'][field] = value
            self.assertFalse(same_identity(changed, expected))
        changed = deepcopy(actual); changed['digest'] = 'b' * 64
        self.assertFalse(same_identity(changed, expected))

    def test_live_guard_allows_only_parameter_order_change(self):
        for parameters, succeeds in (('top_p 0.95\ntemperature 0.6', True),
                                     ('top_p 0.94\ntemperature 0.6', False)):
            with self.subTest(parameters=parameters), tempfile.TemporaryDirectory() as tmp:
                base = self.provider()
                original_handler = base._transport.handle_request
                show_count = 0
                def handler(request):
                    nonlocal show_count
                    response = original_handler(request)
                    if request.url.path == '/api/show':
                        show_count += 1
                        body = response.json()
                        body['parameters'] = 'temperature 0.6\ntop_p 0.95' if show_count == 1 else parameters
                        return httpx.Response(200, json=body)
                    return response
                with base, httpx.Client(transport=httpx.MockTransport(handler)) as client:
                    result = self.run_fixture(Path(tmp) / 'run', client)
                    self.assertEqual(result['status'], 'success' if succeeds else 'failure')
                    self.assertEqual(len(self.calls), 16 if succeeds else 0)
                    if not succeeds:
                        terminal = read_record(Path(tmp) / 'run/terminal.json')
                        self.assertEqual(terminal['error']['code'], 'LOCAL_MODEL_CHANGED')

    def provider(self, fault=None):
        self.calls = []; self.urls = []
        def handle(request):
            self.urls.append(str(request.url))
            path = request.url.path
            if path == '/api/version':
                return httpx.Response(200, json={'version': '0.34.1' if fault == 'version' else '0.34.2'})
            if path == '/api/status':
                return httpx.Response(200, json={'cloud': {'disabled': fault != 'cloud', 'source': 'environment'}})
            if path == '/api/tags':
                return httpx.Response(200, json={'models': [{'name': 'qwen3:1.7b', 'size': 123,
                    'digest': 'f' * 64, 'remote_host': 'https://example.invalid' if fault == 'remote' else ''}]})
            if path == '/api/show':
                return httpx.Response(200, json={'parameters': 'temperature 0.6', 'template': 'fixture',
                    'model_info': {}, 'details': {}, 'system': 'extra instructions' if fault == 'system' else ''})
            self.assertIn(path, ('/api/generate', '/api/chat'))
            body = json.loads(request.content); self.calls.append(body)
            if path == '/api/chat':
                self.assertEqual(body['messages'][0], {'role': 'system', 'content': SYSTEM_INSTRUCTION})
                prompt = body['messages'][1]['content']
            else:
                self.assertEqual(body['system'], SYSTEM_INSTRUCTION)
                prompt = body['prompt']
            self.assertFalse(body['truncate']); self.assertFalse(body['shift'])
            view = json.loads(prompt)['view']; reply = empty()
            if view['turn'] == 1 and view['actor'] == 'MIL':
                reply.update(outgoing=[{'to': ['RES'], 'body': 'private offer'}],
                             private_note='private memory', activities=[offer()])
            if view['turn'] == 2 and view['actor'] == 'RES':
                reply['activities'] = [respond(view)]
            if fault == 'recipient':
                reply['outgoing'] = [{'to': ['UNSEEN'], 'body': 'invalid address'}]
            if fault == 'timeout':
                raise httpx.ReadTimeout('test timeout')
            if fault == 'partial_timeout':
                class Partial(httpx.SyncByteStream):
                    def __iter__(self):
                        yield b'{"response":"partial'
                        raise httpx.ReadTimeout('test interrupted body')
                return httpx.Response(200, stream=Partial())
            if fault == 'interrupt':
                raise KeyboardInterrupt()
            data = {
                'model': 'qwen3:1.7b', 'response': '{' if fault == 'json' else canonical(reply),
                'done': True, 'done_reason': 'length' if fault == 'length' else 'stop',
                'prompt_eval_count': 100, 'eval_count': 50}
            if path == '/api/chat':
                text = data.pop('response')
                data['message'] = {'role': 'assistant', 'content': '' if fault == 'thinking_only' else text,
                                   'thinking': text if fault == 'thinking_only' else 'THINKING_MUST_NOT_BE_AN_AGENT_ANSWER'}
            return httpx.Response(503 if fault == 'http' else 200, json=data)
        return httpx.Client(transport=httpx.MockTransport(handle), trust_env=False, follow_redirects=False)

    def run_fixture(self, directory, client):
        settings = prepare(client, model='qwen3:1.7b', seed=73, turns=2, synthetic=True)
        return execute(directory, settings, protocol_digest=digest(settings), client=client,
                       telemetry=lambda c, m: {'timestamp': 'fixture', 'measurements': {}})

    def test_local_exchange_privacy_seed_and_exact_world_replay(self):
        with tempfile.TemporaryDirectory() as tmp, self.provider() as client:
            path = Path(tmp) / 'run'
            result = self.run_fixture(path, client)
            self.assertEqual(result['status'], 'success')
            self.assertEqual(replay(path)['replayed_turns'], 2)
            self.assertEqual(len(self.calls), 16)
            self.assertEqual([c['options']['seed'] for c in self.calls], list(range(73, 89)))
            for call in self.calls[8:]:
                view = json.loads(call['prompt'])['view']
                if view['actor'] not in ('MIL', 'RES'):
                    self.assertNotIn('private offer', call['prompt'])
                if view['actor'] != 'MIL':
                    self.assertNotIn('private memory', call['prompt'])
            self.assertTrue(all(url.startswith('http://127.0.0.1:11434/') for url in self.urls))
            self.assertEqual(read_record(path / 'manifest.json')['provider'], 'synthetic-transport')
            with self.assertRaises(FileExistsError):
                self.run_fixture(path, client)
            self.assertEqual(len(self.calls), 16)

    def test_all_failed_outputs_are_preserved_without_retry(self):
        for fault in ('json', 'recipient', 'length', 'http', 'timeout', 'partial_timeout', 'interrupt'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp, self.provider(fault) as client:
                path = Path(tmp) / 'run'; result = self.run_fixture(path, client)
                self.assertEqual(result['status'], 'interrupted' if fault == 'interrupt' else 'failure')
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(replay(path)['replayed_turns'], 0)
                self.assertTrue((path / 'RAW/call-000.request.json').is_file())
                wire = read_record(path / 'RAW/call-000.wire.json')
                self.assertEqual(bool(base64.b64decode(wire['body_base64'])), fault not in ('timeout', 'interrupt'))
                self.assertTrue(read_record(path / 'RAW/failure.json')['not_an_agent_decision'])
                self.assertTrue((path / 'RAW/memory-after.json').is_file())

    def test_replay_binds_checkpoints_to_actual_exchange_records(self):
        with tempfile.TemporaryDirectory() as tmp, self.provider() as client:
            original = Path(tmp) / 'original'; self.run_fixture(original, client)
            for changed in ('request', 'wire'):
                path = Path(tmp) / changed
                evidence = EvidenceRun(path, read_record(original / 'manifest.json'))
                for raw in sorted((original / 'RAW').iterdir()):
                    value = read_record(raw)
                    if raw.name == f'call-000.{changed}.json':
                        if changed == 'request':
                            value['body']['system'] = 'altered instruction'
                        else:
                            data = json.loads(base64.b64decode(value['body_base64']))
                            data['response'] = 'altered output'
                            value['body_base64'] = base64.b64encode(json.dumps(data).encode()).decode()
                    evidence.write(raw.name, value)
                evidence.finish('success', completed_turns=2)
                self.assertEqual(verify(path)['status'], 'success')
                with self.assertRaisesRegex(Exception, 'LOCAL_WIRE_'):
                    replay(path)

    def test_cloud_unknown_server_and_embedded_instructions_block_generation(self):
        for fault in ('cloud', 'remote', 'version', 'system'):
            with self.subTest(fault=fault), self.provider(fault) as client:
                with self.assertRaises(Exception):
                    prepare(client, model='qwen3:1.7b', seed=73, turns=2, synthetic=True)
                self.assertEqual(self.calls, [])

    def test_moved_protocol_and_source_block_generation(self):
        with tempfile.TemporaryDirectory() as tmp, self.provider() as client:
            settings = prepare(client, model='qwen3:1.7b', seed=73, turns=2, synthetic=True)
            old = digest(settings); settings['turns'] = 3
            with self.assertRaisesRegex(Exception, 'PREPARED_LOCAL_PROTOCOL_CHANGED'):
                execute(Path(tmp) / 'run', settings, protocol_digest=old, client=client)
            settings['source_hashes']['simulation.py'] = '0' * 64
            with self.assertRaisesRegex(Exception, 'LOCAL_SOURCE_CHANGED'):
                execute(Path(tmp) / 'run', settings, protocol_digest=digest(settings), client=client)
            self.assertFalse((Path(tmp) / 'run').exists())
            self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
