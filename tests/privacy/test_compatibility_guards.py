"""Offline regression checks for the four permitted compatibility repairs."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io

import final_experiment_runner as runner
from prompt_interface.audit import private_checkpoint, private_receipts, ROOT
from response_receipts import ResponseReceipts

class CompatibilityGuards(unittest.TestCase):
    def test_legacy_blocks_both_modes_before_dispatch_and_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'result.json'
            old=output.with_suffix('.json.checkpoint');old.write_bytes(b'{"legacy":"unchanged"}')
            for resume in (False,True):
                with self.subTest(resume=resume):
                    with self.assertRaisesRegex(ValueError,'旧形式checkpointのため再開停止'):
                        runner.run_live(object(),output,1,7,resume)
                    args=SimpleNamespace(output=output,resume=resume,execute=True,confirm='YES',one_run=False,runs=1,seed=7)
                    with patch.object(runner,'parse_args',return_value=args),patch.object(runner,'getpass') as key,patch.object(runner,'create_gemini_client') as client,redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(ValueError,'旧形式checkpointのため再開停止'):runner.main()
                        key.assert_not_called();client.assert_not_called()
                    self.assertEqual(old.read_bytes(),b'{"legacy":"unchanged"}')
                    self.assertFalse(output.exists())
    def test_public_result_destination_routes_sdk_receipts_privately(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'HOMEOSTASIS_PRIVATE_RUNS':temp}):
            output=ROOT/'results/final/no-execution.json'
            store=ResponseReceipts.for_output(output)
            self.assertTrue(store.directory.is_relative_to(Path(temp).resolve()))
            self.assertEqual(store.directory,private_receipts(output))
            self.assertNotEqual(store.directory,output.parent/'.artifacts/response-receipts'/output.name)
    def test_private_checkpoint_requires_resume_before_credentials(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'HOMEOSTASIS_PRIVATE_RUNS':temp}):
            output=Path(temp)/'result.json';cp=private_checkpoint(output);cp.parent.mkdir(parents=True);cp.write_text('{}')
            args=SimpleNamespace(output=output,resume=False,execute=True,confirm='YES',one_run=False,runs=1,seed=7)
            with patch.object(runner,'parse_args',return_value=args),patch.object(runner,'getpass') as key,patch.object(runner,'create_gemini_client') as client,redirect_stdout(io.StringIO()):
                with self.assertRaises(FileExistsError):runner.main()
                key.assert_not_called();client.assert_not_called()
