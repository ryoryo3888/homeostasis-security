import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from homeostasis_core.v2_adapter import load_v2_first_run


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "v2_first_run.json"
BASELINE = Path("/tmp/homeostasis-final-baseline-sha256.txt")


class Phase1CompatibilityTests(unittest.TestCase):
    def test_five_turns_and_countries(self):
        converted = load_v2_first_run(LEGACY)
        self.assertEqual(len(converted.turns), 5)
        self.assertEqual(tuple(converted.initial_world_state.countries), ("A", "B", "C"))

    def test_coordinator_and_country_answers_are_preserved(self):
        source = json.loads(LEGACY.read_text(encoding="utf-8"))
        converted = load_v2_first_run(LEGACY)
        for raw, record in zip(source["turns"], converted.turns):
            self.assertEqual(record.coordinator_proposal.proposal, raw["coordinator_proposal"]["proposal"])
            self.assertEqual(
                {code: item.proposal_response for code, item in record.decisions.items()},
                raw["proposal_responses"],
            )

    def test_key_sequences_and_result(self):
        converted = load_v2_first_run(LEGACY)
        damage = [row.action_results["persistent_effects"]["lost_capacity_before_actions_tons"] for row in converted.turns]
        sovereignty = [row.world_after.countries["A"].sovereignty for row in converted.turns]
        homeostasis = [row.world_after.global_homeostasis for row in converted.turns]
        self.assertEqual(damage, [8000, 6000, 4000, 2000, 0])
        self.assertEqual(sovereignty, [88, 87, 86, 86, 86])
        self.assertEqual(converted.initial_world_state.global_homeostasis, 68)
        self.assertEqual(homeostasis, [70, 73, 76, 80, 82])
        self.assertEqual(converted.final_result["outcome"], "recovered")

    def test_adapter_does_not_modify_legacy_json(self):
        before = hashlib.sha256(LEGACY.read_bytes()).digest()
        load_v2_first_run(LEGACY)
        self.assertEqual(hashlib.sha256(LEGACY.read_bytes()).digest(), before)

    def test_no_api_call(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
            load_v2_first_run(LEGACY)

    def test_existing_tracked_files_match_baseline(self):
        self.assertTrue(BASELINE.is_file(), "baseline SHA-256 list is missing")
        records = {}
        for line in BASELINE.read_text(encoding="utf-8").splitlines():
            digest, filename = line.split("  ", 1)
            records[filename] = digest
        self.assertEqual(len(records), 117)
        for filename, expected in records.items():
            actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, filename)


if __name__ == "__main__":
    unittest.main()
