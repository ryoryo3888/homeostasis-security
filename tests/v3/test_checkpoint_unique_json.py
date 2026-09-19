"""Never select one occurrence from ambiguous stored checkpoint JSON."""
from pathlib import Path
import tempfile
import unittest

from homeostasis_v3.checkpoint import CheckpointStore
from homeostasis_v3.choices import TechnicalFailure
from tests.v3 import test_turn as fixtures


class CheckpointUniqueJsonTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.fixture = fixtures.TurnTests(); self.fixture.setUp()
        self.store = CheckpointStore(self.directory)
        self.store.save(self.fixture.g, expected_digest=None)
        self.head = self.directory / 'HEAD.json'
        self.record = self.directory / (self.fixture.g['checkpoint_digest'] + '.json')

    def snapshot(self):
        return {path: path.read_bytes() for path in self.directory.glob('*.json')}

    def assert_ambiguous_load_stops(self):
        before = self.snapshot()
        with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_DUPLICATE_JSON_KEY'): self.store.load()
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_head_fields_are_rejected_even_when_last_value_is_valid(self):
        original = self.head.read_text()
        for key in ('file', 'checkpoint_digest'):
            with self.subTest(key=key):
                self.head.write_text(original.replace('{', '{"' + key + '":"ignored-first-value",', 1))
                self.assert_ambiguous_load_stops()
        self.head.write_text(original)
        self.assertEqual(self.store.load(), self.fixture.g)

    def test_duplicate_record_fields_are_rejected_at_every_depth(self):
        original = self.record.read_text()
        for raw in (original.replace('{', '{"turn":999,', 1),
                    original.replace('"world_state":{', '"world_state":{"pool":{"food":999},', 1)):
            self.assertNotEqual(raw, original)
            self.record.write_text(raw); self.assert_ambiguous_load_stops()
        self.record.write_text(original)
        self.assertEqual(self.store.load(), self.fixture.g)

    def test_save_cannot_advance_an_ambiguous_head(self):
        self.head.write_text(self.head.read_text().replace('{', '{"file":"ignored-first-value",', 1))
        before = self.snapshot()
        with self.assertRaisesRegex(TechnicalFailure, 'CHECKPOINT_DUPLICATE_JSON_KEY'):
            self.store.save(self.fixture.run_choices(), expected_digest=self.fixture.g['checkpoint_digest'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.directory.glob('.pending-*')), [])


if __name__ == '__main__': unittest.main()
