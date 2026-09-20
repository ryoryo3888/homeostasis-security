import base64
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from homeostasis_v3.contracts import canonical, digest
from homeostasis_v4.dialogue import SYSTEM_INSTRUCTION
from homeostasis_v4.evidence import EvidenceRun, read_record, verify
from homeostasis_v4.local_observation import execute, prepare, replay
from tests.v3.test_v4_dialogue import empty, offer, respond


class LocalPilotTests(unittest.TestCase):
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
            self.assertEqual(path, '/api/generate')
            body = json.loads(request.content); self.calls.append(body)
            self.assertEqual(body['system'], SYSTEM_INSTRUCTION)
            self.assertFalse(body['truncate']); self.assertFalse(body['shift'])
            view = json.loads(body['prompt'])['view']; reply = empty()
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
            return httpx.Response(503 if fault == 'http' else 200, json={
                'model': 'qwen3:1.7b', 'response': '{' if fault == 'json' else canonical(reply),
                'done': True, 'done_reason': 'length' if fault == 'length' else 'stop',
                'prompt_eval_count': 100, 'eval_count': 50})
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
