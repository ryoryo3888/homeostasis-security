from pathlib import Path
import json, hashlib, datetime, subprocess, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeostasis_v5.paired_diplomacy_experiment import (
    NORMAL, NO_DIPLOMACY, VERSION, EVENT_SCHEDULE, COMMUNICATION_BUDGET_CHARS,
    preregistration_seed_pairs, public_world_bulletin, condition_rules,
)
from homeostasis_v5.world_law_settlement import VERSION as WORLD_LAW_VERSION

ROOT = Path('/Users/mk/.codex/.chatgpt-projects/g-p-6aaa878f0bb08191b79262fa642e3801')
ART = ROOT / 'homeostasis-security/.artifacts'
BASE_PLAN = ART / 'v5-fixed-persona-turns-20260922-run2/plan.json'
OUT = ART / 'v5-paired-diplomacy-experiment-preregistration-20260922'
SOURCE_ROOT = Path('/private/tmp/homeostasis-public-nav')
MODEL = 'gemini-3.6-flash'
GENERATION_SETTINGS = {
    'candidateCount': 1,
    'maxOutputTokens': 8192,
    'responseMimeType': 'application/json',
    'temperature': 'current V5 runner setting; frozen in manifest before execution',
    'retry_count': 0,
    'concurrency': 1,
}
SEED_VALUES = [9201, 9203, 9209, 9221, 9227, 9239, 9241, 9257, 9277, 9281]
SEED_LABELS = [f'seed-{i:02d}' for i in range(1, 11)]

def stable_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_base():
    plan = json.loads(BASE_PLAN.read_text())['payload']
    source_world = dict(plan['source_world'])
    source_world['public_contact_directory'] = plan['public_contact_directory']
    return plan, source_world

def source_hashes():
    files = [
        SOURCE_ROOT/'homeostasis_v5/paired_diplomacy_experiment.py',
        SOURCE_ROOT/'homeostasis_v5/world_law_settlement.py',
        SOURCE_ROOT/'tests/v5/test_paired_diplomacy_experiment.py',
        SOURCE_ROOT/'tools/preflight_v5_paired_diplomacy_experiment.py',
        SOURCE_ROOT/'tools/prepare_v5_paired_diplomacy_preregistration.py',
    ]
    return {str(p.relative_to(SOURCE_ROOT)): file_hash(p) for p in files if p.exists()}

