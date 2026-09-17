"""Synthetic law fixtures only; never a research experiment."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homeostasis_v3.physical import load_baseline
from homeostasis_v3.network import load_network
from homeostasis_v3.contracts import digest
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.turn import TurnRunner, CountryInput, PHASES, Snapshot, TurnFailure, validate_checkpoint, seal, totals
from homeostasis_v3.checkpoint import CheckpointStore, CommitUncertain
ROOT = Path(__file__).resolve().parents[2]


class TurnTests(unittest.TestCase):
    def setUp(self):
        self.b = load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
        self.n = load_network(ROOT/'scenarios/v3/synthetic_network.json', self.b)
        self.runner = TurnRunner(self.b, self.n, pool_location='MIL', context_id='synthetic-turn-check')
        self.g = self.runner.genesis()

    def catalogue(self, view):
        s = view.read()['settlement_snapshot']
        return [dict(choice_id=f'fixture-{s["turn"]}-{i}', actor_state_id='MIL', turn=s['turn'],
                     snapshot_hash=digest(s), action_type='transfer', resource='food', maximum_amount=2,
                     target='RES', route_preference='MIL-forward', conditions=[], allow_partial=True, minimum_amount=1)
                for i in range(2)]

    def countries(self, reverse=False, consent=True):
        def choose(view, proposal):
            ids = [t['choice_id'] for t in self.catalogue(view)]
            if reverse: ids.reverse()
            return [{'choice_id': cid, 'requested_amount': 2,
                     'provenance': {'source': 'synthetic fixture', 'public_reason': 'Independent voluntary transfer'}} for cid in ids]
        def agree(view, choices): return {c['choice_id']: consent for c in choices.read()}
        return {'MIL': CountryInput(choose, agree), 'RES': CountryInput(lambda *_: [], agree)}

    def run_choices(self, **kwargs):
        return self.runner.run(self.g, catalogue=self.catalogue, countries=self.countries(), **kwargs)

    def shock(self, kind, target, resource=None, amount=0, eid='shock'):
        return dict(event_id=eid, kind=kind, target=target, resource=resource, amount=amount, evidence='synthetic law fixture')

    def test_full_turn_phases_and_digests(self):
        result = self.run_choices()
        self.assertEqual([p['phase'] for p in result['phases']], list(PHASES))
        self.assertEqual(result['turn'], 1)
        self.assertEqual(result['evaluation']['world_hash'], result['output_digest'])
        self.assertEqual(result['evaluation']['world_state'], result['world_state'])
        self.assertEqual(result['next_event_input']['world_state'], result['world_state'])
        self.assertEqual(result['input_digest'], digest(result['input']))
        self.assertTrue(all(a['established'] for a in result['history'][0]['settlement']['choices']))

    def test_replay_determinism(self):
        self.assertEqual(self.run_choices(), self.run_choices())

    def test_choice_order_independent(self):
        a = self.run_choices()
        b = self.runner.run(self.g, catalogue=self.catalogue, countries=self.countries(reverse=True))
        self.assertEqual(a['world_state'], b['world_state'])
        self.assertEqual(a['history'], b['history'])
        self.assertEqual(a, b)
        self.assertEqual(self.runner.run(a), self.runner.run(b))

    def test_opening_and_initial_assets_unchanged(self):
        before = deepcopy((self.g, self.b, self.n)); self.run_choices()
        self.assertEqual((self.g, self.b, self.n), before)

    def test_common_frozen_observation_and_private_copies(self):
        hashes = []
        def choose(view, proposal):
            hashes.append(view.hash)
            view.read()['world_state']['pool']['food'] = 999999
            with self.assertRaises(FrozenInstanceError): view.payload = '{}'
            return []
        countries = {c['state_id']: CountryInput(choose, lambda *_: {}) for c in self.b['world']['countries']}
        cp = self.runner.run(self.g, countries=countries)
        self.assertEqual(len(set(hashes)), 1); self.assertEqual(len(hashes), 8)
        self.assertEqual(cp['world_state']['pool']['food'], 0)

    def test_coordinator_optional_independent_action(self):
        cp = self.run_choices()
        self.assertIsNone(cp['input']['proposal']); self.assertEqual(len(cp['world_state']['shipments']), 2)

    def test_coordinator_cannot_supply_choices_or_world_patch(self):
        with self.assertRaises(TechnicalFailure):
            self.runner.run(self.g, coordinator=lambda _: {'proposal_id': 'x', 'public_reason': 'x', 'world_state': {}})

    def test_proposal_cannot_mutate_world(self):
        a = self.run_choices()
        b = self.run_choices(coordinator=lambda _: {'proposal_id': 'p', 'public_reason': 'No compulsion'})
        self.assertEqual(a['world_state'], b['world_state'])

    def test_actor_cannot_select_another_actor_choice(self):
        wrong = {'RES': CountryInput(self.countries()['MIL'].choose, lambda *_: {})}
        with self.assertRaises(TechnicalFailure): self.runner.run(self.g, catalogue=self.catalogue, countries=wrong)

    def test_missing_consent_is_world_result(self):
        cp = self.runner.run(self.g, catalogue=self.catalogue, countries={'MIL': self.countries()['MIL']})
        choices = cp['history'][0]['settlement']['choices']
        self.assertTrue(all(not c['established'] and 'MISSING_CONSENT' in c['reason_codes'] for c in choices))
        self.assertEqual(cp['turn'], 1)

    def test_partial_rejection_is_world_result(self):
        people = self.countries()
        people['RES'] = CountryInput(lambda *_: [], lambda _, choices: {c['choice_id']: i == 0 for i,c in enumerate(choices.read())})
        cp = self.runner.run(self.g, catalogue=self.catalogue, countries=people)
        self.assertEqual(sum(a['established'] for a in cp['history'][0]['settlement']['choices']), 1)

    def test_route_shutdown_persists_not_technical_failure(self):
        cp = self.run_choices(shocks=[self.shock('route_stop', 'MIL-forward')])
        self.assertTrue(all('ROUTE_UNAVAILABLE' in c['reason_codes'] for c in cp['history'][0]['settlement']['choices']))
        self.assertFalse(next(r for r in cp['world_state']['network']['routes'] if r['route_id'] == 'MIL-forward')['availability'])

    def test_shortage_worsens_and_is_saved(self):
        account = self.b['world']['accounts'][0]
        cp = self.runner.run(self.g, shocks=[self.shock('resource_loss', account['account_id'], account['resource_id'], account['balance'])])
        normal = self.runner.run(self.g)
        self.assertGreater(sum(x['shortage'] for x in cp['ledger']), sum(x['shortage'] for x in normal['ledger']))
        validate_checkpoint(cp)

    def test_demand_change(self):
        cp = self.runner.run(self.g, shocks=[self.shock('demand_change', 'MIL', 'food', 10000)])
        row = next(r for r in cp['ledger'] if r['owner'] == 'MIL' and r['resource'] == 'food')
        self.assertEqual(row['required'], 10000); self.assertGreater(row['shortage'], 0)

    def test_capacity_loss_not_auto_recovered(self):
        profile = self.b['capacity_profiles'][0]
        cp = self.runner.run(self.g, shocks=[self.shock('capacity_loss', profile['capacity_id'], amount=profile['current_capacity'])])
        next_cp = self.runner.run(cp)
        actual = next(p for p in next_cp['world_state']['physical']['capacity_profiles'] if p['capacity_id'] == profile['capacity_id'])
        self.assertEqual(actual['current_capacity'], 0)
        self.assertEqual(next_cp['audit']['RECOVERY']['applied'], [])

    def test_consumption_before_production(self):
        a = self.b['world']['accounts'][0]
        cp = self.runner.run(self.g, shocks=[self.shock('resource_loss', a['account_id'], a['resource_id'], a['balance'])])
        row = next(r for r in cp['ledger'] if (r['owner'],r['resource']) == (a['owner'],a['resource_id']))
        self.assertEqual(row['consumed'], 0)

    def test_production_dependency_and_conservation(self):
        cp = self.run_choices(); balance = cp['audit']['CONSERVATION']
        for r in balance['opening']:
            self.assertEqual(balance['closing'][r], balance['opening'][r]-balance['loss'][r]-balance['consumed'][r]-balance['production_inputs'][r]+balance['production_outputs'][r])
        self.assertTrue(any(r['inputs'] for r in cp['audit']['PRODUCTION']))
        self.assertTrue(cp['world_state']['production_pending'])
        self.assertTrue(all(p['due_turn'] > cp['turn'] for p in cp['world_state']['production_pending']))

    def test_input_shortage_limits_production(self):
        dep = self.n['production_dependencies'][0]
        a = next(a for a in self.b['world']['accounts'] if a['owner'] == dep['producer_state'] and a['resource_id'] == dep['input_resource'])
        cp = self.runner.run(self.g, shocks=[self.shock('resource_loss', a['account_id'], a['resource_id'], a['balance'])])
        p = next(p for p in cp['audit']['PRODUCTION'] if p['capacity_id'] == dep['production_capacity_id'])
        self.assertEqual(p['quantity'], 0)

    def test_transit_delayed_and_receipt_once(self):
        a = self.run_choices()
        self.assertTrue(all(s['arrived_amount'] == 0 for s in a['world_state']['shipments']))
        b = self.runner.run(a)
        for s in b['world_state']['shipments']:
            if s['arrival_due_turn'] <= b['turn']: self.assertEqual(s['arrived_amount'], s['dispatched_amount'])
        c = self.runner.run(b)
        self.assertFalse(any('shipment_id' in r and r['arrival_turn'] < c['turn'] for r in c['audit']['ARRIVAL']))

    def test_next_input_contains_actual_history_not_story(self):
        cp = self.run_choices(); nxt = cp['next_event_input']
        self.assertEqual(nxt['history'], cp['history'])
        for field in ('shortages','capacity_profiles','network_load','unresolved_conditions'): self.assertIn(field, nxt)
        self.assertNotIn('story', nxt)

    def test_technical_failure_leaves_opening_valid(self):
        before = deepcopy(self.g)
        with self.assertRaises(TechnicalFailure): self.runner.run(self.g, shocks=[self.shock('route_stop', 'unknown')])
        self.assertEqual(self.g, before); validate_checkpoint(self.g)

    def test_callback_exception_not_complete_turn(self):
        def broken(*_): raise RuntimeError('synthetic fault')
        with self.assertRaises(TurnFailure): self.runner.run(self.g, countries={'MIL': CountryInput(broken, lambda *_: {})})
        self.assertEqual(self.g['turn'], 0)

    def test_invalid_schema_and_duplicate_events(self):
        event = self.shock('route_stop', 'MIL-forward')
        for shocks in ([event,event], [{**event, 'unknown': 1}], [{**event, 'amount': True}]):
            with self.assertRaises(TechnicalFailure): self.runner.run(self.g, shocks=shocks)

    def test_digest_tampering_rejected(self):
        cp = self.run_choices(); cp['world_state']['pool']['food'] += 1
        with self.assertRaises(TechnicalFailure): validate_checkpoint(cp)

    def test_input_and_audit_integrity(self):
        for part in ('input','audit'):
            cp = self.run_choices(); cp[part]['extra'] = 1
            if part == 'audit': cp['audit']['SHOCK'] = [] if cp['audit']['SHOCK'] else ['changed']
            cp.pop('checkpoint_digest'); cp = seal(cp)
            with self.assertRaises(TechnicalFailure): validate_checkpoint(cp)

    def test_evaluator_mismatch_rejected(self):
        cp = self.run_choices(); cp['evaluation']['world_state']['pool']['food'] = 1
        cp.pop('checkpoint_digest'); cp = seal(cp)
        with self.assertRaises(TechnicalFailure): validate_checkpoint(cp)

    def test_config_mismatch_rejected(self):
        r = TurnRunner(self.b, self.n, pool_location='RES', context_id='other')
        with self.assertRaises(TechnicalFailure): r.run(self.g)

    def test_checkpoint_save_load_and_resume(self):
        with tempfile.TemporaryDirectory() as path:
            store = CheckpointStore(path); store.save(self.g, expected_digest=None)
            cp = self.run_choices(); store.save(cp, expected_digest=self.g['checkpoint_digest'])
            self.assertEqual(store.load(), cp)
            self.assertEqual(self.runner.run(store.load()), self.runner.run(cp))
            with self.assertRaises(TechnicalFailure): store.save(cp, expected_digest=self.g['checkpoint_digest'])

    def test_save_failure_before_head_preserves_last_valid(self):
        with tempfile.TemporaryDirectory() as path:
            store = CheckpointStore(path); store.save(self.g, expected_digest=None)
            original = store._atomic_write
            def fail(path, data):
                if path.name == 'HEAD.json': raise OSError('synthetic disk failure')
                return original(path, data)
            with patch.object(store, '_atomic_write', side_effect=fail):
                with self.assertRaises(OSError): store.save(self.run_choices(), expected_digest=self.g['checkpoint_digest'])
            self.assertEqual(store.load(), self.g)

    def test_record_fsync_failure_preserves_head(self):
        with tempfile.TemporaryDirectory() as path:
            store = CheckpointStore(path); store.save(self.g, expected_digest=None)
            with patch.object(store, '_sync_dir', side_effect=OSError('synthetic fault')):
                with self.assertRaises(OSError): store.save(self.run_choices(), expected_digest=self.g['checkpoint_digest'])
            self.assertEqual(store.load(), self.g)

    def test_post_commit_fsync_is_uncertain_not_rollback(self):
        with tempfile.TemporaryDirectory() as path:
            store = CheckpointStore(path); store.save(self.g, expected_digest=None); cp = self.run_choices()
            with patch.object(store, '_sync_dir', side_effect=[None, OSError('synthetic fault')]):
                with self.assertRaises(CommitUncertain): store.save(cp, expected_digest=self.g['checkpoint_digest'])
            self.assertEqual(store.load(), cp)

    def test_corrupt_record_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            store = CheckpointStore(path); checksum = store.save(self.g, expected_digest=None)
            (Path(path)/(checksum+'.json')).write_text('{}')
            with self.assertRaises(TechnicalFailure): store.load()

    def test_store_rejects_missing_genesis(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(TechnicalFailure): CheckpointStore(path).save(self.run_choices(), expected_digest=None)

    def test_no_script_or_agent_dependencies(self):
        import ast
        source = (ROOT/'homeostasis_v3/turn.py').read_text(); tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(any(n.name.startswith(('google','http','requests')) for n in node.names))
            if isinstance(node, ast.Compare):
                # No production-code TURN-number schedule.
                names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                if 'turn' in names:
                    self.assertFalse(any(isinstance(n, ast.Constant) and type(n.value) is int and n.value > 1 for n in ast.walk(node)))
        self.assertFalse(any('MIL' == n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)))

    def test_persisted_input_replay(self):
        cp = self.run_choices()
        self.assertEqual(self.runner.replay(self.g, cp['input']), cp)

    def test_failure_machine_record_no_exception_text(self):
        def broken(*_): raise RuntimeError('DO_NOT_PERSIST_RAW_EXCEPTION')
        with self.assertRaises(TurnFailure) as caught:
            self.runner.run(self.g, countries={'MIL': CountryInput(broken, lambda *_: {})})
        record = caught.exception.record
        self.assertEqual(record['phase'], 'CHOICE_COLLECTION')
        self.assertFalse(record['completed'])
        self.assertEqual(record['last_valid_checkpoint'], self.g['checkpoint_digest'])
        self.assertNotIn('DO_NOT_PERSIST', str(record))

    def test_late_conservation_failure_no_formal_checkpoint(self):
        with tempfile.TemporaryDirectory() as path:
            store = CheckpointStore(path); store.save(self.g, expected_digest=None)
            original = self.runner._produce
            def broken(world, turn):
                out = original(world, turn)
                world['pool']['food'] += 1
                return out
            with patch.object(self.runner, '_produce', side_effect=broken):
                with self.assertRaises(TurnFailure) as caught: self.run_choices()
            self.assertEqual(caught.exception.code, 'RESOURCE_CONSERVATION_VIOLATION')
            self.assertEqual(caught.exception.record['phase'], 'CONSERVATION')
            self.assertEqual(store.load(), self.g)

    def test_unused_invalid_catalogue_fails_closed(self):
        with self.assertRaises(TurnFailure):
            self.runner.run(self.g, catalogue=lambda _: [{'choice_id': 'bad'}])

    def test_world_failure_can_be_durably_adopted(self):
        cp = self.runner.run(self.g, catalogue=self.catalogue, countries=self.countries(consent=False))
        with tempfile.TemporaryDirectory() as path:
            store = CheckpointStore(path); store.save(self.g, expected_digest=None)
            store.save(cp, expected_digest=self.g['checkpoint_digest'])
            self.assertEqual(store.load()['turn'], 1)
            self.assertFalse(any(c['established'] for c in store.load()['history'][0]['settlement']['choices']))

    def test_history_restore_requires_core_and_is_one_time(self):
        from homeostasis_v3.choices import Authority
        from homeostasis_v3.settlement import SettlementEngine, Policy
        auth = Authority([c['state_id'] for c in self.b['world']['countries']])
        engine = SettlementEngine(self.b, self.n, auth, [Policy('baseline')], pool_location='MIL', context_id='restore-test')
        for role in ('coordinator', 'evaluator'):
            with self.assertRaises(TechnicalFailure):
                engine.restore_history(auth.issue(role), turn=1, shipments=[], seen_choice_ids=[])
        core = auth.issue('core')
        state = engine.restore_history(core, turn=1, shipments=[], seen_choice_ids=[])
        self.assertEqual(engine.read(state)['turn'], 1)
        with self.assertRaises(TechnicalFailure): engine.restore_history(core, turn=2, shipments=[], seen_choice_ids=[])

    def test_production_order_independent(self):
        world = deepcopy(self.g['world_state']); other = deepcopy(world)
        other['physical']['world']['capacities'].reverse()
        other['network']['production_dependencies'].reverse()
        first = self.runner._produce(world, 1)
        second = self.runner._produce(other, 1)
        # Dependency ordering may reorder evidence lists, never resource results.
        self.assertEqual(first[1:], second[1:])
        self.assertEqual(world['physical']['world']['accounts'], other['physical']['world']['accounts'])
        self.assertEqual(world['production_pending'], other['production_pending'])

    def test_evaluation_view_mutation_cannot_change_formal_world(self):
        cp = self.run_choices(); view = Snapshot.of(cp['evaluation']); copy = view.read()
        copy['world_state']['pool']['food'] = 12345
        self.assertEqual(cp['world_state']['pool']['food'], 0)
        self.assertEqual(view.hash, digest(cp['evaluation']))

    def test_search_budget_failure_not_world_no_trade(self):
        runner = TurnRunner(self.b, self.n, pool_location='MIL', context_id='limited-test', search_budget=1)
        with self.assertRaises(TurnFailure) as caught:
            runner.run(runner.genesis(), catalogue=self.catalogue, countries=self.countries())
        self.assertEqual(caught.exception.code, 'SEARCH_BUDGET_EXCEEDED')
        self.assertEqual(caught.exception.record['phase'], 'SETTLEMENT_TRANSACTION')

    def test_bad_pending_receipt_rejected_even_with_recomputed_checksum(self):
        cp = self.run_choices(); cp['world_state']['production_pending'][0]['due_turn'] = 0
        cp.pop('checkpoint_digest'); cp = seal(cp)
        with self.assertRaises(TechnicalFailure): validate_checkpoint(cp)
