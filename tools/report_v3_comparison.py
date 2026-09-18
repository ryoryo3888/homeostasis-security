"""Summarize saved expanded evidence without API access or changing source records."""
import hashlib
import json
from pathlib import Path
import sqlite3
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'.artifacts/v3-paid-expanded-20260919'


def summarize():
    comparison = json.loads((DATA/'comparison.json').read_text())
    with sqlite3.connect(DATA/'attempts.sqlite') as db:
        attempts = [dict(zip(('digest','state','phase','status','usage'), row))
                    for row in db.execute('SELECT * FROM attempts ORDER BY rowid')]
    total = Decimal(0); inputs = outputs = generated = validated = 0
    for a in attempts:
        u = json.loads(a['usage']) if a['usage'] else {}
        generated += int(u.get('generation_attempted', False))
        if a['status'] == 'response_validated':
            validated += 1; total += Decimal(u['estimated_cost_usd'])
            meta = u['provider_usage']; inputs += meta['promptTokenCount']
            outputs += meta['candidatesTokenCount'] + meta.get('thoughtsTokenCount',0)
    rows = []; summaries = []
    for path in sorted(DATA.glob('*/report.json')):
        r = json.loads(path.read_text())
        arm = r['arm']; seed = r['seed']
        sums = {'full':0,'partial':0,'not_established':0}
        reasons = {}; empty = 0; receipts = 0; explicit_yes = explicit_no = 0; self_withdrawals = incoming_refusals = 0
        for row in r['rows']:
            turn = row['turn']; counts = row['transactions']['counts']
            for key in sums: sums[key] += counts[key]
            for key,n in row['transactions']['reason_codes'].items(): reasons[key] = reasons.get(key,0)+n
            obs = json.loads((path.parent/f'observation-{turn}.json').read_text())
            receipts += sum(q['arrived_amount'] for q in obs['transaction_metrics']['receipts_this_turn']['value']['receipts'])
            for item in json.loads((path.parent/f'exchanges-{turn}.json').read_text()):
                request = json.loads(item['request'])
                if request['phase'] == 'consent':
                    answer = json.loads(item['answer']); empty += int(not answer['consents'])
                    explicit_yes += sum(v is True for v in answer['consents'].values())
                    explicit_no += sum(v is False for v in answer['consents'].values())
                    for c in request['payload']['choices']:
                        if answer['consents'].get(c['choice_id']) is False:
                            self_withdrawals += int(c['actor_state_id'] == request['state_id'])
                            incoming_refusals += int(c['target'] == request['state_id'])
            shortage = {k:v['value'] for k,v in row['shortage'].items()}
            rows.append({'arm':arm,'seed':seed,'turn':turn,'counts':counts,
                         'reasons':row['transactions']['reason_codes'],'shortage':shortage})
        last = r['rows'][-1] if r['rows'] else None
        summaries.append({'arm':arm,'seed':seed,'status':r['status'],'turns':r['completed_turns'],
                          'transactions':sums,'reason_codes':reasons,'empty_consent_responses':empty,
                          'explicit_yes_all_listed':explicit_yes,'explicit_no_all_listed':explicit_no,
                          'arrived_resource_units':receipts, 'self_withdrawals':self_withdrawals,
                          'incoming_refusals':incoming_refusals,
                          'cumulative_shortage':{k:v['value']['cumulative_shortage'] for k,v in last['shortage'].items()} if last else None})
    result = {'status':comparison['status'],'generation_attempts':generated,'validated_responses':validated,
              'uncached_rate_estimated_usd':str(total),'input_tokens':inputs,'output_tokens':outputs,
              'summaries':summaries,'rows':rows,'research_eligible':False}
    (DATA/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    manifest = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA.rglob('*.json'))}
    (ROOT/'.artifacts/v3-expanded-evidence-sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return result


if __name__ == '__main__':
    x = summarize()
    print(json.dumps({k:v for k,v in x.items() if k!='rows'},ensure_ascii=False,indent=2))
