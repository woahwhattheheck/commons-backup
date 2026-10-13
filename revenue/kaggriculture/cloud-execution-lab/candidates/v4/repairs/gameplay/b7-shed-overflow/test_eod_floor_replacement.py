#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("_b7_floor", HERE / "eod_floor_replacement.py")
assert SPEC is not None and SPEC.loader is not None
B7 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B7)
CFG = {"turnsPerDay": 24, "shedCapacity": 100, "maxMarketOrdersPerTurn": 10}


def price_fn(item, stock, params=None):
    if type(stock) is not int:
        raise TypeError("stock")
    quotes = (params or {}).get("quotes", {})
    return quotes.get(item, 2)


def obs(*, item="MILK", carry=5, x_shed=10, step=23, hands=0):
    shed = {key: 0 for key in sorted(B7.CARRYABLE)}
    shed[item] = x_shed
    fill_item = "CARROT" if item != "CARROT" else "TOMATO"
    shed[fill_item] = 100 - x_shed
    inventories = [{item: carry}] + [{} for _ in range(hands)]
    market_inventory = {key: 10000 for key in B7.PRODUCTS}
    quotes = {key: 2 for key in B7.PRODUCTS}
    quotes[item] = 1
    prices = {key: price_fn(key, market_inventory[key], {"quotes": quotes}) for key in B7.PRODUCTS}
    return {
        "step": step,
        "player": 0,
        "farms": [{"money": 100, "farmer": [4, 4], "hands": [[4, 4] for _ in range(hands)]}],
        "private": {"shed": shed, "inventories": inventories},
        "market": {"inventory": market_inventory, "prices": prices, "params": {"quotes": quotes}},
    }


def act(*, prefix_item="CARROT", prefix_qty=1, hands=0, empty=False):
    market = [] if empty else [["SELL", prefix_item, prefix_qty]]
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hands)], "market": market}


