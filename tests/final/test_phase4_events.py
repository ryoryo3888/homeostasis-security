import unittest
from homeostasis_core.events import CausalEvent, EventLedger, EventRule, advance_events, farmland_recovery_history

class Phase4EventTests(unittest.TestCase):
    def setUp(self):
        self.event=CausalEvent("missile","farmland_damage",0,5,80,20,(),("B",),{"food":80})
        self.rules=(EventRule("food","farmland_damage","import_demand",10,0,2,50),)
    def test_five_turn_recovery_history(self): self.assertEqual(farmland_recovery_history(),(8000,6000,4000,2000,0))
    def test_causal_generation(self):
        out=advance_events(EventLedger(0,(self.event,)),self.rules)
        generated=[e for e in out.active_events if e.event_id!="missile"][0]
        self.assertEqual(generated.cause_event_ids,("missile",))
    def test_no_self_reference(self):
        with self.assertRaises(ValueError): CausalEvent("x","x",0,1,1,1,("x",),("B",),{})
    def test_duplicate_event_rejected(self):
        with self.assertRaises(ValueError): EventLedger(0,(self.event,self.event))
    def test_bounded_generation_and_cooldown(self):
        rules=tuple(EventRule(str(i),"farmland_damage",f"e{i}",0,5,1,10) for i in range(5))
        self.assertEqual(len(advance_events(EventLedger(0,(self.event,)),rules,max_generated_per_turn=2).active_events),3)
    def test_deterministic_and_order_independent(self):
        r2=EventRule("z","farmland_damage","z-event",0,0,1,10)
        a=advance_events(EventLedger(0,(self.event,)),self.rules+(r2,))
        b=advance_events(EventLedger(0,(self.event,)),tuple(reversed(self.rules+(r2,))))
        self.assertEqual(a,b)
    def test_input_not_mutated(self):
        ledger=EventLedger(0,(self.event,)); before=ledger.to_dict(); advance_events(ledger,self.rules); self.assertEqual(before,ledger.to_dict())
    def test_invalid_bool_rejected(self):
        with self.assertRaises(ValueError): EventRule("r","a","b",True,0,1,1)

if __name__=='__main__': unittest.main()
