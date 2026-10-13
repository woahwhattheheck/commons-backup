import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from submission_ledger import LedgerError, record, select, state

A, B, C = "a" * 64, "b" * 64, "c" * 64


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def rec(self, sid, score, sha=A, direction="maximize"):
        return record(
            self.path,
            "arc",
            sid,
            sha,
            direction,
            score,
            {"seed": 7},
            "2026-10-05T22:00:00Z",
        )

    def pick(self, sid, slot="protected-best", override=False):
        return select(
            self.path,
            "arc",
            sid,
            slot,
            "2026-10-05T22:01:00Z",
            "test",
            override,
        )

    def test_duplicate_submission_ids_are_rejected(self):
        self.rec("one", 0.4)
        with self.assertRaises(LedgerError):
            self.rec("one", 0.5, B)

    def test_protected_best_accepts_only_strict_improvement(self):
        self.rec("one", 0.4, A)
        self.rec("worse", 0.3, B)
        self.rec("better", 0.5, C)
        self.pick("one")
        with self.assertRaises(LedgerError):
            self.pick("worse")
        self.pick("better")
        self.assertEqual(
            state(self.path, "arc")["selected_final_slots"]["protected-best"],
            "better",
        )

    def test_minimize_direction_is_supported(self):
        self.rec("one", 0.4, A, "minimize")
        self.rec("better", 0.3, B, "minimize")
        self.pick("one")
        self.pick("better")
        self.assertEqual(
            state(self.path, "arc")["selected_final_slots"]["protected-best"],
            "better",
        )

    def test_exploration_slot_can_rotate_to_worse_score(self):
        self.rec("one", 0.4, A)
        self.rec("two", 0.3, B)
        self.pick("one", "exploration")
        self.pick("two", "exploration")
        self.assertEqual(
            state(self.path, "arc")["selected_final_slots"]["exploration"],
            "two",
        )

    def test_regression_override_is_recorded(self):
        self.rec("one", 0.4, A)
        self.rec("two", 0.3, B)
        self.pick("one")
        event = self.pick("two", override=True)
        self.assertTrue(event["regression_override_used"])


if __name__ == "__main__":
    unittest.main()
