"""Extend the observed five-turn world by three turns, with no automatic retry."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeostasis_v4.observation_extend import prepare_extension, extend_observation
from v2_paid_pilot import load_credential

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--parent-directory', type=Path, required=True)
    p.add_argument('--parent-digest', required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--credential-file', type=Path)
    p.add_argument('--protocol-digest')
    args = p.parse_args()
    if not args.execute:
        plan, _, _ = prepare_extension(args.parent_directory, args.parent_digest)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    if not args.credential_file or not args.protocol_digest:
        p.error('execution requires credential-file and protocol-digest')
    result = extend_observation(args.parent_directory, load_credential(args.credential_file),
        expected_parent_digest=args.parent_digest, protocol_digest=args.protocol_digest)
    print(json.dumps({k:v for k,v in result.items() if k != 'usage'}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
