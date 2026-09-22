"""Prepare, dry-run, or execute the V5 paired diplomacy 20run batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx

from homeostasis_v5.paired_diplomacy_generation import prepare, dry_run_validate, generate_next


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'dry-run', 'generate-next', 'run-one', 'run-all'])
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--prepare-dir', type=Path)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--max-calls', type=int, default=1)
    args = parser.parse_args()
    if args.action == 'prepare':
        kwargs = {'prepare_dir': args.prepare_dir} if args.prepare_dir else {}
        result = prepare(args.directory, **kwargs)
    elif args.action == 'dry-run':
        kwargs = {'prepare_dir': args.prepare_dir} if args.prepare_dir else {}
        result = dry_run_validate(args.directory, **kwargs)
    else:
        if (args.key_file is None or args.key_file.is_symlink()
                or not args.key_file.is_file() or args.key_file.stat().st_mode & 0o077):
            raise ValueError('PRIVATE_CREDENTIAL_FILE_REQUIRED')
        result = None
        limit = args.max_calls if args.action in ('run-one', 'run-all') else 1
        for _ in range(limit):
            result = generate_next(args.directory, credential=args.key_file.read_text().strip(),
                                   transport=httpx.HTTPTransport(retries=0), run_id=args.run_id)
            if result.get('status') in ('failure', 'interrupted'):
                break
            if args.action == 'run-one' and (result.get('run_complete') or result.get('status') == 'complete'):
                break
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get('status') in ('failure', 'interrupted') else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__, 'error': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
