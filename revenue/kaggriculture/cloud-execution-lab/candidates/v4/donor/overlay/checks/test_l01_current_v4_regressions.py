# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest


MODULE = Path(__file__).resolve().parents[1] / "l01_mechanics.py"


def load_l01():
    name = "v4_l01_mechanics_guard_test"
    spec = importlib.util.spec_from_file_location(name, MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def row(*, market=None, unit=None):
    return {
        "farmer": list(unit or ["PASS"]),
        "hands": [],
        "market": deepcopy(market or []),
    }


def flags(**enabled):
    base = {key: False for key in ("LAND", "SHEEP", "DAY0BUY", "TRANCHE", "LEANPLANT")}
    base.update(enabled)
    return base


class L01CurrentV4RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.l01 = load_l01()

    def test_historical_day0_basket_is_rejected(self):
        wanted = [["BUY_PRODUCT", item, quantity]
                  for item, quantity in self.l01.DAY0_BASKET]
        issues = self.l01.day0_basket_issues(wanted)
        self.assertEqual([index for index, _ in issues], [0, 1, 2, 3, 4])
        self.assertTrue(all("unsupported_product" in code for _, code in issues))

    def test_engine_supported_product_grammar_is_accepted(self):
        self.assertEqual(
            self.l01.day0_basket_issues([
                ["BUY_PRODUCT", "WHEAT", 13],
                ["BUY_PRODUCT", "FERTILIZER", 2],
            ]),
            (),
        )

    def test_day0_feature_preserves_inherited_opening_on_rejection(self):
        route = [row(market=[["BUY_PRODUCT", "WHEAT", 13]])]
        routes = {"MAIN": route}
        before = deepcopy(routes)
        activations = Counter()
        reasons = []
        self.l01.patch_routes(routes, flags(DAY0BUY=True), activations, reasons)
        self.assertEqual(routes, before)
        self.assertEqual(activations["DAY0BUY"], 0)
        self.assertEqual(len(reasons), 1)
        self.assertTrue(reasons[0].startswith(self.l01.DAY0_REJECT_PREFIX + "["))

    def test_day0_rejection_does_not_block_other_l01_mechanics(self):
        route = [row(market=[["BUY_PRODUCT", "WHEAT", 13]]) for _ in range(100)]
        routes = {"MAIN": route}
        activations = Counter()
        reasons = []
        self.l01.patch_routes(routes, flags(DAY0BUY=True, LAND=True), activations, reasons)
        self.assertEqual(route[0]["market"], [["BUY_PRODUCT", "WHEAT", 13]])
        self.assertEqual(route[74]["market"][-1], ["BUY_LAND"])
        self.assertEqual(route[98]["market"][-1], ["BUY_LAND"])
        self.assertEqual(activations["LAND"], 2)
        self.assertEqual(activations["DAY0BUY"], 0)
        self.assertTrue(any(reason.startswith(self.l01.DAY0_REJECT_PREFIX) for reason in reasons))

    def test_day0_guard_rejects_noncanonical_rows(self):
        cases = [
            None,
            [["SELL", "WHEAT", 1]],
            [["BUY_PRODUCT", "WHEAT"]],
            [["BUY_PRODUCT", "WHEAT", True]],
            [["BUY_PRODUCT", "WHEAT", 0]],
            [["BUY_PRODUCT", 123, 1]],
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertTrue(self.l01.day0_basket_issues(case))

    def test_leanplant_exact_target_is_identity(self):
        route = [row(unit=["PLANT", "WHEAT"]) for _ in range(self.l01.KEEP_WHEAT_PLANTS)]
        routes = {"MAIN": route}
        before = deepcopy(routes)
        activations = Counter()
        reasons = []
        self.l01.patch_routes(routes, flags(LEANPLANT=True), activations, reasons)
        self.assertEqual(routes, before)
        self.assertEqual(activations["LEANPLANT"], 0)

    def test_leanplant_is_idempotent_after_reaching_target(self):
        route = [row(unit=["PLANT", "WHEAT"])
                 for _ in range(self.l01.KEEP_WHEAT_PLANTS + 5)]
        routes = {"MAIN": route}
        activations = Counter()
        reasons = []
        self.l01.patch_routes(routes, flags(LEANPLANT=True), activations, reasons)
        first = deepcopy(routes)
        self.assertEqual(self.l01.plant_counts(route)["WHEAT"], self.l01.KEEP_WHEAT_PLANTS)
        self.assertEqual(activations["LEANPLANT"], 5)
        self.l01.patch_routes(routes, flags(LEANPLANT=True), activations, reasons)
        self.assertEqual(routes, first)
        self.assertEqual(activations["LEANPLANT"], 5)

    def test_all_flags_off_remains_exact_noop(self):
        routes = {"MAIN": [row(market=[["BUY_PRODUCT", "WHEAT", 13]])]}
        before = deepcopy(routes)
        activations = Counter()
        reasons = []
        self.l01.patch_routes(routes, flags(), activations, reasons)
        self.assertEqual(routes, before)
        self.assertEqual(activations, Counter())
        self.assertEqual(reasons, [self.l01.NOOP])


if __name__ == "__main__":
    unittest.main()
