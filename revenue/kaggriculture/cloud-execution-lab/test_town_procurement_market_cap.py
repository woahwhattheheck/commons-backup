# SPDX-License-Identifier: Apache-2.0
"""Regression for TOWNPROCURE market-cap topology preservation."""
from __future__ import annotations

import copy
import unittest

import town_procurement


class TownProcurementMarketCapTests(unittest.TestCase):
    def tearDown(self):
        town_procurement.reset()

    @staticmethod
    def _observation(step: int, wheat: int) -> dict:
        return {
            "step": step,
            "player": 0,
            "private": {"shed": {"WHEAT": wheat}},
        }

    def test_full_source_suppression_keeps_market_cap_topology(self):
        town_procurement.reset()
        configuration = {"maxMarketOrdersPerTurn": 10}

        # Establish a fully confirmed move through the public receipt path:
        # baseline 3 + advanced 3 all arrive on the target callback.
        target_action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["BUY_PRODUCT", "WHEAT", 3, 99]],
        }
        advanced, advance_report = town_procurement.apply(
            self._observation(200, 0), target_action, configuration, completed=True
        )
        self.assertTrue(advance_report["changed"])
        self.assertEqual(advanced["market"][0][2], 6)

        receipt = town_procurement.observe(self._observation(201, 6))
        self.assertEqual(receipt["confirmed_source"], 202)
        self.assertEqual(receipt["confirmed_qty"], 3)
        town_procurement.observe(self._observation(202, 6))

        # Row 10 is outside the engine's ten-order prefix.  Deleting row 0 on
        # full suppression would wrongly promote this sentinel into execution.
        prefix_suffix = [["BUY_PRODUCT", "FERTILIZER", 1, index]
                         for index in range(1, 10)]
        sentinel = ["BUY_PRODUCT", "FERTILIZER", 7, "must-stay-inert"]
        source_action = {
            "market": [["BUY_PRODUCT", "WHEAT", 3, "source"]]
                      + prefix_suffix + [sentinel],
        }
        snapshot = copy.deepcopy(source_action)

        suppressed, report = town_procurement.suppress_confirmed(
            self._observation(202, 6), source_action, configuration
        )

        self.assertTrue(report["changed"])
        self.assertEqual(report["status"], "source_suppressed")
        self.assertEqual(report["suppressed_qty"], 3)
        self.assertEqual(report["source_qty_after"], 0)
        self.assertEqual(len(suppressed["market"]), 11)
        self.assertEqual(
            suppressed["market"][0],
            ["BUY_PRODUCT", "WHEAT", 0, "source"],
        )
        self.assertEqual(suppressed["market"][1:], snapshot["market"][1:])
        self.assertEqual(suppressed["market"][10], sentinel)
        self.assertEqual(source_action, snapshot)


if __name__ == "__main__":
    unittest.main()
