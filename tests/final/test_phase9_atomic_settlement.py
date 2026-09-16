import copy,hashlib,json,math,random,unittest
from pathlib import Path

from homeostasis_core.feasibility import settle_atomic_actions
from homeostasis_core.gemini_agents import eligible_result_paths,pilot_is_eligible
from homeostasis_core.resources import RESOURCE_TYPES

class AtomicSettlementTests(unittest.TestCase):
    def setUp(self):
        resources={r:50.0 for r in RESOURCE_TYPES};self.states={c:{"resources":copy.deepcopy(resources)} for c in ("A","B","C")}
    def action(self,kind,recipient,target,resource,amount):
        return {"action_id":kind,"description":"x","parameters":{"recipient_type":recipient,"target_country":target,"resource":resource,"amount":amount}}
    def test_115_requested_from_100_pool_is_proportional(self):
        self.states["C"]["resources"]["food"]=0;intents={"A":self.action("DRAW_WORLD_POOL","country","C","food",60),"B":self.action("DRAW_WORLD_POOL","country","C","food",55)}
        out=settle_atomic_actions(self.states,intents,{"food":100});rows=out["settlements"]
        self.assertAlmostEqual(sum(x["realized"] for x in rows),100);self.assertAlmostEqual(rows[0]["realized"]/rows[1]["realized"],60/55);self.assertAlmostEqual(out["world_pool"]["food"],0);self.assertAlmostEqual(out["country_states"]["C"]["resources"]["food"],100)
        self.assertAlmostEqual(sum(x["unmet"] for x in rows),15)
    def test_70_contribution_with_insufficient_pool_room(self):
        intents={"A":self.action("PROVIDE_RESOURCE","world_pool",None,"food",40),"B":self.action("PROVIDE_RESOURCE","world_pool",None,"food",30)}
        out=settle_atomic_actions(self.states,intents,{"food":50});rows=out["settlements"]
        self.assertAlmostEqual(sum(x["realized"] for x in rows),50);self.assertAlmostEqual(sum(x["unmet"] for x in rows),20);self.assertEqual(out["world_pool"]["food"],100)
    def test_same_turn_contribution_cannot_fund_draw(self):
        self.states["C"]["resources"]["food"]=0;intents={"A":self.action("PROVIDE_RESOURCE","world_pool",None,"food",30),"B":self.action("DRAW_WORLD_POOL","country","C","food",30)}
        out=settle_atomic_actions(self.states,intents,{"food":0});by_agent={x["agent_id"]:x for x in out["settlements"]}
        self.assertEqual(by_agent["B"]["realized"],0);self.assertEqual(by_agent["B"]["unmet"],30);self.assertEqual(out["world_pool"]["food"],30)
    def test_multiple_resources_fractional_and_zero(self):
        self.states["C"]["resources"]["food"]=0;self.states["C"]["resources"]["funds_economy"]=0
        intents={"A":self.action("DRAW_WORLD_POOL","country","C","food",7.25),"B":self.action("DRAW_WORLD_POOL","country","C","funds_economy",5.5)}
        out=settle_atomic_actions(self.states,intents,{"food":4.5,"funds_economy":0})
        rows={x["resource"]:x for x in out["settlements"]};self.assertEqual(rows["food"]["realized"],4.5);self.assertEqual(rows["funds_economy"]["realized"],0);self.assertEqual(rows["funds_economy"]["unmet"],5.5)
    def test_conservation_and_order_independence_seeded_property(self):
        rng=random.Random(20260916)
        for _ in range(200):
            pool={r:rng.uniform(0,100) for r in RESOURCE_TYPES};states=copy.deepcopy(self.states);states["C"]["resources"]={r:0 for r in RESOURCE_TYPES}
            intents={"A":self.action("DRAW_WORLD_POOL","country","C","food",rng.uniform(0.01,100)),"B":self.action("DRAW_WORLD_POOL","country","C","food",rng.uniform(0.01,100))}
            reverse=dict(reversed(list(intents.items())));one=settle_atomic_actions(states,intents,pool);two=settle_atomic_actions(states,reverse,pool)
            self.assertEqual(one,two)
            before=math.fsum(s["resources"]["food"] for s in states.values())+pool["food"];after=math.fsum(s["resources"]["food"] for s in one["country_states"].values())+one["world_pool"]["food"]
            self.assertAlmostEqual(before,after,places=8)
    def test_aborted_seventh_pilot_is_immutable_and_excluded(self):
        root=Path(__file__).parents[2];cp=root/"results/final/gemini-run-20260916-07.json.checkpoint";manifest=root/"results/final/gemini-run-20260916-07.audit.json";audit=json.loads(manifest.read_text())
        self.assertEqual(hashlib.sha256(cp.read_bytes()).hexdigest(),audit["checkpoint_sha256"]);self.assertEqual(audit["status"],"aborted");self.assertFalse(audit["include_in_research_aggregation"]);self.assertFalse(audit["include_in_dashboard"]);self.assertFalse(audit["resume_allowed"]);self.assertFalse(pilot_is_eligible(cp,manifest));self.assertNotIn(cp,eligible_result_paths(cp.parent))

if __name__=="__main__":unittest.main()
