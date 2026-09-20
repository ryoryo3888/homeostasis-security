"""Offline Evidence Format 1 integrity check; never calls a model."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeostasis_v4.evidence import verify

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--expected-evidence-hash')
    args = parser.parse_args()
    print(json.dumps(verify(args.directory, expected_evidence_hash=args.expected_evidence_hash),
                     ensure_ascii=False, indent=2))
