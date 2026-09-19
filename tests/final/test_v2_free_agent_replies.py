"""Agent content is not an action catalogue; malformed transport still fails."""
import json
import unittest
from unittest.mock import patch

import simulation_v2 as v2


class V2FreeAgentReplyTests(unittest.TestCase):
    def test_unlisted_actions_and_responses_survive_without_rewriting(self):
        for country in v2.AGENTS:
            fields = dict(observation="  未整理の認識\n", action="共同の地名辞典を作る。次に質問する。",
                          proposal_response="返事の前に、その言葉の意味を聞きたい。",
                          reason="\n私的な記録  ")
            self.assertEqual(v2.parse_country_response(json.dumps(fields), country), fields)

    def test_coordinator_can_propose_something_unlisted_or_say_nothing(self):
        for proposal in ("言葉を一緒に定義する場所を提案します。", ""):
            fields = {"proposal": proposal, "reason": ""}
            self.assertEqual(v2.parse_coordinator_response(json.dumps(fields)), fields)

    def test_explicit_silence_is_not_a_missing_or_broken_response(self):
        fields = {key: "" for key in ("observation", "action", "proposal_response", "reason")}
        self.assertEqual(v2.parse_country_response(json.dumps(fields), "A"), fields)
        for key in fields:
            for invalid in (None, [], 2, False):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                    v2.parse_country_response(json.dumps({**fields, key: invalid}), "A")
            missing = dict(fields)
            del missing[key]
            with self.assertRaises(ValueError):
                v2.parse_country_response(json.dumps(missing), "A")

    def test_prompts_do_not_prescribe_menu_reply_or_research_outcome(self):
        fields = dict(observation="", action="", proposal_response="", reason="")
        for code, agent in v2.AGENTS.items():
            with patch.object(v2, "call_json", return_value=json.dumps(fields)) as call:
                v2.call_country(object(), agent, {"event": "initial"}, "raw statement")
                prompt = call.call_args.args[1]
            for prohibited in (*agent.actions, *agent.interests, *v2.PROPOSAL_RESPONSES,
                               "許可された行動", "選択可能", v2.RESEARCH_QUESTION):
                self.assertNotIn(prohibited, prompt)
        with patch.object(v2, "call_json", return_value='{"proposal":"","reason":""}') as call:
            v2.call_coordinator(object(), {})
            prompt = call.call_args.args[1]
        for prohibited in (*v2.COORDINATOR_PROPOSALS, v2.RESEARCH_QUESTION, "選択肢の1つ"):
            self.assertNotIn(prohibited, prompt)

    def test_unknown_identity_is_not_accepted_as_another_country(self):
        with self.assertRaisesRegex(ValueError, "unknown country"):
            v2.parse_country_response('{"observation":"","action":"","proposal_response":"","reason":""}', "D")


if __name__ == "__main__":
    unittest.main()
