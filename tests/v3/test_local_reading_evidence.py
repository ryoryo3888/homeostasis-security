"""Published diagnostic keeps its failed reply and unattempted cases distinct."""
import base64
import json
from pathlib import Path
import unittest

from homeostasis_v4.evidence import read_record, verify
from model_response_json import load_response_object
from tools.secret_scan import has_secret

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'results/local-v4/diagnostic-reading-3aaf1ecc-ed57-46b4-b21c-1f3dacf315fe'
PARENT = ROOT / 'results/local-v4/local-3630a0e5-68c9-4ea8-b17f-aa3a0c035585'
PIN = 'd6010e8e797faaec9a3a18fc114c42bf0ea04a15e0998505553849d96713f612'


class LocalReadingEvidenceTests(unittest.TestCase):
    def test_pinned_failure_preserves_one_reply_and_three_unattempted_cases(self):
        self.assertEqual(verify(RUN, expected_evidence_hash=PIN)['status'], 'failure')
        self.assertEqual(read_record(RUN / 'terminal.json')['completed_turns'], 0)
        self.assertEqual(len(list((RUN / 'RAW').glob('call-*.wire.json'))), 1)
        self.assertEqual(len(list((RUN / 'RAW').glob('call-*.request.json'))), 1)
        wire = read_record(RUN / 'RAW/call-000.wire.json')
        response = load_response_object(base64.b64decode(wire['body_base64']).decode())
        self.assertEqual(wire['status_code'], 200)
        self.assertEqual(response['done_reason'], 'stop')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON response field'):
            load_response_object(response['response'])
        report = read_record(RUN / 'DERIVED/failure-analysis.json')['report']
        self.assertEqual((report['attempted_generations'], report['received_complete_model_responses'],
                          report['parsed_diagnostic_responses'], report['unattempted_cases']), (1, 1, 0, 3))
        self.assertFalse(report['scale_up_ready'])
        self.assertEqual(report['automatic_retries'], 0)

    def test_diagnostic_uses_complete_saved_inputs_and_predeclared_answers(self):
        manifest = read_record(RUN / 'manifest.json')
        self.assertFalse(manifest['experiment_config']['formal_research_eligibility'])
        preflight = read_record(RUN / 'RAW/preflight.json')
        self.assertEqual([(c['source_call_index'], c['body']['options']['seed'])
                          for c in preflight['cases']], [(0, 10073), (8, 10073), (0, 20073), (8, 20073)])
        for case in preflight['cases']:
            old = read_record(PARENT / f"RAW/call-{case['source_call_index']:03d}.request.json")['body']
            self.assertEqual(case['body']['prompt'], old['prompt'])
            self.assertNotEqual(case['body']['system'], old['system'])
            view = json.loads(old['prompt'])['view']
            account = next(a for a in view['public_world']['physical']['world']['accounts']
                           if a['owner'] == view['actor'] and a['resource_id'] == 'food'
                           and a['kind'] == 'stock' and a['in_transit'] is False)
            self.assertEqual(case['expected'], {'actor': view['actor'], 'turn': view['turn'],
                'own_food_stock': account['balance'], 'activity_results': view['activity_results']})
        self.assertEqual(read_record(RUN / 'RAW/call-000.request.json')['body'], preflight['cases'][0]['body'])
        for path in RUN.rglob('*.json'):
            text = path.read_text()
            self.assertFalse(has_secret(text), path.name)
            self.assertNotIn('/Users/', text, path.name)
            payload = read_record(path)
            if 'body_base64' in payload:
                decoded = base64.b64decode(payload['body_base64']).decode()
                self.assertFalse(has_secret(decoded))
                self.assertNotIn('/Users/', decoded)


if __name__ == '__main__':
    unittest.main()
