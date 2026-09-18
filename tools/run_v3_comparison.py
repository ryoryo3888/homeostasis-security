"""Prepare the paired controls offline, then explicitly run the paid pilot once."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from homeostasis_v3.comparison import SEEDS, protocol, deterministic, run_arm, compare
from homeostasis_v3.comparison_transport import PilotExchange
from homeostasis_v3.choices import ensure
from homeostasis_v3.contracts import digest
from homeostasis_v3.validation_runner import _write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-paid', action='store_true')
    p.add_argument('--protocol-digest')
    args = p.parse_args()
    directory = ROOT/'.artifacts/v3-paid-pilot-20260919'
    spec = protocol(ROOT)
    if not args.execute_paid:
        directory.mkdir(parents=True, exist_ok=False)
        _write(directory/'protocol.json', spec)
        for seed in SEEDS:
            run_arm(ROOT, directory/f'control-{seed}', seed=seed, arm='deterministic', exchange=deterministic)
        print('Control preparation complete; remote API calls: 0; protocol digest: '+digest(spec))
        return
    ensure(json.loads((directory/'protocol.json').read_text()) == spec and args.protocol_digest == digest(spec),
           'REVIEWED_PROTOCOL_REQUIRED')
    ensure(not (directory/'paid-start.json').exists(), 'PAID_RESTART_FORBIDDEN')
    key = os.environ.get('GEMINI_API_KEY')
    ensure(bool(key), 'CREDENTIAL_REQUIRED')
    with (directory/'paid-start.json').open('x') as f:
        json.dump({'protocol_digest': digest(spec), 'status': 'started_no_auto_resume'}, f)
        f.flush(); os.fsync(f.fileno())
    exchange = PilotExchange(ROOT, key)
    report = {'status': 'running', 'pairs': [], 'research_eligible': False,
              'artifact_class': 'validation_run', 'publication_status': 'withheld'}
    _write(directory/'comparison.json', report)
    try:
        for seed in SEEDS:
            exchange.seed = seed
            treatment = run_arm(ROOT, directory/f'gemini-{seed}', seed=seed, arm='gemini', exchange=exchange)
            control = json.loads((directory/f'control-{seed}'/'report.json').read_text())
            report['pairs'].append(compare(control, treatment))
            _write(directory/'comparison.json', report)
        report['status'] = 'completed'
    except Exception:
        report['status'] = 'technical_failure_no_retry'
        raise RuntimeError('Paid pilot stopped. Inspect local evidence; no automatic retry.') from None
    finally:
        report['attempts'] = exchange.journal.records()
        _write(directory/'comparison.json', report)
        exchange.close()
    print('Paired pilot completed. Results saved locally; not published or promoted to formal research.')


if __name__ == '__main__':
    try: main()
    except Exception:
        print('Pilot stopped; inspect protocol, credential availability and local reports. No automatic retry.', file=sys.stderr)
        raise SystemExit(1) from None
