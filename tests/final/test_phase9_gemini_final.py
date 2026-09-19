import json,subprocess,tempfile,unittest
from pathlib import Path
from final_experiment_runner import estimate,run_live
from homeostasis_core.gemini_agents import GeminiGateway,parse_country_json,run_gemini_turn

class Usage:
    prompt_token_count=10;candidates_token_count=5;total_token_count=15
class Response:
    def __init__(self,text):self.text=text;self.usage_metadata=Usage()
class Models:
    def __init__(self,invalid=False):self.payloads=[];self.invalid=invalid
    def generate_content(self,**kw):
        data=json.loads(kw["contents"]);self.payloads.append(data)
        if self.invalid:return Response("{}")
        if "observable_world" in data:return Response(json.dumps({"proposal_id":"proposal-1","proposal_type":"食料援助","reason":"r","predicted_global_effect":60,"predicted_sovereignty_burden":5,"requested_action":"cooperate"}))
        if "executed_true_state" in data:return Response(json.dumps({"national_sovereignty":80,"global_homeostasis":75,"resource_stability":70,"resilience":72,"conflict_load":20,"history_effect":30,"assessment":"stable"}))
        return Response(json.dumps({"country_id":data["turn_start_observation"]["own_country"],"proposal_id":data["current_proposal"]["proposal_id"],"response_id":"ACCEPT","response_label":"受け入れる","reason":"r","conditions":{},"self_interest":60,"sovereignty_burden":5,"perceived_global_effect":60,"action":{"action_id":"MEDIATE","description":"mediate","parameters":{"recipient_type":"none","target_country":None,"resource":None,"amount":0}}}))
class Client:
    def __init__(self,invalid=False):self.models=Models(invalid)
class InterruptingModels(Models):
    def __init__(self,fail_at):super().__init__();self.fail_at=fail_at
    def generate_content(self,**kw):
        if len(self.payloads)==self.fail_at:
            self.payloads.append(json.loads(kw["contents"]));raise KeyboardInterrupt("simulated interruption")
        return super().generate_content(**kw)
class InterruptingClient:
    def __init__(self,fail_at):self.models=InterruptingModels(fail_at)

