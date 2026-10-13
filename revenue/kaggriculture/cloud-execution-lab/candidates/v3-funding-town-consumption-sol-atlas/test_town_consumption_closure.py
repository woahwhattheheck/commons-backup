# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from town_consumption_closure import (
    EXPECTED_ENGINE_BLOB_SHA1,
    EXPECTED_SOURCE_BLOB_SHA1,
    apply_public_town_consumption,
    git_blob_sha1,
    materialize,
    receipt,
    require_static_shop_lifecycle,
    verify_official_engine,
)

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
SOURCE = LAB / "frozen_selected.py"
ENGINE = LAB / "reference" / "engine" / "kaggriculture.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _pass_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def _state(module, *, money: int, step: int, route_end: int, buy_step: int):
    route = [_pass_action() for _ in range(route_end + 1)]
    route[buy_step]["market"] = [["BUY_PRODUCT", "WHEAT", 1]]
    farm = {
        "money": money,
        "tiles": [[None for _ in range(10)] for _ in range(10)],
        "farmer": [4, 4],
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    shed = {item: 0 for item in module.m.PRODUCTS + list(module.m.ANIMALS)}
    shed["MILK"] = 1
    private = {
        "shed": shed,
        "seeds": {crop: 0 for crop in module.m.CROPS},
        "inventories": [{}],
    }
    inventory = {item: 10000 for item in module.m.PRODUCTS}
    obs = {
        "step": step,
        "player": 0,
        "market": {"inventory": inventory, "prices": {}},
        "town": {"unlocked_shops": []},
    }
    config = {
        "shedCapacity": 100,
        "maxMarketOrdersPerTurn": 10,
        "turnsPerDay": 24,
        "townShopSellInterval": 4,
        "townCenterSellInterval": 24,
    }
    base = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "MILK", 1]]}
    return obs, config, base, farm, private, route


def _same_day_fixture(module):
    state = _state(module, money=31, step=0, route_end=22, buy_step=22)
    state[0]["town"]["unlocked_shops"] = ["BAKERY"] * 8
    return state


def _cross_day_fixture(module):
    # The current public shop set is stable through step 71 only. A shop can
    # unlock at that day close and affect the inherited step-77 purchase.
    return _state(module, money=26, step=71, route_end=77, buy_step=77)


class TownConsumptionClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest("run from repository candidate directory")
        sys.path.insert(0, str(LAB))
        cls.source_text = SOURCE.read_text(encoding="utf-8")
        cls.engine_text = ENGINE.read_text(encoding="utf-8")
        cls.patched_text = materialize(cls.source_text)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.patched_path = Path(cls.tmp.name) / "frozen_selected_town.py"
        cls.patched_path.write_text(cls.patched_text, encoding="utf-8")
        cls.original = _load("frozen_selected_town_predecessor", SOURCE)
        cls.patched = _load("frozen_selected_town_successor", cls.patched_path)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    def test_exact_source_and_engine_closure(self):
        self.assertEqual(git_blob_sha1(self.source_text), EXPECTED_SOURCE_BLOB_SHA1)
        self.assertEqual(
            verify_official_engine(self.engine_text),
            EXPECTED_ENGINE_BLOB_SHA1,
        )
        self.assertEqual(
            self.patched_text.count("def _funding_apply_town_consumption("), 1
        )
        self.assertEqual(
            self.patched_text.count("def _funding_require_static_shop_lifecycle("), 1
        )
        self.assertEqual(
            self.patched_text.count(
                "    _funding_require_static_shop_lifecycle(now, end, config)\n"
            ),
            1,
        )
        self.assertEqual(
            self.patched_text.count("        _funding_apply_town_consumption(\n"), 1
        )
        compile(self.patched_text, str(self.patched_path), "exec")

    def test_same_day_predecessor_false_minimum_zero_becomes_one(self):
        args = _same_day_fixture(self.original)
        obs, config, base, farm, private, route = args
        current = {"MILK": 1}
        targets = {"MILK": 1}
        old_minimum, old_receipt = self.original.funded_minimum_now(
            obs, config, base, farm, private, route, 22,
            current, targets, "MILK", stress_units=32,
        )

        args = _same_day_fixture(self.patched)
        obs, config, base, farm, private, route = args
        new_minimum, new_receipt = self.patched.funded_minimum_now(
            obs, config, base, farm, private, route, 22,
            current, targets, "MILK", stress_units=32,
        )
        self.assertFalse(old_receipt["fallback"])
        self.assertFalse(new_receipt["fallback"])
        self.assertEqual(old_minimum, 0)
        self.assertEqual(new_minimum, 1)

    def test_day_close_shop_evolution_predecessor_fails_closed(self):
        args = _cross_day_fixture(self.original)
        obs, config, base, farm, private, route = args
        old_minimum, old_receipt = self.original.funded_minimum_now(
            obs, config, base, farm, private, route, 77,
            {"MILK": 1}, {"MILK": 1}, "MILK", stress_units=0,
        )
        args = _cross_day_fixture(self.patched)
        obs, config, base, farm, private, route = args
        new_minimum, new_receipt = self.patched.funded_minimum_now(
            obs, config, base, farm, private, route, 77,
            {"MILK": 1}, {"MILK": 1}, "MILK", stress_units=0,
        )
        self.assertEqual(old_minimum, 0)
        self.assertFalse(old_receipt["fallback"])
        self.assertEqual(new_minimum, 1)
        self.assertTrue(new_receipt["fallback"])
        self.assertIn("day-close shop evolution", new_receipt["error"])

    def test_static_shop_lifecycle_boundary_and_type_contract(self):
        require_static_shop_lifecycle(0, 22, {"turnsPerDay": 24})
        require_static_shop_lifecycle(71, 71, {"turnsPerDay": 24})
        with self.assertRaisesRegex(RuntimeError, "day-close shop evolution"):
            require_static_shop_lifecycle(71, 77, {"turnsPerDay": 24})
        with self.assertRaises(TypeError):
            require_static_shop_lifecycle(0, 0, {"turnsPerDay": True})
        with self.assertRaises(ValueError):
            require_static_shop_lifecycle(0, 0, {"turnsPerDay": 24.5})
        with self.assertRaises(ValueError):
            require_static_shop_lifecycle(0, 0, {"turnsPerDay": 0})

    def test_official_public_wheat_quote_is_32_not_projected_31(self):
        inventory = {item: 10000 for item in self.original.m.PRODUCTS}
        config = {"townShopSellInterval": 4, "townCenterSellInterval": 24}
        for step in range(23):
            apply_public_town_consumption(
                inventory,
                ["BAKERY"] * 8,
                config,
                step,
                shop_products=self.original.m.SHOPS,
                products=self.original.m.PRODUCTS,
            )
        self.assertEqual(inventory["WHEAT"], 9951)
        exact_price = self.original.m.market_price(
            "WHEAT", inventory["WHEAT"] - 1, None
        )
        projected_stress_price = self.original.m.market_price(
            "WHEAT", 10000 - 32 - 1, None
        )
        self.assertEqual(projected_stress_price, 31)
        self.assertEqual(exact_price, 32)
        self.assertLess(31, exact_price)

    def test_duplicate_and_single_product_shops_are_counted_exactly(self):
        inventory = {item: 100 for item in self.original.m.PRODUCTS}
        apply_public_town_consumption(
            inventory,
            ["BAKERY", "YARN_STORE", "YARN_STORE"],
            {"townShopSellInterval": 4, "townCenterSellInterval": 24},
            4,
            shop_products=self.original.m.SHOPS,
            products=self.original.m.PRODUCTS,
        )
        self.assertEqual(inventory["WHEAT"], 99)
        self.assertEqual(inventory["EGG"], 99)
        self.assertEqual(inventory["WOOL"], 96)
        self.assertEqual(inventory["FERTILIZER"], 100)

    def test_town_center_excludes_fertilizer(self):
        inventory = {item: 100 for item in self.original.m.PRODUCTS}
        apply_public_town_consumption(
            inventory,
            [],
            {"townShopSellInterval": 99, "townCenterSellInterval": 6},
            6,
            shop_products=self.original.m.SHOPS,
            products=self.original.m.PRODUCTS,
        )
        self.assertEqual(inventory["WHEAT"], 99)
        self.assertEqual(inventory["FERTILIZER"], 100)

    def test_no_town_event_preserves_trace_exactly(self):
        obs, config, _base, farm, private, route = _same_day_fixture(self.original)
        obs["step"] = 1
        route = route[:4]
        old = self.original._funding_trace(
            obs, config, farm, private, route, 1, 3, [], stress_units=0
        )
        obs, config, _base, farm, private, route = _same_day_fixture(self.patched)
        obs["step"] = 1
        route = route[:4]
        new = self.patched._funding_trace(
            obs, config, farm, private, route, 1, 3, [], stress_units=0
        )
        self.assertEqual(old, new)

    def test_unknown_public_shop_fails_closed_to_parent_minimum(self):
        obs, config, base, farm, private, route = _same_day_fixture(self.patched)
        obs["town"]["unlocked_shops"] = ["NOT_A_SHOP"]
        minimum, report = self.patched.funded_minimum_now(
            obs, config, base, farm, private, route, 22,
            {"MILK": 1}, {"MILK": 1}, "MILK", stress_units=32,
        )
        self.assertEqual(minimum, 1)
        self.assertTrue(report["fallback"])
        self.assertIn("KeyError", report["error"])

    def test_receipt_is_strict_json_and_default_off(self):
        data = receipt(self.source_text, self.patched_text, self.engine_text)
        self.assertEqual(data["schema"], "titan-v3-funding-town-consumption/v2")
        self.assertTrue(data["complete"])
        self.assertEqual(data["lifecycle_guard_count"], 1)
        self.assertEqual(data["lifecycle_call_count"], 1)
        self.assertEqual(
            data["shop_lifecycle_policy"], "same-day exact; cross-day fail-closed"
        )
        self.assertFalse(data["canonical_runtime_modified"])
        self.assertFalse(data["hosted_strength_claim"])
        self.assertFalse(data["release_selection_claim"])
        json.dumps(data, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
