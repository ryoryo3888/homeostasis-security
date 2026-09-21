"""Private, phase-by-phase life-first persona generation. No retries or simulation."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from homeostasis_v5.life_first_generation import prepare_batch, generate_next, review_last


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'generate-next', 'review'])
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--budget-usd')
    p.add_argument('--key-file', type=Path)
    p.add_argument('--accept', action='store_true')
    a = p.parse_args()
    if a.action == 'prepare':
        if a.budget_usd is None:
            raise ValueError('BUDGET_REQUIRED')
        result = prepare_batch(a.directory, budget_usd=a.budget_usd)
    elif a.action == 'review':
        result = review_last(a.directory, accepted=a.accept)
    else:
        if a.key_file is not None:
            if a.key_file.is_symlink() or a.key_file.stat().st_mode & 0o077:
                raise ValueError('PRIVATE_CREDENTIAL_FILE_REQUIRED')
            credential = a.key_file.read_text().strip()
        else:
            credential = os.environ.get('GEMINI_API_KEY', '')
        result = generate_next(a.directory, transport=httpx.HTTPTransport(retries=0), credential=credential)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get('status') in ('failure', 'interrupted', 'unfinalized') else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
