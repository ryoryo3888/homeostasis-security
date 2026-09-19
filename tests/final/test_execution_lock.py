"""Concurrent resumes must not dispatch the same Agent decision twice."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import final_experiment_runner as runner
from homeostasis_core.execution_lock import exclusive_execution
from response_receipts import ResponseReceipts
from tests.final import test_no_regeneration_resume as fixtures


class ExecutionLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / 'synthetic.json'

    def client(self):
        return fixtures.RunnerResumeIntegrationTests.client(None)

    def test_concurrent_resume_rejected_before_checkpoint_or_dispatch(self):
        checkpoint = runner._checkpoint
        def stop(path, data):
            checkpoint(path, data)
            if data.get('active_run') and data['active_run']['completed_turn'] == 2:
                raise KeyboardInterrupt('synthetic boundary stop')
        with patch.object(runner, '_checkpoint', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt): runner.run_live(self.client(), self.output, 1, 7)
        before = self.output.with_suffix('.json.checkpoint').read_bytes()
        prepare = ResponseReceipts.prepare
        ready, release = threading.Event(), threading.Event()
        def pause_owner(store, **kwargs):
            ready.set()
            if not release.wait(timeout=10): raise AssertionError('owner was not released')
            return prepare(store, **kwargs)
        first, second = self.client(), self.client()
        with patch.object(ResponseReceipts, 'prepare', pause_owner), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runner.run_live, first, self.output, 1, 7, True)
            try:
                self.assertTrue(ready.wait(timeout=10))
                with self.assertRaisesRegex(FileExistsError, 'execution already active'):
                    runner.run_live(second, self.output, 1, 7, True)
                self.assertEqual(second.models.payloads, [])
                self.assertEqual(self.output.with_suffix('.json.checkpoint').read_bytes(), before)
                self.assertEqual(first.models.payloads, [])
            finally: release.set()
            result = future.result(timeout=15)
        self.assertEqual(len(first.models.payloads), 60)
        baseline = runner.run_live(self.client(), self.root / 'baseline.json', 1, 7)
        self.assertEqual(result['runs'][0]['turns'], baseline['runs'][0]['turns'])

    def test_lock_releases_after_failure_without_removing_lock_file(self):
        with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
            with exclusive_execution(self.output): raise RuntimeError('synthetic failure')
        path = self.root / '.artifacts/execution-locks/synthetic.json.lock'
        inode = path.stat().st_ino
        with exclusive_execution(self.output): self.assertEqual(path.stat().st_ino, inode)
        self.assertTrue(path.is_file())

    def test_other_process_cannot_enter_and_process_death_releases(self):
        script = ('from pathlib import Path\nfrom homeostasis_core.execution_lock import exclusive_execution\n'
                  'import os,sys\nwith exclusive_execution(Path(sys.argv[1])):\n    os._exit(17)\n')
        command = [sys.executable, '-B', '-c', script, str(self.output)]
        with exclusive_execution(self.output):
            blocked = subprocess.run(command, cwd=runner.SOURCE_ROOT, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(blocked.returncode, 17)
        self.assertIn('execution already active', blocked.stderr)
        crashed = subprocess.run(command, cwd=runner.SOURCE_ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(crashed.returncode, 17, crashed.stderr)
        with exclusive_execution(self.output): pass

    def test_parent_directory_alias_cannot_bypass_same_output_lock(self):
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with exclusive_execution(self.output):
            with self.assertRaisesRegex(FileExistsError, 'execution already active'):
                with exclusive_execution(alias / self.output.name): self.fail('second owner')

    def test_existing_lock_symlink_is_never_followed_or_replaced(self):
        directory = self.root / '.artifacts/execution-locks'; directory.mkdir(parents=True)
        evidence = self.root / 'evidence'; evidence.write_bytes(b'original evidence')
        lock = directory / (self.output.name + '.lock'); lock.symlink_to(evidence)
        with self.assertRaises(OSError):
            with exclusive_execution(self.output): self.fail('symlink accepted')
        self.assertTrue(lock.is_symlink()); self.assertEqual(evidence.read_bytes(), b'original evidence')


if __name__ == '__main__': unittest.main()
