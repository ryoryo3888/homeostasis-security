"""V1 response preservation through real runners and synthetic SDK replies."""
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

import experiment_runner
import simulation
from response_receipts import ResponseReceipts
from test_simulation import FakeModels, sdk_reply


class V1ReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NO_NETWORK'))
        network.start(); self.addCleanup(network.stop)

    def run_comparison(self, models, condition='A', directory=None):
        args = SimpleNamespace(output_dir=directory or self.directory, condition=condition,
                               allow_over_limit=False, yes=True, seed=17)
        client = SimpleNamespace(models=models)
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'offline-dummy'}), \
                patch.object(simulation.genai, 'Client', return_value=client), redirect_stdout(io.StringIO()):
            experiment_runner.run_experiment(args)
        return experiment_runner.output_path(args.output_dir, condition, 1)

    def test_all_comparison_conditions_keep_originals_after_staging_cleanup(self):
        for condition in experiment_runner.CONDITIONS:
            with self.subTest(condition=condition):
                directory = self.directory / condition; directory.mkdir()
                models = FakeModels()
                output = self.run_comparison(models, condition, directory)
                result = json.loads(output.read_text())
                receipts = ResponseReceipts.for_output(output)
                self.assertEqual(models.total_calls, 24)
                self.assertEqual(len(result['response_receipts']), 24)
                self.assertEqual(len(list(receipts.directory.glob('*.json'))), 24)
                receipts.verify(result['response_receipts'])
                self.assertEqual(list(directory.glob('.experiment-*')), [])
                first = result['response_receipts'][0]
                self.assertEqual((first['run'], first['turn'], first['agent_id']), (1, 1, 'A国'))
                raw = json.loads((receipts.directory/(first['response_receipt']['id']+'.json')).read_text())
                self.assertEqual(raw['sdk_response']['candidates'][0]['content']['parts'][0]['text'], sdk_reply(
                    '現在認識: 国境付近の状況には不確実性がある。\n'
                    '懸念: 国家の安全と法的帰結を同時に検討する必要がある。\n'
                    '行動: 観測態勢を維持し、今回の外部イベントに対応する。\n'
                    '理由: 国家利益と現在観測できる情報を踏まえた判断である。').text)
                self.assertEqual([x['agent_type'] for x in result['response_receipts']],
                                 ['country','country','evaluator'] * 8)
                self.assertNotIn('offline-dummy', json.dumps(raw))

    def test_agent_and_evaluator_failure_keep_original_after_cleanup(self):
        for invalid_call in (1, 2, 3, 4, 6):
            with self.subTest(invalid_call=invalid_call):
                directory = self.directory / str(invalid_call); directory.mkdir()
                models = FakeModels(); generate = models.generate_content
                raw = ' \n{"reason": "synthetic truncated response"'
                def invalid(**kwargs):
                    answer = generate(**kwargs)
                    return sdk_reply(raw) if models.total_calls == invalid_call else answer
                models.generate_content = invalid
                with self.assertRaises(ValueError): self.run_comparison(models, directory=directory)
                output = experiment_runner.output_path(directory, 'A', 1)
                receipts = ResponseReceipts.for_output(output)
                saved = [json.loads(path.read_text()) for path in receipts.directory.glob('*.json')]
                self.assertEqual(len(saved), invalid_call)
                self.assertTrue(any(item['sdk_response']['candidates'][0]['content']['parts'][0]['text'] == raw for item in saved))
                self.assertEqual(models.total_calls, invalid_call)
                self.assertFalse(output.exists())
                self.assertEqual(list(directory.glob('.experiment-*')), [])

    def test_storage_error_cannot_be_misread_as_retryable_provider_error(self):
        generate = Mock(return_value=sdk_reply('original decision'))
        recorder = Mock(side_effect=OSError('503 UNAVAILABLE 429 synthetic disk error'))
        with self.assertRaises(OSError), patch.object(simulation.time, 'sleep') as sleep:
            simulation.generate_content_with_retry(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                model='offline-model', contents='unchanged', response_recorder=recorder)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(recorder.call_count, 1)
        sleep.assert_not_called()
        self.assertNotIn('response_recorder', generate.call_args.kwargs)

    def test_existing_receipts_block_before_credentials_and_client(self):
        receipts = ResponseReceipts.for_output(self.directory/'published.json')
        receipts.prepare()
        previous = Path.cwd(); os.chdir(self.directory)
        try:
            with patch.object(simulation, 'USE_GEMINI', True), \
                    patch.object(simulation, 'getpass') as secret, \
                    patch.object(simulation.genai, 'Client') as client:
                with self.assertRaises(FileExistsError):
                    simulation.main(receipt_output=self.directory/'published.json')
            secret.assert_not_called(); client.assert_not_called()
        finally:
            os.chdir(previous)


if __name__ == '__main__': unittest.main()
