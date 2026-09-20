"""Keep the additional organization verifiable against the immutable source."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from tools.audit_provenance import build_report

ROOT = Path(__file__).resolve().parents[2]
BASE = 'a47f155f543c38ccd48487055b45eb606364f708'


def source(path):
    return subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)


class UnregisteredJsonAuditTests(unittest.TestCase):
    def test_all_sixteen_records_preserve_source_and_only_six_move(self):
        audit = json.loads((ROOT / 'research/experiments/unregistered_audit_20260920.json').read_text())
        moves = json.loads((ROOT / 'archive/unregistered-json-moves.json').read_text())
        inventory = json.loads(source('research/experiments/inventory.json'))
        expected = {item['artifact'] for item in inventory['unregistered']
                    if '/' not in item['artifact'] and item['artifact'].endswith('.json')
                    and item['classification'] != 'configuration'}
        self.assertEqual(len(expected), 16)
        self.assertEqual(len(audit['files']), 16)
        self.assertEqual({item['original_path'] for item in audit['files']}, expected)
        self.assertEqual(audit['source_commit'], BASE)
        self.assertEqual(moves['source_commit'], BASE)
        self.assertFalse(audit['research_registration_changed'])
        self.assertEqual(Counter(item['classification'] for item in audit['files']),
                         {'referenced': 5, 'retain_distinct_history': 5,
                          'derived_intermediate': 2, 'exact_duplicate': 4})
        self.assertEqual(len(moves['files']), 6)
        archived = {item['original_path']: item for item in moves['files']}
        self.assertEqual(set(archived), {item['original_path'] for item in audit['files']
                                       if item['disposition'] == 'archive'})
        for item in audit['files']:
            with self.subTest(path=item['original_path']):
                path = ROOT / item['path']
                self.assertFalse(path.is_symlink())
                raw = path.read_bytes()
                self.assertEqual(raw, source(item['original_path']))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'])
                self.assertEqual(len(raw), item['bytes'])
                self.assertFalse(item['provider_execution_verified'])
                if item['disposition'] == 'keep':
                    self.assertEqual(item['path'], item['original_path'])
                else:
                    self.assertFalse((ROOT / item['original_path']).exists())
                    self.assertEqual(archived[item['original_path']],
                                     {k: item[k] for k in ('original_path', 'path', 'sha256')})
                    self.assertEqual(item['direct_or_dynamic_consumers'], [])
                    folder = 'duplicate-results' if item['duplicate_of'] else 'legacy-derived'
                    self.assertEqual(item['path'], f"archive/{folder}/{item['original_path']}")
                if item['duplicate_of']:
                    self.assertEqual(raw, (ROOT / item['duplicate_of']).read_bytes())
                if item['retained_subset']:
                    condition = 'no_hotline' if 'no_hotline' in item['original_path'] else 'hotline'
                    split = json.loads(raw)
                    combined = json.loads((ROOT / 'contrast_scores.json').read_text())
                    self.assertEqual(split['scores'], combined['conditions'][condition])
                    self.assertEqual(split['scale'], combined['scale'])

    def test_prior_archive_and_registered_research_are_unchanged(self):
        for path in ('archive/manifest.json', 'research/experiments/inventory.json',
                     'research/experiments/registry.json'):
            self.assertEqual((ROOT / path).read_bytes(), source(path), path)
        before = json.loads(source('research/experiments/artifact_allowlist.json'))
        after = json.loads((ROOT / 'research/experiments/artifact_allowlist.json').read_text())
        self.assertEqual([i for i in before['artifacts'] if i['path'] != 'README.md'],
                         [i for i in after['artifacts'] if i['path'] != 'README.md'])
        for item in after['artifacts']:
            raw = (ROOT / item['path']).read_bytes()
            if item['path'] == 'README.md':
                self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'])
            else:
                self.assertEqual(raw, source(item['path']), item['path'])

    def test_provenance_inventory_still_includes_every_historical_result(self):
        before = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE],
                                         cwd=ROOT, text=True).splitlines()
        expected = {p for p in before if '/' not in p and (
            p.startswith(('simulation_result', 'result_')) and p.endswith('.json') or p == 'summary.json')}
        moves = json.loads((ROOT / 'archive/unregistered-json-moves.json').read_text())
        mapping = {i['path']: i['original_path'] for i in moves['files']}
        report = build_report()['systems']['v1_and_comparison']['saved_files']
        self.assertEqual({mapping.get(i['path'], i['path']) for i in report}, expected)
