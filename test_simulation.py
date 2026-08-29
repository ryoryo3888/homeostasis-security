import json
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import simulation


class FakeModels:
    def __init__(self):
        self.total_calls = 0
        self.evaluator_calls = 0

    def generate_content(self, model, contents, config=None):
        self.total_calls += 1

        if config and config.get("response_mime_type") == "application/json":
            self.evaluator_calls += 1
            score = 28 + self.evaluator_calls * 3
            payload = {
                "actual_threat_level": score,
                "perceived_threat_a": score + 8,
                "perceived_threat_b": score - 4,
                "immune_response_strength_a": score + 12,
                "immune_response_strength_b": score - 7,
                "legal_alignment_a": 76,
                "legal_alignment_b": 82,
                "escalation_pressure": 48,
                "clarification_quality": 55,
                "trust_signal": 52,
                "recovery_capacity": 64,
            }
            return SimpleNamespace(text=json.dumps(payload))

        return SimpleNamespace(
            text=(
                "現在認識: 国境付近の状況には不確実性がある。\n"
                "懸念: 国家の安全と法的帰結を同時に検討する必要がある。\n"
                "行動: 観測態勢を維持し、今回の外部イベントに対応する。\n"
                "理由: 国家利益と現在観測できる情報を踏まえた判断である。"
            )
        )


class SimulationTest(unittest.TestCase):
    def run_fake_simulation(self, turn_count):
        fake_models = FakeModels()
        fake_client = SimpleNamespace(models=fake_models)

        with tempfile.TemporaryDirectory() as temp_dir:
            previous_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                with (
                    patch.object(simulation, "TURN_COUNT", turn_count),
                    patch.object(simulation, "USE_GEMINI", True),
                    patch.object(simulation, "getpass", return_value="test-key"),
                    patch.object(simulation.genai, "Client", return_value=fake_client),
                ):
                    with redirect_stdout(io.StringIO()):
                        simulation.main()

                output_path = os.path.join(
                    temp_dir,
                    "simulation_result_independent_agents_no_hotline.json",
                )
                with open(output_path, encoding="utf-8") as file:
                    output = json.load(file)
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(fake_models.total_calls, turn_count * 3)
        self.assertEqual(fake_models.evaluator_calls, turn_count)
        self.assertEqual(output["turn_count"], turn_count)
        self.assertEqual(len(output["results"]), turn_count)

        for result in output["results"]:
            self.assertTrue(result["country_a"]["action"])
            self.assertTrue(result["country_b"]["action"])
            self.assertIn("external_event", result)
            self.assertEqual(
                set(result["evaluation"]),
                set(simulation.EVALUATION_FIELDS),
            )
            for legacy_metric in (
                "homeostasis",
                "tension",
                "misperception_risk",
                "trust",
                "resilience",
            ):
                self.assertIn(legacy_metric, result["metrics"])

        return output

    def test_two_turn_smoke(self):
        self.run_fake_simulation(2)

    def test_eight_turn_run(self):
        output = self.run_fake_simulation(8)
        self.assertEqual(
            [item["external_event"]["event_id"] for item in output["results"]],
            [event.event_id for event in simulation.EXTERNAL_EVENTS],
        )

    def test_metrics_reward_response_fit_not_action_words(self):
        evaluation = {
            "actual_threat_level": 90,
            "perceived_threat_a": 88,
            "perceived_threat_b": 92,
            "immune_response_strength_a": 82,
            "immune_response_strength_b": 86,
            "legal_alignment_a": 92,
            "legal_alignment_b": 88,
            "escalation_pressure": 70,
            "clarification_quality": 40,
            "trust_signal": 45,
            "recovery_capacity": 72,
        }
        metrics = simulation.calculate_metrics(evaluation)
        self.assertGreaterEqual(metrics["response_fit"], 90)
        self.assertEqual(metrics["overreaction"], 0)
        self.assertLessEqual(metrics["underreaction"], 10)
        self.assertEqual(metrics["legal_alignment"], 90)

    def test_overreaction_and_underreaction_are_deterministic(self):
        base = {
            "actual_threat_level": 20,
            "perceived_threat_a": 20,
            "perceived_threat_b": 20,
            "immune_response_strength_a": 90,
            "immune_response_strength_b": 10,
            "legal_alignment_a": 30,
            "legal_alignment_b": 80,
            "escalation_pressure": 60,
            "clarification_quality": 30,
            "trust_signal": 40,
            "recovery_capacity": 50,
        }
        metrics = simulation.calculate_metrics(base)
        self.assertEqual(metrics["overreaction_a"], 70)
        self.assertEqual(metrics["underreaction_b"], 10)

    def test_agent_sections_remain_separate(self):
        decision = (
            "現在認識: 観測した事実。\n"
            "懸念: 不確実な点。\n"
            "行動: 自由に選んだ行動。\n"
            "理由: 国家利益に基づく理由。"
        )
        self.assertEqual(simulation.extract_belief(decision), "観測した事実。")
        self.assertEqual(simulation.extract_concern(decision), "不確実な点。")
        self.assertEqual(simulation.extract_action(decision), "自由に選んだ行動。")
        self.assertEqual(simulation.extract_reason(decision), "国家利益に基づく理由。")


if __name__ == "__main__":
    unittest.main()
