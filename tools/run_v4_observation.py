"""Prepare or explicitly execute one bounded V4 exploratory observation."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from homeostasis_v3.contracts import digest
from homeostasis_v4.observation_run import execute, profile
from v2_paid_pilot import load_credential


def main():
    parser = argparse.ArgumentParser(description='V4自由対話と有限世界の観測。準備はAPI通信なし。')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output-directory', type=Path)
    parser.add_argument('--credential-file', type=Path)
    parser.add_argument('--protocol-digest')
    args = parser.parse_args()
    if not args.execute:
        settings = profile()
        print(json.dumps({'protocol': settings, 'protocol_digest': digest(settings)}, ensure_ascii=False, indent=2))
        return
    if not all((args.output_directory, args.credential_file, args.protocol_digest)):
        parser.error('execution requires output-directory, credential-file, protocol-digest')
    result = execute(args.output_directory, load_credential(args.credential_file), protocol_digest=args.protocol_digest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
