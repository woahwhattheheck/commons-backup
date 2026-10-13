# SPDX-License-Identifier: Apache-2.0
"""Regression: M1 pickup funding proof requires complete same-day frozen tape."""
from __future__ import annotations

import unittest

import r04_m1_wheat_trade as m1


def _planned(command=None):
    return {
        "farmer": list(command or ["PASS"]),
        "hands": [],
        "market": [],
    }


def _tape_through(end_step: int, *, pickup_step: int = 104):
    tape = [_planned() for _ in range(end_step + 1)]
    tape[pickup_step] = _planned(["PICKUP", "WHEAT", 3])
    return tape


class M1CompleteDayFundingCustodyTests(unittest.TestCase):
    def test_truncated_tape_through_candidate_fails_closed(self):
        # step 101 is day 4; the literal same-day end is step 119.  The old
        # implementation treated EOF=104 as day_end, certified the pickup at
        # 104, and therefore never proved that omitted 105..119 contain no cash
        # owner.  Incomplete day evidence must not authorize a pre-buy.
        due, demand = m1._future_literal_pickup(
            _tape_through(104),
            101,
            [[4, 4]],
            [["PASS"]],
            10,
        )
        self.assertIsNone(due)
        self.assertEqual(demand, 0)

    def test_complete_day_with_same_inert_suffix_preserves_candidate(self):
        due, demand = m1._future_literal_pickup(
            _tape_through(119),
            101,
            [[4, 4]],
            [["PASS"]],
            10,
        )
        self.assertEqual(due, 104)
        self.assertEqual(demand, 3)

    def test_complete_day_late_purchase_still_vetoes(self):
        tape = _tape_through(119)
        tape[110]["market"] = [["HIRE"]]
        due, demand = m1._future_literal_pickup(
            tape,
            101,
            [[4, 4]],
            [["PASS"]],
            10,
        )
        self.assertIsNone(due)
        self.assertEqual(demand, 0)


if __name__ == "__main__":
    unittest.main()
