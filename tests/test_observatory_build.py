"""The exhibit cannot silently bundle raw runs or unverified timeline data."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.build_observatory import build, ROOT
from homeostasis_core.observability import source_digest

class ObservatoryBuildTests(unittest.TestCase):
    def test_build_preserves_evidence_and_allowlists_files(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'site'
            manifest = build(target)
            self.assertEqual(manifest['api_calls'], 0)
            self.assertFalse(any(name.startswith(('results/research/', 'results/probe/', 'homeostasis_core/')) for name in manifest['files']))
            for name, digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(), digest)
                self.assertEqual((target/name).read_bytes(), (ROOT/name).read_bytes())

    def test_tampered_pin_fails_before_output(self):
        from tools import build_observatory as module
        original = module.read_json
        def altered(path):
            value = original(path)
            if path.name == 'config.json': value['sha256'] = '0'*64
            return value
        with tempfile.TemporaryDirectory() as temp, patch.object(module, 'read_json', altered):
            target = Path(temp)/'site'
            with self.assertRaisesRegex(ValueError, 'hash mismatch'): build(target)
            self.assertFalse(target.exists())

    def test_frontend_source_is_in_preflight_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'observatory').mkdir()
            path=root/'observatory/view-model.js'; path.write_text('original')
            before=source_digest(root); path.write_text('changed')
            self.assertNotEqual(before,source_digest(root))

    def test_contaminated_build_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp); (target/'private.log').write_text('not allowed')
            with self.assertRaisesRegex(ValueError, 'Unexpected file'): build(target)
            self.assertFalse((target/'worldline_observatory.html').exists())
