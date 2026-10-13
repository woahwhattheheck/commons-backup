# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import itertools
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve()
ROOT = HERE.parents[5]
ENGINE_DIR = Path(os.environ.get("TITAN_ENGINE_DIR", str(ROOT / "test_support/engine")))
DEFAULT_LOADER = ROOT / "test_support/existing_loader.py"
if not DEFAULT_LOADER.exists():
    DEFAULT_LOADER = ROOT / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"
ENGINE_LOADER = Path(os.environ.get("TITAN_ENGINE_LOADER", str(DEFAULT_LOADER)))
ORIGINAL_OVERLAY = HERE.parents[1] / "fixtures/original_overlay.py"
sys.path.insert(0, str(HERE.parents[1]))
from reproduce import apply_overlay, load_engine, load_file, reproduce, run_market, SOURCE_PATH


class OrderedAblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixed = load_file(ROOT / SOURCE_PATH, "test_fixed_overlay")
        cls.original = load_file(ORIGINAL_OVERLAY, "test_original_overlay")
        cls.engine, cls.struct = load_engine(ENGINE_DIR, ENGINE_LOADER)

    def action(self, orders):
        return {"farmer": ["EAST"], "hands": [["HARVEST"], ["WATER"]], "market": orders,
                "extra": {"preserved": [1, 2]}}

    def apply(self, orders, name="agent_no_goose"):
        return apply_overlay(self.fixed, self.action(orders), name)

    def test_slot_count_and_indices(self):
        orders = [["BUY_ANIMAL", "GOOSE", 1], ["SELL", "WOOL", 8], ["HIRE"]]
        result = self.apply(orders)
        self.assertEqual(result["market"], [[], orders[1], orders[2]])

    def test_multiple_suppression(self):
        orders = [["BUY_ANIMAL", "GOOSE", 1], ["HIRE"], ["BUY_ANIMAL", "GOOSE", 2], ["SELL", "EGG", 4]]
        self.assertEqual(self.apply(orders)["market"], [[], orders[1], [], orders[3]])

    def test_suppress_at_end(self):
        self.assertEqual(self.apply([["HIRE"], ["BUY_ANIMAL", "GOOSE", 1]])["market"], [["HIRE"], []])

    def test_all_other_actions_unchanged(self):
        action = self.action([["BUY_ANIMAL", "GOOSE", 1]])
        changed = apply_overlay(self.fixed, action)
        for field in ("farmer", "hands", "extra"):
            self.assertEqual(changed[field], action[field])

    def test_parent_and_nested_values_not_mutated(self):
        action = self.action([["BUY_ANIMAL", "GOOSE", 1], ["SELL", "WOOL", 8]])
        before = copy.deepcopy(action)
        changed = apply_overlay(self.fixed, action)
        changed["hands"][0].append("mutation probe")
        self.assertEqual(action, before)

    def test_parent_called_once_with_same_arguments(self):
        obs, cfg, calls = {"private": {}}, {"maxMarketOrdersPerTurn": 10}, []
        old = self.fixed._BASE
        def parent(o, c):
            calls.append((o, c))
            return self.action([["BUY_ANIMAL", "GOOSE", 1]])
        try:
            self.fixed._BASE = parent
            self.fixed.agent_no_goose(obs, cfg)
        finally:
            self.fixed._BASE = old
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], obs)
        self.assertIs(calls[0][1], cfg)

    def test_no_op_quantities_preserved(self):
        orders = [["BUY_ANIMAL", "GOOSE", q] for q in (0, -1, "1", None)]
        self.assertEqual(self.apply(orders)["market"], orders)

    def test_other_animals_and_products_preserved(self):
        orders = [["BUY_ANIMAL", "SHEEP", 1], ["BUY_ANIMAL", "COW", 1], ["BUY_PRODUCT", "WHEAT", 4], ["BUY_SEED", "WHEAT", 2]]
        self.assertEqual(self.apply(orders)["market"], orders)

    def test_existing_empty_slots_preserved(self):
        orders = [[], ["BUY_ANIMAL", "GOOSE", 1], [], ["HIRE"]]
        self.assertEqual(self.apply(orders)["market"], [[], [], [], ["HIRE"]])

    def test_malformed_orders_unchanged(self):
        orders = [None, {}, "SELL", ["BUY_ANIMAL"], ["BUY_ANIMAL", "GOOSE"]]
        self.assertEqual(self.apply(orders)["market"], orders)

    def test_empty_market(self):
        self.assertEqual(self.apply([])["market"], [])

    def test_legacy_exact_historical_behavior(self):
        options = [[], ["HIRE"], ["BUY_ANIMAL", "GOOSE", 1], ["BUY_ANIMAL", "GOOSE", 0], ["SELL", "WOOL", 8]]
        for orders in itertools.product(options, repeat=3):
            action = self.action(list(orders))
            with self.subTest(orders=orders):
                self.assertEqual(apply_overlay(self.fixed, action, "agent_no_goose_compacted_legacy"),
                                 apply_overlay(self.original, action))

    def test_all_other_experiment_entrypoints_unchanged(self):
        orders = [["BUY_ANIMAL", "GOOSE", 1], ["BUY_ANIMAL", "GOOSE", 2], ["HIRE"], ["SELL", "WOOL", 8]]
        for name in ("agent", "agent_single_upgrade", "agent_budget_neutral", "agent_two_sheep_budget", "agent_late_upgrade", "agent_consistent_deposit"):
            with self.subTest(entry=name):
                action = self.action(orders)
                self.assertEqual(apply_overlay(self.fixed, action, name), apply_overlay(self.original, action, name))

    def test_official_engine_accepts_empty_order_slot(self):
        self.assertIsNone(self.engine._parse_order([]))
        result = run_market(self.engine, self.struct, [[], ["HIRE"]], [])
        self.assertEqual(result["hires_own_rival"], [1, 0])

    def test_exact_wool_receipt_counterexample_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                orders = [["BUY_ANIMAL", "GOOSE", 1], ["SELL", "WOOL", 8]]
                fixed = self.apply(orders)["market"]
                legacy = self.apply(orders, "agent_no_goose_compacted_legacy")["market"]
                a = run_market(self.engine, self.struct, fixed, [["SELL", "WOOL", 8]], own_seat=seat)
                b = run_market(self.engine, self.struct, legacy, [["SELL", "WOOL", 8]], own_seat=seat)
                self.assertEqual(a["cash_own_rival"], [2536, 2592])
                self.assertEqual(b["cash_own_rival"], [2568, 2568])
                self.assertEqual(b["margin"] - a["margin"], 56)
                self.assertEqual(a["market"], b["market"])
                self.assertEqual(a["shed_own_rival"], b["shed_own_rival"])

    def test_purchase_saving_is_exact_without_compaction(self):
        orders = [["BUY_ANIMAL", "GOOSE", 1], ["SELL", "WOOL", 8]]
        before = run_market(self.engine, self.struct, orders, [["SELL", "WOOL", 8]])
        after = run_market(self.engine, self.struct, self.apply(orders)["market"], [["SELL", "WOOL", 8]])
        self.assertEqual(after["cash_own_rival"][0]-before["cash_own_rival"][0], 300)
        self.assertEqual(after["cash_own_rival"][1], before["cash_own_rival"][1])
        self.assertEqual(before["shed_own_rival"][0]["GOOSE"], 1)
        self.assertEqual(after["shed_own_rival"][0]["GOOSE"], 0)

    def test_no_op_sibling_with_idle_opponent(self):
        orders = [["BUY_ANIMAL", "GOOSE", 1], ["SELL", "WOOL", 8]]
        a = run_market(self.engine, self.struct, self.apply(orders)["market"], [])
        b = run_market(self.engine, self.struct, self.apply(orders, "agent_no_goose_compacted_legacy")["market"], [])
        self.assertEqual(a, b)

    def test_cap_does_not_admit_previously_out_of_range_order(self):
        orders = [["BUY_ANIMAL", "GOOSE", 1], *([[]] * 9), ["BUY_SEED", "TOMATO", 1]]
        fixed = run_market(self.engine, self.struct, self.apply(orders)["market"], [])
        legacy = run_market(self.engine, self.struct, self.apply(orders, "agent_no_goose_compacted_legacy")["market"], [])
        self.assertEqual(fixed["seeds_own_rival"][0]["TOMATO"], 0)
        self.assertEqual(legacy["seeds_own_rival"][0]["TOMATO"], 1)
        self.assertEqual(fixed["cash_own_rival"][0]-legacy["cash_own_rival"][0], 50)

    def test_sweep_purchase_only_delta_with_slots_preserved(self):
        # 9 products x 4 quantities x 3 inventory offsets x 2 seats = 216
        # unseeded manufactured state pairs. No full-game panel is consumed.
        for item, qty, offset, seat in itertools.product(self.engine.PRODUCTS, (1, 2, 8, 17), (-10, 0, 100), (0, 1)):
            with self.subTest(item=item, qty=qty, offset=offset, seat=seat):
                orders = [["BUY_ANIMAL", "GOOSE", 1], ["SELL", item, qty]]
                kwargs = dict(product=item, quantity=qty, inventory_offset=offset, own_seat=seat)
                a = run_market(self.engine, self.struct, orders, [["SELL", item, qty]], **kwargs)
                b = run_market(self.engine, self.struct, self.apply(orders)["market"], [["SELL", item, qty]], **kwargs)
                self.assertEqual(b["cash_own_rival"][0] - a["cash_own_rival"][0], 300)
                self.assertEqual(b["cash_own_rival"][1], a["cash_own_rival"][1])
                self.assertEqual(a["market"], b["market"])

    def test_deterministic_serializable_evidence(self):
        a = reproduce(ROOT, ENGINE_DIR, ENGINE_LOADER)
        b = reproduce(ROOT, ENGINE_DIR, ENGINE_LOADER)
        self.assertEqual(a, b)
        self.assertEqual(json.loads(json.dumps(a)), a)
        self.assertEqual(a["game_seeds_consumed"], [])


if __name__ == "__main__":
    unittest.main()
