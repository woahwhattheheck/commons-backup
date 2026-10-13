# SPDX-License-Identifier: Apache-2.0
"""Exact installed-engine witness for the raw-prefix-before-parse behavior."""
from __future__ import annotations

import unittest

from market_prefix_rescue import rescue_market_prefix

try:
    from kaggle_environments import make
except ImportError:  # Local connector shells may not have the 59 MB package.
    make = None


@unittest.skipIf(make is None, "kaggle-environments not installed")
class OfficialEngineContractTests(unittest.TestCase):
    @staticmethod
    def _after_one_step(market, opponent_market=None, cap=1):
        env = make(
            "kaggriculture",
            configuration={"maxMarketOrdersPerTurn": cap, "episodeSteps": 4, "seed": 20260909},
            debug=True,
        )
        env.step([
            {"farmer": ["PASS"], "market": market},
            {"farmer": ["PASS"], "market": opponent_market or []},
        ])
        state = env.state[0]
        seeds = dict(state.observation.private["seeds"])
        money = float(state.observation.farms[0]["money"])
        return seeds, money

    def test_exact_blank_consumes_raw_cap_and_rescue_promotes_tail_buy(self):
        stranded = {"farmer": ["PASS"], "market": [[], ["BUY_SEED", "WHEAT", 1]]}
        rescued, report = rescue_market_prefix(stranded, {"maxMarketOrdersPerTurn": 1})
        self.assertTrue(report["changed"])
        before_seeds, before_money = self._after_one_step(stranded["market"])
        after_seeds, after_money = self._after_one_step(rescued["market"])
        self.assertEqual(before_seeds.get("WHEAT", 0), 0)
        self.assertEqual(before_money, 3000.0)
        self.assertEqual(after_seeds.get("WHEAT", 0), 1)
        self.assertEqual(after_money, 2990.0)

    def test_interior_blank_refused_preserves_absolute_indices(self):
        """Predecessor-discriminating witness from SOL-LATTICE review.

        Official engine advances both players by absolute market index and
        refreshes prices after each index. Interior [] packing would retime
        already-live rows; suffix-only activation must refuse that case.
        """
        original = [
            [],
            ["BUY_PRODUCT", "WHEAT", 1],
            ["HIRE"],
            ["BUY_SEED", "WHEAT", 1],
        ]
        action = {"market": original}
        output, report = rescue_market_prefix(action, {"maxMarketOrdersPerTurn": 3})
        self.assertIs(output, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "interior_blank_refused_to_avoid_retiming")
        self.assertEqual(report["blank_prefix_slots"], [0])

    def test_suffix_blank_rescues_without_retiming_live_prefix(self):
        original = [
            ["BUY_PRODUCT", "WHEAT", 1],
            ["HIRE"],
            [],
            ["BUY_SEED", "WHEAT", 1],
        ]
        action = {"market": original}
        output, report = rescue_market_prefix(action, {"maxMarketOrdersPerTurn": 3})
        self.assertTrue(report["changed"])
        self.assertEqual(output["market"], [
            ["BUY_PRODUCT", "WHEAT", 1],
            ["HIRE"],
            ["BUY_SEED", "WHEAT", 1],
            [],
        ])
        # Indices 0 and 1 stay put; only the blank slot is filled from the tail.
        self.assertEqual(output["market"][0], original[0])
        self.assertEqual(output["market"][1], original[1])
        self.assertEqual(report["rescued_orders"][0]["from_index"], 3)
        self.assertEqual(report["rescued_orders"][0]["to_index"], 2)


if __name__ == "__main__":
    unittest.main()
