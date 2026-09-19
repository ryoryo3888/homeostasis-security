"""Synthetic JSON boundaries and multi-TURN validation, never model findings."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homeostasis_v3.agent_adapter import JsonCountryAdapter, ExchangeBudget
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical, digest
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.network import load_network
from homeostasis_v3.turn import TurnRunner, Snapshot, TurnFailure
from homeostasis_v3.checkpoint import CheckpointStore
from homeostasis_v3.validation_runner import run_validation

ROOT = Path(__file__).resolve().parents[2]


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.baseline = load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
        self.network = load_network(ROOT/'scenarios/v3/synthetic_network.json', self.baseline)
        self.runner = TurnRunner(self.baseline, self.network, pool_location='MIL', context_id='adapter-fixture')
        self.genesis = self.runner.genesis()
        self.budget = ExchangeBudget(16)

    def catalogue(self, view):
        snapshot = view.read()['settlement_snapshot']
        return [dict(choice_id='fixture-'+str(snapshot['turn']), actor_state_id='MIL',
                     turn=snapshot['turn'], snapshot_hash=digest(snapshot), action_type='transfer',
                     resource='food', maximum_amount=2, target='RES', route_preference='MIL-forward',
                     conditions=[], allow_partial=True, minimum_amount=1)]

    def response(self, raw):
        request = json.loads(raw)
        result = {'request_digest':request['request_digest'], 'state_id':request['state_id'],
                  'decisions':[], 'consents':{}}
        if request['phase'] == 'choice' and request['state_id'] == 'MIL':
            result['decisions'] = [{'choice_id':request['payload']['catalogue'][0]['choice_id'],
                                    'requested_amount':2, 'public_reason':'Synthetic voluntary transfer'}]
        if request['phase'] == 'consent':
            result['consents'] = {c['choice_id']:True for c in request['payload']['choices']}
        return result

    def countries(self, mutate=None):
        def exchange(raw):
            response = self.response(raw)
            if mutate: mutate(response)
            return canonical(response)
        return {sid:JsonCountryAdapter(sid, catalogue=self.catalogue, exchange=exchange,
                                      budget=self.budget, source='synthetic fixture').callbacks()
                for sid in ('MIL','RES')}

    def run_fixture(self, countries=None):
        return self.runner.run(self.genesis, catalogue=self.catalogue,
                               countries=countries if countries is not None else self.countries())

    def test_independent_transfer_and_saved_input_replay(self):
        result = self.run_fixture()
        self.assertIsNone(result['input']['proposal'])
        self.assertEqual(result['world_state']['shipments'][0]['dispatched_amount'], 2)
        attempts = len(self.budget.attempts)
        self.assertEqual(self.runner.replay(self.genesis, result['input']), result)
        self.assertEqual(len(self.budget.attempts), attempts)
        self.assertEqual(attempts, 4)

    def test_all_refusal_is_valid_world_result(self):
        countries = self.countries(lambda a:a.update(consents={k:False for k in a['consents']}))
        result = self.run_fixture(countries)
        self.assertEqual(result['turn'], 1)
        self.assertEqual(result['world_state']['shipments'], [])

    def test_cross_country_and_stale_snapshot_fail_closed(self):
        for field, value in [('state_id','OTHER'),('request_digest','0'*64)]:
            with self.subTest(field=field):
                self.budget = ExchangeBudget(16)
                with self.assertRaises(TurnFailure):
                    self.run_fixture(self.countries(lambda a:a.update({field:value})))

    def test_model_cannot_patch_world_or_add_execution_fields(self):
        for mutate in [lambda a:a.update(world_state={}),
                       lambda a:a['decisions'][0].update(target='OTHER'),
                       lambda a:a['decisions'][0].update(requested_amount=True),
                       lambda a:a['decisions'][0].update(requested_amount=3),
                       lambda a:a['decisions'][0].update(choice_id='invented')]:
            self.budget = ExchangeBudget(16)
            with self.assertRaises(TurnFailure): self.run_fixture(self.countries(mutate))

    def test_duplicate_selection_rejected(self):
        with self.assertRaises(TurnFailure):
            self.run_fixture(self.countries(lambda a:a['decisions'].extend(deepcopy(a['decisions']))))

    def test_premature_consent_and_late_decision_rejected(self):
        with self.assertRaises(TurnFailure):
            self.run_fixture(self.countries(lambda a:a.update(consents={'fixture-1':True})))
        self.budget = ExchangeBudget(16)
        def late(raw):
            reply = self.response(raw)
            if json.loads(raw)['phase']=='consent':
                reply['decisions']=[{'choice_id':'fixture-1','requested_amount':1,'public_reason':'fixture'}]
            return canonical(reply)
        country=JsonCountryAdapter('MIL',catalogue=self.catalogue,exchange=late,budget=self.budget,source='fixture')
        with self.assertRaises(TurnFailure): self.run_fixture({'MIL':country.callbacks()})

    def test_invalid_json_duplicate_keys_and_oversize_rejected(self):
        for raw in ('not json', '{"state_id":"MIL","state_id":"RES"}', ' '*65537):
            with self.subTest(raw_length=len(raw)):
                country=JsonCountryAdapter('MIL',catalogue=self.catalogue,exchange=lambda _:raw,
                                          budget=ExchangeBudget(1),source='fixture')
                with self.assertRaises(TurnFailure): self.run_fixture({'MIL':country.callbacks()})

    def test_budget_reserved_before_failure_and_no_retry(self):
        called=[]
        def fail(raw):
            called.append(raw)
            raise RuntimeError('sensitive-provider-error')
        adapter=JsonCountryAdapter('MIL',catalogue=lambda _:[],exchange=fail,
                                   budget=ExchangeBudget(1),source='fixture')
        for _ in range(2):
            with self.assertRaises((RuntimeError,TechnicalFailure)):
                adapter.choose(Snapshot.of({}),Snapshot.of(None))
        self.assertEqual(len(called),1)
        self.assertEqual(len(adapter.budget.attempts),1)

    def test_zero_budget_never_dispatches(self):
        called=[]
        adapter=JsonCountryAdapter('MIL',catalogue=lambda _:[],exchange=lambda r:called.append(r),
                                   budget=ExchangeBudget(0),source='fixture')
        with self.assertRaises(TechnicalFailure): adapter.choose(Snapshot.of({}),Snapshot.of(None))
        self.assertFalse(called)

    def test_multi_turn_validation_durable_and_not_research(self):
        with tempfile.TemporaryDirectory() as temp:
            report=run_validation(self.baseline,self.network,Path(temp)/'run',turns=3)
            self.assertEqual(report['completed_turns'],3)
            self.assertEqual(report['replay_verified'],3)
            self.assertEqual(report['synthetic_exchanges'],24)
            self.assertEqual(report['api_calls'],0)
            self.assertFalse(report['research_eligible'])
            self.assertFalse(report['formal_experiment_ready'])
            protocol=json.loads((Path(temp)/'run/protocol.json').read_text())
            for record in (report,protocol):
                self.assertEqual(record['decision_origin'],'synthetic_fixture')
                self.assertEqual(record['fixture'],'synthetic_abstention')
                self.assertEqual(record['fixture_behavior'],'always_empty_decisions_not_agent_chosen_abstention')
            cp=CheckpointStore(Path(temp)/'run/checkpoints').load()
            self.assertEqual(cp['turn'],3)
            self.assertEqual(cp['audit']['RECOVERY']['applied'],[])
            self.assertEqual(len(list((Path(temp)/'run').glob('observation-*.json'))),3)

    def test_run_directory_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'run'
            run_validation(self.baseline,self.network,path,turns=1)
            before=(path/'report.json').read_bytes()
            with self.assertRaises(FileExistsError): run_validation(self.baseline,self.network,path,turns=1)
            self.assertEqual((path/'report.json').read_bytes(),before)

    def test_storage_failure_stops_and_excludes_raw_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'run'
            with patch.object(CheckpointStore,'save',side_effect=OSError('sensitive-error')):
                with self.assertRaisesRegex(RuntimeError,'inspect saved report'):
                    run_validation(self.baseline,self.network,path,turns=2)
            report=json.loads((path/'report.json').read_text())
            self.assertEqual(report['status'],'technical_failure')
            self.assertFalse(report['automatic_retry'])
            self.assertEqual(report['decision_origin'],'synthetic_fixture')
            self.assertEqual(report['completed_turns'],0)
            self.assertNotIn('sensitive-error',(path/'report.json').read_text())

    def test_second_turn_failure_preserves_first_checkpoint(self):
        from homeostasis_v3.validation_runner import synthetic_abstention
        calls=[]
        def fail_second_turn(raw):
            calls.append(raw)
            if json.loads(raw)['observation']['turn']==2:
                raise RuntimeError('sensitive-provider-error')
            return synthetic_abstention(raw)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'run'
            with patch('homeostasis_v3.validation_runner.synthetic_abstention',fail_second_turn):
                with self.assertRaises(RuntimeError): run_validation(self.baseline,self.network,path,turns=3)
            self.assertEqual(len(calls),9)
            self.assertEqual(CheckpointStore(path/'checkpoints').load()['turn'],1)
            report=json.loads((path/'report.json').read_text())
            self.assertEqual(report['completed_turns'],1)
            self.assertEqual(report['synthetic_exchanges'],9)
            self.assertEqual(report['status'],'technical_failure')

    def test_invalid_turn_counts_do_not_create_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'run'
            for count in (0,True,33,1.5):
                with self.assertRaises(TechnicalFailure): run_validation(self.baseline,self.network,path,turns=count)
                self.assertFalse(path.exists())


if __name__ == '__main__': unittest.main()
