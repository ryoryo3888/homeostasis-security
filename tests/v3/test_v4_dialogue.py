"""Synthetic free choices: privacy, opt-in execution, refusal and replay."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from homeostasis_v3.agent_adapter import ExchangeBudget
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical
from homeostasis_v3.network import load_network
from homeostasis_v3.physical import load_baseline
from homeostasis_v3.turn import TurnFailure, TurnRunner
from homeostasis_v4.dialogue import DialogueRunner

ROOT = Path(__file__).resolve().parents[2]


def empty():
    return {'outgoing': [], 'activities': [], 'private_note': ''}


def offer(**overrides):
    terms = {'id': 'voluntary-1', 'target': 'RES', 'resource': 'food', 'route': 'MIL-forward',
             'amount': 2, 'minimum_amount': 1, 'allow_partial': True, 'conditions': []}
    terms.update(overrides)
    return {'body': 'Agent authored offer', 'operation': 'offer_transfer', 'arguments': terms}


def respond(view, accepted=True, **overrides):
    pending = next(o for o in view['offers'] if o['status'] == 'pending')
    arguments = {'offer_id': pending['id'], 'terms_digest': pending['terms_digest'], 'accepted': accepted}
    arguments.update(overrides)
    return {'body': 'Agent authored response', 'operation': 'respond_transfer', 'arguments': arguments}


class FreeDialogueTests(unittest.TestCase):
    def setUp(self):
        baseline = load_baseline(ROOT / 'scenarios/v3/synthetic_baseline.json')
        network = load_network(ROOT / 'scenarios/v3/synthetic_network.json', baseline)
        self.world = TurnRunner(baseline, network, pool_location='MIL', context_id='free-dialogue-fixture')
        self.runner = DialogueRunner(self.world, source='synthetic test fixture')
        self.opening = self.runner.genesis()
        self.requests = []

    def run_turn(self, opening=None, decide=lambda v: empty(), **kwargs):
        def exchange(raw):
            request = json.loads(raw); self.requests.append(request)
            return canonical(decide(request['view']))
        return self.runner.run(opening or self.opening, exchange=exchange,
                               budget=ExchangeBudget(8), **kwargs)

    def proposal(self, **terms):
        return self.run_turn(decide=lambda v: {**empty(), 'activities': [offer(**terms)]}
                             if v['actor'] == 'MIL' else empty())

    def test_private_message_and_note_never_leak_or_deliver_in_same_turn(self):
        def decide(view):
            reply = empty()
            if view['actor'] == 'MIL':
                reply.update(outgoing=[{'to': ['RES'], 'body': 'private-plan-48271'}],
                             private_note='private-memory-98312', activities=[offer()])
            return reply
        first = self.run_turn(decide=decide)
        self.assertTrue(all(not r['view']['messages'] and not r['view']['offers'] for r in self.requests))
        self.assertFalse(first['world']['world_state']['shipments'])
        second = self.run_turn(first)
        views = {r['view']['actor']: r['view'] for r in self.requests[8:]}
        self.assertEqual(views['RES']['messages'][0]['body'], 'private-plan-48271')
        self.assertEqual(views['MIL']['private_note'], 'private-memory-98312')
        for actor in set(views) - {'MIL', 'RES'}:
            self.assertNotIn('private-plan-48271', canonical(views[actor]))
            self.assertFalse(views[actor]['offers'])
        for actor in set(views) - {'MIL'}:
            self.assertNotIn('private-memory-98312', canonical(views[actor]))
        self.assertEqual(self.runner.replay(first, second), second)

    def test_consent_dispatch_arrival_and_saved_reply_replay(self):
        first = self.proposal()
        second = self.run_turn(first, lambda v: {**empty(), 'activities': [respond(v)]}
                               if v['actor'] == 'RES' else empty())
        shipment = second['world']['world_state']['shipments'][0]
        self.assertEqual(shipment['dispatched_amount'], 2)
        self.assertEqual(shipment['arrived_amount'], 0)
        self.assertEqual(second['dialogue']['offers']['offer:MIL:voluntary-1']['status'], 'dispatched')
        third = self.run_turn(second)
        self.assertEqual(third['world']['world_state']['shipments'][0]['arrived_amount'], 2)
        self.assertEqual(self.runner.replay(self.opening, first), first)
        self.assertEqual(self.runner.replay(first, second), second)
        self.assertEqual(self.runner.replay(second, third), third)
        self.assertEqual(len(self.requests), 24)

    def test_silence_and_free_institution_text_do_not_create_recovery(self):
        def decide(view):
            reply = empty()
            if view['actor'] == 'MIL':
                reply['activities'] = [{'body': '独自の制度を作り食料を100万生成したい',
                    'operation': 'my_new_institution', 'arguments': {'food': 1000000}}]
            return reply
        result = self.run_turn(decide=decide)
        expected = self.world.run(self.opening['world'])
        self.assertEqual(result['world']['world_state'], expected['world_state'])
        self.assertEqual(result['dialogue']['receipts']['MIL'][0]['status'], 'environment_unsupported')
        self.assertEqual(result['world']['audit']['RECOVERY']['applied'], [])

    def test_missing_consent_never_becomes_acceptance(self):
        first = self.proposal()
        second = self.run_turn(first)
        self.assertFalse(second['world']['world_state']['shipments'])
        self.assertEqual(second['dialogue']['offers']['offer:MIL:voluntary-1']['status'], 'pending')

    def test_refusal_and_simultaneous_withdrawal_prevent_dispatch(self):
        for withdraw in (False, True):
            self.setUp(); first = self.proposal()
            def decide(view):
                reply = empty()
                if view['actor'] == 'RES': reply['activities'] = [respond(view, accepted=withdraw)]
                if withdraw and view['actor'] == 'MIL':
                    o = view['offers'][0]
                    reply['activities'] = [{'body': '撤回', 'operation': 'withdraw_transfer',
                        'arguments': {'offer_id': o['id'], 'terms_digest': o['terms_digest']}}]
                return reply
            second = self.run_turn(first, decide)
            self.assertFalse(second['world']['world_state']['shipments'])
            self.assertEqual(second['dialogue']['offers']['offer:MIL:voluntary-1']['status'],
                             'withdrawn' if withdraw else 'rejected')

    def test_malformed_activity_is_preserved_without_executing(self):
        first = self.proposal(amount=True)
        receipt = first['dialogue']['receipts']['MIL'][0]
        self.assertEqual(receipt['status'], 'invalid_activity_request')
        self.assertEqual(receipt['request']['arguments']['amount'], True)
        self.assertFalse(first['dialogue']['offers'])
        self.assertFalse(first['world']['world_state']['shipments'])

    def test_only_recipient_can_accept_exact_terms(self):
        for forgery in ('wrong_digest', 'other_actor'):
            self.setUp(); first = self.proposal()
            def decide(view):
                reply = empty()
                if forgery == 'wrong_digest' and view['actor'] == 'RES':
                    reply['activities'] = [respond(view, terms_digest='0' * 64)]
                if forgery == 'other_actor' and view['actor'] == 'MIL':
                    reply['activities'] = [respond(view)]
                return reply
            second = self.run_turn(first, decide)
            self.assertFalse(second['world']['world_state']['shipments'])
            self.assertEqual(second['dialogue']['offers']['offer:MIL:voluntary-1']['status'], 'pending')

    def test_invalid_reply_rolls_back_and_no_retry(self):
        before = deepcopy(self.opening)
        for raw in ('{"outgoing":[],"outgoing":[],"activities":[],"private_note":""}',
                    canonical({**empty(), 'world_patch': {'food': 999}}),
                    canonical({**empty(), 'outgoing': [{'to': ['RES'], 'body': 'x', 'reply_to': ['invisible']}]}) ):
            runner = DialogueRunner(self.world, source='synthetic test fixture')
            with self.assertRaises(TurnFailure):
                runner.run(self.opening, exchange=lambda _: raw, budget=ExchangeBudget(8))
            with self.assertRaisesRegex(TechnicalFailure, 'DIALOGUE_RETRY_FORBIDDEN'):
                runner.run(self.opening, exchange=lambda _: canonical(empty()), budget=ExchangeBudget(8))
            self.assertEqual(self.opening, before)

    def test_ambiguous_accept_and_reject_stop_without_picking_one(self):
        first = self.proposal()
        with self.assertRaises(TurnFailure):
            self.run_turn(first, lambda v: {**empty(), 'activities': [respond(v), respond(v, False)]}
                          if v['actor'] == 'RES' else empty())
        self.assertFalse(first['world']['world_state']['shipments'])

    def test_budget_checked_before_call_and_configuration_cannot_change(self):
        calls = []
        with self.assertRaisesRegex(TechnicalFailure, 'COMPLETE_ROUND_BUDGET_REQUIRED'):
            self.runner.run(self.opening, exchange=lambda x: calls.append(x), budget=ExchangeBudget(7))
        self.assertEqual(calls, [])
        self.runner = DialogueRunner(self.world, source='synthetic test fixture')
        budget = ExchangeBudget(8)
        def mutate(raw):
            budget.limit = 80
            return canonical(empty())
        with self.assertRaises(TurnFailure):
            self.runner.run(self.opening, exchange=mutate, budget=budget)
        self.assertEqual(len(budget.attempts), 8)  # Complete round reserved before dispatch.

    def test_physical_failure_is_not_a_success_or_automatic_retry(self):
        first = self.proposal(route='no-such-route')
        second = self.run_turn(first, lambda v: {**empty(), 'activities': [respond(v)]}
                               if v['actor'] == 'RES' else empty())
        o = second['dialogue']['offers']['offer:MIL:voluntary-1']
        self.assertEqual(o['status'], 'not_dispatched')
        self.assertIn('NO_ROUTE', o['outcome']['reason_codes'])
        third = self.run_turn(second)
        self.assertFalse(third['world']['input']['selections']['MIL'])
        self.assertFalse(third['world']['world_state']['shipments'])

    def test_agent_can_author_multiple_offers_without_host_opportunity_ids(self):
        result = self.run_turn(decide=lambda v: {**empty(), 'activities': [offer(id='first'),
            offer(id='another', target='NEUTRAL', route='MIL-reverse', resource='energy', amount=1234)]}
            if v['actor'] == 'MIL' else empty())
        self.assertEqual(len(result['dialogue']['offers']), 2)
        self.assertEqual(result['dialogue']['offers']['offer:MIL:another']['terms']['amount'], 1234)
        self.assertTrue(all('opportunities' not in r['view'] for r in self.requests))

    def test_condition_on_unaccepted_visible_offer_is_not_fabricated(self):
        first = self.proposal()
        second = self.run_turn(first, lambda v: {**empty(), 'activities': [offer(
            id='reply-offer', target='MIL', resource='energy', route='RES-reverse',
            conditions=[{'kind': 'settled_amount', 'choice_id': 'offer:MIL:voluntary-1',
                         'minimum_amount': 2}])]}
            if v['actor'] == 'RES' else empty())
        def accept_reply(view):
            result = empty()
            if view['actor'] == 'MIL':
                o = next(o for o in view['offers'] if o['sender'] == 'RES')
                result['activities'] = [{'body': 'accept', 'operation': 'respond_transfer',
                    'arguments': {'offer_id': o['id'], 'terms_digest': o['terms_digest'], 'accepted': True}}]
            return result
        third = self.run_turn(second, accept_reply)
        self.assertFalse(third['world']['world_state']['shipments'])
        self.assertIn('CONDITION_NOT_MET', third['dialogue']['offers']['offer:RES:reply-offer']['outcome']['reason_codes'])
        self.assertEqual(self.runner.replay(second, third), third)

    def test_new_event_inputs_apply_once_without_added_story_events(self):
        baseline = self.opening['world']['world_state']['physical']
        account = baseline['world']['accounts'][0]
        shock = {'event_id': 'explicit-test-event', 'kind': 'resource_loss',
                 'target': account['account_id'], 'resource': account['resource_id'],
                 'amount': 1, 'evidence': 'synthetic test input, not a live scenario'}
        first = self.run_turn(shocks=[shock])
        second = self.run_turn(first)
        self.assertEqual(first['world']['audit']['SHOCK'], [shock])
        self.assertEqual(second['world']['audit']['SHOCK'], [])
        self.assertTrue(all(r['view']['external_events_this_turn'] == [shock] for r in self.requests[:8]))
        self.assertTrue(all(r['view']['external_events_this_turn'] == [] for r in self.requests[8:]))
