# SPDX-License-Identifier: Apache-2.0
"""M1 complete-day source-order repair: boundary and action-level regressions.

Tests use the exact repaired helper, not an alternate execution model. They
prove source behavior only; they are not an engine/economic promotion panel.
"""
from __future__ import annotations

import copy
import unittest

import r04_m1_wheat_trade as m1
from test_v4_m1_complete_day import _planned, _tape_through
from test_v4_m1_money_overflow import CONFIG, _eligible_prefix


class DayCoverageBoundaryTests(unittest.TestCase):
    def setUp(self):
        m1.reset_for_tests()

    def _certify(self, tape, step=101):
        return m1._future_literal_pickup(tape, step, [[4, 4]], [["PASS"]], 10)

    def _apply(self, tape, *, player=0, enabled=True):
        observation, parent = _eligible_prefix(player=player)
        warmup = copy.deepcopy(observation)
        warmup["step"] -= 1
        warmup["market"]["inventory"]["WHEAT"] += 2
        m1.apply_m1_wheat_trade(warmup, parent, tape,
                                configuration=CONFIG, enabled=enabled)
        before = copy.deepcopy((observation, parent, tape))
        out = m1.apply_m1_wheat_trade(observation, parent, tape,
                                     configuration=CONFIG, enabled=enabled)
        self.assertEqual((observation, parent, tape), before)
        return parent, out

    def test_complete_day_activates_without_mutating_inputs_for_both_seats(self):
        for player in (0, 1):
            with self.subTest(player=player):
                m1.reset_for_tests()
                parent, out = self._apply(_tape_through(119), player=player)
                self.assertIsNot(out, parent)
                self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 3]])
                self.assertEqual(m1.REPORT["buy_units"], 3)

    def test_truncation_preserves_parent_identity_and_never_books_buy(self):
        for end in range(104, 119):
            with self.subTest(end=end):
                m1.reset_for_tests()
                parent, out = self._apply(_tape_through(end))
                self.assertIs(out, parent)
                self.assertEqual(m1.REPORT["future_pickups"], 0)
                self.assertEqual(m1.REPORT["buy_orders"], 0)
                self.assertEqual(m1._STATE[0]["bought_today"], 0)

    def test_all_eligible_step_lookahead_and_eof_boundaries(self):
        cases = 0
        complete = 0
        # Covers every eligible callback, not only the original step-101 witness.
        for step in range(24, 696):
            day_end = (step // 24 + 1) * 24 - 1
            for delta in range(2, 7):
                pickup = step + delta
                if pickup >= day_end:
                    continue
                tape = _tape_through(day_end, pickup_step=pickup)
                with self.subTest(step=step, pickup=pickup, eof=day_end):
                    self.assertEqual(self._certify(tape, step), (pickup, 3))
                complete += 1
                for eof in range(pickup, day_end):
                    with self.subTest(step=step, pickup=pickup, eof=eof):
                        self.assertEqual(self._certify(tape[:eof + 1], step), (None, 0))
                    cases += 1
        self.assertEqual(complete, 2660)
        self.assertEqual(cases, 26740)

    def test_all_cash_owner_ops_all_remaining_hours_and_live_edge_slots(self):
        for step in range(105, 120):
            for opcode in sorted(m1._PURCHASE_OPS):
                for slot in (0, 9):
                    with self.subTest(step=step, opcode=opcode, slot=slot):
                        tape = _tape_through(119)
                        tape[step]["market"] = [[] for _ in range(slot)] + [[opcode]]
                        self.assertEqual(self._certify(tape), (None, 0))

    def test_cash_owner_at_first_dead_raw_slot_does_not_veto(self):
        for opcode in sorted(m1._PURCHASE_OPS):
            with self.subTest(opcode=opcode):
                tape = _tape_through(119)
                tape[110]["market"] = [[] for _ in range(10)] + [[opcode]]
                self.assertEqual(self._certify(tape), (104, 3))

    def test_next_day_purchase_does_not_claim_this_day_cash(self):
        tape = _tape_through(120)
        tape[120]["market"] = [["HIRE"]]
        self.assertEqual(self._certify(tape), (104, 3))

    def test_hour23_pickup_is_still_not_certified(self):
        self.assertEqual(self._certify(_tape_through(119, pickup_step=119), 116),
                         (None, 0))

    def test_missing_market_evidence_at_literal_day_end_declines(self):
        tape = _tape_through(119)
        tape[119] = {"farmer": ["PASS"], "hands": []}
        self.assertEqual(self._certify(tape), (None, 0))

    def test_tuple_tape_has_identical_day_coverage_contract(self):
        self.assertEqual(self._certify(tuple(_tape_through(119))), (104, 3))
        self.assertEqual(self._certify(tuple(_tape_through(118))), (None, 0))

    def test_disabled_lane_is_identity_and_does_not_touch_state(self):
        parent, out = self._apply(_tape_through(104), enabled=False)
        self.assertIs(out, parent)
        self.assertEqual(m1._STATE, {})
        self.assertEqual(m1.REPORT["calls"], 0)


if __name__ == "__main__":
    unittest.main()
