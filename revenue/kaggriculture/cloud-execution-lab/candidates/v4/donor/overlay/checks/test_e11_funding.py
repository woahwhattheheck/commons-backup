# SPDX-License-Identifier: Apache-2.0
"""Focused V3 E11 executable-prefix and downstream-funding regressions."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import e11_rival_sell as e11  # noqa: E402


def obs(*, step=5, money=3000, hires_today=0):
    return {
        "step": step,
        "player": 0,
        "farms": [
            {
                "money": money,
                "hires_today": hires_today,
                "unlocked_quadrants": ["NW"],
                "tiles": [[None]],
                "hands": [],
            },
            {
                "money": 3000,
                "hires_today": 0,
                "unlocked_quadrants": ["NW"],
                "tiles": [[None]],
                "hands": [],
            },
        ],
        "market": {"prices": {"WHEAT": 10}, "inventory": {"WHEAT": 10000}},
        "town": {"unlocked_shops": ["BAKERY"]},
    }


def absorb(_item, step, _shops, _config):
    return 2 if step % 4 == 0 else 0


class E11FundingEquivalenceTests(unittest.TestCase):
    def apply(self, observation, market, **cfg):
        action = {"farmer": ["PASS"], "hands": [], "market": deepcopy(market)}
        before = deepcopy(action)
        out, report = e11.apply_e11(
            observation,
            action,
            [(2, {"WHEAT": 40})],
            {
                "episodeSteps": 12,
                "rival_dump_lookback_steps": 8,
                "e11_min_future_absorption": 2,
                **cfg,
            },
            absorb,
            enabled=True,
        )
        self.assertEqual(action, before)
        return out, report

    def test_standalone_qualifying_sell_still_defers(self):
        out, report = self.apply(obs(), [["SELL", "WHEAT", 1]])
        self.assertEqual(out["market"], [[]])
        self.assertTrue(report["changed"])
        self.assertEqual(report["protected_indices"], [])

    def test_cash_funding_sell_before_buy_land_is_preserved(self):
        market = [["SELL", "WHEAT", 1], ["BUY_LAND"]]
        out, report = self.apply(obs(money=999), market)
        self.assertEqual(out["market"], market)
        self.assertFalse(report["changed"])
        self.assertEqual(report["protected_indices"], [0])
        self.assertEqual(report["reason"], "NO_OP_DOWNSTREAM_MARKET_DEPENDENCY")

    def test_capacity_releasing_sell_before_buy_animal_is_preserved(self):
        market = [["SELL", "WHEAT", 1], ["BUY_ANIMAL", "SHEEP", 1]]
        out, report = self.apply(obs(money=3000), market)
        self.assertEqual(out["market"], market)
        self.assertEqual(report["protected_indices"], [0])

    def test_engine_inert_tail_sell_is_untouched(self):
        prefix = [["HIRE"] for _ in range(10)]
        market = prefix + [["SELL", "WHEAT", 1]]
        out, report = self.apply(obs(money=1000), market, maxMarketOrdersPerTurn=10)
        self.assertEqual(out["market"], market)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "PRICE_DROP_NO_MATCHING_SELL")

    def test_zero_and_negative_limits_match_official_minimum_one(self):
        market = [["SELL", "WHEAT", 1], ["SELL", "WHEAT", 1]]
        for limit in (0, -3):
            with self.subTest(limit=limit):
                out, report = self.apply(
                    obs(), market, maxMarketOrdersPerTurn=limit)
                self.assertEqual(out["market"], [[], ["SELL", "WHEAT", 1]])
                self.assertTrue(report["changed"])
                self.assertEqual(report["executable_prefix_length"], 1)
                self.assertEqual(report["deferred"], ["WHEAT"])

    def test_later_hire_can_remain_when_public_cash_proves_independent(self):
        market = [["SELL", "WHEAT", 4], ["HIRE"]]
        out, report = self.apply(obs(money=3000), market)
        self.assertEqual(out["market"], [[], ["HIRE"]])
        self.assertTrue(report["changed"])

    def test_later_hire_is_preserved_when_sale_is_needed_for_cash(self):
        market = [["SELL", "WHEAT", 4], ["HIRE"]]
        out, report = self.apply(obs(money=0), market)
        self.assertEqual(out["market"], market)
        self.assertEqual(report["protected_indices"], [0])

    def test_disabled_is_exact_object_identity(self):
        action = {"market": [["SELL", "WHEAT", 1], ["BUY_LAND"]]}
        out, report = e11.apply_e11(obs(money=999), action, [(2, {"WHEAT": 40})], {}, absorb)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "OFF")


if __name__ == "__main__":
    unittest.main()
