# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import unittest

from novel_rank_guard import FinalActionNoveltyGuard


def action(rows):
    return {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rows)}


class FinalActionNoveltyPrefixBoundaryTests(unittest.TestCase):
    def test_malformed_raw_suffix_is_inert_for_parent_and_final_evidence(self):
        config = {"maxMarketOrdersPerTurn": 2}
        parent_suffix = {"raw": "engine never parses row 2"}
        base = action([
            ["SELL", "WOOL", 5],
            ["SELL", "MILK", 4],
            parent_suffix,
        ])
        row = action([
            ["SELL", "MILK", 4],
            ["SELL", "WOOL", 5],
            parent_suffix,
        ])
        incumbent_final = action([
            ["SELL", "WOOL", 3],
            ["SELL", "MILK", 4],
            {"final": "incumbent-only inert suffix"},
        ])
        row_final = action([
            ["SELL", "MILK", 4],
            ["SELL", "WOOL", 3],
            7,
        ])

        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, incumbent_final, row_final, config), row
        )
        self.assertEqual(guard.diagnostics["status"], "applied")
        self.assertEqual(
            guard.diagnostics["reason"],
            "survives_complete_suffix_in_executable_prefix",
        )
        self.assertEqual(guard.diagnostics["market_prefix_limit"], 2)

    def test_raw_parent_candidate_suffix_still_requires_exact_preservation(self):
        config = {"maxMarketOrdersPerTurn": 2}
        base = action([
            ["SELL", "WOOL", 5],
            ["SELL", "MILK", 4],
            {"raw": "left"},
        ])
        row = action([
            ["SELL", "MILK", 4],
            ["SELL", "WOOL", 5],
            {"raw": "right"},
        ])

        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, base, row, config), base)
        self.assertIn("outside executable SELL block", guard.diagnostics["reason"])

    def test_malformed_candidate_inside_executable_prefix_fails_closed(self):
        config = {"maxMarketOrdersPerTurn": 2}
        base = action([
            ["SELL", "WOOL", 5],
            ["SELL", "MILK", 4],
            {"raw": "inert"},
        ])
        row = action([
            ["SELL", "MILK", 4],
            {"poison": "inside prefix"},
            {"raw": "inert"},
        ])

        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, base, row, config), base)
        self.assertIn("executable row-shed market row", guard.diagnostics["reason"])

    def test_malformed_final_row_inside_executable_prefix_fails_closed(self):
        config = {"maxMarketOrdersPerTurn": 2}
        base = action([
            ["SELL", "WOOL", 5],
            ["SELL", "MILK", 4],
            {"raw": "inert"},
        ])
        row = action([
            ["SELL", "MILK", 4],
            ["SELL", "WOOL", 5],
            {"raw": "inert"},
        ])
        malformed_final = action([
            7,
            ["SELL", "MILK", 4],
            {"raw": "ignored"},
        ])

        guard = FinalActionNoveltyGuard()
        self.assertEqual(
            guard.choose(base, row, malformed_final, row, config), base
        )
        self.assertIn("executable final market row", guard.diagnostics["reason"])

    def test_unsupported_sell_first_is_hard_barrier_not_sortable(self):
        # Red-team witness: live WOOL must not cross engine-inert unsupported SELL.
        config = {"maxMarketOrdersPerTurn": 2}
        base = action([["SELL", "NOT_A_PRODUCT", 1], ["SELL", "WOOL", 5]])
        row = action([["SELL", "WOOL", 5], ["SELL", "NOT_A_PRODUCT", 1]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, base, row, config), base)
        self.assertEqual(guard.diagnostics["leading_sell_count"], 0)
        self.assertEqual(
            guard.diagnostics["reason"], "executable_leading_sell_block_lt_2"
        )

    def test_unsupported_sell_interior_is_hard_barrier(self):
        config = {"maxMarketOrdersPerTurn": 3}
        base = action([
            ["SELL", "WOOL", 5],
            ["SELL", "NOT_A_PRODUCT", 1],
            ["SELL", "MILK", 4],
        ])
        row = action([
            ["SELL", "MILK", 4],
            ["SELL", "WOOL", 5],
            ["SELL", "NOT_A_PRODUCT", 1],
        ])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, base, row, config), base)
        self.assertEqual(guard.diagnostics["leading_sell_count"], 1)
        self.assertEqual(
            guard.diagnostics["reason"], "executable_leading_sell_block_lt_2"
        )

    def test_supported_products_permutation_still_admits(self):
        config = {"maxMarketOrdersPerTurn": 2}
        base = action([["SELL", "WOOL", 5], ["SELL", "MILK", 4]])
        row = action([["SELL", "MILK", 4], ["SELL", "WOOL", 5]])
        guard = FinalActionNoveltyGuard()
        self.assertEqual(guard.choose(base, row, base, row, config), row)
        self.assertEqual(guard.diagnostics["status"], "applied")
        self.assertEqual(guard.diagnostics["leading_sell_count"], 2)


if __name__ == "__main__":
    unittest.main()
