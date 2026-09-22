import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from homeostasis_v5.paired_diplomacy_experiment import (
    NORMAL, NO_DIPLOMACY, build_turn_snapshot, compare_condition_invariants,
    public_world_bulletin, validate_decision, ContractError,
)
from homeostasis_v5.world_law_settlement import (
    WorldLawState, settlement_funnel, apply_dispatch_if_scheduled, process_arrivals,
)


def source_world():
    return {
        'world_id': 'world-test',
        'pairs': [{'nation_id': 'nation-001', 'leader_id': 'leader-001'}, {'nation_id': 'nation-002', 'leader_id': 'leader-002'}],
        'nations': [{'nation': {'nation_id': 'nation-001', 'name': 'A'}}, {'nation': {'nation_id': 'nation-002', 'name': 'B'}}],
        'leaders': [{'fixed_profile': {'name': 'A'}, 'presentation': {}}, {'fixed_profile': {'name': 'B'}, 'presentation': {}}],
        'public_contact_directory': [{'nation_id': 'nation-001'}, {'nation_id': 'nation-002'}],
    }


class PairedDiplomacyExperimentTests(unittest.TestCase):
    def test_public_bulletin_same_between_conditions(self):
        world = source_world()
        normal = build_turn_snapshot(source_world=world, condition=NORMAL, run_id='rA', seed_label='seed-01', turn=24, actor_index=0, message_history=[], world_state={'x': 1})
        off = build_turn_snapshot(source_world=world, condition=NO_DIPLOMACY, run_id='rB', seed_label='seed-01', turn=24, actor_index=0, message_history=[{'turn': 1, 'to_nation_ids': ['nation-001']}], world_state={'x': 1})
        check = compare_condition_invariants(normal, off)
        self.assertTrue(check['same_required_fields'], check)
        self.assertEqual(normal['public_world_bulletin'], off['public_world_bulletin'])
        self.assertEqual(off['messages_received_before_this_turn'], [])
        self.assertEqual(off['public_contact_directory'], [])

    def test_no_diplomacy_rejects_cross_border_message(self):
        world = source_world()
        snap = build_turn_snapshot(source_world=world, condition=NO_DIPLOMACY, run_id='rB', seed_label='seed-01', turn=10, actor_index=0)
        decision = {
            'document_type': 'v5-paired-leader-turn-decision-1', 'condition': NO_DIPLOMACY,
            'world_id': 'world-test', 'run_id': 'rB', 'seed_label': 'seed-01', 'turn': 10,
            'leader_id': 'leader-001', 'nation_id': 'nation-001',
            'observation_summary': '観測', 'contact_selection_reason': '外交なし',
            'outgoing_messages': [{'message_id': 'm1', 'to_nation_ids': ['nation-002'], 'body': 'hello', 'attach_self_introduction': False}],
            'proposals': [], 'private_note': None, 'no_direct_world_mutation_ack': True,
        }
        with self.assertRaises(ContractError):
            validate_decision(decision, condition=NO_DIPLOMACY, world_id='world-test', run_id='rB', seed_label='seed-01', turn=10, leader_id='leader-001', nation_id='nation-001', nation_ids=['nation-001', 'nation-002'], turn_start_snapshot=snap)

    def test_no_diplomacy_accepts_domestic_action_without_targets(self):
        world = source_world()
        snap = build_turn_snapshot(source_world=world, condition=NO_DIPLOMACY, run_id='rB', seed_label='seed-01', turn=10, actor_index=0)
        decision = {
            'document_type': 'v5-paired-leader-turn-decision-1', 'condition': NO_DIPLOMACY,
            'world_id': 'world-test', 'run_id': 'rB', 'seed_label': 'seed-01', 'turn': 10,
            'leader_id': 'leader-001', 'nation_id': 'nation-001',
            'observation_summary': '観測', 'contact_selection_reason': '外交通信は禁止されているため国内対応のみ',
            'outgoing_messages': [],
            'proposals': [{'proposal_id': 'p1', 'to_nation_ids': [], 'action_type': 'domestic_public_health_measure', 'body': '国内の井戸水検査を10件実施する計画', 'requested_world_effect': 'domestic water testing'}],
            'private_note': None, 'no_direct_world_mutation_ack': True,
        }
        result = validate_decision(decision, condition=NO_DIPLOMACY, world_id='world-test', run_id='rB', seed_label='seed-01', turn=10, leader_id='leader-001', nation_id='nation-001', nation_ids=['nation-001', 'nation-002'], turn_start_snapshot=snap)
        self.assertEqual(result['contacted_nation_ids'], [])
        self.assertEqual(result['proposal_count'], 1)

    def test_world_law_requires_all_physical_conditions(self):
        state = WorldLawState(world_id='w', turn=5, transport_capacity={'nation-001': 20}, route_eligibility={'nation-001->nation-002': True})
        proposal = {'proposal_id': 'p1', 'to_nation_ids': ['nation-002'], 'action_type': 'resource_offer', 'body': '簡易浄水材を10箱輸送する', 'requested_world_effect': 'deliver purification supplies'}
        funnel = settlement_funnel(proposal, source_nation_id='nation-001', acceptances=[], state=state)
        self.assertEqual(funnel['status'], 'not_dispatched')
        self.assertEqual(funnel['stop_reason'], 'explicit_acceptance')
        accepted = [{'from_nation_id': 'nation-002', 'to_nation_ids': ['nation-001']}]
        funnel2 = settlement_funnel(proposal, source_nation_id='nation-001', acceptances=accepted, state=state)
        self.assertEqual(funnel2['status'], 'dispatch_scheduled')
        applied = apply_dispatch_if_scheduled(funnel2, state)
        self.assertTrue(applied['world_state_mutated'])
        self.assertEqual(state.transport_capacity['nation-001'], 10)
        arrivals = process_arrivals(state, turn=6)
        self.assertEqual(len(arrivals), 1)


if __name__ == '__main__':
    unittest.main()
