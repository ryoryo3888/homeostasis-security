import json
import tempfile
from pathlib import Path
import unittest

import httpx

from homeostasis_v5.life_first_generation import wire_bytes
from homeostasis_v5.paired_diplomacy_generation import prepare, dry_run_validate, generate_next, CALLS_PER_RUN
from homeostasis_v4.evidence import read_record, verify


class PairedDiplomacyGenerationTests(unittest.TestCase):
    def test_dry_run_checks_all_twenty_36_turn_runs_without_api(self):
        result = dry_run_validate(Path('/tmp/not-used'))
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['manifest_count'], 20)
        self.assertEqual(result['leader_calls_checked_per_run'], 432)
        self.assertEqual(result['total_calls_checked'], 8640)
        self.assertFalse(result['api_executed'])

    def test_prepare_and_one_fake_generation_step_records_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'batch'
            prepared = prepare(root)
            self.assertEqual(prepared['runs'], 20)
            self.assertEqual(prepared['calls_total'], CALLS_PER_RUN * 20)

            def handler(request):
                payload = json.loads(request.content.decode('utf-8'))
                if request.url.path.endswith(':countTokens'):
                    return httpx.Response(200, json={'totalTokens': 100})
                snapshot = json.loads(payload['contents'][0]['parts'][1]['text'])
                output = {
                    'document_type': 'v5-paired-leader-turn-decision-1',
                    'condition': snapshot['condition'],
                    'world_id': snapshot['world_id'],
                    'run_id': snapshot['run_id'],
                    'seed_label': snapshot['seed_label'],
                    'turn': snapshot['turn'],
                    'leader_id': snapshot['actor_leader_id'],
                    'nation_id': snapshot['actor_nation_id'],
                    'observation_summary': 'synthetic offline test observation',
                    'contact_selection_reason': 'synthetic offline test decision',
                    'outgoing_messages': [],
                    'proposals': [],
                    'private_note': None,
                    'no_direct_world_mutation_ack': True,
                }
                return httpx.Response(200, json={
                    'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(output)}]}}],
                    'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 50, 'totalTokenCount': 150},
                    'modelVersion': 'synthetic-test',
                    'responseId': 'synthetic-response',
                })

            result = generate_next(root, credential='SYNTHETIC_SECRET', transport=httpx.MockTransport(handler))
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['manifest_run_id'], 'seed-01-A-NORMAL')
            state = read_record(root / 'seed-01-A-NORMAL' / 'run-state-001.json')
            self.assertEqual(state['next_index'], 2)
            self.assertEqual(len(state['turn_decisions']), 1)
            checked = verify(root / 'seed-01-A-NORMAL' / 'attempt-001')
            self.assertEqual(checked['status'], 'success')


if __name__ == '__main__':
    unittest.main()
