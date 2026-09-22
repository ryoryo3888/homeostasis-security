from pathlib import Path
import json, hashlib, datetime, subprocess, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeostasis_v5.paired_diplomacy_experiment import (
    NORMAL, NO_DIPLOMACY, VERSION, EVENT_SCHEDULE, build_turn_snapshot,
    compare_condition_invariants, decision_schema, preregistration_seed_pairs,
    public_world_bulletin, validate_decision, ContractError,
)
from homeostasis_v5.world_law_settlement import (
    VERSION as WORLD_LAW_VERSION, WorldLawState, settlement_funnel,
    apply_dispatch_if_scheduled, process_arrivals, summarize_world_state,
)

ROOT = Path('/Users/mk/.codex/.chatgpt-projects/g-p-6aaa878f0bb08191b79262fa642e3801')
ART = ROOT / 'homeostasis-security/.artifacts'
BASE_PLAN = ART / 'v5-fixed-persona-turns-20260922-run2/plan.json'
OUT = ART / 'v5-paired-diplomacy-experiment-implementation-preflight-20260922'
SOURCE_ROOT = Path('/private/tmp/homeostasis-public-nav')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_source_world():
    plan = json.loads(BASE_PLAN.read_text())['payload']
    world = dict(plan['source_world'])
    world['public_contact_directory'] = plan['public_contact_directory']
    return plan, world


def assert_no_diplomacy_rejects_external(world):
    snap = build_turn_snapshot(source_world=world, condition=NO_DIPLOMACY, run_id='seed-01-B-NO-DIPLOMACY', seed_label='seed-01', turn=24, actor_index=0)
    decision = {
        'document_type': 'v5-paired-leader-turn-decision-1', 'condition': NO_DIPLOMACY,
        'world_id': world['world_id'], 'run_id': 'seed-01-B-NO-DIPLOMACY', 'seed_label': 'seed-01', 'turn': 24,
        'leader_id': world['pairs'][0]['leader_id'], 'nation_id': world['pairs'][0]['nation_id'],
        'observation_summary': '危機を観測', 'contact_selection_reason': '試験',
        'outgoing_messages': [{'message_id': 'bad', 'to_nation_ids': [world['pairs'][1]['nation_id']], 'body': '外交通信', 'attach_self_introduction': False}],
        'proposals': [], 'private_note': None, 'no_direct_world_mutation_ack': True,
    }
    try:
        validate_decision(decision, condition=NO_DIPLOMACY, world_id=world['world_id'], run_id='seed-01-B-NO-DIPLOMACY', seed_label='seed-01', turn=24, leader_id=world['pairs'][0]['leader_id'], nation_id=world['pairs'][0]['nation_id'], nation_ids=world['nation_ids'], turn_start_snapshot=snap)
    except ContractError:
        return True
    return False


