import json,subprocess,tempfile,unittest
from pathlib import Path
from final_experiment_runner import estimate,run_live
from homeostasis_core.gemini_agents import GeminiGateway,parse_country_json,run_gemini_turn

class Response:
    def __init__(self,text):self.text=text
class Models:
    def __init__(self,invalid=False):self.payloads=[];self.invalid=invalid
    def generate_content(self,**kw):
        data=json.loads(kw["contents"]);self.payloads.append(data)
        if self.invalid:return Response("{}")
        if "observable_world" in data:return Response(json.dumps({"proposal_id":"proposal-1","proposal_type":"食料援助","reason":"r","predicted_global_effect":60,"predicted_sovereignty_burden":5,"requested_action":"cooperate"}))
        if "executed_world" in data:return Response(json.dumps({"national_sovereignty":80,"global_homeostasis":75,"resource_stability":70,"resilience":72,"conflict_load":20,"history_effect":30,"assessment":"stable"}))
        return Response(json.dumps({"country_id":data["turn_start_observation"]["own_country"],"proposal_id":data["current_proposal"]["proposal_id"],"response":"受け入れる","reason":"r","conditions":{},"self_interest":60,"sovereignty_burden":5,"perceived_global_effect":60,"policy_action":"cooperate"}))
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
    def test_invalid_json_stops_after_bounded_retries(self):
        g=GeminiGateway(Client(True),max_calls=3,retry_limit=3,sleep_fn=lambda _:None)
        with self.assertRaises(RuntimeError):g.call("MIL",1,1,{},parse_country_json)
        self.assertEqual(len(g.calls),3)
    def test_structured_conditions_reject_bool_and_identity_mismatch(self):
        invalid={"country_id":"A","proposal_id":"p","response":"条件付きで応じる","reason":"r","conditions":{"minimum_aid_amount":True},"self_interest":50,"sovereignty_burden":5,"perceived_global_effect":50,"policy_action":"cooperate"}
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
        evaluator_payload=[p for p in client.models.payloads if "executed_world" in p][0]
        self.assertIn("participation_ratio",evaluator_payload["executed_world"])
    def test_call_audit_has_no_prompt_or_secret(self):
        class StaticModels:
            def generate_content(self,**kw):return Response(json.dumps({"country_id":"MIL","proposal_id":"p","response":"受け入れる","reason":"r","conditions":{},"self_interest":60,"sovereignty_burden":5,"perceived_global_effect":60,"policy_action":"cooperate"}))
        g=GeminiGateway(type("StaticClient",(),{"models":StaticModels()})(),max_calls=1);g.call("MIL",1,1,{"private":"x"},parse_country_json)
        self.assertEqual(set(g.calls[0]),{"agent","run","turn","attempt","model"})
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
            self.assertEqual(len(result["runs"][0]["turns"]),8);self.assertEqual(len(result["runs"][0]["call_audit"]),80);self.assertTrue(p.exists());self.assertFalse(p.with_suffix(".json.checkpoint").exists())
    def test_resume_continues_after_last_completed_turn(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.json";first=InterruptingClient(20)
            with self.assertRaises(KeyboardInterrupt):run_live(first,p,1,7)
            checkpoint=json.loads(p.with_suffix(".json.checkpoint").read_text())
            self.assertEqual(checkpoint["active_run"]["completed_turn"],2)
            second=Client();result=run_live(second,p,1,7,True)
            self.assertEqual(len(result["runs"][0]["turns"]),8)
            self.assertEqual(len(second.models.payloads),60)
            self.assertEqual(len(result["runs"][0]["call_audit"]),81)
            self.assertEqual(result["runs"][0]["call_audit"][20]["turn"],3)
    def test_cli_defaults_to_dry_run_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x.json";out=subprocess.check_output(["python3","-B","final_experiment_runner.py","--output",str(p)],text=True)
            self.assertIn('"mode": "dry-run"',out);self.assertFalse(p.exists())
if __name__=='__main__':unittest.main()
