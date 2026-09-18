"""Free validation entry point. Does not read credentials or run a live Agent."""
import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--turns', type=int, default=8)
    args = parser.parse_args()
    def denied(*_args, **_kwargs):
        raise RuntimeError('Network disabled in V3 free validation')
    socket.socket.connect = denied
    socket.create_connection = denied
    from homeostasis_v3.physical import load_baseline
    from homeostasis_v3.network import load_network
    from homeostasis_v3.validation_runner import run_validation
    from homeostasis_v3.contracts import canonical
    baseline = load_baseline(ROOT/'scenarios/v3/synthetic_baseline.json')
    network = load_network(ROOT/'scenarios/v3/synthetic_network.json', baseline)
    print(canonical(run_validation(baseline, network, args.output, turns=args.turns)))


if __name__ == '__main__':
    main()