def assert_world_law_conservative(world):
    source = world['pairs'][0]['nation_id']; target = world['pairs'][1]['nation_id']
    state = WorldLawState(world_id=world['world_id'], turn=24, unmet_need={'purification': 10}, transport_capacity={source: 20}, route_eligibility={f'{source}->{target}': True})
    proposal = {'proposal_id': 'p-test', 'to_nation_ids': [target], 'action_type': 'resource_offer', 'body': '簡易浄水材を10箱輸送する', 'requested_world_effect': 'deliver purification materials'}
    without_acceptance = settlement_funnel(proposal, source_nation_id=source, acceptances=[], state=state)
    with_acceptance = settlement_funnel(proposal, source_nation_id=source, acceptances=[{'from_nation_id': target, 'to_nation_ids': [source]}], state=state)
    applied = apply_dispatch_if_scheduled(with_acceptance, state)
    arrivals = process_arrivals(state, turn=25)
    return {
        'without_acceptance_status': without_acceptance['status'],
        'without_acceptance_stop_reason': without_acceptance['stop_reason'],
        'with_acceptance_status': with_acceptance['status'],
        'applied_dispatch': applied.get('applied'),
        'arrival_count_next_turn': len(arrivals),
        'state_summary': summarize_world_state(state),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan, world = load_source_world()
    invariant_failures = []
    sample_checks = []
    for turn in range(1, 37):
        for actor_index in range(12):
            n = build_turn_snapshot(source_world=world, condition=NORMAL, run_id='seed-01-A-NORMAL', seed_label='seed-01', turn=turn, actor_index=actor_index, message_history=[], world_state={'preflight': True})
            b = build_turn_snapshot(source_world=world, condition=NO_DIPLOMACY, run_id='seed-01-B-NO-DIPLOMACY', seed_label='seed-01', turn=turn, actor_index=actor_index, message_history=[{'turn': 1, 'to_nation_ids': [world['pairs'][actor_index]['nation_id']], 'body': 'should be hidden'}], world_state={'preflight': True})
            cmp = compare_condition_invariants(n, b)
            if not cmp['same_required_fields']:
                invariant_failures.append({'turn': turn, 'actor_index': actor_index, 'mismatches': cmp['mismatches']})
            if turn in (1,10,21,24,29) and actor_index == 0:
                sample_checks.append({'turn': turn, 'event': public_world_bulletin(turn), 'comparison': cmp})
    no_diplomacy_rejects = assert_no_diplomacy_rejects_external(world)
    world_law = assert_world_law_conservative(world)
    schema_checks = {
        'normal_schema_action_count': len(decision_schema(NORMAL)['properties']['proposals']['items']['properties']['action_type']['enum']),
        'no_diplomacy_schema_action_count': len(decision_schema(NO_DIPLOMACY)['properties']['proposals']['items']['properties']['action_type']['enum']),
        'no_diplomacy_outgoing_messages_max_items': decision_schema(NO_DIPLOMACY)['properties']['outgoing_messages'].get('maxItems'),
        'no_diplomacy_proposal_targets_max_items': decision_schema(NO_DIPLOMACY)['properties']['proposals']['items']['properties']['to_nation_ids'].get('maxItems'),
    }
    tests = subprocess.run(['python3','-m','unittest','discover','-s','tests/v5','-p','test_paired_diplomacy_experiment.py'], cwd=SOURCE_ROOT, text=True, capture_output=True)
    source_files = [
        SOURCE_ROOT/'homeostasis_v5/paired_diplomacy_experiment.py',
        SOURCE_ROOT/'homeostasis_v5/world_law_settlement.py',
        SOURCE_ROOT/'tests/v5/test_paired_diplomacy_experiment.py',
    ]
    report = {
        'document_type': 'v5-paired-diplomacy-implementation-preflight-result',
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'api_executed': False,
        'twenty_runs_started': False,
        'contract_version': VERSION,
        'world_law_version': WORLD_LAW_VERSION,
        'source_world_id': world['world_id'],
        'nation_count': len(world['nation_ids']),
        'leader_count': len(world['leader_ids']),
        'seed_pairs': preregistration_seed_pairs(),
        'event_schedule': EVENT_SCHEDULE,
        'condition_difference_policy': 'A/B snapshots must match on world, turn, actor, own nation/leader, public bulletin, and world state. Allowed differences are condition label, public_contact_directory, received diplomatic messages, and condition rules.',
        'invariant_failures': invariant_failures,
        'sample_snapshot_checks': sample_checks,
        'schema_checks': schema_checks,
        'no_diplomacy_rejects_external_contact': no_diplomacy_rejects,
        'world_law_conservative_check': world_law,
        'unit_tests': {'returncode': tests.returncode, 'stdout': tests.stdout, 'stderr': tests.stderr},
        'source_hashes': {str(p.relative_to(SOURCE_ROOT)): sha(p) for p in source_files},
        'preflight_status': 'pass' if not invariant_failures and no_diplomacy_rejects and tests.returncode == 0 and world_law['without_acceptance_status'] == 'not_dispatched' and world_law['with_acceptance_status'] == 'dispatch_scheduled' else 'fail',
        'remaining_before_api': [
            'Freeze preregistration with model/generation settings and output directories.',
            'Wire these contracts into an API runner before executing 20 runs.',
            'Run a dry prepare-only pass for all 20 manifests.',
        ],
    }
    report['report_sha256'] = hashlib.sha256(json.dumps({k:v for k,v in report.items() if k!='report_sha256'}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    (OUT/'implementation_preflight_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    md = OUT/'implementation_preflight_report.md'
    md.write_text(f'''# V5 Paired Diplomacy Experiment — Implementation Preflight\n\nAPIは実行していません。20runも開始していません。\n\n## Status\n\n`{report['preflight_status']}`\n\n## Added minimal implementation\n\n- `homeostasis_v5/paired_diplomacy_experiment.py`\n- `homeostasis_v5/world_law_settlement.py`\n- `tests/v5/test_paired_diplomacy_experiment.py`\n\n## What is fixed\n\n- TURN 1〜36 event schedule\n- NORMAL / NO-DIPLOMACY condition schemas\n- NO-DIPLOMACY forbids direct diplomatic messages and cross-border proposals\n- public_world_bulletin gives both A/B the same crisis information\n- world-law requires quantity, acceptance, route eligibility, capacity, and requested world effect before dispatch\n- dispatch and next-turn arrival can be recorded as world state mutations\n\n## Preflight results\n\n- A/B invariant failures: {len(invariant_failures)}\n- NO-DIPLOMACY rejects external contact: {no_diplomacy_rejects}\n- Unit tests return code: {tests.returncode}\n- World-law without acceptance: {world_law['without_acceptance_status']} / {world_law['without_acceptance_stop_reason']}\n- World-law with acceptance: {world_law['with_acceptance_status']}\n- Dispatch applied: {world_law['applied_dispatch']}\n- Next-turn arrivals: {world_law['arrival_count_next_turn']}\n\n## Still not executed\n\n- Gemini/API 20run\n- Final preregistration freeze\n- Dry prepare-only manifests for all 20 runs\n\n## SHA-256\n\n`{report['report_sha256']}`\n''')
    print(json.dumps({'status': report['preflight_status'], 'json': str(OUT/'implementation_preflight_report.json'), 'md': str(md), 'tests_returncode': tests.returncode, 'invariant_failures': len(invariant_failures), 'sha256': report['report_sha256']}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
