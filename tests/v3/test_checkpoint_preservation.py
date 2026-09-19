"""Immutable records survive conflicting writers and failed HEAD publication."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homeostasis_v3 import checkpoint
from homeostasis_v3.choices import TechnicalFailure
from tests.v3 import test_turn as fixtures


class CheckpointPreservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        fixture = fixtures.TurnTests(); fixture.setUp()
        self.genesis, self.candidate = fixture.g, fixture.run_choices()
        self.store = checkpoint.CheckpointStore(self.directory)
        self.store.save(self.genesis, expected_digest=None)
        self.head = self.directory / 'HEAD.json'
        self.record = self.directory / (self.candidate['checkpoint_digest'] + '.json')

    def save_next(self):
        return self.store.save(self.candidate, expected_digest=self.genesis['checkpoint_digest'])

    def test_conflicting_record_preserves_original_bytes_and_head(self):
        self.record.write_bytes(b'existing evidence'); head = self.head.read_bytes()
        with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_RECORD_CONFLICT'): self.save_next()
        self.assertEqual(self.record.read_bytes(), b'existing evidence')
        self.assertEqual(self.head.read_bytes(), head)
        self.assertEqual(self.store.load(), self.genesis)
        self.assertEqual(list(self.directory.glob('.pending-*')), [])

    def test_concurrent_record_is_not_replaced(self):
        original = checkpoint.os.link; head = self.head.read_bytes()
        def concurrent(source, destination):
            Path(destination).write_bytes(b'concurrent evidence')
            return original(source, destination)
        with patch.object(checkpoint.os, 'link', side_effect=concurrent):
            with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_RECORD_CONFLICT'): self.save_next()
        self.assertEqual(self.record.read_bytes(), b'concurrent evidence')
        self.assertEqual(self.head.read_bytes(), head)
        self.assertEqual(list(self.directory.glob('.pending-*')), [])

    def test_written_bytes_must_match_before_publication(self):
        original = checkpoint.os.fsync; target = self.directory / 'synthetic-write.json'
        def corrupt(fd):
            original(fd)
            for pending in self.directory.glob('.pending-*'):
                pending.write_text(pending.read_text().replace('"value":1', '"value":true'))
        with patch.object(checkpoint.os, 'fsync', side_effect=corrupt):
            with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_WRITE_MISMATCH'):
                self.store._atomic_write(target, '{"value":1}', replace=False)
        self.assertFalse(target.exists())
        self.assertEqual(self.store.load(), self.genesis)
        self.assertEqual(list(self.directory.glob('.pending-*')), [])

    def test_identical_orphan_is_reused_without_rewrite(self):
        original = self.store._atomic_write
        def fail_head(path, data, **kwargs):
            if path.name == 'HEAD.json': raise OSError('synthetic pre-HEAD failure')
            return original(path, data, **kwargs)
        with patch.object(self.store, '_atomic_write', side_effect=fail_head):
            with self.assertRaises(OSError): self.save_next()
        raw, stat = self.record.read_bytes(), self.record.stat()
        self.assertEqual(self.store.load(), self.genesis)
        self.save_next()
        self.assertEqual(self.store.load(), self.candidate)
        self.assertEqual(self.record.read_bytes(), raw)
        self.assertEqual((self.record.stat().st_ino, self.record.stat().st_mtime_ns), (stat.st_ino, stat.st_mtime_ns))

    def test_dangling_record_is_not_replaced(self):
        target = self.directory / 'missing-original'; self.record.symlink_to(target)
        head = self.head.read_bytes()
        with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_RECORD_CONFLICT'): self.save_next()
        self.assertTrue(self.record.is_symlink()); self.assertFalse(target.exists())
        self.assertEqual(self.head.read_bytes(), head)

    def test_dangling_head_is_not_treated_as_a_new_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); head = root / 'HEAD.json'; target = root / 'missing-head'
            head.symlink_to(target); store = checkpoint.CheckpointStore(root)
            with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_SYMLINK_FORBIDDEN'): store.load()
            with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_SYMLINK_FORBIDDEN'):
                store.save(self.genesis, expected_digest=None)
            self.assertTrue(head.is_symlink()); self.assertFalse(target.exists())

    def test_committed_record_symlink_is_not_followed(self):
        path = self.directory / (self.genesis['checkpoint_digest'] + '.json')
        retained = self.directory / 'retained-original'; path.rename(retained); path.symlink_to(retained)
        original = retained.read_bytes()
        with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_SYMLINK_FORBIDDEN'): self.store.load()
        self.assertEqual(retained.read_bytes(), original); self.assertTrue(path.is_symlink())


if __name__ == '__main__': unittest.main()