def make_manifest(seed_label, seed_value, condition, pair_index, source_world_hash, prereg_hash=None):
    suffix = 'A-NORMAL' if condition == NORMAL else 'B-NO-DIPLOMACY'
    run_id = f'{seed_label}-{suffix}'
    manifest = {
        'document_type': 'v5-paired-diplomacy-run-manifest-prepare-only',
        'status': 'prepared_not_executed',
        'run_id': run_id,
        'pair_index': pair_index,
        'seed_label': seed_label,
        'seed_value_fixed_before_execution': seed_value,
        'condition': condition,
        'paired_counterfactual_run_id': f'{seed_label}-B-NO-DIPLOMACY' if condition == NORMAL else f'{seed_label}-A-NORMAL',
        'turns': {'start': 1, 'end': 36, 'turn_count': 36, 'turn_length_days': 30},
        'world': {'number_of_worlds': 1, 'nation_count': 12, 'leader_count': 12, 'source_world_sha256': source_world_hash},
        'model': MODEL,
        'generation_settings': GENERATION_SETTINGS,
        'condition_rules': condition_rules(condition),
        'event_schedule': EVENT_SCHEDULE,
        'public_world_bulletin_schedule': [public_world_bulletin(turn) for turn in range(1, 37)],
        'world_law_version': WORLD_LAW_VERSION,
        'contract_version': VERSION,
        'raw_output_required': ['run manifest', 'seed', 'condition', 'model identity', 'generation settings', 'input', 'leader decision', 'agent response', 'messages', 'proposals', 'requested_world_effect', 'world-law judgement', 'TURN', 'world state', 'dispatch', 'arrival', 'failure', 'execution end'],
        'derived_output_required': ['primary outcomes', 'secondary outcomes', 'network metrics', 'physical transaction funnel', 'crisis response timeline', 'pairwise comparison rows'],
        'api_executed': False,
        'preregistration_sha256': prereg_hash,
    }
    manifest['manifest_sha256'] = stable_hash({k:v for k,v in manifest.items() if k != 'manifest_sha256'})
    return manifest

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base_plan, source_world = load_base()
    source_world_hash = stable_hash(source_world)
    seed_pairs = []
    for idx, (label, value) in enumerate(zip(SEED_LABELS, SEED_VALUES), 1):
        seed_pairs.append({'pair_index': idx, 'seed_label': label, 'seed_value': value, 'normal_run_id': f'{label}-A-NORMAL', 'no_diplomacy_run_id': f'{label}-B-NO-DIPLOMACY'})
    prereg = {
        'document_type': 'v5-paired-diplomacy-preregistration',
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'frozen_prepare_only_not_executed',
        'api_executed': False,
        'research_question': '同じ初期条件・同じ危機系列を持つV5 AI国家社会において、自律的な国家間外交の有無だけを変えたとき、危機対応・資源移転・社会の恒常性に再現可能な差が現れるか。',
        'hypotheses': {
            'non_directional_primary': 'NORMAL と NO-DIPLOMACY の間で、物理支援dispatch/arrival、unmet need、network metrics、危機対応timelineに差が生じる可能性がある。方向は事前固定しない。',
            'null': '外交通信の有無による主要アウトカム差は観測されない、またはTURN36まで両条件とも物理支援が成立しない可能性がある。'
        },
        'seed_pairs': seed_pairs,
        'run_count': 20,
        'paired_design': 'Each seed has one NORMAL and one NO-DIPLOMACY run. A/B differ by autonomous cross-border diplomacy permissions only.',
        'turns_fixed': {'start': 1, 'end': 36, 'turn_count': 36},
        'conditions': {
            NORMAL: {'definition': 'Current V5-style autonomous diplomacy: leaders may select contacts, send messages, share information, propose cooperation, make resource offers, and request world effects subject to world-law.', 'rules': condition_rules(NORMAL)},
            NO_DIPLOMACY: {'definition': 'Autonomous cross-border diplomacy disabled. No direct diplomatic messages, cross-border proposals, resource_offer to other nations, diplomatic acceptance/rejection, or negotiation. Public crisis information and own-state observation remain available.', 'rules': condition_rules(NO_DIPLOMACY)},
        },
        'event_schedule': EVENT_SCHEDULE,
        'public_world_bulletin': {'definition': 'Identical public crisis/event bulletin visible in both conditions. Does not create a diplomatic channel or assign responsibility.', 'schedule': [public_world_bulletin(turn) for turn in range(1, 37)]},
        'primary_outcomes': [
            'TURN from crisis onset to first physical support dispatch; save as not established if absent by TURN36',
            'TURN from crisis onset to first physical support arrival; save as not established if absent by TURN36',
            'TURN from crisis onset to homeostasis recovery condition; save as TURN36まで未回復 if absent',
            'unmet need at TURN36',
            'number of physical world state changes established by world-law',
        ],
        'secondary_outcomes': ['messages count','proposals count','resource_offer count','explicit acceptance count','rejection count','dispatch count','arrival count','directed contact edge count','bidirectional relationship count','isolated nation count','unreached nation count','network density per TURN','reciprocity per TURN','max degree per TURN','hub candidates per TURN','hub persistence','support requests by crisis','first response TURN by crisis','resource bottleneck','logistics bottleneck','communication bottleneck','institutional bottleneck','final world state'],
        'success_failure_definitions': {
            'successful_run': 'All planned 36 TURN x 12 leader decisions complete, world-law settlement runs, final manifest written.',
            'technical_failure': 'Provider/runtime/schema/validation failure prevents a run from completing as specified. Preserve RAW failure evidence and exclude from substantive pairwise outcome while counting as comparison impossible.',
            'substantive_non_establishment': 'No dispatch/arrival/recovery by TURN36. This is a valid result, not technical failure.',
        },
        'stop_conditions': ['Do not run extra turns beyond TURN36','Stop a run on schema/runtime/provider failure and preserve evidence','Stop whole batch if same technical failure repeats in 3 consecutive runs before diagnosis','Do not alter conditions after observing results','Do not count proposal or speech as physical support'],
        'model': MODEL,
        'generation_settings': GENERATION_SETTINGS,
        'world_law_settlement': {
            'version': WORLD_LAW_VERSION,
            'dispatch_requirements': ['explicit quantity','counterpart acceptance for cross-border action','route eligibility','transport capacity','requested_world_effect','action type allows physical review'],
            'arrival_rule': 'A scheduled dispatch records arrival on a later turn according to world-law; speech alone does not create arrival.',
            'unmet_need_rule': 'Unmet need is read from/updated by world-law state only, not by rhetoric.',
        },
        'initial_world': {'source_world_sha256': source_world_hash, 'nation_count': len(source_world['nation_ids']), 'leader_count': len(source_world['leader_ids']), 'base_plan_sha256': stable_hash(base_plan)},
        'leader_generation_condition': 'Fixed existing V5 leaders; no regeneration, no selection after results.',
        'nation_generation_condition': 'Fixed existing V5 nations, geography, resources; no change after results.',
        'evaluation_method': 'Pairwise comparison seed-01 A vs B through seed-10 A vs B. Count A improved, B improved, equal, and comparison impossible for each primary outcome. Do not infer causality beyond this design.',
        'raw_derived_policy': 'RAW is never rewritten. Analysis and tables are DERIVED. Technical failures are preserved separately from substantive results.',
        'source_hashes': source_hashes(),
        'interpretation_bans': ['Do not assume diplomacy improves outcomes before results','Do not call correlation causation','Do not claim Singularity or Leadership discovery','Do not generalize from one run or one pair'],
    }
    prereg['preregistration_sha256'] = stable_hash({k:v for k,v in prereg.items() if k != 'preregistration_sha256'})
    (OUT/'preregistration.json').write_text(json.dumps(prereg, ensure_ascii=False, indent=2))
    manifests_dir = OUT/'manifests'
    manifests_dir.mkdir(exist_ok=True)
    manifests = []
    for pair in seed_pairs:
        for condition in (NORMAL, NO_DIPLOMACY):
            manifest = make_manifest(pair['seed_label'], pair['seed_value'], condition, pair['pair_index'], source_world_hash, prereg['preregistration_sha256'])
            path = manifests_dir / f"{manifest['run_id']}.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
            manifests.append({'run_id': manifest['run_id'], 'condition': condition, 'seed_label': pair['seed_label'], 'seed_value': pair['seed_value'], 'path': str(path.relative_to(ROOT)), 'manifest_sha256': manifest['manifest_sha256']})
    summary = {
        'document_type': 'v5-paired-diplomacy-prepare-only-summary',
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'api_executed': False,
        'preregistration_path': str((OUT/'preregistration.json').relative_to(ROOT)),
        'preregistration_sha256': prereg['preregistration_sha256'],
        'manifest_count': len(manifests),
        'seed_pairs': seed_pairs,
        'manifests': manifests,
    }
    summary['summary_sha256'] = stable_hash({k:v for k,v in summary.items() if k != 'summary_sha256'})
    (OUT/'prepare_only_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    md = OUT/'prepare_only_summary.md'
    md.write_text(f'''# V5 Paired Diplomacy Experiment — Prepare-only Summary\n\nAPIは実行していません。20runも開始していません。\n\n## Frozen preregistration\n\n- path: `{summary['preregistration_path']}`\n- sha256: `{prereg['preregistration_sha256']}`\n\n## Fixed seeds\n\n{json.dumps(seed_pairs, ensure_ascii=False, indent=2)}\n\n## Manifests\n\n- manifest count: {len(manifests)}\n- NORMAL: 10\n- NO-DIPLOMACY: 10\n\n## Conditions\n\n- A / NORMAL: autonomous cross-border diplomacy enabled.\n- B / NO-DIPLOMACY: direct diplomatic messages, cross-border proposals, resource_offer to other nations, negotiation, and explicit diplomatic acceptance/rejection disabled. Public crisis bulletin remains visible.\n\n## Event schedule\n\n{json.dumps(EVENT_SCHEDULE, ensure_ascii=False, indent=2)}\n\n## Primary Outcomes\n\n{json.dumps(prereg['primary_outcomes'], ensure_ascii=False, indent=2)}\n\n## Next step\n\nDo not run API until explicitly approved.\n\n## Summary SHA-256\n\n`{summary['summary_sha256']}`\n''')
    print(json.dumps({'status':'prepared_only','api_executed':False,'preregistration':str(OUT/'preregistration.json'),'summary':str(md),'manifest_count':len(manifests),'seeds':seed_pairs,'preregistration_sha256':prereg['preregistration_sha256'],'summary_sha256':summary['summary_sha256']}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
