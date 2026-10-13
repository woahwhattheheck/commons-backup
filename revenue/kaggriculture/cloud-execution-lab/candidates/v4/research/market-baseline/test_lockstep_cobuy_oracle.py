#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import lockstep_cobuy_oracle as cobuy


ENGINE = Path(__file__).resolve().parents[4] / "reference" / "engine" / "kaggriculture.py"


class LockstepCobuyOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = cobuy.load_engine(ENGINE)

    def test_exact_engine_pin(self):
        self.assertEqual(cobuy.git_blob(ENGINE.read_bytes()), cobuy.ENGINE_BLOB)

    def test_wheat_q100_exact_pair_discount(self):
        r = cobuy.compare(self.engine, item="WHEAT", self_qty=100, rival_qty=100)
        self.assertEqual(r["simultaneous_self_cost"], 3445)
        self.assertEqual(r["wait_behind_self_cost"], 3720)
        self.assertEqual(r["simultaneous_saving_vs_wait"], 275)
        self.assertEqual(r["misaligned_same_callback_self_cost"], 3720)
        self.assertEqual(r["misaligned_saving_vs_wait"], 0)
        self.assertEqual(r["terminal_market_inventory"], 9800)
        self.assertTrue(r["same_terminal_inventory"])

    def test_fertilizer_q100_exact_pair_discount(self):
        r = cobuy.compare(self.engine, item="FERTILIZER", self_qty=100, rival_qty=100)
        self.assertEqual(r["simultaneous_self_cost"], 12000)
        self.assertEqual(r["wait_behind_self_cost"], 13010)
        self.assertEqual(r["simultaneous_saving_vs_wait"], 1010)
        self.assertEqual(r["misaligned_same_callback_self_cost"], 13010)
        self.assertEqual(r["misaligned_saving_vs_wait"], 0)

    def test_equal_quantity_pair_is_seat_symmetric(self):
        p = cobuy.simulate_pair(
            self.engine, self_item="WHEAT", self_qty=50,
            rival_item="WHEAT", rival_qty=50, aligned=True,
        )
        self.assertEqual(p["self_cost"], 1585)
        self.assertEqual(p["rival_cost"], 1585)
        self.assertEqual(p["snapshot"]["self_shed"], 50)
        self.assertEqual(p["snapshot"]["rival_shed"], 50)

    def test_quantity_mismatch_only_pairs_shared_prefix(self):
        r = cobuy.compare(self.engine, item="WHEAT", self_qty=100, rival_qty=50)
        self.assertEqual(r["simultaneous_self_cost"], 3393)
        self.assertEqual(r["wait_behind_self_cost"], 3490)
        self.assertEqual(r["simultaneous_saving_vs_wait"], 97)

    def test_no_rival_buy_is_null(self):
        r = cobuy.compare(self.engine, item="WHEAT", self_qty=100, rival_qty=0)
        self.assertEqual(r["simultaneous_saving_vs_wait"], 0)
        self.assertEqual(r["misaligned_saving_vs_wait"], 0)

    def test_cross_product_buy_is_null_for_our_quote(self):
        paired = cobuy.simulate_pair(
            self.engine, self_item="FERTILIZER", self_qty=100,
            rival_item="WHEAT", rival_qty=100, aligned=True,
        )
        waited = cobuy.simulate_wait(
            self.engine, self_item="FERTILIZER", self_qty=100,
            rival_item="WHEAT", rival_qty=100,
        )
        self.assertEqual(paired["self_cost"], waited["self_cost"])
        self.assertEqual(paired["snapshot"]["market_inventory"],
                         waited["snapshot"]["market_inventory"])

    def test_row_misalignment_collapses_to_wait_behind(self):
        paired = cobuy.simulate_pair(
            self.engine, self_item="FERTILIZER", self_qty=50,
            rival_item="FERTILIZER", rival_qty=50, aligned=False,
        )
        waited = cobuy.simulate_wait(
            self.engine, self_item="FERTILIZER", self_qty=50,
            rival_item="FERTILIZER", rival_qty=50,
        )
        self.assertEqual(paired["self_cost"], waited["self_cost"])
        self.assertEqual(paired["self_cost"], 5755)

    def test_default_capacity_bound_is_fail_closed(self):
        with self.assertRaises(ValueError):
            cobuy.compare(self.engine, item="WHEAT", self_qty=101, rival_qty=1)
        with self.assertRaises(ValueError):
            cobuy.compare(self.engine, item="WHEAT", self_qty=True, rival_qty=1)

    def test_source_drift_refuses_before_import(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "kaggriculture.py"
            p.write_bytes(ENGINE.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "engine Git blob mismatch"):
                cobuy.load_engine(p)


if __name__ == "__main__":
    unittest.main()
