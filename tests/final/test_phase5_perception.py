import unittest
from homeostasis_core.perception import *
from tests.final.test_phase3_coordination import fixture_world
from homeostasis_core.models import WorldState

class Phase5Tests(unittest.TestCase):
    def histories(self):
        _,w=fixture_world(); return tuple(WorldState(i,{**w.indicators,"food":70+i},w.countries,global_homeostasis=w.global_homeostasis) for i in range(3))
    def policies(self,order=("S","T","N")):
        return {c:InformationPolicy(c,{"S":0,"T":1,"N":2}[c],80,("food",),{"food":50}) for c in order}
    def test_delay_prevents_future_leak(self):
        m=observe_world(self.histories(),self.policies()); self.assertEqual((m["S"].observed_turn,m["T"].observed_turn,m["N"].observed_turn),(2,1,0))
    def test_bias_and_error(self):
        p=self.policies(); p["S"]=InformationPolicy("S",0,80,("food",),{"food":60}); m=observe_world(self.histories(),p); self.assertEqual(m["S"].observed_world["food"],82); self.assertEqual(m["S"].perception_error["food"],10)
    def test_order_independent(self): self.assertEqual(observe_world(self.histories(),self.policies()),observe_world(self.histories(),self.policies(("N","T","S"))))
    def test_input_immutable(self):
        h=self.histories(); before=[x.to_dict() for x in h]; observe_world(h,self.policies()); self.assertEqual(before,[x.to_dict() for x in h])
    def test_policy_country_set_required(self):
        with self.assertRaises(ValueError): observe_world(self.histories(),{"S":self.policies()["S"]})
    def test_decision_uses_memory_and_is_repeatable(self):
        profiles,w=fixture_world(); m=observe_world(self.histories(),self.policies())["S"]; p=DeterministicDecisionProvider(); self.assertEqual(p.decide(profiles["S"],w.countries["S"],m),p.decide(profiles["S"],w.countries["S"],m))
    def test_memory_persists(self):
        old=CountryMemory("S",0,{"food":1},{"food":0},50,("damage",),("reject",)); m=observe_world(self.histories(),self.policies(),{"S":old}); self.assertEqual(m["S"].decision_history,("reject",))
    def test_recovery_is_bounded(self):
        _,w=fixture_world(); out=recover_country(w.countries["S"],100); self.assertTrue(all(0<=v<=100 for v in out.indicators.values()))
    def test_bool_rejected(self):
        with self.assertRaises(ValueError): InformationPolicy("S",True,50,("food",),{})

if __name__=='__main__': unittest.main()
