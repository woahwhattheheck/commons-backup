# SPDX-License-Identifier: MIT
"""Regression tests for the paired comparison consumed by the actual panels."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from measure import compare
from panel import describe, receipt_totals, summarize


def row(seat=0, scores=(10, 10), seed=1, status="complete"):
    return dict(seed=seed, opponent="baseline", candidate_seat=seat,
                scores=list(scores), status=status, arm="control",
                pre698_sha256="real-prefix", final_day_receipts=[],
                actors=[dict(max_call_seconds=.01), dict(max_call_seconds=.02)])


class PairingTests(unittest.TestCase):
    def test_seat_one_uses_candidate_score(self):
        r = compare([row(1, (30, 30))], [row(1, (40, 45))])["pairs"][0]
        self.assertEqual((r["own_cash_delta"], r["rival_cash_delta"], r["margin_delta"]), (15, 10, 5))
        self.assertEqual(r["flip"], "T>W")

    def test_join_not_array_order(self):
        result = compare([row(seed=1), row(seed=2)],
                         [row(scores=(20, 10), seed=2), row(scores=(8, 10), seed=1)])
        self.assertEqual([r["flip"] for r in result["pairs"]], ["T>L", "T>W"])

    def test_duplicate_is_not_counted_twice(self):
        with self.assertRaises(ValueError):
            compare([row(), row()], [row()])

    def test_failure_remains_unresolved(self):
        result = compare([row()], [row(status="failed", scores=(999, 0))])
        self.assertEqual(result["pairs"], [])
        self.assertEqual(len(result["unresolved"]), 1)
        self.assertEqual(result["flips"], {})

    def test_missing_side_remains_unresolved(self):
        result = compare([row()], [])
        self.assertEqual(len(result["unresolved"]), 1)
        self.assertIsNone(result["unresolved"][0]["candidate"])

    def test_absent_prefix_is_not_parity(self):
        a, b = row(), row()
        del a["pre698_sha256"]; del b["pre698_sha256"]
        self.assertFalse(compare([a], [b])["pairs"][0]["same_pre698_observations_and_actions"])

    def test_rival_cash_can_reverse_own_gain(self):
        result = compare([row(scores=(100, 100))], [row(scores=(105, 110))])["pairs"][0]
        self.assertEqual(result["own_cash_delta"], 5)
        self.assertEqual(result["margin_delta"], -5)
        self.assertEqual(result["flip"], "T>L")

    def test_empty_bank_is_not_win_or_parity(self):
        summary = describe([])
        self.assertEqual(summary["WTL"], {"W": 0, "T": 0, "L": 0})
        self.assertIsNone(summary["mean_margin"])

    def test_receipts_keep_player_and_operation(self):
        r = row()
        r["final_day_receipts"] = [dict(player=p, op=op, item="EGG", cash=c)
            for p, op, c in [(0, "SELL", 9), (1, "SELL", 8), (0, "BUY_PRODUCT", 12), (0, "SELL", 1)]]
        self.assertEqual(receipt_totals(r, 0), {"EGG": {"units": 2, "cash": 10}})

    def test_unknown_comparison_arm_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "one.json").write_text(json.dumps(row()))
            with self.assertRaises(ValueError):
                summarize(Path(d), [("control", "misspelled")])

    def test_summary_does_not_mutate_evidence(self):
        r = row(); previous = copy.deepcopy(r)
        describe([r]); receipt_totals(r, 0)
        self.assertEqual(r, previous)


if __name__ == "__main__":
    unittest.main()
