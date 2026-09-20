"""Offline, allowlisted publication of completed dialogue records. No model imports."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ACTORS = ('A', 'B', 'C', 'COORDINATOR')
MESSAGE_FIELDS = {'id', 'sender', 'to', 'body', 'sent_round', 'available_round', 'cause', 'reply_to'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_journal(path):
    record = json.loads(Path(path).read_text())
    if digest(record['payload']) != record['sha256']:
        raise ValueError('Journal checksum mismatch')
    return record['payload']


def export_trials(states, verification):
    """Project verified final states; never export notes, SDK objects or credentials."""
    if len(states) != 5 or verification['status'] != 'verified_without_model_calls':
        raise ValueError('Five verified trials required')
    trials = []
    for number, (state, audit) in enumerate(zip(states, verification['trials']), 1):
        if audit['trial'] != number or state['round'] != 8 or digest(state) != audit['state_sha256']:
            raise ValueError('Verified state mismatch')
        if state['initial'] != states[0]['initial']:
            raise ValueError('Initial conditions differ')
        messages = []
        for message in state['messages']:
            if not set(message) <= MESSAGE_FIELDS:
                raise ValueError('Unknown message fields require review')
            messages.append(deepcopy(message))
        decisions = []
        for turn in range(1, 9):
            for actor in ACTORS:
                entries = [h for h in state['history'][actor] if h['round'] == turn]
                if len(entries) != 1:
                    raise ValueError('Missing/duplicate decision')
                output = entries[0]['output']
                if output['activities']:
                    raise ValueError('This observation does not support physical activity claims')
                sent = [m for m in messages if m['sender'] == actor and m['sent_round'] == turn]
                if len(sent) != len(output['outgoing']):
                    raise ValueError('Outgoing count mismatch')
                decisions.append({'actor': actor, 'round': turn, 'message_ids': [m['id'] for m in sent]})
        if len(messages) != audit['messages'] or sum(len(m['body']) for m in messages) != audit['body_characters']:
            raise ValueError('Message totals differ from verified audit')
        trials.append({'trial': number, 'rounds': 8, 'source_state_sha256': digest(state),
                       'messages': messages, 'decisions': decisions})
    if len(trials) != 5:
        raise ValueError('Incomplete audit')
    return {'schema_version': 1, 'kind': 'saved_v2_dialogue_observation',
            'initial': deepcopy(states[0]['initial']), 'physical_execution': False,
            'model': 'gemini-3.6-flash', 'trials': trials,
            'operational_difference': '初回は途中で入力上限を12,000から24,000へ拡大。第2〜5回は最初から24,000。出力上限は全回8,192。履歴の切り捨ては行っていない。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--verification', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    first, batch = Path(plan['first_trial_directory']), Path(plan['output_directory'])
    states = [read_journal(first / 'dialogue/result.json')['state']]
    states += [read_journal(batch / f'trial-{n:02d}/result.json')['state'] for n in range(2, 6)]
    result = export_trials(states, json.loads(args.verification.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Published projection: 5 trials, 40 rounds, 163 original messages; no model calls.')


if __name__ == '__main__':
    main()
