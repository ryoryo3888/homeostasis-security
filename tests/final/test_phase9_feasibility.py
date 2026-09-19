import copy,hashlib,json,random,unittest
from pathlib import Path

from homeostasis_core.feasibility import feasible_actions,validate_action_feasible
from homeostasis_core.gemini_agents import apply_structured_actions,country_response_schema,pilot_is_eligible
from homeostasis_core.resources import ResourceNetwork,SupplyLink

class FeasibilityTests(unittest.TestCase):
    def setUp(self):
        base={"archetype":"x","sovereignty":80,"indicators":{"food_reserves":50,"energy_stability":50,"economy":50,"military_security":50,"domestic_stability":50,"recovery_capacity":50,"international_trust":50,"diplomatic_posture":50},"resources":{"food":50,"fossil_fuel":50,"renewable_energy":50,"nuclear":50,"grid_storage_resilience":50,"funds_economy":50,"logistics":50},"energy_portfolio":{"sources":{"fossil_fuel":34,"renewable_energy":33,"nuclear":33},"import_dependency":50}}
        self.states={"A":copy.deepcopy(base),"B":copy.deepcopy(base)}
        self.network=ResourceNetwork(1,(SupplyLink("ab-food","A","B","food",20,100,100,True),SupplyLink("ab-logistics","A","B","logistics",20,100,100,True)),{},("food","logistics"))
    def options(self,c="A",pool=None,policy=None,network=None):
        return feasible_actions(c,self.states,pool or {},self.network if network is None else network,policy or {})
    def test_empty_pool_never_offers_draw(self):
        self.assertNotIn("DRAW_WORLD_POOL",{x["action_id"] for x in self.options(pool={"food":0})})
    def test_pool_balance_and_receiver_headroom_bound_draw(self):
        choices=feasible_actions("A",self.states,{"food":7},self.network,{})
        draws=[x for x in choices if x["action_id"]=="DRAW_WORLD_POOL" and x["resource"]=="food"]
        self.assertEqual(draws[0]["maximum_amount"],7)
        action={"action_id":"DRAW_WORLD_POOL","parameters":{"recipient_type":"country","target_country":"B","resource":"food","amount":8}}
        with self.assertRaises(ValueError):validate_action_feasible("A",action,choices)
    def test_stock_logistics_route_and_stops_control_transfer(self):
        self.states["A"]["resources"]["food"]=3
        choices=self.options();food=[x for x in choices if x["action_id"]=="PROVIDE_RESOURCE" and x["recipient_type"]=="country" and x["resource"]=="food"]
        self.assertEqual(food[0]["maximum_amount"],3)
        self.states["A"]["resources"]["logistics"]=0
        self.assertFalse([x for x in self.options() if x["action_id"] in ("PROVIDE_RESOURCE","SUPPORT_LOGISTICS","PROVIDE_FUNDS") and x["maximum_amount"]>0])
        self.states["A"]["resources"]["logistics"]=50
        self.assertFalse([x for x in self.options(policy={"suspended":["A"]}) if x["recipient_type"]=="country"])
    def test_self_transfer_nonpositive_unknown_and_overage_rejected(self):
        choices=self.options()
        for target,amount in (("A",1),("UNKNOWN",1),("B",0),("B",21)):
            action={"action_id":"PROVIDE_RESOURCE","parameters":{"recipient_type":"country","target_country":target,"resource":"food","amount":amount}}
            with self.assertRaises(ValueError):validate_action_feasible("A",action,choices)
    def test_dynamic_schema_contains_only_current_action_ids(self):
        ids=sorted({x["action_id"] for x in self.options(pool={})})
        schema=country_response_schema(("A","B"),ids)
        self.assertEqual(schema["properties"]["action"]["properties"]["action_id"]["enum"],ids)
        self.assertNotIn("DRAW_WORLD_POOL",ids)
    def test_state_matrix_and_seeded_properties(self):
        rng=random.Random(20260916)
        for _ in range(200):
            stock=rng.uniform(0,100);logistics=rng.uniform(0,100);pool=rng.uniform(0,100);capacity=rng.uniform(0,100);reliability=rng.uniform(0,100)
            states=copy.deepcopy(self.states);states["A"]["resources"]["food"]=stock;states["A"]["resources"]["logistics"]=logistics
            network=ResourceNetwork(1,(SupplyLink("r","A","B","food",20,capacity,reliability,True),),{},("food",))
            choices=feasible_actions("A",states,{"food":pool},network,{})
            for choice in choices:
                self.assertGreaterEqual(choice["maximum_amount"],0);self.assertLessEqual(choice["maximum_amount"],100)
                if choice["target_country"] is not None and choice["action_id"]!="DRAW_WORLD_POOL":self.assertNotEqual(choice["target_country"],"A")
                if choice["maximum_amount"]>0:
                    action={"action_id":choice["action_id"],"parameters":{"recipient_type":choice["recipient_type"],"target_country":choice["target_country"],"resource":choice["resource"],"amount":choice["maximum_amount"]}}
                    self.assertTrue(validate_action_feasible("A",action,choices))
    def test_apply_revalidates_without_mutating_on_violation(self):
        before=copy.deepcopy(self.states)
        answer={"country_id":"A","proposal_id":"p","response_id":"ACCEPT","response_label":"受け入れる","reason":"r","conditions":{},"self_interest":50,"sovereignty_burden":1,"perceived_global_effect":50,"action_requires_participation":True,"action":{"action_id":"DRAW_WORLD_POOL","description":"x","parameters":{"recipient_type":"country","target_country":"B","resource":"food","amount":1}}}
        reject=copy.deepcopy(answer);reject["country_id"]="B";reject["response_id"]="REJECT";reject["response_label"]="拒否する";reject["action"]={"action_id":"NO_ACTION","description":"x","parameters":{"recipient_type":"none","target_country":None,"resource":None,"amount":0}}
        with self.assertRaises(ValueError):apply_structured_actions(self.states,{"A":answer,"B":reject},{"food":50,"energy":50,"economy":50,"environment":50,"international_trust":50,"conflict_load":50},0,world_pool={},resource_network=self.network)
        self.assertEqual(self.states,before)
    def test_aborted_sixth_pilot_is_immutable_and_excluded(self):
        root=Path(__file__).parents[2];cp=root/"results/final/gemini-run-20260916-06.json.checkpoint";manifest=root/"results/final/gemini-run-20260916-06.audit.json";audit=json.loads(manifest.read_text())
        self.assertEqual(hashlib.sha256(cp.read_bytes()).hexdigest(),audit["checkpoint_sha256"]);self.assertEqual(audit["status"],"aborted");self.assertFalse(audit["include_in_research_aggregation"]);self.assertFalse(audit["include_in_dashboard"]);self.assertFalse(audit["resume_allowed"]);self.assertFalse(pilot_is_eligible(cp,manifest))

if __name__=="__main__":unittest.main()
