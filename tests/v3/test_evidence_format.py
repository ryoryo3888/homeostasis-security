import json
from pathlib import Path
import tempfile
import unittest

from homeostasis_v4.evidence import EvidenceRun, FORMAT, timestamp, verify


def manifest():
    return {'format': FORMAT, 'run_id': 'fixture', 'started_at': timestamp(),
            'seed': 1, 'seed_scope': 'model requests', 'provider': 'synthetic-test',
            'model': 'fixture', 'model_version_or_digest': None,
            'generation_config': {}, 'experiment_config': {}, 'world_config': {},
            'provenance': {'source_hashes': {'fixture.py': '0' * 64},
                           'source_commit': None, 'runtime': {},
                           'parent_evidence_hash': None, 'purpose': 'offline test'}}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'run'
        self.run = EvidenceRun(self.path, manifest())

    def test_complete_public_copy_and_derived_binding(self):
        self.run.write('response.json', {'response': 'original text'})
        pin = self.run.finish('success', completed_turns=1)['evidence_hash']
        self.run.derive('metrics.json', {'count': 1})
        for path in self.path.rglob('*.json'):
            path.chmod(0o644)
        self.assertEqual(verify(self.path, expected_evidence_hash=pin)['status'], 'success')

    def test_failed_and_interrupted_attempts_retain_raw(self):
        for status in ('failure', 'interrupted'):
            path = Path(self.tmp.name) / status
            run = EvidenceRun(path, manifest())
            run.write('response.json', {'raw': 'not JSON'})
            run.finish(status, completed_turns=0, error={'kind': 'parser_failure'})
            self.assertEqual(verify(path)['status'], status)
            self.assertTrue((path / 'RAW/response.json').exists())

    def test_unfinalized_is_not_success(self):
        self.run.write('request.json', {'sent': 'unknown after process kill'})
        result = verify(self.path)
        self.assertEqual(result['status'], 'unfinalized')
        self.assertIsNone(result['ended_at'])
        with self.assertRaises(ValueError):
            self.run.derive('metrics.json', {})

    def test_raw_corruption_missing_and_added_files_rejected(self):
        self.run.write('response.json', {'text': 'observed'})
        self.run.finish('success', completed_turns=1)
        path = self.path / 'RAW/response.json'
        original = path.read_bytes()
        path.write_text(original.decode().replace('observed', 'invented'))
        with self.assertRaises(ValueError):
            verify(self.path)
        path.unlink()
        with self.assertRaises(ValueError):
            verify(self.path)
        path.write_bytes(original)
        (self.path / 'RAW/extra.json').write_bytes(original)
        with self.assertRaises(ValueError):
            verify(self.path)

    def test_overwrite_resume_and_post_terminal_writes_forbidden(self):
        self.run.write('response.json', {})
        with self.assertRaises(FileExistsError):
            self.run.write('response.json', {})
        with self.assertRaises(FileExistsError):
            EvidenceRun(self.path, manifest())
        self.run.finish('success', completed_turns=1)
        with self.assertRaises(ValueError):
            self.run.write('another.json', {})
        with self.assertRaises(FileExistsError):
            self.run.finish('failure', completed_turns=0)

    def test_path_traversal_and_symlink_rejected(self):
        with self.assertRaises(ValueError):
            self.run.write('../escape.json', {})
        self.run.write('response.json', {})
        (self.path / 'RAW/link.json').symlink_to(self.path / 'RAW/response.json')
        with self.assertRaises(ValueError):
            verify(self.path)

    def test_pin_detects_resealed_changes(self):
        from homeostasis_v3.contracts import canonical, digest
        self.run.write('response.json', {})
        pin = self.run.finish('success', completed_turns=1)['evidence_hash']
        path = self.path / 'terminal.json'
        value = json.loads(path.read_text())
        value['payload']['completed_turns'] = 2
        value['sha256'] = digest(value['payload'])
        path.write_text(canonical(value))
        with self.assertRaises(ValueError):
            verify(self.path, expected_evidence_hash=pin)


if __name__ == '__main__':
    unittest.main()
