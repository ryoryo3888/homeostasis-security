from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import hashlib
import itertools
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeostasis_v4.evidence import read_record, verify
from homeostasis_v5.world_law_settlement import WorldLawState, settlement_funnel, apply_dispatch_if_scheduled, process_arrivals, summarize_world_state

ROOT = Path(__file__).resolve().parents[1]
ART = Path('/Users/mk/.codex/.chatgpt-projects/g-p-6aaa878f0bb08191b79262fa642e3801/homeostasis-security/.artifacts')
OUT = ROOT / 'results/v5-generated-nations/offline-paired-diplomacy-derived-20260922'
SEEDS = [9201, 9203, 9209, 9221, 9227, 9239, 9241, 9257, 9277, 9281]
BATCHES = [
    'v5-fixed-persona-turns-20260922-run2',
    'v5-fixed-persona-turns-4-6-20260922',
    'v5-fixed-persona-turns-7-9-20260922',
    'v5-fixed-persona-turns-10-12-vegetable-fresh-produce-comms-20260922',
    'v5-fixed-persona-turns-13-15-vegetable-event-20260922',
    'v5-fixed-persona-turns-16-20-vegetable-event-20260922',
    'v5-fixed-persona-turns-21-23-security-action-space-20260922',
    'v5-fixed-persona-turns-24-26-waterborne-illness-event-20260922-v2',
    'v5-fixed-persona-turns-27-36-waterborne-illness-continuation-20260922',
]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def attempt_index(path: Path) -> int:
    return int(path.name.split('-')[-1])


def load_decisions():
    decisions = []
    evidence = []
    seen = set()
    for batch in BATCHES:
        root = ART / batch
        for attempt in sorted(root.glob('attempt-*'), key=attempt_index):
            checked = verify(attempt)
            if checked['status'] != 'success':
                continue
            output = read_record(attempt / 'DERIVED/output.json')['report']['output']
            key = (output['turn'], output['leader_id'], output['nation_id'])
            if key in seen:
                continue
            seen.add(key)
            decisions.append(output)
            evidence.append({'batch': batch, 'attempt': attempt.name, 'turn': output['turn'], 'leader_id': output['leader_id'], 'nation_id': output['nation_id'], 'evidence_hash': checked['evidence_hash']})
    decisions.sort(key=lambda d: (d['turn'], d['leader_id'], d['nation_id']))
    return decisions, evidence


def directed_edges(decisions):
    edges = Counter()
    for d in decisions:
        src = d['nation_id']
        for item in d.get('outgoing_messages', []) + d.get('proposals', []):
            for dst in item.get('to_nation_ids', []):
                if dst != src:
                    edges[(src, dst)] += 1
    return edges


def reciprocal_count(edges):
    pairs = set()
    for a, b in edges:
        if (b, a) in edges:
            pairs.add(tuple(sorted((a, b))))
    return len(pairs)


def strip_diplomacy(decision):
    stripped = dict(decision)
    stripped['outgoing_messages'] = [m for m in decision.get('outgoing_messages', []) if not m.get('to_nation_ids')]
    stripped['proposals'] = [p for p in decision.get('proposals', []) if not p.get('to_nation_ids')]
    return stripped


def condition_decisions(source, condition):
    if condition == 'NORMAL':
        return [dict(d) for d in source]
    if condition == 'NO-DIPLOMACY':
        return [strip_diplomacy(d) for d in source]
    raise ValueError(condition)


def settle(decisions):
    world_id = decisions[0]['world_id'] if decisions else 'unknown'
    state = WorldLawState(world_id=world_id, turn=1, unmet_need={}, transport_capacity={}, route_eligibility={})
    by_turn = defaultdict(list)
    for d in decisions:
        by_turn[d['turn']].append(d)
    turns = []
    for turn in range(1, 37):
        state.turn = turn
        arrivals = process_arrivals(state, turn=turn)
        funnels = []
        for d in by_turn.get(turn, []):
            for p in d.get('proposals', []):
                funnel = settlement_funnel(p, source_nation_id=d['nation_id'], acceptances=[], state=state)
                funnels.append(apply_dispatch_if_scheduled(funnel, state))
        turns.append({'turn': turn, 'arrivals': arrivals, 'proposal_funnels': funnels, 'world_state_summary': summarize_world_state(state)})
    return turns, summarize_world_state(state)


