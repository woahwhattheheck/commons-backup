# SPDX-License-Identifier: Apache-2.0
"""M1 complete-day funding: donor witness, action-level checks, exhaustive hours.

Extends donor regression db0cc52f70be6908816f5dc52c1eed5e0eae691d.
Run beside the canonical repair module; no legacy materializer is involved.
"""
from __future__ import annotations

import copy
import unittest

import r04_m1_wheat_trade as m1


CONFIG = {
    "episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
    "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
}


def _planned(command=None):
    return {"farmer": list(command or ["PASS"]), "hands": [], "market": []}


def _tape(end_step=119, pickup_step=104):
    tape = [_planned() for _ in range(end_step + 1)]
    tape[pickup_step] = _planned(["PICKUP", "WHEAT", 3])
    return tape


def _certificate(tape, step=101):
    return m1._future_literal_pickup(tape, step, [[4, 4]], [["PASS"]], 10)


def _observation(step=101, player=0):
    return {
        "step": step, "player": player,
        "market": {"inventory": {"WHEAT": 200 - step},
                   "prices": {"WHEAT": 20}},
        "private": {"shed": {}},
        "farms": [{"money": 5000.0, "farmer": [4, 4], "hands": []}
                  for _ in range(2)],
    }


def _apply(tape, player=0, *, money=5000.0, stock=None):
    m1.reset_for_tests()
    parent = _planned()
    m1.apply_m1_wheat_trade(_observation(100, player), parent, tape,
                          configuration=CONFIG, enabled=True)
    obs = _observation(101, player)
    obs["farms"][player]["money"] = money
    if stock is not None:
        obs["private"]["shed"] = stock
    before = copy.deepcopy((obs, parent, tape))
    out = m1.apply_m1_wheat_trade(obs, parent, tape,
                                configuration=CONFIG, enabled=True)
    return out, parent, before, (obs, parent, tape)


class M1CompleteDayFundingTests(unittest.TestCase):
    def setUp(self):
        m1.reset_for_tests()

    def test_truncated_tape_through_candidate_fails_closed(self):
        self.assertEqual(_certificate(_tape(104)), (None, 0))

    def test_complete_day_preserves_candidate(self):
        self.assertEqual(_certificate(_tape()), (104, 3))

    def test_late_purchase_vetoes(self):
        tape = _tape()
        tape[110]["market"] = [["HIRE"]]
        self.assertEqual(_certificate(tape), (None, 0))

    def test_every_partial_same_day_suffix_rejected(self):
        for end in range(104, 119):
            with self.subTest(end=end):
                self.assertEqual(_certificate(_tape(end)), (None, 0))

    def test_exact_day_end_inclusive_boundary(self):
        self.assertEqual(_certificate(_tape(118)), (None, 0))
        self.assertEqual(_certificate(_tape(119)), (104, 3))

    def test_each_purchase_at_final_same_day_step_vetoes(self):
        for op in ("HIRE", "BUY_LAND", "BUY_PRODUCT", "BUY_ANIMAL", "BUY_SEED"):
            with self.subTest(op=op):
                tape = _tape()
                tape[119]["market"] = [[op]]
                self.assertEqual(_certificate(tape), (None, 0))

    def test_next_day_purchase_is_outside_certificate(self):
        tape = _tape(120)
        tape[120]["market"] = [["HIRE"]]
        self.assertEqual(_certificate(tape), (104, 3))

    def test_final_executable_market_slot_vetoes(self):
        tape = _tape()
        tape[119]["market"] = [[] for _ in range(9)] + [["HIRE"]]
        self.assertEqual(_certificate(tape), (None, 0))

    def test_dead_suffix_purchase_does_not_veto(self):
        tape = _tape()
        tape[119]["market"] = [[] for _ in range(10)] + [["HIRE"]]
        self.assertEqual(_certificate(tape), (104, 3))

    def test_malformed_executable_row_fails_closed(self):
        tape = _tape()
        tape[119]["market"] = [[17]]
        self.assertEqual(_certificate(tape), (None, 0))

    def test_malformed_dead_suffix_is_ignored(self):
        tape = _tape()
        tape[119]["market"] = [[] for _ in range(10)] + [object()]
        self.assertEqual(_certificate(tape), (104, 3))

    def test_missing_final_plan_fails_closed(self):
        tape = _tape()
        tape[119] = None
        self.assertEqual(_certificate(tape), (None, 0))

    def test_tuple_tape_has_same_coverage_contract(self):
        self.assertEqual(_certificate(tuple(_tape(104))), (None, 0))
        self.assertEqual(_certificate(tuple(_tape(119))), (104, 3))

    def test_hour_23_pickup_remains_rejected(self):
        self.assertEqual(_certificate(_tape(119, 119), 117), (None, 0))

    def test_last_eligible_day_boundary(self):
        self.assertEqual(_certificate(_tape(694, 694), 692), (None, 0))
        self.assertEqual(_certificate(_tape(695, 694), 692), (694, 3))

    def test_complete_day_all_eligible_hours_and_lookahead_offsets(self):
        cases = 0
        for step in range(24, 696):
            end = (step // 24 + 1) * 24 - 1
            for offset in range(2, 7):
                due = step + offset
                if due >= end:
                    continue
                with self.subTest(step=step, due=due):
                    self.assertEqual(_certificate(_tape(end, due), step), (due, 3))
                cases += 1
        self.assertEqual(cases, 2660)

    def test_complete_tapes_buy_for_both_public_seats_without_mutation(self):
        for player in (0, 1):
            with self.subTest(player=player):
                out, parent, before, after = _apply(_tape(), player)
                self.assertIsNot(out, parent)
                self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 3]])
                self.assertEqual(before, after)
                self.assertEqual(m1.REPORT["buy_orders"], 1)
                self.assertEqual(m1._STATE[player]["bought_today"], 3)

    def test_truncated_tapes_return_parent_and_do_not_spend_for_both_seats(self):
        for player in (0, 1):
            with self.subTest(player=player):
                out, parent, before, after = _apply(_tape(104), player)
                self.assertIs(out, parent)
                self.assertEqual(before, after)
                self.assertEqual(m1.REPORT["buy_orders"], 0)
                self.assertEqual(m1.REPORT["buy_units"], 0)
                self.assertEqual(m1._STATE[player]["bought_today"], 0)
                self.assertEqual(m1._STATE[player]["last_buy"], -1000)

    def test_disabled_path_is_identity_and_has_no_observation_side_effects(self):
        parent = _planned()
        before = copy.deepcopy(m1.REPORT)
        out = m1.apply_m1_wheat_trade(object(), parent, object(), enabled=False)
        self.assertIs(out, parent)
        self.assertEqual(m1.REPORT, before)
        self.assertEqual(m1._STATE, {})

    def test_money_reserve_and_price_padding_boundary_preserved(self):
        for money, buys in ((1134.99, False), (1135, True), (10**1000, False)):
            with self.subTest(buys=buys, money_type=type(money).__name__):
                out, parent, _, _ = _apply(_tape(), money=money)
                self.assertEqual(out is not parent, buys)

    def test_shed_capacity_boundary_preserved(self):
        for stock, buys in ((97, True), (98, False)):
            with self.subTest(stock=stock):
                out, parent, _, _ = _apply(_tape(), stock={"CARROT": stock})
                self.assertEqual(out is not parent, buys)


if __name__ == "__main__":
    unittest.main()
