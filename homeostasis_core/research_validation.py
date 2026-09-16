"""Fail-closed admission for new research artifacts; old files stay untouched."""
import hashlib
import json
from .decision_audit import validate_choice_trace
from .emergent_dynamics import INITIAL_EVENT, reconstruction_step
from .gemini_agents import parse_country_json, parse_coordinator_json, parse_evaluator_json, derive_event


def validate_research(result, transport_audit):
    reasons = []
    try:
        if result['metadata']['turns'] != 8 or len(result['runs']) != 1:
            raise ValueError('requires one complete eight-turn worldline')
        run = result['runs'][0]['details']
        turns = run['turns']
        if [r['turn'] for r in turns] != list(range(1, 9)):
            raise ValueError('incomplete turns')
        calls = run['call_audit']
        if len(calls) != 80 or transport_audit['api_calls'] != 80:
            raise ValueError('missing or unexpected API attempts')
        if len(transport_audit['attempts']) != 80 or any(a['status'] != 'returned' for a in transport_audit['attempts']):
            raise ValueError('incomplete transport audit')
        if len({a.get('call_id') for a in calls}) != 80:
            raise ValueError('duplicate or missing decision audit identity')
        for item, transport in zip(calls, transport_audit['attempts']):
            if item.get('validation_status') != 'PASS' or item.get('model_response') is None:
                raise ValueError('unvalidated decision audit')
            for key in ('run_id', 'run', 'turn', 'agent_id', 'attempt', 'call_id'):
                if not item.get(key) or item[key] != transport.get(key):
                    raise ValueError('transport/decision audit identity mismatch')
        for row in turns:
            t = row['turn']; snapshot = row['snapshot']; executed = row['executed_state']
            parse_coordinator_json(json.dumps(row['proposal']))
            parse_evaluator_json(json.dumps(row['evaluator_commentary']))
            from final_experiment_runner import COUNTRIES
            if set(row['country_responses']) != set(COUNTRIES):
                raise ValueError('country logs missing')
            for country, answer in row['country_responses'].items():
                parse_country_json(json.dumps(answer), COUNTRIES)
                if answer['country_id'] != country or answer['proposal_id'] != row['proposal']['proposal_id']:
                    raise ValueError('identity mismatch')
            audit = [a for a in calls if a['turn'] == t]
            if len(audit) != 10 or any(a['structured_response'] is None for a in audit):
                raise ValueError('structured audit missing')
            if {a['agent_id'] for a in audit if a['agent_type'] == 'country'} != set(COUNTRIES):
                raise ValueError('country audit missing')
            for item in audit:
                if item['agent_type'] == 'country':
                    validate_choice_trace(item)
                    answer = row['country_responses'][item['agent_id']]
                    if item['structured_response'] != answer:
                        raise ValueError('audit/response mismatch')
                    from .feasibility import validate_action_feasible
                    validate_action_feasible(item['agent_id'], answer['action'], item['public_observation_payload']['action_choices'])
                elif item['agent_type'] == 'coordinator':
                    if item['model_response'] != item['structured_response']: raise ValueError('original coordinator response mismatch')
                    if item['structured_response'] != row['proposal']:
                        raise ValueError('proposal audit mismatch')
                elif item['agent_type'] == 'evaluator':
                    if item['model_response'] != item['structured_response']: raise ValueError('original evaluator response mismatch')
                    if item['structured_response'] != row['evaluator_commentary']:
                        raise ValueError('evaluator audit mismatch')
                else:
                    raise ValueError('unknown audited agent')
            if row['research_metrics'] != executed['research_metrics'] or not executed['causal_record']:
                raise ValueError('required causal logs missing')
            if t == 1:
                if snapshot['event'] != INITIAL_EVENT or snapshot['damage'] != 8000:
                    raise ValueError('initial crisis mismatch')
            else:
                previous = turns[t-2]['executed_state']
                if snapshot['event_origin'] != 'derived_from_previous_executed_state':
                    raise ValueError('scripted later event')
                if snapshot['world'] != previous['true_world'] or snapshot['damage'] != previous['reconstruction']['after']:
                    raise ValueError('broken state continuity')
                expected = derive_event(snapshot['world'], snapshot['history_state'], previous['action_counts'],
                                        [r['snapshot']['event'] for r in turns[:t-1]])
                if snapshot['event'] != expected:
                    raise ValueError('event derivation mismatch')
            if executed['reconstruction'] != reconstruction_step(snapshot['damage'], executed, executed['country_states']):
                raise ValueError('reconstruction mismatch')
        if all(row['response_convergence'] for row in turns):
            reasons.append('all turns have converged responses; research review required')
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        reasons.append(str(exc))
    return reasons


def research_manifest(path, reasons):
    return {'schema_version': 1, 'result_file': path.name,
            'result_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'status': 'rejected' if reasons else 'accepted',
            'include_in_research_aggregation': not reasons,
            'include_in_dashboard': not reasons, 'reasons': reasons}


def accepted_research_paths(directory):
    paths = []
    for path in directory.rglob('result.json'):
        if path.name.endswith('.audit.json'):
            continue
        manifest = path.with_suffix('.audit.json')
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text())
            transport = json.loads((path.parent/'transport.audit.json').read_text())
            result = json.loads(path.read_text())
            if data == research_manifest(path, []) and not validate_research(result, transport):
                paths.append(path)
        except (OSError, ValueError, TypeError):
            continue
    return tuple(sorted(paths))
