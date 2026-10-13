# SPDX-License-Identifier: Apache-2.0
"""Additional evidence-shape checks for the one composed M1 repair package.

Complements, rather than replaces, test_v4_m1_daycoverage_boundaries. No
alternate helper, gameplay wiring, feature key, or economic claim is introduced.
"""
from __future__ import annotations

import copy
import unittest

import r04_m1_wheat_trade as m1
from test_v4_m1_complete_day import _tape_through
from test_v4_m1_money_overflow import CONFIG, _eligible_prefix


class M1EvidenceShapeTests(unittest.TestCase):
    def setUp(self):
        m1.reset_for_tests()

    def certificate(self, tape):
        return m1._future_literal_pickup(tape, 101, [[4, 4]], [["PASS"]], 10)

    def test_absent_final_action_cannot_certify_day_coverage(self):
        tape = _tape_through(119)
        tape[119] = None
        self.assertEqual(self.certificate(tape), (None, 0))

    def test_malformed_executable_market_row_declines(self):
        tape = _tape_through(119)
        tape[119]["market"] = [[] for _ in range(9)] + [object()]
        self.assertEqual(self.certificate(tape), (None, 0))

    def test_malformed_dead_market_suffix_is_never_validated(self):
        tape = _tape_through(119)
        tape[119]["market"] = [[] for _ in range(10)] + [object()]
        self.assertEqual(self.certificate(tape), (104, 3))

    def test_disabled_does_not_inspect_nonmapping_arguments(self):
        parent = object()
        before = copy.deepcopy((m1._STATE, m1.REPORT))
        out = m1.apply_m1_wheat_trade(
            object(), parent, object(), route_state=object(),
            configuration=object(), enabled=False)
        self.assertIs(out, parent)
        self.assertEqual((m1._STATE, m1.REPORT), before)

    def test_truncated_second_seat_preserves_inputs_and_buy_accounting(self):
        observation, parent = _eligible_prefix(player=1)
        tape = tuple(_tape_through(104))
        warmup = copy.deepcopy(observation)
        warmup["step"] -= 1
        warmup["market"]["inventory"]["WHEAT"] += 2
        m1.apply_m1_wheat_trade(
            warmup, parent, tape, configuration=CONFIG, enabled=True)
        before = copy.deepcopy((observation, parent, tape))
        out = m1.apply_m1_wheat_trade(
            observation, parent, tape, configuration=CONFIG, enabled=True)
        self.assertIs(out, parent)
        self.assertEqual((observation, parent, tape), before)
        self.assertEqual(m1.REPORT["buy_orders"], 0)
        self.assertEqual(m1._STATE[1]["bought_today"], 0)


if __name__ == "__main__":
    unittest.main()
