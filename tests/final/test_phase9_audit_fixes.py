import hashlib,json,tempfile,unittest
from pathlib import Path
from homeostasis_core.gemini_agents import (
    apply_structured_actions,build_private_views,derive_event,eligible_result_paths,parse_country_json,pilot_is_eligible,
)

class AuditFixTests(unittest.TestCase):
    def setUp(self):
        self.states={
            "MIL":{"archetype":"軍事大国","sovereignty":90,"indicators":{"food_reserves":68,"energy_stability":70,"economy":82,"military_security":95,"domestic_stability":76,"recovery_capacity":80,"international_trust":62,"diplomatic_posture":58},"resources":{"food":68,"fossil_fuel":70,"renewable_energy":55,"nuclear":82,"grid_storage_resilience":78,"funds_economy":84,"logistics":88}},
            "FOOD":{"archetype":"食料輸入国","sovereignty":76,"indicators":{"food_reserves":42,"energy_stability":55,"economy":72,"military_security":58,"domestic_stability":67,"recovery_capacity":60,"international_trust":74,"diplomatic_posture":72},"resources":{"food":42,"fossil_fuel":58,"renewable_energy":60,"nuclear":45,"grid_storage_resilience":64,"funds_economy":70,"logistics":74}},
        }
    def response(self,c,action="NO_ACTION",response="REJECT",params=None):
        labels={"ACCEPT":"受け入れる","REJECT":"拒否する","CONDITIONAL":"条件付きで応じる"}
        return {"country_id":c,"proposal_id":"p","response_id":response,"response_label":labels[response],"reason":"r","conditions":({"required_countries":["MIL"],"maximum_sovereignty_burden":20} if response=="CONDITIONAL" else {}),"self_interest":50,"sovereignty_burden":10,"perceived_global_effect":50,"action":{"action_id":action,"description":"d","parameters":params or {}}}
    def test_private_views_include_only_own_archetype_and_state(self):
        views=build_private_views("s1",1,{"food":60},self.states,{"MIL":90,"FOOD":80})
        self.assertEqual(views["MIL"]["archetype"],"軍事大国");self.assertEqual(views["FOOD"]["own_state"]["food_reserves"],42)
        self.assertNotIn("FOOD",json.dumps(views["MIL"],ensure_ascii=False));self.assertEqual(views["MIL"]["snapshot_id"],views["FOOD"]["snapshot_id"])
    def test_unknown_action_and_bad_response_stop(self):
        bad=self.response("MIL","UNKNOWN","ACCEPT")
        with self.assertRaises(ValueError):parse_country_json(json.dumps(bad))
    def test_structured_resource_action_conserves_and_recomputes_world(self):
        answers={"MIL":self.response("MIL","PROVIDE_RESOURCE","ACCEPT",{"resource":"food","amount":10,"target_country":"FOOD"}),"FOOD":self.response("FOOD")}
        out=apply_structured_actions(self.states,answers,{"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30},8000)
        self.assertAlmostEqual(out["country_states"]["MIL"]["resources"]["food"],58);self.assertAlmostEqual(out["country_states"]["FOOD"]["resources"]["food"],52)
        self.assertEqual(out["research_metrics"]["global_homeostasis"],out["true_world"]["global_homeostasis"])
        self.assertTrue(out["transfers"])
    def test_conditional_and_reject_are_not_forced(self):
        answers={"MIL":self.response("MIL","PROVIDE_RESOURCE","CONDITIONAL",{"resource":"food","amount":10,"target_country":"FOOD"}),"FOOD":self.response("FOOD")}
        answers["MIL"]["conditions"]["required_countries"]=["FOOD"]
        out=apply_structured_actions(self.states,answers,{"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30},8000)
        self.assertFalse(out["transfers"]);self.assertIn("MIL",out["condition_unmet"]);self.assertIn("FOOD",out["rejected"])
    def test_derived_events_have_multiple_state_driven_paths(self):
        self.assertNotEqual(derive_event({"food":30,"international_trust":30,"conflict_load":80},{"reserve_gap":40,"alertness":50},{"PROTECT_RESERVES":5}),derive_event({"food":85,"international_trust":85,"conflict_load":10},{"reserve_gap":5,"alertness":5},{"MEDIATE":5}))
    def test_rejected_pilot_manifest_excludes_result(self):
        with tempfile.TemporaryDirectory() as d:
            result=Path(d)/"pilot.json";result.write_text('{}');manifest=Path(d)/"pilot.audit.json";manifest.write_text(json.dumps({"schema_version":1,"result_file":"pilot.json","status":"rejected","include_in_research_aggregation":False}))
            self.assertFalse(pilot_is_eligible(result,manifest))
    def test_real_pilot_is_rejected_and_dashboard_does_not_reference_it(self):
        root=Path(__file__).parents[2];result=root/"results/final/gemini-run-20260915-01.json";manifest=root/"results/final/gemini-run-20260915-01.audit.json"
        audit=json.loads(manifest.read_text());self.assertEqual(hashlib.sha256(result.read_bytes()).hexdigest(),audit["result_sha256"])
        self.assertTrue(result.exists());self.assertFalse(pilot_is_eligible(result,manifest));self.assertNotIn(result,eligible_result_paths(result.parent));self.assertNotIn(result.name,(root/"dashboard_final.html").read_text())

if __name__=='__main__':unittest.main()
