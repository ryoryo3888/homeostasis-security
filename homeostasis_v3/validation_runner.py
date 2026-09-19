"""Multi-TURN offline validation, explicitly ineligible for formal research.

This host runs synthetic abstention through all eight JSON country boundaries.
It verifies laws, durable checkpoints, observations and saved-input replay;
it does not discover, predict or script a research world's outcome.
"""
import json
import os
import hashlib
from pathlib import Path
import tempfile

from .agent_adapter import JsonCountryAdapter, ExchangeBudget
from .checkpoint import CheckpointStore
from .choices import ensure
from .contracts import canonical, digest
from .observation import observe, validate_observation
from .turn import TurnRunner


def _write(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(canonical(data)); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def synthetic_abstention(request_json):
    request = json.loads(request_json)
    return canonical({'request_digest': request['request_digest'],
                      'state_id': request['state_id'], 'decisions': [], 'consents': {}})


def run_validation(baseline, network, directory, *, turns=8):
    ensure(type(turns) is int and 1 <= turns <= 32, 'INVALID_VALIDATION_TURN_COUNT')
    states = sorted(c['state_id'] for c in baseline['world']['countries'])
    ensure(len(states) == 8, 'EIGHT_STATE_BASELINE_REQUIRED')
    runner = TurnRunner(baseline, network, pool_location=states[0],
                        context_id='v3-json-boundary-validation')
    directory = Path(directory)
    # Never overwrite, resume, or retry a previous run implicitly.
    directory.mkdir(parents=True, exist_ok=False)
    store = CheckpointStore(directory/'checkpoints')
    protocol = {'version': 'v3', 'artifact_class': 'validation_run',
                'decision_origin': 'synthetic_fixture',
                'fixture_behavior': 'always_empty_decisions_not_agent_chosen_abstention',
                'fixture': 'synthetic_abstention', 'turns': turns, 'states': states,
                'baseline_digest': digest(baseline), 'network_digest': digest(network),
                'runner_config': runner.config,
                'source_hashes': {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(Path(__file__).parent.glob('*.py'))},
                'retry': 0, 'api_calls': 0,
                'research_eligible': False, 'publication_status': 'withheld'}
    _write(directory/'protocol.json', protocol)
    report = {'status': 'running', 'protocol_digest': digest(protocol),
              'decision_origin': 'synthetic_fixture',
              'fixture': 'synthetic_abstention',
              'fixture_behavior': 'always_empty_decisions_not_agent_chosen_abstention',
              'completed_turns': 0, 'planned_turns': turns, 'api_calls': 0,
              'artifact_class': 'validation_run', 'research_eligible': False,
              'publication_status': 'withheld', 'replay_verified': 0,
              'formal_experiment_ready': False}
    _write(directory/'report.json', report)
    opening = runner.genesis(); prior = []; sources = {}
    budget = ExchangeBudget(turns * len(states))
    countries = {sid: JsonCountryAdapter(sid, catalogue=lambda _: [],
                                        exchange=synthetic_abstention, budget=budget,
                                        source='synthetic validation fixture').callbacks()
                 for sid in states}
    try:
        store.save(opening, expected_digest=None)
        reference = opening; sources[opening['checkpoint_digest']] = opening
        for _ in range(turns):
            candidate = runner.run(opening, countries=countries)
            ensure(runner.replay(opening, candidate['input']) == candidate, 'REPLAY_MISMATCH')
            measurement = observe(candidate, worldline_id='v3-json-boundary-validation',
                                  provisional_reference='v3-offline-preflight', previous=prior,
                                  reference=reference, artifact_class='validation_run')
            sources[candidate['checkpoint_digest']] = candidate
            validate_observation(measurement, sources)
            store.save(candidate, expected_digest=opening['checkpoint_digest'])
            # Observation publication follows the authoritative checkpoint HEAD.
            _write(directory/f'observation-{candidate["turn"]:03}.json', measurement)
            prior.append(candidate); opening = candidate
            report.update(completed_turns=candidate['turn'], replay_verified=candidate['turn'],
                          last_checkpoint=candidate['checkpoint_digest'],
                          synthetic_exchanges=len(budget.attempts))
            _write(directory/'report.json', report)
        report['status'] = 'completed'
    except Exception:
        # Raw errors/provider payloads may contain secrets. Leave checkpoints for
        # inspection; uncertain commits must not trigger an automatic rerun.
        report.update(status='technical_failure', automatic_retry=False,
                      synthetic_exchanges=len(budget.attempts),
                      failure_code='VALIDATION_FAILED_INSPECT_CHECKPOINT_HEAD')
        _write(directory/'report.json', report)
        raise RuntimeError('V3 validation failed; inspect saved report and checkpoint HEAD') from None
    _write(directory/'report.json', report)
    return report
