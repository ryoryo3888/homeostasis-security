"""A navigation exception must never mask an unapproved world/source change."""
import hashlib
import unittest
from pathlib import Path
from tools.navigation_revision import NEW, original_navigation

ROOT = Path(__file__).resolve().parents[2]


class NavigationRevisionTests(unittest.TestCase):
    def test_wrong_destination_and_duplicate_navigation_rejected(self):
        for version in ('v1', 'v2'):
            source = (ROOT / f'dashboard_{version}.html').read_bytes()
            for changed in [source.replace(b'href="results/v2-five-runs/index.html"', b'href="dashboard_v2.html"'),
                            source + NEW[version].encode()]:
                with self.assertRaises(ValueError):
                    original_navigation(changed, version)

    def test_unapproved_earth_change_still_changes_protected_hash(self):
        for version in ('v1', 'v2'):
            source = (ROOT / f'dashboard_{version}.html').read_bytes()
            changed = source.replace(b'class="earth-panel', b'class="changed-earth-panel', 1)
            self.assertNotEqual(hashlib.sha256(original_navigation(source, version)).digest(),
                                hashlib.sha256(original_navigation(changed, version)).digest())
