import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from unittest.mock import patch
from types import SimpleNamespace
import unittest

import simulation_v2 as sim


class SimulationV2Tests(unittest.TestCase):
    def test_direct_run_stops_before_client_access(self):
        class ForbiddenClient:
            @property
            def models(self):
                raise AssertionError("provider must not be accessed")
        with self.assertRaisesRegex(sim.WorldUpdateNotApprovedError, "V2_WORLD_UPDATE_NOT_APPROVED"):
            sim.run_simulation(ForbiddenClient())

    def test_stop_is_not_a_synthetic_no_action_result(self):
        with self.assertRaisesRegex(sim.WorldUpdateNotApprovedError, "研究結果ではありません"):
            sim.run_simulation(None)

    def test_cli_stops_before_confirmation_credentials_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "new-run.json"
            for yes in (False, True):
                with self.subTest(yes=yes), ExitStack() as stack:
                    stack.enter_context(patch.object(sim, "parse_args", return_value=SimpleNamespace(output=destination, yes=yes)))
                    forbidden = [stack.enter_context(patch(target, side_effect=AssertionError("must not be called")))
                                 for target in ("builtins.input", "simulation_v2.getpass", "simulation_v2.create_gemini_client", "simulation_v2.call_json", "simulation_v2.save_result")]
                    with self.assertRaisesRegex(SystemExit, "V2_WORLD_UPDATE_NOT_APPROVED"):
                        sim.main()
                    for function in forbidden:
                        function.assert_not_called()
                    self.assertFalse(destination.exists())
                    self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "existing.json"
            original = b'{"historical":"unchanged"}\n'
            destination.write_bytes(original)
            with patch.object(sim, "parse_args", return_value=SimpleNamespace(output=destination, yes=True)):
                with self.assertRaisesRegex(SystemExit, "既に存在"):
                    sim.main()
            self.assertEqual(destination.read_bytes(), original)

    def test_real_cli_refuses_before_api_key_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "new.json"
            env = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
            result = subprocess.run([sys.executable, "-B", str(Path(sim.__file__)), "--yes", "--output", str(destination)],
                                    input="", capture_output=True, text=True, env=env, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("V2_WORLD_UPDATE_NOT_APPROVED", result.stderr)
            self.assertNotIn("API Key", result.stdout + result.stderr)
            self.assertFalse(destination.exists())

    def test_historical_file_is_untouched_by_rejected_run(self):
        saved = Path(sim.__file__).with_name("v2_first_run.json")
        before = saved.read_bytes()
        with self.assertRaises(sim.WorldUpdateNotApprovedError):
            sim.run_simulation(None)
        self.assertEqual(saved.read_bytes(), before)
        self.assertEqual(len(json.loads(before)["turns"]), 5)

    def test_invalid_agent_response_is_detected(self):
        bad = json.dumps({
            "observation": "観測", "action": ["壊れた通信形式"],
            "proposal_response": "受け入れる", "reason": "理由",
        }, ensure_ascii=False)
        with self.assertRaises(ValueError):
            sim.parse_country_response(bad, "A")

    def test_retry_succeeds_after_temporary_failure(self):
        from google.genai.errors import APIError

        class FlakyModels:
            def __init__(self):
                self.count = 0

            def generate_content(self, **kwargs):
                self.count += 1
                if self.count == 1:
                    raise APIError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}})
                return SimpleNamespace(text="ok")

        models = FlakyModels()
        response = sim.generate_content_with_retry(
            SimpleNamespace(models=models),
            model="fake", contents="fake", sleep_fn=lambda _: None, jitter_fn=lambda _a, _b: 0,
        )
        self.assertEqual(response.text, "ok")
        self.assertEqual(models.count, 2)


if __name__ == "__main__":
    unittest.main()
