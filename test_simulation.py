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
        self.prompts = []

    def generate_content(self, model, contents, config=None):
        self.total_calls += 1
        self.prompts.append(contents)

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
            for country in ("country_a", "country_b"):
                self.assertEqual(result[country]["action_status"], "declared")
                self.assertEqual(result[country]["realization_status"], "unverified")
            self.assertNotIn("を実行した。", result["world_state"])
            self.assertIn("実行結果や相手国への到達を確認した記録ではない", result["world_state"])
            provenance = result["metric_provenance"]
            self.assertEqual(provenance["evaluation_source"], "model_evaluator_estimates")
            self.assertFalse(provenance["direct_world_measurement"])
            previous = output["results"][result["turn"] - 2]["metrics"] if result["turn"] > 1 else None
            self.assertEqual(result["metrics"], simulation.calculate_metrics(result["evaluation"], previous))
            self.assertEqual(provenance["previous_values_used"], {key: (previous or {}).get(key, default) for key, default in (("tension",45),("trust",50),("resilience",60))})
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

        if turn_count > 1:
            second_turn_agent_prompts = fake_models.prompts[3:5]
            for prompt in second_turn_agent_prompts:
                self.assertIn("行動選択と実現結果は別", prompt)
                self.assertNotIn("を実行した。", prompt)
        for prompt in fake_models.prompts[2::3]:
            self.assertIn("行動に関する採点は宣言内容についての推定", prompt)
        return output

    def test_declarations_do_not_establish_delivery_or_realization(self):
        state = simulation.build_world_state("ホットラインで停戦を提案する", "食料を輸送する")
        self.assertIn("ホットラインで停戦を提案する", state)
        self.assertIn("食料を輸送する", state)
        self.assertIn("を選択した。", state)
        self.assertNotIn("を実行した。", state)
        self.assertNotIn("互いに相手国の行動を観測できる", state)
        self.assertIn("実行結果や相手国への到達を確認した記録ではない", state)

    def test_provenance_does_not_mutate_previous_metrics(self):
        previous = {"tension": 0, "trust": 100, "resilience": 13}
        before = dict(previous)
        provenance = simulation.metric_provenance(previous, live_evaluator=False)
        self.assertEqual(provenance["evaluation_source"], "synthetic_fixture")
        self.assertEqual(provenance["previous_values_source"], "previous_turn_metrics")
        self.assertEqual(provenance["previous_values_used"], before)
        provenance["previous_values_used"]["tension"] = 999
        self.assertEqual(previous, before)
        initial = simulation.metric_provenance(None, live_evaluator=False)
        self.assertEqual(initial["previous_values_source"], "implementation_initial_values")
        self.assertEqual(initial["bounded_update_max_delta"], 15)

    def test_same_evaluation_can_retain_implementation_history(self):
        evaluation = {field: 50 for field in simulation.EVALUATION_FIELDS}
        low = simulation.calculate_metrics(evaluation, {"tension": 0, "trust": 0, "resilience": 0})
        high = simulation.calculate_metrics(evaluation, {"tension": 100, "trust": 100, "resilience": 100})
        for key in ("tension", "trust", "resilience"):
            self.assertEqual(low[key], 15)
            self.assertEqual(high[key], 85)
        self.assertNotEqual(low["homeostasis"], high["homeostasis"])

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
