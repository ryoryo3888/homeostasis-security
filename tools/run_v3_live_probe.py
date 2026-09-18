"""Prepare offline, or execute exactly the separately approved one-call protocol."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from homeostasis_v3.live_probe import prepare, execute
from homeostasis_v3.contracts import canonical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--execute', type=Path)
    parser.add_argument('--approval-digest')
    args = parser.parse_args()
    if bool(args.prepare) == bool(args.execute):
        parser.error('Choose exactly one of --prepare or --execute')
    if args.prepare:
        protocol = prepare(ROOT)
        args.prepare.parent.mkdir(parents=True, exist_ok=True)
        with args.prepare.open('x') as out:
            out.write(canonical(protocol)+'\n')
        print(canonical({'status': 'prepared', 'api_calls': 0, 'protocol_digest': protocol['protocol_digest'],
                         'pricing': protocol['pricing']}))
        return
    try:
        protocol = json.loads(args.execute.read_text())
        result = execute(ROOT, protocol, args.approval_digest, os.environ.get('GEMINI_API_KEY'))
        target = ROOT/'.artifacts/v3-live-single-probe/result.json'
        with target.open('x') as out:
            out.write(canonical(result)+'\n')
    except Exception:
        print('Probe stopped. No automatic retry. Review the local attempt journal; no secrets printed.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Connection response validated. Adopted TURNs: 0. Result saved locally.')


if __name__ == '__main__':
    main()
