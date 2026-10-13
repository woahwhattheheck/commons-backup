# SPDX-License-Identifier: Apache-2.0
"""Regression for pinned-engine market-order floor in selected SELL replay."""
import unittest

import mechanics as m
from selected_action_sell import ProjectionLedger


class SelectedSellMarketLimitTests(unittest.TestCase):
    @staticmethod
    def _ledger(limit):
        now = 4
        observation = {
            "step": now,
            "player": 0,
            "farms": [
                {"money": 0, "hires_today": 0, "unlocked_quadrants": ["NW"]},
                {"money": 0, "hires_today": 0, "unlocked_quadrants": ["NW"]},
            ],
            "market": {
                "inventory": {product: 10000 for product in m.PRODUCTS},
                "params": None,
            },
            "town": {"unlocked_shops": []},
        }
        configuration = {
            "episodeSteps": 720,
            "turnsPerDay": 24,
            "shedCapacity": 100,
            "farmHandCostMult": 1,
            "maxMarketOrdersPerTurn": limit,
        }
        action = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
        projection = {
            "observed_step": now,
            "end_step": now,
            "stock_events": [],
            "future_market": {},
        }
        shed = {product: 0 for product in m.PRODUCTS}
        return ProjectionLedger(
            observation, configuration, action, shed, projection, None, {}, 8
        )

    def test_nonpositive_market_cap_still_executes_first_order(self):
        for limit in (0, -3):
            with self.subTest(limit=limit):
                ledger = self._ledger(limit)
                self.assertEqual(ledger.max_orders, 1)
                self.assertFalse(
                    ledger.feasible(None, ()),
                    "Pinned engine executes first HIRE even when configured cap is nonpositive",
                )


if __name__ == "__main__":
    unittest.main()
