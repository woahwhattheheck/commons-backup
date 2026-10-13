# SPDX-License-Identifier: Apache-2.0
"""Focused V5 regressions for the seed-funding certificate's market grammar."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "reference" / "titan-current" / "seed_funding.py"
SPEC = importlib.util.spec_from_file_location("_v5_seed_funding", SOURCE)
seed_funding = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(seed_funding)


class Mechanics:
    CROPS = {"WHEAT": {"seed": 10}, "CARROT": {"seed": 20}}
    ANIMALS = {"COW": {"cost": 40}}
    PRODUCTS = {"WHEAT", "MILK", "FERTILIZER"}
    LAND_ORDER = ("NE", "SW", "SE")
    LAND_PRICES = (100, 200, 300)

    @staticmethod
    def _hire_cost(hires, multiplier):
        return (5 + hires) * multiplier


M = Mechanics()


def action(orders):
    return {"farmer": ["PASS"], "hands": [], "market": deepcopy(orders)}


def observation(money=100, hires=0):
    return {
        "player": 0,
        "farms": [{
            "money": money,
            "hires_today": hires,
            "unlocked_quadrants": ["NW"],
        }],
    }


class SeedFundingEngineGrammarTests(unittest.TestCase):
    def certify(self, rows, proposed_rows, *, money=100, config=None,
                public_product_bounds=False):
        return seed_funding.certify_seed_funding(
            M,
            observation(money),
            action(rows),
            action(proposed_rows),
            config,
            public_product_bounds=public_product_bounds,
        )

    def test_market_cap_matches_engine_minimum_one_and_int_coercion(self):
        rows = [["BUY_SEED", "WHEAT", 2], ["HIRE"]]
        proposed = [[], ["HIRE"]]
        for cap in (0, -1, -9):
            with self.subTest(cap=cap):
                report = self.certify(
                    rows, proposed, money=20,
                    config={"maxMarketOrdersPerTurn": cap},
                )
                self.assertEqual(report["status"], "certified", report)
                self.assertEqual(report["original_fixed_cost_upper_bound"], 20)
                self.assertEqual([p["slot"] for p in report["prefixes"]], [0])

        for cap in (2.9, "2"):
            with self.subTest(cap=cap):
                report = self.certify(
                    rows, proposed, money=20,
                    config={"maxMarketOrdersPerTurn": cap},
                )
                self.assertEqual(report["status"], "not_certified", report)
                self.assertEqual(report["reason"], "original_queue_needs_additional_cash")
                self.assertEqual(report["original_fixed_cost_upper_bound"], 25)

    def test_inherited_quantity_rows_use_engine_int_coercion_and_trailing_fields(self):
        rows = [
            ["BUY_SEED", "WHEAT", 2],
            ["BUY_ANIMAL", "COW", 2.9, "ignored-metadata"],
            ["SELL", "WHEAT", "1", "ignored-metadata"],
        ]
        proposed = [[], rows[1], rows[2]]
        report = self.certify(rows, proposed, money=100)
        self.assertEqual(report["status"], "certified", report)
        self.assertEqual(report["original_fixed_cost_upper_bound"], 100)
        self.assertEqual(
            [(p["operation"], p["cost_upper_bound"]) for p in report["prefixes"]],
            [("BUY_SEED", 20), ("BUY_ANIMAL", 80), ("SELL", 0)],
        )

    def test_malformed_unknown_and_nonpositive_inherited_rows_are_inert(self):
        rows = [
            ["BUY_SEED", "WHEAT", 2],
            {"malformed": True},
            ["BUY_ANIMAL", "COW", "x"],
            ["BUY_ANIMAL", "DRAGON", 2],
            ["BUY_ANIMAL", "COW", 0.7],
            ["BUY_ANIMAL", "COW", -3],
            ["BUY_PRODUCT", "NOT_A_PRODUCT", 3],
            ["UNKNOWN", "WHEAT", 2],
            ["HIRE"],
        ]
        proposed = [[], *deepcopy(rows[1:])]
        report = self.certify(rows, proposed, money=25)
        self.assertEqual(report["status"], "certified", report)
        self.assertEqual(report["original_fixed_cost_upper_bound"], 25)
        self.assertEqual(
            [(p["slot"], p["operation"]) for p in report["prefixes"]],
            [(0, "BUY_SEED"), (8, "HIRE")],
        )

    def test_inherited_quantity_overflow_matches_engine_failure(self):
        for quantity in (float("inf"), float("-inf")):
            with self.subTest(quantity=quantity):
                rows = [
                    ["BUY_SEED", "WHEAT", 2],
                    ["BUY_ANIMAL", "COW", quantity],
                ]
                report = self.certify(rows, [[], rows[1]], money=100)
                self.assertEqual(report["status"], "not_certified", report)
                self.assertIn("infinity", report["reason"].lower())

    def test_valid_product_row_still_requires_product_cash_evidence(self):
        for quantity in (2, 2.9, "2"):
            with self.subTest(quantity=quantity):
                rows = [
                    ["BUY_SEED", "WHEAT", 2],
                    ["BUY_PRODUCT", "WHEAT", quantity, "ignored-metadata"],
                ]
                report = self.certify(rows, [[], rows[1]], money=100)
                self.assertEqual(report["status"], "not_certified", report)
                self.assertIn("paired-flow", report["reason"])

    def test_edited_seed_rows_remain_strictly_certifiable(self):
        for malformed in (2.9, "2"):
            with self.subTest(malformed=malformed):
                rows = [["BUY_SEED", "WHEAT", malformed], ["HIRE"]]
                report = self.certify(rows, [[], ["HIRE"]], money=100)
                self.assertEqual(report["status"], "not_certified", report)

    def test_pathological_executable_quantity_preserves_certificate_safety_bound(self):
        rows = [
            ["BUY_SEED", "WHEAT", 2],
            ["BUY_ANIMAL", "COW", 99_999],
        ]
        report = self.certify(rows, [[], rows[1]], money=10_000_000)
        self.assertEqual(report["status"], "not_certified", report)
        self.assertIn("unit-loop boundary", report["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
