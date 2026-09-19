import hashlib,json,tempfile,unittest
from pathlib import Path
from test_simulation import sdk_reply
from homeostasis_core.gemini_agents import (
    GeminiGateway,apply_structured_actions,build_private_views,coordinator_response_schema,country_response_schema,derive_event,eligible_result_paths,evaluator_response_schema,parse_country_json,pilot_is_eligible,
)
from homeostasis_core.resources import ResourceNetwork,SupplyLink

class AuditFixTests(unittest.TestCase):
    def setUp(self):
        self.states={
            "MIL":{"archetype":"軍事大国","sovereignty":90,"indicators":{"food_reserves":68,"energy_stability":70,"economy":82,"military_security":95,"domestic_stability":76,"recovery_capacity":80,"international_trust":62,"diplomatic_posture":58},"resources":{"food":68,"fossil_fuel":70,"renewable_energy":55,"nuclear":82,"grid_storage_resilience":78,"funds_economy":84,"logistics":88},"energy_portfolio":{"sources":{"fossil_fuel":50,"renewable_energy":25,"nuclear":25},"import_dependency":20}},
            "FOOD":{"archetype":"食料輸入国","sovereignty":76,"indicators":{"food_reserves":42,"energy_stability":55,"economy":72,"military_security":58,"domestic_stability":67,"recovery_capacity":60,"international_trust":74,"diplomatic_posture":72},"resources":{"food":42,"fossil_fuel":58,"renewable_energy":60,"nuclear":45,"grid_storage_resilience":64,"funds_economy":70,"logistics":74},"energy_portfolio":{"sources":{"fossil_fuel":50,"renewable_energy":40,"nuclear":10},"import_dependency":60}},
        }
    def response(self,c,action="NO_ACTION",response="REJECT",params=None):
        labels={"ACCEPT":"受け入れる","REJECT":"拒否する","CONDITIONAL":"条件付きで応じる"}
        return {"country_id":c,"proposal_id":"p","response_id":response,"response_label":labels[response],"reason":"r","conditions":({"required_countries":["MIL"],"maximum_sovereignty_burden":20} if response=="CONDITIONAL" else {}),"self_interest":50,"sovereignty_burden":10,"perceived_global_effect":50,"action_requires_participation":True,"action":{"action_id":action,"description":"d","parameters":params if params is not None else {"recipient_type":"none","target_country":None,"resource":None,"amount":0}}}
    def test_private_views_include_only_own_archetype_and_state(self):
        views=build_private_views("s1",1,{"food":60},self.states,{"MIL":90,"FOOD":80})
        self.assertEqual(views["MIL"]["archetype"],"軍事大国");self.assertEqual(views["FOOD"]["own_state"]["food_reserves"],42)
        self.assertNotIn("FOOD",json.dumps(views["MIL"],ensure_ascii=False));self.assertEqual(views["MIL"]["snapshot_id"],views["FOOD"]["snapshot_id"])
    def test_unknown_action_and_bad_response_stop(self):
        bad=self.response("MIL","UNKNOWN","ACCEPT")
        with self.assertRaises(ValueError):parse_country_json(json.dumps(bad))
    def test_structured_resource_action_conserves_and_recomputes_world(self):
        answers={"MIL":self.response("MIL","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"country","resource":"food","amount":10,"target_country":"FOOD"}),"FOOD":self.response("FOOD")}
        out=apply_structured_actions(self.states,answers,{"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30},8000)
        self.assertAlmostEqual(out["country_states"]["MIL"]["resources"]["food"],58);self.assertAlmostEqual(out["country_states"]["FOOD"]["resources"]["food"],52)
        self.assertEqual(out["research_metrics"]["global_homeostasis"],out["true_world"]["global_homeostasis"])
        self.assertTrue(out["transfers"])
    def test_conditional_and_reject_are_not_forced(self):
        answers={"MIL":self.response("MIL","PROVIDE_RESOURCE","CONDITIONAL",{"recipient_type":"country","resource":"food","amount":10,"target_country":"FOOD"}),"FOOD":self.response("FOOD")}
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
    def test_recipient_schema_rejects_global_and_unknown_country(self):
        for target in ("GLOBAL","UNKNOWN","世界"):
            bad=self.response("MIL","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"country","resource":"food","amount":10,"target_country":target})
            with self.assertRaises(ValueError):parse_country_json(json.dumps(bad),{"MIL","FOOD"})
    def test_world_pool_and_none_are_distinct(self):
        pool=self.response("MIL","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"world_pool","resource":"food","amount":10,"target_country":None})
        none=self.response("FOOD","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"none","resource":None,"amount":0,"target_country":None})
        parse_country_json(json.dumps(pool),{"MIL","FOOD"});parse_country_json(json.dumps(none),{"MIL","FOOD"})
        out=apply_structured_actions(self.states,{"MIL":pool,"FOOD":none},{"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30},0)
        self.assertEqual(out["world_pool"]["food"],10);self.assertEqual(out["country_states"]["MIL"]["resources"]["food"],58)
    def test_invalid_action_cannot_partially_apply_turn(self):
        before=json.loads(json.dumps(self.states));valid=self.response("MIL","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"country","resource":"food","amount":10,"target_country":"FOOD"});invalid=self.response("FOOD","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"country","resource":"food","amount":5,"target_country":"GLOBAL"})
        with self.assertRaises(ValueError):apply_structured_actions(self.states,{"MIL":valid,"FOOD":invalid},{"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30},0)
        self.assertEqual(self.states,before)
    def test_aborted_second_pilot_manifest_preserves_checkpoint(self):
        root=Path(__file__).parents[2];cp=root/"results/final/gemini-run-20260915-02.json.checkpoint";manifest=root/"results/final/gemini-run-20260915-02.audit.json";audit=json.loads(manifest.read_text())
        self.assertEqual(hashlib.sha256(cp.read_bytes()).hexdigest(),audit["checkpoint_sha256"]);self.assertEqual(audit["status"],"aborted");self.assertEqual(audit["stopped_at"],"turn_2_action_validation");self.assertFalse(audit["include_in_research_aggregation"]);self.assertFalse(audit["include_in_dashboard"])
    def test_world_pool_persists_and_distributes_without_creation(self):
        donate={"MIL":self.response("MIL","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"world_pool","resource":"food","amount":10,"target_country":None}),"FOOD":self.response("FOOD")};world={"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30}
        one=apply_structured_actions(self.states,donate,world,0,world_pool={})
        draw={"MIL":self.response("MIL"),"FOOD":self.response("FOOD","DRAW_WORLD_POOL","ACCEPT",{"recipient_type":"country","resource":"food","amount":6,"target_country":"FOOD"})}
        two=apply_structured_actions(one["country_states"],draw,one["true_world"],0,world_pool=one["world_pool"])
        self.assertEqual(two["world_pool"]["food"],4);self.assertEqual(two["country_states"]["FOOD"]["resources"]["food"],48)
        self.assertEqual(sum(x["resources"]["food"] for x in two["country_states"].values())+two["world_pool"]["food"],sum(x["resources"]["food"] for x in self.states.values()))
    def test_world_pool_overdraw_is_rejected_atomically(self):
        draw={"MIL":self.response("MIL"),"FOOD":self.response("FOOD","DRAW_WORLD_POOL","ACCEPT",{"recipient_type":"country","resource":"food","amount":6,"target_country":"FOOD"})};before=json.loads(json.dumps(self.states))
        with self.assertRaises(ValueError):apply_structured_actions(self.states,draw,{"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30},0,world_pool={"food":5})
        self.assertEqual(self.states,before)
    def test_funds_and_logistics_actions_change_recipient_state(self):
        answers={"MIL":self.response("MIL","SUPPORT_LOGISTICS","ACCEPT",{"recipient_type":"country","resource":"logistics","amount":5,"target_country":"FOOD"}),"FOOD":self.response("FOOD","PROVIDE_FUNDS","ACCEPT",{"recipient_type":"country","resource":"funds_economy","amount":4,"target_country":"MIL"})}
        out=apply_structured_actions(self.states,answers,{"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30},0,world_pool={})
        self.assertEqual(out["country_states"]["FOOD"]["resources"]["logistics"],79);self.assertEqual(out["country_states"]["MIL"]["resources"]["funds_economy"],88);self.assertGreater(out["country_states"]["FOOD"]["indicators"]["domestic_stability"],67);self.assertGreater(out["country_states"]["MIL"]["indicators"]["economy"],82)
    def test_econ_support_actions_share_world_pool_contract(self):
        for action,resource in (("SUPPORT_LOGISTICS","logistics"),("PROVIDE_FUNDS","funds_economy")):
            answer=self.response("MIL",action,"ACCEPT",{"recipient_type":"world_pool","target_country":None,"resource":resource,"amount":5})
            parse_country_json(json.dumps(answer),{"MIL","FOOD"})
            out=apply_structured_actions(self.states,{"MIL":answer,"FOOD":self.response("FOOD")},{"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30},0,world_pool={})
            self.assertEqual(out["world_pool"][resource],5)
    def test_all_agent_schemas_are_strict(self):
        for schema in (coordinator_response_schema(),country_response_schema(("MIL","FOOD")),evaluator_response_schema()):
            self.assertFalse(schema["additionalProperties"]);self.assertEqual(set(schema["required"]),set(schema["properties"]))
    def test_aborted_fifth_pilot_is_immutable_and_excluded(self):
        root=Path(__file__).parents[2];cp=root/"results/final/gemini-run-20260916-05.json.checkpoint";manifest=root/"results/final/gemini-run-20260916-05.audit.json";audit=json.loads(manifest.read_text())
        self.assertEqual(hashlib.sha256(cp.read_bytes()).hexdigest(),audit["checkpoint_sha256"]);self.assertEqual(audit["status"],"aborted");self.assertFalse(audit["include_in_research_aggregation"]);self.assertFalse(audit["include_in_dashboard"]);self.assertFalse(audit["resume_allowed"]);self.assertNotIn(cp.name,(root/"dashboard_final.html").read_text())
    def test_rejected_third_pilot_is_immutable_and_excluded(self):
        root=Path(__file__).parents[2];result=root/"results/final/gemini-run-20260915-03.json";manifest=root/"results/final/gemini-run-20260915-03.audit.json";audit=json.loads(manifest.read_text())
        self.assertEqual(hashlib.sha256(result.read_bytes()).hexdigest(),audit["result_sha256"]);self.assertEqual(audit["status"],"rejected");self.assertFalse(audit["include_in_research_aggregation"]);self.assertFalse(audit["include_in_dashboard"]);self.assertNotIn(result,eligible_result_paths(result.parent));self.assertNotIn(result.name,(root/"dashboard_final.html").read_text())
    def test_target_country_is_required_by_sdk_schema(self):
        schema=country_response_schema(("MIL","FOOD"));params=schema["properties"]["action"]["properties"]["parameters"]
        self.assertIn("target_country",params["required"]);self.assertEqual(params["properties"]["target_country"]["type"],["string","null"])
    def test_aborted_fourth_pilot_is_immutable_and_excluded(self):
        root=Path(__file__).parents[2];cp=root/"results/final/gemini-run-20260915-04.json.checkpoint";manifest=root/"results/final/gemini-run-20260915-04.audit.json";audit=json.loads(manifest.read_text())
        self.assertEqual(hashlib.sha256(cp.read_bytes()).hexdigest(),audit["checkpoint_sha256"]);self.assertEqual(audit["status"],"aborted");self.assertFalse(audit["include_in_research_aggregation"]);self.assertFalse(audit["include_in_dashboard"]);self.assertNotIn(cp.name,(root/"dashboard_final.html").read_text())
    def test_phase2_network_moves_resources_and_supply_stop_persists(self):
        network=ResourceNetwork(1,(SupplyLink("mil-food","MIL","FOOD","food",10,100,100,True),),{},("food",))
        accept={"MIL":self.response("MIL","NO_ACTION","ACCEPT"),"FOOD":self.response("FOOD")};world={"food":55,"energy":60,"economy":65,"environment":70,"international_trust":60,"conflict_load":30}
        moved=apply_structured_actions(self.states,accept,world,0,resource_network=network,world_pool={})
        self.assertEqual(moved["network_transfers"][0]["delivered"],10);self.assertEqual(moved["country_states"]["MIL"]["resources"]["food"],58);self.assertEqual(moved["country_states"]["FOOD"]["resources"]["food"],52)
        stopped={"MIL":self.response("MIL","SUSPEND_SUPPLY","ACCEPT"),"FOOD":self.response("FOOD")};halted=apply_structured_actions(self.states,stopped,world,0,resource_network=network,world_pool={})
        self.assertEqual(halted["network_transfers"][0]["delivered"],0);self.assertIn("MIL",halted["network_policy"]["suspended"])
        again=apply_structured_actions(self.states,accept,world,0,resource_network=network,world_pool={},network_policy=halted["network_policy"])
        self.assertEqual(again["network_transfers"][0]["delivered"],0)
    def test_invalid_target_does_not_regenerate_a_valid_replacement(self):
        valid=self.response("MIL","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"country","resource":"food","amount":5,"target_country":"FOOD"});invalid=json.loads(json.dumps(valid));invalid["action"]["parameters"]["target_country"]="GLOBAL"
        def R(x):return sdk_reply(json.dumps(x))
        class M:
            def __init__(self):self.payloads=[];self.configs=[]
            def generate_content(s,**kw):s.payloads.append(json.loads(kw["contents"]));s.configs.append(kw["config"]);return R(invalid if len(s.payloads)==1 else valid)
        client=type("C",(),{})();client.models=M();g=GeminiGateway(client,retry_limit=2,sleep_fn=lambda _:None)
        schema=country_response_schema(("MIL","FOOD"));help_data={"allowed_country_ids":["MIL","FOOD"],"correct_json_examples":{"country":{"recipient_type":"country","target_country":"FOOD","resource":"food","amount":5}}}
        with self.assertRaisesRegex(RuntimeError,"automatic regeneration is disabled"):
            g.call("MIL",1,1,{},lambda text:parse_country_json(text,{"MIL","FOOD"}),json_schema=schema,validation_help=help_data)
        self.assertEqual(len(client.models.payloads),1)
        self.assertNotIn("validation_feedback",client.models.payloads[0])
        self.assertIsNone(g.calls[0]["structured_response"])
        self.assertEqual(g.calls[0]["response_status"],"validation_failed")
        self.assertEqual(client.models.configs[0]["response_json_schema"],schema)
    def test_invalid_target_stops_on_first_received_response(self):
        invalid=self.response("MIL","PROVIDE_RESOURCE","ACCEPT",{"recipient_type":"country","resource":"food","amount":5,"target_country":"GLOBAL"})
        def R():return sdk_reply(json.dumps(invalid))
        class M:
            def generate_content(self,**kw):return R()
        client=type("C",(),{})();client.models=M();g=GeminiGateway(client,retry_limit=2,sleep_fn=lambda _:None)
        with self.assertRaises(RuntimeError):g.call("MIL",1,1,{},lambda text:parse_country_json(text,{"MIL","FOOD"}))
        self.assertEqual(len(g.calls),1)
        self.assertIs(g.calls[0]["automatic_regeneration"],False)

if __name__=='__main__':unittest.main()
