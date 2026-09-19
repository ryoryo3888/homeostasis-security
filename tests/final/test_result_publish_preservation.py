"""Final result publication must never replace existing evidence."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import final_experiment_runner
from homeostasis_core import experiments


class ResultPublishPreservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.output = self.directory / 'synthetic.json'
        self.result = experiments.ResearchResult({'fixture': True}, ({'synthetic': True},), {'value': 1})

    def test_concurrent_result_is_never_replaced(self):
        original_link = experiments.os.link
        def concurrent(source, destination):
            Path(destination).write_bytes(b'other process original evidence')
            return original_link(source, destination)
        with patch.object(experiments.os, 'link', side_effect=concurrent), self.assertRaises(FileExistsError):
            experiments.save_result_atomic(self.result, self.output)
        self.assertEqual(self.output.read_bytes(), b'other process original evidence')
        self.assertEqual(list(self.directory.glob('.result-*')), [])

    def test_dangling_symlink_is_preserved(self):
        target = self.directory / 'absent-original.json'
        self.output.symlink_to(target)
        with self.assertRaises(FileExistsError):
            experiments.save_result_atomic(self.result, self.output)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(self.output.readlink(), target)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.directory.glob('.result-*')), [])

    def test_failure_leaves_no_partial_result(self):
        def broken_dump(data, stream, **kwargs):
            stream.write('partial')
            raise OSError('synthetic disk full')
        with patch.object(experiments.json, 'dump', side_effect=broken_dump), self.assertRaises(OSError):
            experiments.save_result_atomic(self.result, self.output)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_successful_bytes_match_existing_format_and_cannot_be_rewritten(self):
        expected = json.dumps(self.result.to_dict(), ensure_ascii=False, indent=2).encode()
        self.assertEqual(experiments.save_result_atomic(self.result, self.output), self.output)
        self.assertEqual(self.output.read_bytes(), expected)
        with self.assertRaises(FileExistsError): experiments.save_result_atomic(self.result, self.output)
        self.assertEqual(self.output.read_bytes(), expected)
        self.assertEqual(list(self.directory.glob('.result-*')), [])

    def test_runner_and_cli_stop_at_dangling_output_before_client_or_calls(self):
        self.output.symlink_to(self.directory / 'absent-original.json')
        generate = Mock()
        with self.assertRaises(FileExistsError):
            final_experiment_runner.run_live(SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
                                             self.output, 1, 7)
        generate.assert_not_called()
        args = SimpleNamespace(output=self.output, runs=1, seed=7, one_run=False, execute=True,
                               confirm='YES', resume=False)
        with patch.object(final_experiment_runner, 'parse_args', return_value=args), \
                patch.object(final_experiment_runner, 'getpass') as credential, \
                patch.object(final_experiment_runner, 'create_gemini_client') as client, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit): final_experiment_runner.main()
        credential.assert_not_called(); client.assert_not_called()
        self.assertTrue(self.output.is_symlink())
        self.assertFalse((self.directory / '.artifacts').exists())


if __name__ == '__main__': unittest.main()
