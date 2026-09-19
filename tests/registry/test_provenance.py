import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.audit_provenance import ROOT, build_report, describe_file


class ProvenanceTests(unittest.TestCase):
    def test_report_is_read_only_and_does_not_promote_saved_results(self):
        report = build_report()
        self.assertFalse(report['research_eligible'])
        self.assertFalse(report['publication_performed'])
        self.assertFalse(report['historical_provenance_reconstructed'])
        self.assertEqual(set(report['systems']), {'v1_and_comparison', 'v2', 'legacy_eight_state', 'v3'})
        for system in report['systems'].values():
            self.assertEqual(system['historical_execution_source_match'], 'not_verified_by_this_report')
            self.assertTrue(system['saved_files'])
            for item in system['saved_files']:
                self.assertEqual(item['sha256'], hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest())
        self.assertEqual(report, build_report())
        self.assertEqual(report['systems']['v1_and_comparison']['current_source_stages']['realization'], [])
        self.assertEqual(report['systems']['v2']['current_source_stages']['realization'], [])

    def test_digest_detects_change_without_exposing_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'result.json'
            p.write_text('{"value":1}')
            before = describe_file(directory, p.name)
            p.write_text('{"value":2}')
            after = describe_file(directory, p.name)
            self.assertNotEqual(before['sha256'], after['sha256'])
            self.assertEqual(set(after), {'path', 'sha256', 'bytes'})

    def test_missing_or_unsafe_evidence_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError): describe_file(directory, 'missing.json')
            for name in ('../outside.json', '/tmp/outside.json'):
                with self.assertRaises(ValueError): describe_file(directory, name)
            p = Path(directory) / 'link.json'; p.symlink_to('/tmp/missing-evidence')
            with self.assertRaises(ValueError): describe_file(directory, p.name)
