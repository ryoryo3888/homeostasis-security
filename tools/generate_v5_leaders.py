"""Approved V5 persona-only generation; each network step requires a preceding review."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from homeostasis_v5.persona_generation import prepare_batch, generate_next, review_last


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'generate-next', 'review'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--continue-from', type=Path)
    parser.add_argument('--parent-evidence-hash')
    parser.add_argument('--accept', action='store_true')
    parser.add_argument('--notes', default='')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare_batch(args.directory, continuation_from=args.continue_from,
                               expected_parent_evidence_hash=args.parent_evidence_hash)
    elif args.action == 'review':
        result = review_last(args.directory, accepted=args.accept, notes=args.notes)
    else:
        if args.key_file is not None:
            if args.key_file.is_symlink() or args.key_file.stat().st_mode & 0o077:
                raise ValueError('PRIVATE_CREDENTIAL_FILE_REQUIRED')
            credential = args.key_file.read_text().strip()
        else:
            credential = os.environ.get('GEMINI_API_KEY', '')
        result = generate_next(args.directory, transport=httpx.HTTPTransport(retries=0), credential=credential)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get('status') in ('failure', 'unfinalized', 'interrupted') else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Exception messages can contain credentials or personal filesystem paths.
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
