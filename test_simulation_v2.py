import json
from types import SimpleNamespace
import unittest

import simulation_v2 as sim


class FakeModels:
    def __init__(self):
        self.calls = []
        self.turn = 0

    def generate_content(self, model, contents, config=None):
        self.calls.append(contents)
        if "ROLE: COORDINATOR" in contents:
            proposals = ["食料援助", "資源再配分", "仲裁", "緊急協定提案", "食料援助"]
            proposal = proposals[self.turn]
            return SimpleNamespace(text=json.dumps({"proposal": proposal, "reason": "地球状態の安定化"}, ensure_ascii=False))
        if "ROLE: COUNTRY " in contents:
            code = contents.split("ROLE: COUNTRY ", 1)[1][0]
            actions = {
                "A": ["制裁への反発", "外交交渉", "停戦", "補償", "外交交渉"],
                "B": ["農地復旧"] * 4 + ["停戦交渉"],
                "C": ["自国優先", "輸入政策変更", "制裁参加", "援助参加", "援助参加"],
            }
            answers = {
                "A": ["拒否する", "条件付きで応じる", "受け入れる", "条件付きで応じる", "受け入れる"],
                "B": ["受け入れる"] * 5,
                "C": ["条件付きで応じる", "条件付きで応じる", "条件付きで応じる", "受け入れる", "受け入れる"],
            }
            return SimpleNamespace(text=json.dumps({
                "observation": f"{code}国が公開情報を観測",
                "action": actions[code][self.turn],
                "proposal_response": answers[code][self.turn],
                "reason": f"{code}国の利益に基づく判断",
            }, ensure_ascii=False))
        if "ROLE: EVALUATOR" in contents:
            t = self.turn
            payload = {
                "food": 70 + t * 3,
                "energy": 76,
                "economy": 72 + t * 2,
                "environment": 74 + t,
                "international_trust": 62 + t * 5,
                "conflict_load": 36 - t * 5,
                "sovereignty_pressure": 18 - t * 2,
                "assessment": "公開された行動結果を評価",
            }
            self.turn += 1
            return SimpleNamespace(text=json.dumps(payload, ensure_ascii=False))
        raise AssertionError("unknown prompt role")


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


class SimulationV2Tests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.result = sim.run_simulation(self.client)

    def test_completes_five_turns(self):
        self.assertEqual(len(self.result["turns"]), 5)
        self.assertEqual([row["turn"] for row in self.result["turns"]], [1, 2, 3, 4, 5])

    def test_four_decision_makers_are_separate(self):
        calls = self.client.models.calls
        for turn in range(5):
            roles = calls[turn * 5 : turn * 5 + 4]
            self.assertIn("ROLE: COORDINATOR", roles[0])
            self.assertIn("ROLE: COUNTRY A", roles[1])
            self.assertIn("ROLE: COUNTRY B", roles[2])
            self.assertIn("ROLE: COUNTRY C", roles[3])
        self.assertEqual(len({id(agent) for agent in sim.AGENTS.values()}), 3)

    def test_evaluator_is_independent(self):
        evaluator_calls = [call for call in self.client.models.calls if "ROLE: EVALUATOR" in call]
        self.assertEqual(len(evaluator_calls), 5)
        self.assertEqual(len(self.client.models.calls), 25)

    def test_damage_persists_between_turns(self):
        effects = [row["persistent_effects"] for row in self.result["turns"]]
        self.assertEqual([row["lost_capacity_before_actions_tons"] for row in effects], [8000, 6000, 4000, 2000, 0])

    def test_restoration_reduces_damage_gradually(self):
        effects = [row["persistent_effects"] for row in self.result["turns"]]
        self.assertEqual([row["remaining_lost_capacity_tons"] for row in effects], [6000, 4000, 2000, 0, 0])
        self.assertEqual([row["recovered_this_turn_tons"] for row in effects], [2000, 2000, 2000, 2000, 0])

    def test_proposal_responses_are_saved(self):
        for row in self.result["turns"]:
            self.assertEqual(set(row["proposal_responses"]), {"A", "B", "C"})
            self.assertTrue(set(row["proposal_responses"].values()) <= set(sim.PROPOSAL_RESPONSES))

    def test_world_state_is_bounded(self):
        for row in self.result["turns"]:
            for value in row["world_state"].values():
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 100)

    def test_sovereignty_and_homeostasis_are_recorded(self):
        for row in self.result["turns"]:
            self.assertIn("national_sovereignty", row["world_state"])
            self.assertIn("global_homeostasis", row["world_state"])

    def test_required_json_shape(self):
        self.assertEqual(set(self.result), {
            "metadata", "research_question", "source_event", "initial_world_state", "turns", "final_result"
        })
        required_turn = {
            "turn", "persistent_effects", "coordinator_proposal", "countries",
            "proposal_responses", "world_state", "evaluator", "action_log",
        }
        for row in self.result["turns"]:
            self.assertEqual(set(row), required_turn)
            self.assertEqual(set(row["countries"]), {"A", "B", "C"})

    def test_api_key_is_not_in_result(self):
        serialized = json.dumps(self.result, ensure_ascii=False)
        self.assertNotIn("test-secret-key", serialized)
        self.assertNotIn("GEMINI_API_KEY", serialized)

    def test_invalid_agent_response_is_detected(self):
        bad = json.dumps({
            "observation": "観測", "action": "許可されない行動",
            "proposal_response": "受け入れる", "reason": "理由",
        }, ensure_ascii=False)
        with self.assertRaises(ValueError):
            sim.parse_country_response(bad, "A")

    def test_retry_succeeds_after_temporary_failure(self):
        class TemporaryError(Exception):
            code = 503
            status = "UNAVAILABLE"

        class FlakyModels:
            def __init__(self):
                self.count = 0

            def generate_content(self, **kwargs):
                self.count += 1
                if self.count == 1:
                    raise TemporaryError("503 UNAVAILABLE")
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