def metrics(decisions):
    edges = directed_edges(decisions)
    message_count = sum(len(d.get('outgoing_messages', [])) for d in decisions)
    proposal_count = sum(len(d.get('proposals', [])) for d in decisions)
    message_recipients = sum(len(m.get('to_nation_ids', [])) for d in decisions for m in d.get('outgoing_messages', []))
    action_counts = Counter(p.get('action_type') for d in decisions for p in d.get('proposals', []))
    settlement_by_turn, final_world = settle(decisions)
    funnels = list(itertools.chain.from_iterable(t['proposal_funnels'] for t in settlement_by_turn))
    return {
        'leader_judgments': len(decisions),
        'turns': sorted(set(d['turn'] for d in decisions)),
        'outgoing_messages': message_count,
        'message_recipients': message_recipients,
        'proposals': proposal_count,
        'directed_edges': len(edges),
        'reciprocal_pairs': reciprocal_count(edges),
        'nations_with_outgoing_contact': len({a for a, _ in edges}),
        'nations_reached': len({b for _, b in edges}),
        'isolated_nations': 12 - len({n for edge in edges for n in edge}),
        'action_type_counts': dict(sorted(action_counts.items())),
        'settlement': {
            'proposal_funnels': len(funnels),
            'dispatch_scheduled': sum(1 for f in funnels if f.get('status') == 'dispatch_scheduled'),
            'not_dispatched': sum(1 for f in funnels if f.get('status') == 'not_dispatched'),
            'arrivals': final_world['arrival_count'],
            'world_state_mutations': final_world['world_state_mutation_count'],
            'top_stop_reasons': dict(Counter(f.get('stop_reason') for f in funnels if f.get('stop_reason')).most_common()),
        },
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source, evidence = load_decisions()
    if len(source) != 432:
        raise RuntimeError(f'EXPECTED_432_DECISIONS_GOT_{len(source)}')
    runs = []
    for idx, seed in enumerate(SEEDS, 1):
        seed_label = f'seed-{idx:02d}'
        normal = condition_decisions(source, 'NORMAL')
        no_diplomacy = condition_decisions(source, 'NO-DIPLOMACY')
        nm = metrics(normal)
        bm = metrics(no_diplomacy)
        runs.append({
            'seed_label': seed_label,
            'seed_value': seed,
            'normal_run_id': f'{seed_label}-A-NORMAL-OFFLINE',
            'no_diplomacy_run_id': f'{seed_label}-B-NO-DIPLOMACY-OFFLINE',
            'api_executed': False,
            'seed_role': 'offline paired audit label; no new behavior generation',
            'conditions': {'NORMAL': nm, 'NO_DIPLOMACY': bm},
            'paired_difference': {
                'outgoing_messages': nm['outgoing_messages'] - bm['outgoing_messages'],
                'message_recipients': nm['message_recipients'] - bm['message_recipients'],
                'proposals': nm['proposals'] - bm['proposals'],
                'directed_edges': nm['directed_edges'] - bm['directed_edges'],
                'reciprocal_pairs': nm['reciprocal_pairs'] - bm['reciprocal_pairs'],
                'dispatch_scheduled': nm['settlement']['dispatch_scheduled'] - bm['settlement']['dispatch_scheduled'],
                'arrivals': nm['settlement']['arrivals'] - bm['settlement']['arrivals'],
            },
        })
    summary = {
        'document_type': 'v5-offline-paired-diplomacy-derived-comparison-1',
        'status': 'derived_from_existing_36_turn_observation_no_api',
        'api_executed': False,
        'source': {
            'turns': [1, 36],
            'leader_judgments': len(source),
            'batches': BATCHES,
            'source_decisions_sha256': digest(source),
            'source_evidence_count': len(evidence),
        },
        'method': {
            'NORMAL': 'Use existing 36-turn observed decisions as recorded.',
            'NO_DIPLOMACY': 'Use the same decisions but remove other-nation messages and other-nation proposals before deriving network and settlement metrics.',
            'not_generated': 'No new leader behavior, persona, nation, crisis, or turn output is generated.',
            'settlement': 'Existing world-law funnel is applied conservatively. Speech/proposal alone does not create dispatch or arrival.',
        },
        'runs': runs,
        'aggregate': {
            'normal': runs[0]['conditions']['NORMAL'],
            'no_diplomacy': runs[0]['conditions']['NO_DIPLOMACY'],
            'all_10_seed_labels_identical_reason': 'Offline deterministic derivation from the same frozen 36-turn observation; seeds are retained as preregistered paired labels, not random generators.',
        },
    }
    summary['summary_sha256'] = digest({k: v for k, v in summary.items() if k != 'summary_sha256'})
    (OUT / 'offline_paired_diplomacy_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    md = f"""# V5 オフライン派生比較 — 外交通信あり／なし\n\nAPIは実行していません。既存の36ターン観測だけから派生集計しました。\n\n## 方法\n\n- NORMAL: 既存36ターンの外交通信・提案をそのまま使う。\n- NO-DIPLOMACY: 同じ36ターン記録から、他国宛の通信・提案を取り除いて集計する。\n- 人物・国家・危機内容・ターン列・物理成立条件は変更しない。\n- 新しいLeader判断は生成しない。\n\n## 入力\n\n- TURN: 1〜36\n- Leader判断: {len(source)}\n- seed label: 10組（オフライン派生比較用ラベル）\n\n## 結果\n\n| 指標 | 外交通信あり | 外交通信なし | 差分 |\n|---|---:|---:|---:|\n| 外交通信 | {runs[0]['conditions']['NORMAL']['outgoing_messages']} | {runs[0]['conditions']['NO_DIPLOMACY']['outgoing_messages']} | {runs[0]['paired_difference']['outgoing_messages']} |\n| 通信宛先延べ | {runs[0]['conditions']['NORMAL']['message_recipients']} | {runs[0]['conditions']['NO_DIPLOMACY']['message_recipients']} | {runs[0]['paired_difference']['message_recipients']} |\n| 提案 | {runs[0]['conditions']['NORMAL']['proposals']} | {runs[0]['conditions']['NO_DIPLOMACY']['proposals']} | {runs[0]['paired_difference']['proposals']} |\n| 接触エッジ | {runs[0]['conditions']['NORMAL']['directed_edges']} | {runs[0]['conditions']['NO_DIPLOMACY']['directed_edges']} | {runs[0]['paired_difference']['directed_edges']} |\n| 双方向関係 | {runs[0]['conditions']['NORMAL']['reciprocal_pairs']} | {runs[0]['conditions']['NO_DIPLOMACY']['reciprocal_pairs']} | {runs[0]['paired_difference']['reciprocal_pairs']} |\n| 物理dispatch成立 | {runs[0]['conditions']['NORMAL']['settlement']['dispatch_scheduled']} | {runs[0]['conditions']['NO_DIPLOMACY']['settlement']['dispatch_scheduled']} | {runs[0]['paired_difference']['dispatch_scheduled']} |\n| 到着 | {runs[0]['conditions']['NORMAL']['settlement']['arrivals']} | {runs[0]['conditions']['NO_DIPLOMACY']['settlement']['arrivals']} | {runs[0]['paired_difference']['arrivals']} |\n\n## 解釈\n\nこの比較は、新しい世界を生成したものではありません。既存36ターン世界で観測された外交通信を残した場合と、同じ記録から外交通信だけを取り除いた場合の派生比較です。したがって、NO-DIPLOMACY側の国内判断を新たに推定していません。\n\nsummary sha256: `{summary['summary_sha256']}`\n"""
    (OUT / 'offline_paired_diplomacy_summary.md').write_text(md, encoding='utf-8')
    print(json.dumps({'status': 'success', 'out': str(OUT), 'summary_sha256': summary['summary_sha256'], 'api_executed': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