class GeminiFinalTests(unittest.TestCase):
    def test_dry_run_call_estimates(self):
        self.assertEqual(estimate(1)["planned_api_calls"],80);self.assertEqual(estimate(36)["planned_api_calls"],2880);self.assertEqual(estimate(36)["maximum_api_attempts"],8640)
    def test_run_limit(self):
        with self.assertRaises(ValueError):estimate(37)
    def test_invalid_json_stops_without_regeneration(self):
        g=GeminiGateway(Client(True),max_calls=3,retry_limit=3,sleep_fn=lambda _:None)
        with self.assertRaises(RuntimeError):g.call("MIL",1,1,{},parse_country_json)
        self.assertEqual(len(g.calls),1)
        self.assertEqual(len(g.client.models.payloads),1)
        self.assertEqual(g.calls[0]["response_status"],"validation_failed")
        self.assertIs(g.calls[0]["automatic_regeneration"],False)
    def test_structured_conditions_reject_bool_and_identity_mismatch(self):
        invalid={"country_id":"A","proposal_id":"p","response_id":"CONDITIONAL","response_label":"条件付きで応じる","reason":"r","conditions":{"minimum_aid_amount":True},"self_interest":50,"sovereignty_burden":5,"perceived_global_effect":50,"action":{"action_id":"NO_ACTION","description":"none","parameters":{"recipient_type":"none","target_country":None,"resource":None,"amount":0}}}
        with self.assertRaises(ValueError):parse_country_json(json.dumps(invalid))
        class WrongModels(Models):
            def generate_content(self,**kw):
                response=super().generate_content(**kw)
                data=json.loads(kw["contents"])
                if "turn_start_observation" in data:
                    value=json.loads(response.text);value["country_id"]="WRONG";return Response(json.dumps(value))
                return response
        g=GeminiGateway(type("WrongClient",(),{"models":WrongModels()})(),max_calls=10)
        with self.assertRaises(RuntimeError):run_gemini_turn(g,1,1,{"world":{"food":70}},{"A":{"own_country":"A","observed_world":{"food":70}}},{"A":()},("A",))
    def test_same_turn_country_snapshots_are_isolated_and_equal(self):
        client=Client();g=GeminiGateway(client,max_calls=10);countries=("A","B")
        views={c:{"turn":1,"observed_world":{"food":70},"own_country":c} for c in countries}
        out=run_gemini_turn(g,1,1,{"world":{"food":70}},views,{c:() for c in countries},countries)
        country_payloads=[p for p in client.models.payloads if "turn_start_observation" in p]
        self.assertEqual([p["turn_start_observation"]["observed_world"] for p in country_payloads],[{"food":70},{"food":70}]);self.assertEqual(set(out["country_responses"]),set(countries))
        self.assertTrue(all("country_responses" not in p for p in country_payloads))
        self.assertEqual(len(country_payloads),2)
        self.assertTrue(out["response_convergence"])
    def test_call_audit_has_no_prompt_or_secret(self):
        class StaticModels:
            def generate_content(self,**kw):return Response(json.dumps({"country_id":"MIL","proposal_id":"p","response_id":"ACCEPT","response_label":"受け入れる","reason":"r","conditions":{},"self_interest":60,"sovereignty_burden":5,"perceived_global_effect":60,"action":{"action_id":"NO_ACTION","description":"none","parameters":{"recipient_type":"none","target_country":None,"resource":None,"amount":0}}}))
        g=GeminiGateway(type("StaticClient",(),{"models":StaticModels()})(),max_calls=1);g.call("MIL",1,1,{"private":"x"},parse_country_json)
        self.assertNotIn("GEMINI_API_KEY",json.dumps(g.calls[0]));self.assertEqual(g.calls[0]["token_usage"]["total_tokens"],15)
    def test_existing_output_stops_before_api(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.json";p.write_text("old");c=Client()
            with self.assertRaises(FileExistsError):run_live(c,p,1,1)
            self.assertEqual(c.models.payloads,[]);self.assertEqual(p.read_text(),"old")
    def test_checkpoint_requires_explicit_resume(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.json";p.with_suffix(".json.checkpoint").write_text('{"completed_runs":[]}');c=Client()
            with self.assertRaises(FileExistsError):run_live(c,p,1,1,False)
            self.assertEqual(c.models.payloads,[])
    def test_explicit_resume_from_empty_checkpoint_completes_eight_turns(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.json";p.with_suffix(".json.checkpoint").write_text('{"completed_runs":[]}');c=Client()
            result=run_live(c,p,1,7,True)
            run=result["runs"][0];self.assertEqual(len(run["turns"]),8);self.assertEqual(len(run["call_audit"]),80);self.assertEqual(run["token_usage"]["total_tokens"],1200);self.assertTrue(p.exists());self.assertFalse(p.with_suffix(".json.checkpoint").exists())
            first=[x for x in run["call_audit"] if x["turn"]==1 and x["agent_type"]=="country"]
            self.assertEqual(len({x["snapshot_id"] for x in first}),1);self.assertEqual(len({x["agent_archetype"] for x in first}),8)
            for audit in first:
                own=audit["agent_id"];payload=audit["public_observation_payload"];self.assertEqual(payload["turn_start_observation"]["own_country"],own);self.assertNotIn("country_responses",payload)
            self.assertNotEqual(run["turns"][0]["research_metrics"]["global_homeostasis"],run["turns"][0]["evaluator_commentary"]["global_homeostasis"])
    def test_resume_refuses_attempted_uncommitted_turn(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.json";first=InterruptingClient(20)
            with self.assertRaises(KeyboardInterrupt):run_live(first,p,1,7)
            checkpoint=json.loads(p.with_suffix(".json.checkpoint").read_text())
            self.assertEqual(checkpoint["active_run"]["completed_turn"],2)
            original=p.with_suffix(".json.checkpoint").read_bytes()
            second=Client()
            with self.assertRaisesRegex(ValueError,"RESUME_UNCOMMITTED_DECISION"):
                run_live(second,p,1,7,True)
            self.assertEqual(second.models.payloads,[])
            self.assertEqual(p.with_suffix(".json.checkpoint").read_bytes(),original)
            self.assertFalse(p.exists())
    def test_cli_defaults_to_dry_run_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.json";out=subprocess.check_output(["python3","-B","final_experiment_runner.py","--output",str(p)],text=True)
            self.assertIn('"mode": "dry-run"',out);self.assertFalse(p.exists())
if __name__=='__main__':unittest.main()
