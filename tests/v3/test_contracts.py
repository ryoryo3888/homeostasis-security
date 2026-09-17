"""Synthetic contract records only: no simulation, model, or generated research."""
import copy
from dataclasses import FrozenInstanceError
import unittest
from jsonschema import ValidationError
from homeostasis_v3.contracts import (
    CONTRACTS, OBSERVATION_AXES, FrozenExperiment, digest, validate,
    validate_world, validate_trace, validate_intent, validate_policy_reference,
    validate_change_accounts,
)
H = 'a' * 64
REF = {'id': 'example', 'digest': H}
ERRORS = (ValueError, ValidationError)


def world():
    countries = []
    for cid in ['A', 'B']:
        countries.append({'state_id': cid, 'accounts': [cid], 'capacities': [cid],
            'demands': [{'resource_id': 'food', 'unit_id': 'food_unit', 'quantity': 2, 'function_id': 'nutrition'}],
            'essential_functions': ['nutrition'], 'dependencies': ['AB'] if cid == 'B' else [],
            'decision_state': {'observation_hash': H, 'intent_ids': []},
            'autonomy': {'mandate_ids': [], 'decision_authority': 'self'},
            'self_reliance': {'assumption_set': REF.copy(), 'evidence_refs': []}})
    return {'contract_version': 'v3', 'schema_version': 1,
        'resources': [{'resource_id': 'food', 'unit_id': 'food_unit'}], 'countries': countries,
        'accounts': [{'kind': 'stock', 'account_id': c, 'resource_id': 'food', 'owner': c,
            'location': c, 'unit_id': 'food_unit', 'balance': 10, 'in_transit': False} for c in ['A', 'B']],
        'capacities': [{'kind': 'capacity', 'capacity_id': c, 'owner': c, 'category': 'transport',
            'unit_id': 'capacity_unit', 'available': 5, 'reserved': 0} for c in ['A', 'B']],
        'routes': [{'route_id': 'AB', 'source': 'A', 'target': 'B'}],
        'dependencies': [{'dependency_id': 'AB', 'supplier': 'A', 'consumer': 'B', 'resource_id': 'food',
            'route_id': 'AB', 'capacity_id': 'A', 'alternative_routes': [], 'upstream_dependencies': []}],
        'policies': [{'policy_id': 'baseline', 'definition_hash': H}], 'active_policy': 'baseline'}


def experiment():
    return {'contract_version': 'v3', 'kind': 'experiment_spec', 'experiment_id': 'synthetic-test',
        'research_question': 'Test only', 'secondary_questions': [], 'policy_refs': [REF.copy()],
        'initial_conditions': REF.copy(), 'primary_endpoints': ['shortage'], 'repetitions': 2,
        'seed_policy': REF.copy(), 'law_refs': [REF.copy()], 'observation_axes': list(OBSERVATION_AXES)}


def trace():
    i = {'contract_version': 'v3', 'kind': 'intent', 'intent_id': 'i', 'state_id': 'A',
         'snapshot_hash': digest(world()), 'law_ref': REF.copy(), 'proposal_id': None,
         'choice_ref': REF.copy(), 'parameters': [], 'evidence_refs': []}
    f = {'contract_version': 'v3', 'kind': 'feasibility', 'intent_hash': digest(i),
         'snapshot_hash': i['snapshot_hash'], 'validator_ref': REF.copy(), 'feasible': True, 'constraint_refs': []}
    s = {'contract_version': 'v3', 'kind': 'settlement', 'intent_hash': digest(i),
         'feasibility_hash': digest(f), 'snapshot_hash': i['snapshot_hash'],
         'policy_ref': {'id': 'baseline', 'digest': H}, 'established': True,
         'consent_refs': ['consent'], 'condition_refs': []}
    c = {'contract_version': 'v3', 'kind': 'state_change', 'producer': 'settlement_core',
         'settlement_hash': digest(s), 'snapshot_hash': i['snapshot_hash'], 'entries': [
         {'entry_id': 'e', 'resource_id': 'food', 'unit_id': 'food_unit', 'source_account': 'A',
          'target_account': 'B', 'quantity': 4, 'category': 'transfer', 'evidence_ref': 'settled-leg'}]}
    return i,f,s,c