class EodFloorReplacementTest(unittest.TestCase):
    def test_exact_same_product_replacement(self):
        observation = obs()
        parent = act()
        decision = B7.analyze(observation, parent, CFG, market_price_fn=price_fn)
        self.assertTrue(decision["admit"], decision)
        self.assertEqual(decision["proposal"], ["SELL", "MILK", 4])
        self.assertEqual(decision["cash_gain"], 4)
        self.assertEqual(decision["baseline_final_shed"], decision["candidate_final_shed"])
        self.assertFalse(decision["full_callback_promotion"])

    def test_empty_prefix_is_safe_under_full_price_map_custody(self):
        decision = B7.analyze(obs(), act(empty=True), CFG, market_price_fn=price_fn)
        self.assertTrue(decision["admit"], decision)
        self.assertEqual(decision["proposal"], ["SELL", "MILK", 5])
        self.assertEqual(decision["prefix_sold"], {})

    def test_transform_appends_without_mutating_parent(self):
        observation = obs()
        parent = act()
        before = copy.deepcopy(parent)
        out = B7.transform(observation, parent, CFG, enabled=True, market_price_fn=price_fn)
        self.assertEqual(parent, before)
        self.assertIsNot(out, parent)
        self.assertEqual(out["market"], before["market"] + [["SELL", "MILK", 4]])

    def test_literal_true_only(self):
        parent = act()
        for poison in (None, 0, 1, 1.0, "false", [True], {"enabled": True}, object()):
            with self.subTest(poison=repr(poison)):
                self.assertIs(B7.transform(object(), parent, object(), enabled=poison, market_price_fn=price_fn), parent)
        self.assertIs(B7.transform(obs(), parent, CFG, enabled=False, market_price_fn=price_fn), parent)

    def test_install_marker_requires_literal_true_and_price_abi(self):
        parent_action = act()
        def parent(_obs, _cfg=None):
            return parent_action
        self.assertTrue(B7.install(parent, market_price_fn=price_fn, enabled=True).b7_eod_floor_replacement_enabled)
        self.assertFalse(B7.install(parent, market_price_fn=None, enabled=True).b7_eod_floor_replacement_enabled)
        for poison in (False, None, 1, "true", [True]):
            self.assertFalse(B7.install(parent, market_price_fn=price_fn, enabled=poison).b7_eod_floor_replacement_enabled)

    def test_requires_authenticated_price_abi(self):
        parent = act()
        decision = B7.analyze(obs(), parent, CFG)
        self.assertFalse(decision["admit"])
        self.assertEqual(decision["reason"], "missing_market_price_abi")
        self.assertIs(B7.transform(obs(), parent, CFG, enabled=True), parent)

    def test_requires_observed_theorem_configuration(self):
        class ExplodingConfig:
            shedCapacity = 100
            maxMarketOrdersPerTurn = 10

            @property
            def turnsPerDay(self):
                raise RuntimeError("no configuration authority")

        for bad_cfg in (
            None,
            {},
            {"shedCapacity": 100, "maxMarketOrdersPerTurn": 10},
            {"turnsPerDay": 24, "maxMarketOrdersPerTurn": 10},
            {"turnsPerDay": 24, "shedCapacity": 100},
            {"turnsPerDay": True, "shedCapacity": 100, "maxMarketOrdersPerTurn": 10},
            {"turnsPerDay": 24, "shedCapacity": 100.0, "maxMarketOrdersPerTurn": 10},
            {"turnsPerDay": 24, "shedCapacity": 100, "maxMarketOrdersPerTurn": "10"},
            ExplodingConfig(),
        ):
            with self.subTest(cfg=bad_cfg):
                decision = B7.analyze(obs(), act(), bad_cfg, market_price_fn=price_fn)
                self.assertFalse(decision["admit"], decision)
                self.assertEqual(decision["reason"], "clock_or_configuration")

        # A non-default capacity is valid only when it is explicitly observed.
        custom = {"turnsPerDay": 24, "shedCapacity": 101, "maxMarketOrdersPerTurn": 10}
        decision = B7.analyze(obs(), act(empty=True), custom, market_price_fn=price_fn)
        self.assertTrue(decision["admit"], decision)
        self.assertEqual(decision["proposal"], ["SELL", "MILK", 4])
        self.assertEqual(decision["baseline_final_shed"], decision["candidate_final_shed"])

    def test_rejects_non_eod(self):
        decision = B7.analyze(obs(step=22), act(), CFG, market_price_fn=price_fn)
        self.assertEqual(decision["reason"], "not_eod")

    def test_rejects_unit_mutation(self):
        parent = act()
        parent["farmer"] = ["NORTH"]
        self.assertEqual(B7.analyze(obs(), parent, CFG, market_price_fn=price_fn)["reason"], "unit_mutation")

    def test_rejects_non_sell_prefix(self):
        parent = act()
        parent["market"] = [["BUY_SEED", "WHEAT", 1]]
        self.assertEqual(B7.analyze(obs(), parent, CFG, market_price_fn=price_fn)["reason"], "market_prefix_or_slot")

    def test_effective_market_cap_minimum_one(self):
        cfg = dict(CFG)
        cfg["maxMarketOrdersPerTurn"] = 1
        self.assertEqual(B7.analyze(obs(), act(), cfg, market_price_fn=price_fn)["reason"], "market_prefix_or_slot")
        cfg["maxMarketOrdersPerTurn"] = 0
        empty_decision = B7.analyze(obs(), act(empty=True), cfg, market_price_fn=price_fn)
        self.assertTrue(empty_decision["admit"], empty_decision)

    def test_rejects_mixed_discard(self):
        observation = obs(carry=5, hands=1)
        observation["private"]["inventories"][1] = {"WOOL": 2}
        decision = B7.analyze(observation, act(hands=1), CFG, market_price_fn=price_fn)
        self.assertEqual(decision["reason"], "mixed_discard")

    def test_rejects_buyable_discard_product(self):
        for item in ("WHEAT", "FERTILIZER"):
            observation = obs(item=item)
            decision = B7.analyze(observation, act(), CFG, market_price_fn=price_fn)
            self.assertEqual(decision["reason"], "buyable_discard_product")

    def test_rejects_nonfloor_exact_quote(self):
        observation = obs()
        observation["market"]["params"]["quotes"]["MILK"] = 2
        observation["market"]["prices"]["MILK"] = 2
        decision = B7.analyze(observation, act(), CFG, market_price_fn=price_fn)
        self.assertEqual(decision["reason"], "not_exact_floor_quote")

    def test_rejects_insufficient_same_product_stock(self):
        observation = obs(x_shed=3, carry=5)
        observation["private"]["shed"]["CARROT"] = 97
        decision = B7.analyze(observation, act(), CFG, market_price_fn=price_fn)
        self.assertEqual(decision["reason"], "insufficient_same_product_shed_stock")

    def test_rejects_malformed_numeric_state(self):
        observation = obs()
        observation["farms"][0]["money"] = True
        self.assertEqual(B7.analyze(observation, act(), CFG, market_price_fn=price_fn)["reason"], "farm_state")
        observation = obs()
        observation["private"]["shed"]["MILK"] = True
        self.assertEqual(B7.analyze(observation, act(), CFG, market_price_fn=price_fn)["reason"], "private_state")
        observation = obs()
        parent = act()
        parent["market"][0][2] = True
        self.assertEqual(B7.analyze(observation, parent, CFG, market_price_fn=price_fn)["reason"], "market_prefix_or_slot")

    def test_rejects_price_map_drift_before_extra_refresh(self):
        observation = obs()
        observation["market"]["prices"]["WOOL"] += 7
        decision = B7.analyze(observation, act(), CFG, market_price_fn=price_fn)
        self.assertEqual(decision["reason"], "market_price_map_drift")

    def test_existing_floor_sell_of_same_product_is_allowed_when_stock_remains(self):
        observation = obs(carry=5, x_shed=12)
        parent = act(prefix_item="MILK", prefix_qty=1)
        decision = B7.analyze(observation, parent, CFG, market_price_fn=price_fn)
        self.assertTrue(decision["admit"], decision)
        self.assertEqual(decision["proposal"], ["SELL", "MILK", 4])

    def test_price_abi_exception_fails_closed(self):
        def broken(*_args, **_kwargs):
            raise RuntimeError("nope")
        decision = B7.analyze(obs(), act(), CFG, market_price_fn=broken)
        self.assertEqual(decision["reason"], "market_price_map_drift")


if __name__ == "__main__":
    unittest.main()
