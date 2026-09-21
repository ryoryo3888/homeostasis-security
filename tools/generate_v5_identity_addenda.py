"""Generate the approved eight fictional identity addenda one at a time."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from homeostasis_v5.identity_addendum import prepare, generate_next, review_last


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'generate-next', 'review'])
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--accept', action='store_true')
    parser.add_argument('--notes', default='')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.directory, args.source)
    elif args.action == 'review':
        result = review_last(args.directory, accepted=args.accept, notes=args.notes)
    else:
        if args.key_file.is_symlink() or args.key_file.stat().st_mode & 0o077:
            raise ValueError('PRIVATE_CREDENTIAL_FILE_REQUIRED')
        result = generate_next(args.directory, transport=httpx.HTTPTransport(retries=0),
                               credential=args.key_file.read_text().strip())
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get('status') in ('failure', 'interrupted', 'unfinalized') else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