class ContractsTest(unittest.TestCase):
    def test_schema_validity(self):
        from jsonschema import Draft202012Validator
        for schema in CONTRACTS.values(): Draft202012Validator.check_schema(schema)

    def test_valid_world(self): validate_world(world())

    def test_versions(self):
        for v in ['v1', 'v2', 'V3', 3]:
            w=world(); w['contract_version']=v
            with self.subTest(v=v), self.assertRaises(ERRORS): validate_world(w)

    def test_separation(self):
        w=world(); w['accounts'][0]=w['capacities'][0]
        with self.assertRaises(ERRORS): validate_world(w)

    def test_numbers(self):
        for q in [-1, True, 0.5, float('nan')]:
            w=world(); w['accounts'][0]['balance']=q
            with self.subTest(q=q), self.assertRaises(ERRORS): validate_world(w)

    def test_resource_units(self):
        w=world(); w['accounts'][0]['unit_id']='capacity_unit'
        with self.assertRaises(ERRORS): validate_world(w)

    def test_capacity(self):
        w=world(); w['capacities'][0]['reserved']=6
        with self.assertRaises(ERRORS): validate_world(w)

    def test_dependency_refs(self):
        for field in ['supplier','consumer','resource_id','route_id','capacity_id']:
            w=world(); w['dependencies'][0][field]='missing'
            with self.subTest(field=field), self.assertRaises(ERRORS): validate_world(w)

    def test_self_dependency(self):
        w=world(); w['dependencies'][0]['consumer']='A'
        with self.assertRaises(ERRORS): validate_world(w)
        w=world(); w['dependencies'][0]['upstream_dependencies']=['AB']
        with self.assertRaises(ERRORS): validate_world(w)

    def test_cycle_is_not_forbidden(self):
        w=world(); w['routes'].append({'route_id':'BA','source':'B','target':'A'})
        w['dependencies'].append({**w['dependencies'][0], 'dependency_id':'BA',
            'supplier':'B','consumer':'A','route_id':'BA','upstream_dependencies':['AB']})
        w['dependencies'][0]['upstream_dependencies']=['BA'];w['countries'][0]['dependencies']=['BA']
        validate_world(w)

    def test_policy_references(self):
        w=world();w['active_policy']='unknown'
        with self.assertRaises(ERRORS): validate_world(w)
        with self.assertRaises(ERRORS): validate_policy_reference(REF, world())
        validate_policy_reference({'id':'baseline','digest':H}, world())

    def test_exchange_policy(self):
        w=world();w['policies'].append({'policy_id':'alternative','definition_hash':'b'*64})
        w['active_policy']='alternative';validate_world(w)

    def test_autonomy_and_self_reliance_distinct(self):
        w=world(); w['countries'][0]['self_reliance']=w['countries'][0]['autonomy']
        with self.assertRaises(ERRORS): validate_world(w)

    def test_independent_intent(self):
        i,*_=trace();validate_intent(i,world(),laws={'example':H},choices={'example':H})
        i['law_ref']['id']='unregistered'
        with self.assertRaises(ERRORS): validate_intent(i,world(),laws={'example':H},choices={'example':H})

    def test_direct_state_write(self):
        i,*_=trace();i['world_patch']={'food':100}
        with self.assertRaises(ERRORS): validate('intent',i)

    def test_trace(self):
        values=trace();before=copy.deepcopy(values)
        validate_trace(*values,authorized_producer='settlement_core')
        self.assertEqual(values,before)

    def test_agent_and_coordinator_denied(self):
        for actor in ['agent','coordinator']:
            with self.subTest(actor=actor),self.assertRaises(ERRORS):
                validate_trace(*trace(),authorized_producer=actor)

    def test_stale_trace(self):
        values=list(trace());values[0]['parameters']=[{'name':'amount','quantity':5,'unit_id':'food_unit'}]
        with self.assertRaises(ERRORS):validate_trace(*values,authorized_producer='settlement_core')

    def test_failed_settlement_no_change(self):
        i,f,s,c=trace();s['established']=False;c['settlement_hash']=digest(s)
        with self.assertRaises(ERRORS):validate_trace(i,f,s,c,authorized_producer='settlement_core')
        c['entries']=[];validate_trace(i,f,s,c,authorized_producer='settlement_core')

    def test_double_spend(self):
        *_,c=trace();validate_change_accounts(c,world())
        c['entries'].append({**c['entries'][0],'entry_id':'e2','quantity':7})
        with self.assertRaises(ERRORS): validate_change_accounts(c,world())

    def test_transit_not_second_balance(self):
        w=world();w['accounts'][0]['in_transit']=True;validate_world(w)
        w['accounts'].append(dict(w['accounts'][0]))
        with self.assertRaises(ERRORS):validate_world(w)

    def test_coordinator_only_advisory(self):
        c={'contract_version':'v3','kind':'coordinator_message','message_id':'m',
           'snapshot_hash':H,'mode':'proposal','public_reason':'Public','proposal_refs':[]}
        validate('coordinator_message',c)
        for key in ['force_accept','state_patch','transfer','recovery_target']:
            with self.subTest(key=key),self.assertRaises(ERRORS):validate('coordinator_message',{**c,key:True})

    def test_no_scripted_future(self):
        e={'contract_version':'v3','kind':'event_input','world_hash':H,'intent_refs':[],
           'balance_hash':H,'unresolved_shortages_hash':H,'network_load_hash':H,
           'transaction_history_hash':H,'turn_history_hash':H,'rule_ref':REF}
        validate('event_input',e)
        for key in ['turn_schedule','recovery_turn','winner','final_world']:
            with self.subTest(key=key),self.assertRaises(ERRORS):validate('event_input',{**e,key:6})

    def test_experiment_immutable(self):
        source=experiment();f=FrozenExperiment.freeze(source);anchor=f.sha256
        f.verify(source,expected_digest=anchor)
        for key,value in [('research_question','changed'),('repetitions',3),('policy_refs',[])]:
            changed=copy.deepcopy(source);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ERRORS):f.verify(changed,expected_digest=anchor)
        source['primary_endpoints'].append('posthoc')
        self.assertEqual(f.to_dict()['primary_endpoints'],['shortage'])
        with self.assertRaises(FrozenInstanceError):f.sha256='changed'
        with self.assertRaises(ERRORS):f.verify(f.to_dict(),expected_digest='b'*64)

    def test_unknown_fields(self):
        spec=experiment();spec['desired_outcome']='recovery'
        with self.assertRaises(ERRORS):FrozenExperiment.freeze(spec)

    def test_observation_axes_required(self):
        spec=experiment();spec['observation_axes'].remove('national_self_reliance')
        with self.assertRaises(ERRORS):FrozenExperiment.freeze(spec)

    def test_pipeline(self):
        from homeostasis_v3.contracts import validate_pipeline
        values=trace()
        validate_pipeline(*values,world(),laws={'example':H},choices={'example':H},authorized_producer='settlement_core')
        i,f,s,c=trace();s['policy_ref']=REF;c['settlement_hash']=digest(s)
        with self.assertRaises(ERRORS):
            validate_pipeline(i,f,s,c,world(),laws={'example':H},choices={'example':H},authorized_producer='settlement_core')
