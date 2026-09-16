import hashlib,json,unittest
from pathlib import Path

from homeostasis_core.gemini_agents import decision_factors,derive_event,event_candidates,ordered_feasible_actions,ordered_response_options,pilot_is_eligible

class DecisionDiversityTests(unittest.TestCase):
    def view(self,sovereignty=50,diplomacy=50,stability=50,trust=50,security=50,resources=50,conflict=50):
        return {"own_state":{"sovereignty_sense":sovereignty,"diplomatic_posture":diplomacy,"domestic_stability":stability,"international_trust":trust,"military_security":security,"resources":{"food":resources,"logistics":resources}},"observed_world":{"conflict_load":conflict}}
    def proposal(self,benefit=50,cost=50):return {"predicted_global_effect":benefit,"predicted_sovereignty_burden":cost}
    def test_accept_reject_and_conditional_have_distinct_state_rationales(self):
        aid_dependent=decision_factors(self.view(35,85,25,80,45,15,60),self.proposal(90,15),[])
        sovereignty_hawk=decision_factors(self.view(98,20,80,25,90,80,70),self.proposal(35,90),[])
        cautious=decision_factors(self.view(80,60,45,55,55,40,55),self.proposal(70,60),[{"response_id":"REJECT"}])
        self.assertGreater(aid_dependent["proposal_expected_benefit"],aid_dependent["proposal_sovereignty_cost"])
        self.assertGreater(sovereignty_hawk["proposal_sovereignty_cost"],sovereignty_hawk["proposal_expected_benefit"])
        self.assertGreater(cautious["sovereignty_priority"],50);self.assertGreater(cautious["proposal_expected_benefit"],50)
        self.assertNotEqual(aid_dependent,sovereignty_hawk);self.assertNotEqual(cautious,aid_dependent)
    def test_seeded_order_is_input_order_independent(self):
        actions=[{"action_id":x,"recipient_type":"none","target_country":None,"resource":None,"maximum_amount":0} for x in ("MEDIATE","NO_ACTION","PROTECT_RESERVES","DEFENSIVE_ESCORT")]
        self.assertEqual(ordered_feasible_actions(actions,7,3,"MIL"),ordered_feasible_actions(list(reversed(actions)),7,3,"MIL"))
    def test_seeded_order_does_not_keep_one_action_first(self):
        actions=[{"action_id":x,"recipient_type":"none","target_country":None,"resource":None,"maximum_amount":0} for x in ("MEDIATE","NO_ACTION","PROTECT_RESERVES","DEFENSIVE_ESCORT","SUPPORT_LOGISTICS")]
        first={ordered_feasible_actions(actions,20260915,t,c)[0]["action_id"] for t in range(1,9) for c in ("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")}
        self.assertGreaterEqual(len(first),4)
        response_first={ordered_response_options(20260915,t,c)[0] for t in range(1,9) for c in ("MIL","RES","FOOD","SMALL","ISLAND","ECON","FRAGILE","NEUTRAL")}
        self.assertEqual(response_first,{"ACCEPT","REJECT","CONDITIONAL"})
    def test_event_candidates_differ_by_world_pressure(self):
        history={"reserve_gap":10,"economic_loss":10,"trust_loss":10,"alertness":10,"unmet_resource_demand":0}
        food=event_candidates({"food":20,"energy":80,"economy":80,"environment":80,"international_trust":80,"conflict_load":10},history,{})
        energy=event_candidates({"food":80,"energy":20,"economy":80,"environment":80,"international_trust":80,"conflict_load":10},history,{})
        conflict=event_candidates({"food":80,"energy":80,"economy":80,"environment":80,"international_trust":80,"conflict_load":90},history,{})
        self.assertEqual(food[0]["event"],"食料不足と価格圧力");self.assertEqual(energy[0]["event"],"エネルギー供給不安");self.assertEqual(conflict[0]["event"],"安全保障摩擦")
    def test_cooldown_suppresses_immediate_duplicate(self):
        world={"food":20,"energy":50,"economy":50,"environment":80,"international_trust":80,"conflict_load":10};history={"reserve_gap":50,"economic_loss":50,"trust_loss":0,"alertness":10,"unmet_resource_demand":20}
        first=derive_event(world,history,{},[]);second=derive_event(world,history,{},[first]);third=derive_event(world,history,{},[first,second])
        self.assertNotEqual(first,second);self.assertNotIn(third,(first,second))
    def test_full_pool_does_not_offer_more_contribution_pressure(self):
        from homeostasis_core.feasibility import feasible_actions
        from homeostasis_core.resources import ResourceNetwork,SupplyLink
        resources={r:50 for r in ("food","fossil_fuel","renewable_energy","nuclear","grid_storage_resilience","funds_economy","logistics")};states={"A":{"resources":dict(resources)},"B":{"resources":dict(resources)}};network=ResourceNetwork(1,(SupplyLink("x","A","B","food",10,100,100,True),),{},("food",))
        choices=feasible_actions("A",states,{"food":100},network,{})
        self.assertFalse([x for x in choices if x["recipient_type"]=="world_pool" and x["resource"]=="food"])
    def test_rejected_eighth_pilot_is_immutable_and_excluded(self):
        root=Path(__file__).parents[2];result=root/"results/final/gemini-run-20260916-08.json";manifest=root/"results/final/gemini-run-20260916-08.audit.json";audit=json.loads(manifest.read_text())
        self.assertEqual(hashlib.sha256(result.read_bytes()).hexdigest(),audit["result_sha256"]);self.assertEqual(audit["status"],"rejected");self.assertFalse(audit["include_in_research_aggregation"]);self.assertFalse(audit["include_in_dashboard"]);self.assertFalse(pilot_is_eligible(result,manifest))

if __name__=="__main__":unittest.main()
