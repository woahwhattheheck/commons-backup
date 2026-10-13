# SPDX-License-Identifier: Apache-2.0
"""Pinned-engine market grammar regressions for TOWNPROCURE."""
from __future__ import annotations

import unittest

import town_procurement


class TownProcurementMarketGrammarTests(unittest.TestCase):
    def tearDown(self):
        town_procurement.reset()

    @staticmethod
    def _observation(step: int, wheat: int = 0) -> dict:
        return {
            "step": step,
            "player": 0,
            "private": {"shed": {"WHEAT": wheat}},
        }

    @staticmethod
    def _action(market: list) -> dict:
        return {
            "farmer": ["PASS"],
            "hands": [],
            "market": market,
        }

    def test_coercible_cap_and_quantity_use_only_executable_prefix(self):
        action = self._action([
            ["PASS"],
            ["BUY_PRODUCT", "WHEAT", "3", "engine-valid-metadata"],
            ["BUY_PRODUCT", "WHEAT", 99, "inert-suffix-duplicate"],
        ])
        result, report = town_procurement.apply(
            self._observation(200),
            action,
            {"maxMarketOrdersPerTurn": "2"},
            completed=True,
        )
        self.assertEqual(report["status"], "target_advanced")
        self.assertEqual(
            result["market"][1],
            ["BUY_PRODUCT", "WHEAT", 6, "engine-valid-metadata"],
        )
        self.assertEqual(result["market"][2], action["market"][2])

    def test_inert_wheat_sell_rows_do_not_block_target(self):
        action = self._action([
            ["SELL", "WHEAT", 0, "parsed-inert"],
            ["SELL", "WHEAT", "not-a-number", "malformed"],
            ["SELL", "WHEAT", float("nan"), "value-error-inert"],
            ["BUY_PRODUCT", "WHEAT", 3],
        ])
        result, report = town_procurement.apply(
            self._observation(200),
            action,
            {"maxMarketOrdersPerTurn": 4},
            completed=True,
        )
        self.assertEqual(report["status"], "target_advanced")
        self.assertEqual(result["market"][3][2], 6)

    def test_infinite_market_quantities_match_engine_overflow(self):
        for quantity in (float("inf"), float("-inf")):
            for op in ("BUY_PRODUCT", "SELL"):
                with self.subTest(quantity=quantity, op=op):
                    with self.assertRaises(OverflowError):
                        town_procurement._market_quantity(
                            [op, "WHEAT", quantity],
                            op,
                            "WHEAT",
                        )

        action = self._action([
            ["SELL", "WHEAT", float("inf"), "engine-fatal-row"],
            ["BUY_PRODUCT", "WHEAT", 3],
        ])
        with self.assertRaises(OverflowError):
            town_procurement.apply(
                self._observation(200),
                action,
                {"maxMarketOrdersPerTurn": 2},
                completed=True,
            )
        self.assertEqual(action["market"][1][2], 3)
        self.assertIsNone(town_procurement._STATE.get(0, {}).get("pending"))

    def test_engine_valid_coercible_wheat_sell_still_blocks_target(self):
        action = self._action([
            ["SELL", "WHEAT", "1", "engine-valid-metadata"],
            ["BUY_PRODUCT", "WHEAT", 3],
        ])
        result, report = town_procurement.apply(
            self._observation(200),
            action,
            {"maxMarketOrdersPerTurn": 2},
            completed=True,
        )
        self.assertIs(result, action)
        self.assertEqual(report["status"], "target_wheat_sale_conflict")

    def test_market_cap_coercion_matches_engine_effective_prefix(self):
        self.assertEqual(
            town_procurement._prefix_limit({}, {"maxMarketOrdersPerTurn": "2"}), 2
        )
        self.assertEqual(
            town_procurement._prefix_limit({}, {"maxMarketOrdersPerTurn": 2.9}), 2
        )
        self.assertEqual(
            town_procurement._prefix_limit({}, {"maxMarketOrdersPerTurn": 0}), 1
        )
        self.assertEqual(
            town_procurement._prefix_limit({}, {"maxMarketOrdersPerTurn": -3}), 1
        )

    def test_invalid_market_cap_fails_closed_instead_of_inventing_prefix(self):
        for value in (
            float("inf"),
            float("-inf"),
            float("nan"),
            "not-a-number",
            None,
            [],
            {},
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    town_procurement._prefix_limit(
                        {}, {"maxMarketOrdersPerTurn": value}
                    )

        action = self._action([["BUY_PRODUCT", "WHEAT", 3]])
        with self.assertRaises(ValueError):
            town_procurement.apply(
                self._observation(200),
                action,
                {"maxMarketOrdersPerTurn": float("inf")},
                completed=True,
            )
        self.assertEqual(action["market"][0][2], 3)
        self.assertIsNone(town_procurement._STATE.get(0, {}).get("pending"))


if __name__ == "__main__":
    unittest.main()
