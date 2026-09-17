"""Four-stage workflow. Paid modes are plans unless explicitly confirmed."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
PLANS = {
    'probe': {'turns': 0, 'agents': 1, 'planned_api_calls': 1, 'maximum_api_calls': 1},
    'turn': {'turns': 1, 'agents': 10, 'planned_api_calls': 10, 'maximum_api_calls': 10},
    'experiment': {'turns': 8, 'agents': 10, 'planned_api_calls': 80, 'maximum_api_calls': 80},
}


def probe(client, *, audit_hook=None):
    from gemini_choice_probe import COUNTRY, COUNTRIES, initial_states
    from homeostasis_core.action_choices import build_action_choices, materialize_choice
    from homeostasis_core.feasibility import feasible_actions
    from homeostasis_core.resources import load_resource_network
    from homeostasis_core.gemini_agents import GeminiGateway
    states = initial_states()
    network = load_resource_network(Path('scenarios/resource_network_sample.json'), COUNTRIES)
    feasible = feasible_actions(COUNTRY, states, {}, network, {})
    choices = build_action_choices(feasible)
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['choice_id', 'amount', 'reason'],
              'properties': {'choice_id': {'type': 'string', 'enum': [c['choice_id'] for c in choices]},
                             'amount': {'type': 'number', 'minimum': 0, 'maximum': 100},
                             'reason': {'type': 'string'}}}
    def parse(text):
        answer = json.loads(text)
        if set(answer) != {'choice_id', 'amount', 'reason'}:
            raise ValueError('unexpected fields')
        return materialize_choice(COUNTRY, answer['choice_id'], answer['amount'], answer['reason'], choices, feasible)
    gateway = GeminiGateway(client, max_calls=1, retry_limit=1, audit_hook=audit_hook)
    action = gateway.call(COUNTRY, 1, 1, {'country_id': COUNTRY, 'private_observation': states[COUNTRY],
        'instruction': 'Independently select one choice_id and bounded amount; zero only for a zero maximum.',
        'action_choices': choices}, parse, agent_type='country', json_schema=schema)
    return {'mode': 'probe', 'include_in_research_aggregation': False, 'run_id': gateway.run_id, 'action': action, 'call_audit': gateway.calls}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=PLANS)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm')
    parser.add_argument('--seed', type=int, default=20260917)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    plan = {'mode': 'execute' if args.execute else 'dry-run', 'experiment_mode': args.mode,
            'worldlines': 1, **PLANS[args.mode], 'retries': 0}
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    if not args.execute:
        return
    if args.confirm != 'YES' or os.environ.get('HOMEOSTASIS_OFFLINE') == '1':
        raise SystemExit('Explicit --execute --confirm YES outside offline check required; API calls: 0')
    if args.output is not None:
        raise SystemExit('Paid outputs use isolated managed directories; custom output not allowed')
    env = dict(os.environ, HOMEOSTASIS_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=os.pathsep.join((str(ROOT/'tools/offline'), str(ROOT))))
    subprocess.run([sys.executable, '-B', 'tools/check.py'], env=env, check=True)
    key = os.environ.get('GEMINI_API_KEY', '')
    if not key:
        raise SystemExit('API credential unavailable; stopped without prompting or API calls')
    from homeostasis_core.transport_safety import validate_credential, runtime_manifest, exception_evidence
    validate_credential(key)  # Before client creation, audit reservation or any request.
    from homeostasis_core.api_budget import BoundedClient
    from homeostasis_core.gemini_agents import create_gemini_client
    from final_experiment_runner import run_live, _checkpoint
    from homeostasis_core.research_validation import validate_research, research_manifest
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    staging = ROOT/'results/rejected'/run_id
    staging.mkdir(parents=True, exist_ok=False)
    audit_path = staging/'transport.audit.json'
    output = staging/'result.json'
    client = None
    _checkpoint(staging/'runtime.json', runtime_manifest(ROOT, args.mode))
    try:
        client = BoundedClient(None, plan['maximum_api_calls'], audit_path)
        client.client = create_gemini_client(key)
        if args.mode == 'probe':
            output.write_text(json.dumps(probe(client, audit_hook=lambda calls: _checkpoint(staging/"decision.audit.json", {"run_id": run_id, "calls": calls})), ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            run_live(client, output, 1, args.seed, turns=plan['turns'],
                     max_calls=plan['maximum_api_calls'], retry_limit=1)
        reasons = validate_research(json.loads(output.read_text()), json.loads(audit_path.read_text())) if args.mode == 'experiment' else ['probe or one-turn validation; not research']
        manifest = research_manifest(output, reasons)
        output.with_suffix('.audit.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        destination = 'research' if not reasons else 'probe' if args.mode != 'experiment' else 'rejected'
        if destination != 'rejected':
            staging.rename(ROOT/'results'/destination/run_id)
        print(f'Result: results/{destination}/{run_id}; durable API attempts: {len(client.attempts)}; provider billing is not measured')
    except BaseException as exc:
        (staging/'failure.json').write_text(json.dumps({'status': 'rejected', 'mode': args.mode,
            'error_type': type(exc).__name__, 'api_calls': len(client.attempts) if client is not None else 0,
            'failure_evidence': exception_evidence(exc, 'client_initialization' if client is None or not client.attempts else 'execution'),
            'include_in_research_aggregation': False}, indent=2), encoding='utf-8')
        raise RuntimeError('Experiment stopped; inspect sanitized failure audit') from None
    finally:
        # Observation export only: no model, commit, push or stage advancement.
        try:
            from homeostasis_core.observability import prepare
            prepare(ROOT)
        except Exception:
            print('Status publication blocked; local run evidence retained. Run make publish-status after diagnosis.')

if __name__ == '__main__':
    main()
