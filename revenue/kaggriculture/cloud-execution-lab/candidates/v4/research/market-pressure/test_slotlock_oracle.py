#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import slotlock_oracle as oracle

HERE = Path(__file__).resolve().parent
CLOUD = HERE.parents[3]
PRESSURE_DIR = CLOUD.parent / "cloud-opponent-league" / "lark-responsive"
ENGINE = CLOUD / "reference" / "engine" / "kaggriculture.py"
PRESSURE = PRESSURE_DIR / "pressure_priority.py"
MAIN = CLOUD / "main.py"
RUNTIME = CLOUD / "titan_runtime.py"
CONFIG = CLOUD / "TITAN-CONFIG.json"


def git_blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_pressure():
    sys.path.insert(0, str(PRESSURE_DIR))
    try:
        spec = importlib.util.spec_from_file_location("_slotlock_pressure", PRESSURE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        try:
            sys.path.remove(str(PRESSURE_DIR))
        except ValueError:
            pass


class SlotlockOracleTests(unittest.TestCase):
    def test_exact_live_source_pins(self):
        self.assertEqual(git_blob(ENGINE), oracle.ENGINE_BLOB)
        self.assertEqual(git_blob(PRESSURE), oracle.PRESSURE_BLOB)
        self.assertEqual(git_blob(MAIN), oracle.MAIN_BLOB)
        self.assertEqual(git_blob(RUNTIME), oracle.RUNTIME_BLOB)
        self.assertEqual(git_blob(CONFIG), oracle.CONFIG_BLOB)

    def test_live_pressure_is_enabled(self):
        data = json.loads(CONFIG.read_text())
        self.assertIs(data["market_pressure"], True)

    def test_direct_buy_goods_cannot_alias_compacted_goods(self):
        self.assertFalse(set(oracle.SALE_ONLY_GOODS) & oracle.DIRECT_BUY_GOODS)

    def test_all_official_sale_only_curves_are_nonincreasing(self):
        receipt = oracle.curve_contract()
        self.assertGreater(receipt["adjacent_quote_checks"], 2000)
        self.assertGreaterEqual(receipt["minimum_300_unit_drop"], 0)

    def test_current_compactor_matches_structural_oracle(self):
        pressure = load_pressure()
        orders = [[], ["SELL", "WOOL", 2], ["SELL", "MILK", 1], []]
        market = {
            "inventory": {"WOOL": 10000, "MILK": 10000},
            "prices": {
                "WOOL": oracle.market_price("WOOL", 10000),
                "MILK": oracle.market_price("MILK", 10000),
            },
        }
        current = pressure.compact_sale_only_prefix(
            [list(row) for row in orders], len(orders), market, {"shedCapacity": 100},
            oracle.market_price,
        )
        self.assertEqual(current, oracle.compact_model(orders))
        self.assertEqual(current, [
            ["SELL", "WOOL", 2], ["SELL", "MILK", 1], [], []
        ])

    def test_current_compactor_refuses_buyable_operating_goods(self):
        pressure = load_pressure()
        orders = [[], ["SELL", "WHEAT", 1]]
        current = pressure.compact_sale_only_prefix(
            [list(row) for row in orders], len(orders),
            {"inventory": {"WHEAT": 10000}, "prices": {"WHEAT": 25}},
            {"shedCapacity": 100}, lambda *_: 25,
        )
        self.assertEqual(current, orders)

    def test_three_slot_lockstep_search_has_no_negative_margin_case(self):
        receipt = oracle.exhaustive_three_slot()
        self.assertEqual(receipt["comparisons"], 165816)
        self.assertEqual(receipt["minimum_margin_delta"], 0)
        self.assertIsNone(receipt["counterexample"])
        self.assertGreater(receipt["positive_margin_cases"], 0)

    def test_constructed_same_product_pairing_is_strictly_helpful(self):
        parent = [[], ["SELL", "WOOL", 2]]
        candidate = oracle.compact_model(parent)
        rival = [["SELL", "WOOL", 2], []]
        self.assertGreater(oracle.margin_delta(parent, candidate, rival), 0)

    def test_bundle_disposition_is_bounded_proof_not_strength_claim(self):
        result = oracle.result_bundle()
        self.assertTrue(result["disposition"].startswith("PROVED_"))
        self.assertIn("not full-game EV", result["scope"])
        self.assertEqual(result["contracts"]["direct_buy_overlap"], [])


if __name__ == "__main__":
    unittest.main()
