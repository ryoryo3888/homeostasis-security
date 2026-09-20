"""The published failure remains a failure, with replayable unmodified evidence."""
import base64
from collections import Counter
import json
from pathlib import Path
import unittest

from homeostasis_v4.dialogue import parse_reply
from homeostasis_v4.evidence import read_record, verify
from homeostasis_v4.local_observation import replay
from tools.secret_scan import has_secret

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'results/local-v4/local-3630a0e5-68c9-4ea8-b17f-aa3a0c035585'
PIN = 'ed43c801793f83af4223f067841e27c7bbbfcbf9610831ba32d932e891869314'


class LocalPilotEvidenceTests(unittest.TestCase):
    def test_pinned_failure_has_only_one_replayable_completed_turn(self):
        verified = verify(RUN, expected_evidence_hash=PIN)
        self.assertEqual(verified['status'], 'failure')
        self.assertEqual(verified['raw_files'], 51)
        result = replay(RUN)
        self.assertEqual(result['evidence_hash'], PIN)
        self.assertEqual(result['replayed_turns'], 1)
        self.assertFalse((RUN / 'RAW/turn-002.json').exists())
        terminal = read_record(RUN / 'terminal.json')
        self.assertEqual(terminal['error']['code'], 'PILOT_DEADLINE_REACHED')

    def test_assessment_matches_raw_and_decoded_responses(self):
        report = json.loads((RUN.parent / 'pilot-01-assessment.json').read_text())
        self.assertEqual(report['evidence_hash'], PIN)
        self.assertEqual(report['raw_evidence_hash'], verify(RUN)['raw_evidence_hash'])
        self.assertFalse(report['scale_up_ready'])
        self.assertFalse(report['same_seed_regeneration_tested'])
        replies = []
        for record in report['calls']:
            prefix = f"call-{record['sequence']:03d}"
            wire = read_record(RUN / f'RAW/{prefix}.wire.json')
            decoded = base64.b64decode(wire['body_base64']).decode()
            self.assertFalse(has_secret(decoded))
            response = json.loads(decoded)
            request = read_record(RUN / f'RAW/{prefix}.request.json')
            view = json.loads(request['body']['prompt'])['view']
            reply = parse_reply(response['response'], view)
            replies.append(reply)
            self.assertEqual(record['actor'], view['actor'])
            self.assertEqual(record['seconds'], wire['duration_seconds'])
            self.assertEqual(record['prompt_tokens'], response['prompt_eval_count'])
            self.assertEqual(record['output_tokens'], response['eval_count'])
            self.assertEqual(record['outgoing_messages'], len(reply['outgoing']))
            self.assertEqual(record['activities'], len(reply['activities']))
            self.assertEqual(response['done_reason'], 'stop')
        self.assertEqual(len(replies), report['parsed_replies'])
        self.assertEqual(len(replies), 15)
        self.assertEqual(replies[:7], replies[8:])
        checkpoint = read_record(RUN / 'RAW/turn-001.json')
        receipts = [r for values in checkpoint['dialogue']['receipts'].values() for r in values]
        observed = report['committed_first_turn']
        self.assertEqual(len(checkpoint['dialogue']['messages']), observed['outgoing_messages'])
        self.assertEqual(len(receipts), observed['activity_requests'])
        self.assertEqual(dict(Counter(r['status'] for r in receipts)), observed['receipt_statuses'])
        self.assertEqual(sum(r['executed'] for r in receipts), 0)
        for path in RUN.rglob('*.json'):
            text = path.read_text()
            self.assertFalse(has_secret(text), path.name)
            self.assertNotIn('/Users/', text, path.name)
