# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

from novel_rank_guard import FinalActionNoveltyGuard


def action(rows, farmer=None, hands=None):
    return {
        "farmer": ["PASS"] if farmer is None else farmer,
        "hands": [] if hands is None else hands,
        "market": copy.deepcopy(rows),
    }


class FinalActionNoveltyGuardTests(unittest.TestCase):
    def test_complete_suffix_collapse_returns_identity(self):
        base = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4], ["HIRE"]
        ])
        row = action([
            ["SELL", "MILK", 4], ["SELL", "WOOL", 5], ["HIRE"]
        ])
        # Remaining FrozenSelected economics + pressure converged both arms.
        final = action([
            ["SELL", "WOOL", 3], ["SELL", "MILK", 4], ["HIRE"]
        ])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, final, final, {}), base)
        self.assertEqual(guard.diagnostics["reason"], "collapsed_before_engine_execution")

    def test_complete_suffix_survivor_inside_prefix_is_admitted(self):
        base = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4], ["HIRE"]
        ])
        row = action([
            ["SELL", "MILK", 4], ["SELL", "WOOL", 5], ["HIRE"]
        ])
        incumbent_final = action([
            ["SELL", "WOOL", 3], ["SELL", "MILK", 4], ["HIRE"]
        ])
        row_final = action([
            ["SELL", "MILK", 4], ["SELL", "WOOL", 3], ["HIRE"]
        ])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), row
        )
        self.assertEqual(guard.diagnostics["status"], "applied")
        self.assertEqual(
            guard.diagnostics["reason"],
            "survives_complete_suffix_in_executable_prefix",
        )

    def test_final_difference_only_in_inert_suffix_returns_identity(self):
        config = {"maxMarketOrdersPerTurn": 2}
        base = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4],
            ["SELL", "EGG", 3], ["HIRE"],
        ])
        row = action([
            ["SELL", "MILK", 4], ["SELL", "WOOL", 5],
            ["SELL", "EGG", 3], ["HIRE"],
        ])
        incumbent_final = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4],
            ["SELL", "EGG", 3], ["HIRE"],
        ])
        row_final = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4],
            ["HIRE"], ["SELL", "EGG", 3],
        ])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, config), base
        )
        self.assertEqual(guard.diagnostics["reason"], "collapsed_before_engine_execution")

    def test_pre_seller_suffix_only_swap_is_rejected(self):
        config = {"maxMarketOrdersPerTurn": 2}
        base = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4],
            ["SELL", "EGG", 3], ["SELL", "CARROT", 2],
        ])
        row = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4],
            ["SELL", "CARROT", 2], ["SELL", "EGG", 3],
        ])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, base, row, config), base)
        self.assertIn("outside executable SELL block", guard.diagnostics["reason"])

    def test_pre_seller_suffix_promotion_into_prefix_is_rejected(self):
        config = {"maxMarketOrdersPerTurn": 2}
        base = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4],
            ["SELL", "EGG", 3], ["HIRE"],
        ])
        row = action([
            ["SELL", "EGG", 3], ["SELL", "WOOL", 5],
            ["SELL", "MILK", 4], ["HIRE"],
        ])
        self.assertEqual(
            FinalActionNoveltyGuard().choose(base, row, base, row, config), base
        )

    def test_market_cap_zero_is_min_one_and_row1_is_inert(self):
        config = {"maxMarketOrdersPerTurn": 0}
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "WOOL", 5], ["SELL", "EGG", 4]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, base, row, config), base)
        self.assertEqual(guard.diagnostics["market_prefix_limit"], 1)
        self.assertEqual(
            guard.diagnostics["reason"], "executable_leading_sell_block_lt_2"
        )

    def test_engine_dead_zero_quantity_is_a_barrier(self):
        base = action([["SELL", "WOOL", 0], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 0]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, base, row, {}), base)
        self.assertEqual(guard.diagnostics["leading_sell_count"], 0)

    def test_duplicate_rows_preserve_multiplicity(self):
        base = action([
            ["SELL", "WOOL", 5], ["SELL", "WOOL", 5],
            ["SELL", "MILK", 4], ["HIRE"],
        ])
        row = action([
            ["SELL", "MILK", 4], ["SELL", "WOOL", 5],
            ["SELL", "WOOL", 5], ["HIRE"],
        ])
        self.assertEqual(
            FinalActionNoveltyGuard().choose(base, row, base, row, {}), row
        )

    def test_quantity_change_is_not_a_permutation(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 5], ["SELL", "WOOL", 5]])
        self.assertEqual(
            FinalActionNoveltyGuard().choose(base, row, base, row, {}), base
        )

    def test_final_non_market_divergence_fails_closed(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = copy.deepcopy(base)
        row_final = action(
            [["SELL", "MILK", 4], ["SELL", "WOOL", 5]], farmer=["LEFT"]
        )
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )
        self.assertIn("non-market", guard.diagnostics["reason"])

    def test_stateful_suffix_may_resize_and_blank_before_final_compare(self):
        base = action([
            ["SELL", "WOOL", 5], ["SELL", "MILK", 4], ["HIRE"]
        ])
        row = action([
            ["SELL", "MILK", 4], ["SELL", "WOOL", 5], ["HIRE"]
        ])
        incumbent_final = action([["SELL", "WOOL", 2], [], ["HIRE"]])
        row_final = action([[], ["SELL", "WOOL", 2], ["HIRE"]])
        self.assertEqual(
            FinalActionNoveltyGuard().choose(
                base, row, incumbent_final, row_final, {}
            ),
            row,
        )

    def test_zero_quantity_vs_empty_final_row_collapses(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([["SELL", "WOOL", 0], ["HIRE"]])
        row_final = action([[], ["HIRE"]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )
        self.assertEqual(
            guard.diagnostics["incumbent_final_prefix"],
            guard.diagnostics["row_shed_final_prefix"],
        )
        self.assertEqual(guard.diagnostics["reason"], "collapsed_before_engine_execution")

    def test_unknown_op_vs_empty_final_row_collapses(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([["BOGUS"], ["HIRE"]])
        row_final = action([[], ["HIRE"]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )
        self.assertEqual(guard.diagnostics["reason"], "collapsed_before_engine_execution")

    def test_hire_extra_tokens_are_engine_equivalent(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([["HIRE"], ["SELL", "WOOL", 1]])
        row_final = action([["HIRE", "ignored"], ["SELL", "WOOL", 1]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )
        self.assertEqual(guard.diagnostics["reason"], "collapsed_before_engine_execution")

    def test_interior_inert_slot_alignment_remains_novel(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([[], ["HIRE"]])
        row_final = action([["HIRE"]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), row
        )
        self.assertEqual(guard.diagnostics["status"], "applied")

    def test_trailing_inert_slot_and_absence_are_engine_equivalent(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([["SELL", "WOOL", 1], []])
        row_final = action([["SELL", "WOOL", 1]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )
        self.assertEqual(guard.diagnostics["reason"], "collapsed_before_engine_execution")

    def test_quantity_coercion_matches_official_parser(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([["SELL", "WOOL", "2"], ["HIRE"]])
        row_final = action([["SELL", "WOOL", 2], ["HIRE"]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )
        self.assertEqual(guard.diagnostics["reason"], "collapsed_before_engine_execution")

    def test_unsupported_sell_item_is_quote_stage_inert(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([["SELL", "NOT_A_PRODUCT", 1], ["HIRE"]])
        row_final = action([[], ["HIRE"]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )

    def test_overflow_quantity_evidence_fails_closed(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([["SELL", "WOOL", float("inf")]])
        row_final = action([["SELL", "WOOL", 1]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )
        self.assertIn("overflows official parser", guard.diagnostics["reason"])

    def test_non_string_item_evidence_fails_closed(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        incumbent_final = action([["BUY_SEED", ["WHEAT"], 1]])
        row_final = action([["BUY_SEED", "WHEAT", 1]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, {}), base
        )
        self.assertIn("item must be a string", guard.diagnostics["reason"])

    def test_type_poisoned_market_cap_fails_closed(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        for poison in (True, 2.0, "2"):
            with self.subTest(poison=poison):
                guard = FinalActionNoveltyGuard()
                self.assertEqual(
                    guard.choose(
                        base, row, base, row,
                        {"maxMarketOrdersPerTurn": poison},
                    ),
                    base,
                )

    def test_malformed_final_action_fails_closed(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        malformed = copy.deepcopy(row)
        malformed["market"][0] = 7
        self.assertEqual(
            FinalActionNoveltyGuard().choose(base, row, base, malformed, {}), base
        )

    def test_inputs_are_never_mutated(self):
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4], ["HIRE"]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5], ["HIRE"]])
        incumbent_final = action([["SELL", "WOOL", 3], [], ["HIRE"]])
        row_final = action([[], ["SELL", "WOOL", 3], ["HIRE"]])
        config = {"maxMarketOrdersPerTurn": 10}
        values = (base, row, incumbent_final, row_final, config)
        snapshots = tuple(copy.deepcopy(value) for value in values)
        FinalActionNoveltyGuard().choose(
            base, row, incumbent_final, row_final, config
        )
        self.assertEqual(values, snapshots)


if __name__ == "__main__":
    unittest.main()
