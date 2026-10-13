#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("r04_sell_queue_order", HERE / "r04_sell_queue_order.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def action(*market):
    return {"farmer": ["PASS"], "hands": [], "market": list(market)}


class SellQueueOrderTests(unittest.TestCase):
    def test_crossed_sell_slots_create_two_same_item_index_exposures(self):
        pair = mod.classify_pair(
            action(["SELL", "WHEAT", 3], ["SELL", "CARROT", 2]),
            action(["SELL", "CARROT", 2], ["SELL", "WHEAT", 3]),
        )
        self.assertTrue(pair["a_reorderable"])
        self.assertTrue(pair["b_reorderable"])
        observed = {
            (row["item"], row["a_index"], row["b_index"], row["earlier"])
            for row in pair["same_item_index_mismatches"]
        }
        self.assertEqual(observed, {("CARROT", 1, 0, "b"), ("WHEAT", 0, 1, "a")})

    def test_aligned_same_item_sell_is_not_an_index_exposure(self):
        pair = mod.classify_pair(
            action(["SELL", "WHEAT", 3]),
            action(["SELL", "WHEAT", 7]),
        )
        self.assertEqual(pair["same_item_index_mismatches"], [])
        self.assertFalse(pair["a_reorderable"])
        self.assertFalse(pair["b_reorderable"])

    def test_non_sell_prefix_can_create_exposure_without_sell_slot_repair(self):
        pair = mod.classify_pair(
            action(["HIRE"], ["SELL", "WHEAT", 1]),
            action(["SELL", "WHEAT", 1]),
        )
        self.assertEqual(len(pair["same_item_index_mismatches"]), 1)
        mismatch = pair["same_item_index_mismatches"][0]
        self.assertEqual((mismatch["a_index"], mismatch["b_index"]), (1, 0))
        self.assertFalse(mismatch["a_sell_slot_permutation_available"])
        self.assertFalse(mismatch["b_sell_slot_permutation_available"])

    def test_executable_prefix_cap_excludes_tail_sell(self):
        market = [["PASS"] for _ in range(mod.MAX_ORDERS)] + [["SELL", "WHEAT", 9]]
        self.assertEqual(mod.sell_slots({"market": market}), [])

    def test_malformed_and_nonpositive_sell_rows_are_ignored(self):
        slots = mod.sell_slots(
            action(
                ["SELL", "WHEAT", 0],
                ["SELL", "WHEAT", -1],
                ["SELL", "NOT_A_PRODUCT", 3],
                ["SELL", "CARROT", "bad"],
                ["BUY_PRODUCT", "WHEAT", 3],
                ["SELL", "MILK", "2"],
            )
        )
        self.assertEqual(slots, [{"index": 5, "item": "MILK", "quantity": 2}])

    def test_plain_positive_integer_market_cap_required(self):
        with self.assertRaises(mod.SellQueueCensusError):
            mod.sell_slots(action(["SELL", "WHEAT", 1]), max_orders=True)
        with self.assertRaises(mod.SellQueueCensusError):
            mod.sell_slots(action(["SELL", "WHEAT", 1]), max_orders=0)

    def test_effective_route_uses_canonical_r04_splice(self):
        tapes = []
        for plan in range(mod.TAPE_COUNT):
            tapes.append([
                {"farmer": ["PASS", plan, step], "hands": [], "market": []}
                for step in range(mod.TAPE_STEPS)
            ])
        route = mod.effective_route(tapes, 7)
        self.assertEqual(len(route), mod.TAPE_STEPS)
        self.assertEqual(route[143]["farmer"][1], 0)
        self.assertEqual(route[144]["farmer"][1], 7)
        self.assertEqual(route[647]["farmer"][1], 7)
        self.assertEqual(route[648]["farmer"][1], 2)

    def test_checkout_sources_and_full_bank_report(self):
        if not (
            mod.ENGINE_PATH.exists()
            and mod.ENGINE_SPEC_PATH.exists()
            and mod.TAPES_PATH.exists()
            and mod.ROUTER_PATH.exists()
        ):
            self.skipTest("repository checkout not mounted")
        sources = mod.verify_sources()
        self.assertEqual(sources.max_orders, mod.MAX_ORDERS)
        tapes = mod.load_tapes(snapshot=sources.tapes_snapshot)
        report = mod.build_report(tapes, sources)
        self.assertEqual(report["schema"], "titan.v4.r04-sell-queue-order.v1")
        self.assertEqual(len(tapes), 13)
        self.assertEqual(report["theorem"]["rewrite_authority"], "NONE; current-native replay is required")
        self.assertNotIn("uplift", report["totals"])
        self.assertGreaterEqual(report["totals"]["authored_reorderable_steps"], 0)
        self.assertGreaterEqual(report["totals"]["cross_route_index_exposures"], 0)


if __name__ == "__main__":
    unittest.main()
