import unittest
from homeostasis_core.governance import *
class Phase7Tests(unittest.TestCase):
    def setUp(self):
        self.rules=GovernanceRuleSet(1,0,{"approval_threshold":60,"veto":True})
        self.p=RuleChangeProposal("c1","voting_rule","need resilience",("A","B","C"),{"approval_threshold":50},1)
    def votes(self,choices=("accept","accept","reject")):return {c:GovernanceVote(c,"c1",v) for c,v in zip("ABC",choices)}
    def test_old_rule_decides_and_next_turn_applies(self):
        out,rec=decide_rule_change(self.rules,self.p,self.votes(),1);self.assertEqual(rec.basis_version,1);self.assertEqual(out.effective_turn,2);self.assertEqual(out.rules["approval_threshold"],50)
    def test_rejection_not_forced_and_recorded(self):
        out,rec=decide_rule_change(self.rules,self.p,self.votes(("accept","reject","reject")),1);self.assertEqual(out,self.rules);self.assertEqual(rec.status,"rejected")
    def test_conditional_unmet_not_counted(self):
        v=self.votes();v["B"]=GovernanceVote("B","c1","conditional",False);out,_=decide_rule_change(self.rules,self.p,v,1);self.assertEqual(out,self.rules)
    def test_duplicate_apply_rejected(self):
        out,_=decide_rule_change(self.rules,self.p,self.votes(),1)
        with self.assertRaises(ValueError):decide_rule_change(out,self.p,self.votes(),2)
    def test_emergency_requires_duration_and_expires(self):
        with self.assertRaises(ValueError):RuleChangeProposal("e","emergency_authority","x",("A",),{"power":True},0)
        p=RuleChangeProposal("e","emergency_authority","x",("A",),{"power":True},0,2,"stability")
        r=GovernanceRuleSet(2,1,{"approval_threshold":50,"power":True},("e",));self.assertNotIn("power",expire_emergency_rules(r,p,2).rules)
    def test_no_retroactive_mutation(self):
        before=self.rules.to_dict();decide_rule_change(self.rules,self.p,self.votes(),1);self.assertEqual(before,self.rules.to_dict())
    def test_vote_identity_and_missing_rejected(self):
        with self.assertRaises(ValueError):decide_rule_change(self.rules,self.p,{"A":GovernanceVote("A","c1","accept")},1)
    def test_bool_threshold_rejected(self):
        with self.assertRaises(ValueError):GovernanceRuleSet(1,0,{"approval_threshold":True})
    def test_authority_burden_affects_sovereignty_only_when_established(self):
        p=RuleChangeProposal("e","emergency_authority","x",("A",),{"power":True},0,2,"stable",30)
        self.assertEqual(governance_sovereignty_maintenance(p,True),70);self.assertEqual(governance_sovereignty_maintenance(p,False),100)
if __name__=='__main__':unittest.main()
