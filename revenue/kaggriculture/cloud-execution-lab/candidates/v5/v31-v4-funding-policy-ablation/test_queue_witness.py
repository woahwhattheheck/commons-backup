# SPDX-License-Identifier: Apache-2.0
"""Queue-level predecessors against the exact submitted-V4 frozen selector.

Set TITAN_EXACT_V4_ROOT to a detached worktree for source 4af1113154... .
The pricing receipt is stubbed deliberately; these contracts target only the
exact V4 queue-movement theorem, while official-engine economics remain in
paired.py.
"""
from __future__ import annotations

import copy
import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


EXACT_V4 = "4af1113154e78c662780e6658cd920daac7902e3"
ROOT_ENV = "TITAN_EXACT_V4_ROOT"


def _load_exact():
    value = os.environ.get(ROOT_ENV)
    if not value:
        raise unittest.SkipTest(f"{ROOT_ENV} is required for exact-source witnesses")
    root = Path(value).resolve(strict=True)
    # The submitted archive flattens these helpers, but the pinned source tree
    # retains them in sibling project directories. Import only that same tree.
    sources = {
        "frozen_selected": root / "frozen_selected.py",
        "scheduler": root / "scheduler.py",
        "mechanics": root / "mechanics.py",
        "selected_sell_core": root / "selected_sell_core.py",
        "observed_clone": root.parent / "cloud-runtime-pulse" / "observed_clone.py",
        "seller_snapshot": root.parent / "cloud-quickstep" / "seller_snapshot.py",
    }
    for name, path in sources.items():
        if not path.is_file():
            raise AssertionError(f"missing exact {name} source: {path}")
    sys.path[:0] = [str(root), str(root.parent / "cloud-runtime-pulse"),
                   str(root.parent / "cloud-quickstep")]
    for name in sources:
        sys.modules.pop(name, None)
    module = importlib.import_module("frozen_selected")
    for name, expected in sources.items():
        loaded = sys.modules[name]
        if Path(loaded.__file__).resolve() != expected.resolve():
            raise AssertionError(f"loaded wrong {name} source: {loaded.__file__}")
    return module


class ExactV4QueueWitnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_exact()
        products = list(cls.mod.m.PRODUCTS)
        if not products:
            raise AssertionError("exact V4 exposes no products")
        cls.item = products[0]

    def _call(self, orders, *, money=0):
        item = self.item
        farm = {
            "money": money,
            "hires_today": 0,
            "unlocked_quadrants": [],
        }
        private = {"shed": {item: 4}}
        market = {"inventory": {product: 100 for product in self.mod.m.PRODUCTS}, "params": None}
        config = {
            "farmHandCostMult": 1,
            "shedCapacity": 100,
            "maxMarketOrdersPerTurn": 10,
        }
        # Queue logic is under test, not the SELL price curve. A selected sale
        # is made unambiguously sufficient to fund the first fixed acquisition.
        def receipt(_item, quantity, inventory, *_args, **_kwargs):
            return int(quantity) * 10**9, int(inventory), "queue-witness"

        before = copy.deepcopy(orders)
        with mock.patch.object(self.mod, "_stressed_sale_receipt", side_effect=receipt):
            out, info = self.mod.fund_same_turn_acquisition(
                copy.deepcopy(orders), farm, private, market, [], config, 0,
                {item}, lambda _product: 0,
            )
        self.assertEqual(orders, before, "exact V4 helper mutated caller queue")
        return out, info

    def test_later_selected_sale_moves_into_empty_prefix_and_funds_hire(self):
        item = self.item
        original = [[], ["HIRE"], ["SELL", item, 1]]
        out, info = self._call(original)
        self.assertTrue(info["applied"])
        self.assertEqual(info["target_index"], 1)
        self.assertEqual(info["source_index"], 2)
        self.assertEqual(info["destination_index"], 0)
        self.assertEqual(info["moved_quantity"], 1)
        self.assertEqual(out[0], ["SELL", item, 1])
        self.assertEqual(out[1], ["HIRE"])
        self.assertEqual(out[2], [])
        self.assertEqual(self.mod.sale_quantities(out), self.mod.sale_quantities(original))

    def test_no_empty_or_same_product_prefix_slot_keeps_queue_unchanged(self):
        item = self.item
        original = [["NOOP"], ["HIRE"], ["SELL", item, 1]]
        out, info = self._call(original)
        self.assertFalse(info["applied"])
        self.assertEqual(info["reason"], "no-safe-prefix-sale")
        self.assertEqual(out, original)

    def test_buy_product_barrier_refuses_to_launder_sale_across_unknown_price(self):
        item = self.item
        original = [[], ["BUY_PRODUCT", item, 1], ["HIRE"], ["SELL", item, 1]]
        out, info = self._call(original)
        self.assertFalse(info["applied"])
        self.assertEqual(info["reason"], "unsupported-buy-product")
        self.assertEqual(info["barrier_index"], 1)
        self.assertEqual(out, original)

    def test_already_funded_acquisition_does_not_reorder(self):
        item = self.item
        original = [[], ["HIRE"], ["SELL", item, 1]]
        out, info = self._call(original, money=10**9)
        self.assertIsNone(info)
        self.assertEqual(out, original)


if __name__ == "__main__":
    unittest.main()
