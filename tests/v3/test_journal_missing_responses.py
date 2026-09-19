"""Missing historic replies stop dispatch; they are never reconstructed."""
from contextlib import closing
import sqlite3
import unittest

from tests.v3 import test_autonomous_gemini as fixtures
from homeostasis_v3.choices import TechnicalFailure
from homeostasis_v3.contracts import canonical


class MissingResponseTests(unittest.TestCase):
    def fixture(self):
        case = fixtures.SDKTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def test_missing_reply_blocks_new_request_in_same_process_and_after_restart(self):
        for restart in (False, True):
            for missing_index in (0, 1):
                with self.subTest(restart=restart, missing_index=missing_index):
                    case = self.fixture(); exchange = case.exchange()
                    for turn in (1, 2):
                        exchange(canonical(case.request(turn=turn)))
                    key = exchange.journal.records()[missing_index]['request_digest']
                    with closing(sqlite3.connect(case.path)) as db, db:
                        db.execute('DELETE FROM responses WHERE request_digest=?', (key,))
                    before = exchange.journal.records()
                    receipts = exchange.journal.response_records()
                    if restart:
                        exchange = case.exchange()
                    with self.assertRaisesRegex(TechnicalFailure, 'PRIOR_RESPONSE_NOT_RECORDED'):
                        exchange(canonical(case.request(turn=3)))
                    self.assertEqual(len(case.sent), 2)
                    self.assertEqual(exchange.journal.records(), before)
                    self.assertEqual(exchange.journal.response_records(), receipts)

    def test_old_journal_without_response_table_cannot_continue_new_requests(self):
        case = self.fixture(); exchange = case.exchange()
        exchange(canonical(case.request()))
        with closing(sqlite3.connect(case.path)) as db, db:
            db.execute('DROP TABLE responses')
        reopened = case.exchange()
        before = reopened.journal.records()
        self.assertEqual(reopened.journal.response_records(), [])
        with self.assertRaisesRegex(TechnicalFailure, 'PRIOR_RESPONSE_NOT_RECORDED'):
            reopened(canonical(case.request(turn=2)))
        self.assertEqual(len(case.sent), 1)
        self.assertEqual(reopened.journal.records(), before)
        self.assertEqual(reopened.journal.response_records(), [])

    def test_complete_receipts_allow_restart_and_next_request(self):
        case = self.fixture(); exchange = case.exchange()
        first = exchange(canonical(case.request()))
        before = exchange.journal.response_records()
        reopened = case.exchange()
        second = reopened(canonical(case.request(turn=2)))
        self.assertNotEqual(first, second)
        self.assertEqual(len(case.sent), 2)
        self.assertEqual(reopened.journal.response_records()[:1], before)
        self.assertEqual([r['status'] for r in reopened.journal.records()],
                         ['response_validated', 'response_validated'])


if __name__ == '__main__':
    unittest.main()
