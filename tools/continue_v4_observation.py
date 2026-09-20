"""Prepare/execute a fixed-path continuation without regenerating saved replies."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeostasis_v3.contracts import digest
from homeostasis_v4.observation_continue import inspect_parent, continue_observation
from v2_paid_pilot import load_credential

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent-directory', type=Path, required=True)
    parser.add_argument('--parent-digest', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--credential-file', type=Path)
    parser.add_argument('--protocol-digest')
    args = parser.parse_args()
    if not args.execute:
        _, stopped, settings, _, _ = inspect_parent(args.parent_directory, args.parent_digest)
        print(json.dumps({'protocol': settings, 'protocol_digest': digest(settings),
            'reused_generations': stopped['api_calls'], 'remaining_generations': settings['max_calls'] - stopped['api_calls'],
            'output_directory': str(args.parent_directory.with_name(args.parent_directory.name + '-completion'))}, indent=2))
        return
    if not args.credential_file or not args.protocol_digest:
        parser.error('execution requires credential-file and protocol-digest')
    print(json.dumps(continue_observation(args.parent_directory, load_credential(args.credential_file),
        expected_parent_digest=args.parent_digest, protocol_digest=args.protocol_digest), indent=2))

if __name__ == '__main__':
    main()
