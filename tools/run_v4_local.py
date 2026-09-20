"""Prepare, run once, or replay a local V4 pilot. Never uses paid API keys."""
import argparse
import json
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeostasis_v3.contracts import digest
from homeostasis_v4.local_observation import execute, prepare, replay, validate_runtime_limits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--replay', type=Path)
    parser.add_argument('--model', default='qwen3:1.7b')
    parser.add_argument('--seed', type=int, default=73)
    parser.add_argument('--turns', type=int, default=2)
    parser.add_argument('--num-ctx', type=int, default=16384)
    parser.add_argument('--num-predict', type=int, default=2048)
    parser.add_argument('--structured-output', action='store_true',
                        help='Send the existing reply schema as the local API output format')
    parser.add_argument('--thinking', action='store_true',
                        help='Enable model reasoning through the chat API; final answer only drives the world')
    parser.add_argument('--request-timeout', type=int, default=180,
                        help='Seconds per HTTP operation, fixed in the prepared protocol')
    parser.add_argument('--run-deadline', type=int, default=1200,
                        help='Seconds after which no further generation may start')
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.replay:
        result = replay(args.replay)
    else:
        saved = None
        if args.execute:
            if not args.prepared or not args.output:
                parser.error('--execute requires --prepared and --output')
            saved = json.loads(args.prepared.read_text())
            timeout = saved['protocol']['request_timeout_seconds']
            deadline = saved['protocol']['run_deadline_seconds']
        else:
            timeout, deadline = args.request_timeout, args.run_deadline
        validate_runtime_limits(timeout, deadline)
        with httpx.Client(transport=httpx.HTTPTransport(retries=0), trust_env=False,
                          follow_redirects=False, timeout=timeout) as client:
            if args.prepare:
                settings = prepare(client, model=args.model, seed=args.seed, turns=args.turns,
                                   num_ctx=args.num_ctx, num_predict=args.num_predict,
                                   structured_output=args.structured_output,
                                   thinking=args.thinking,
                                   request_timeout_seconds=timeout, run_deadline_seconds=deadline)
                result = {'protocol': settings, 'protocol_digest': digest(settings)}
            else:
                result = execute(args.output, saved['protocol'],
                                 protocol_digest=saved['protocol_digest'], client=client)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('status') in ('failure', 'interrupted', 'unfinalized') else 0


if __name__ == '__main__':
    raise SystemExit(main())
