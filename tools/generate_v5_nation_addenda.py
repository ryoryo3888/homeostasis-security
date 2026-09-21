"""Collect approved nation addenda serially, with no retries or state mutation."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from homeostasis_v5.nation_addendum_generation import prepare, generate_next


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare','generate-next'])
    p.add_argument('--directory', required=True, type=Path)
    p.add_argument('--proposal-directory', type=Path)
    p.add_argument('--key-file', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        if a.proposal_directory is None: raise ValueError('PROPOSAL_DIRECTORY_REQUIRED')
        result = prepare(a.directory, proposal_directory=a.proposal_directory)
    else:
        if a.key_file is None or a.key_file.is_symlink() or not a.key_file.is_file() or a.key_file.stat().st_mode & 0o077:
            raise ValueError('PRIVATE_CREDENTIAL_FILE_REQUIRED')
        result = generate_next(a.directory, credential=a.key_file.read_text().strip(), transport=httpx.HTTPTransport(retries=0))
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get('status') in ('failure','interrupted','blocked') else 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'blocked','error_type':type(exc).__name__}))
        raise SystemExit(1)
