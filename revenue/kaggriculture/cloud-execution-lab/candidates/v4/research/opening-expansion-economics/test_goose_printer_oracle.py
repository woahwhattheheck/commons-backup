#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import goose_printer_oracle as g


class GanderTests(unittest.TestCase):
    def test_hire_cost_matches_engine_fibonacci(self):
        self.assertEqual([g.fib(i) for i in range(7)], [1, 1, 2, 3, 5, 8, 13])
        self.assertEqual(g.hire_cost(0), 0)
        self.assertEqual(g.hire_cost(1), 1)
        self.assertEqual(g.hire_cost(9), 88)

    def test_seven_geese_single_worker_constructive(self):
        actions = g.day0_schedule(7, 0)
        self.assertEqual(g._placed_count(actions), 7)
        self.assertEqual(g._max_step(actions), 21)
        self.assertTrue(all(a.step <= 23 for a in actions))

    def test_nine_geese_one_hire_constructive(self):
        actions = g.day0_schedule(9, 1)
        self.assertEqual(g._placed_count(actions), 9)
        self.assertEqual(g._max_step(actions), 15)
        sites = {(a.x, a.y) for a in actions if a.op == "PLACE"}
        self.assertEqual(len(sites), 9)
        self.assertTrue(all(0 <= x <= 4 and 0 <= y <= 4 for x, y in sites))

    def test_literal_ten_goose_claim_is_infeasible(self):
        row = g.day0_frontier()[10]
        self.assertFalse(row["feasible"])
        self.assertIn("30 > 23", row["reason"])
        self.assertEqual(10 * g.GOOSE_COST, g.STARTING_MONEY)
        self.assertGreater(10 * g.GOOSE_COST + g.hire_cost(1), g.STARTING_MONEY)

    def test_frontier_max_is_nine(self):
        rows = g.day0_frontier()
        feasible = [r["geese"] for r in rows if r["feasible"]]
        self.assertEqual(max(feasible), 9)
        row = rows[9]
        self.assertEqual(row["hires"], 1)
        self.assertEqual(row["cash_after_day0"], 299)
        self.assertEqual(row["fertilizer_ready_eod0"], 9)

    def test_day1_two_worker_service_is_constructive(self):
        actions = g.day1_keepalive_schedule()
        self.assertEqual(sum(1 for a in actions if a.op == "FEED"), 9)
        self.assertEqual(sum(1 for a in actions if a.op == "COLLECT_FERTILIZER"), 9)
        self.assertEqual(sum(1 for a in actions if a.op == "DROP"), 2)
        self.assertEqual(g._max_step(actions), 45)

    def test_fertilizer_first_sale_curve(self):
        prices = g.sell_prices("FERTILIZER", 9, 10000)
        self.assertEqual(prices, [100, 100, 100, 99, 99, 99, 99, 99, 98])
        self.assertEqual(sum(prices), 893)

    def test_wheat_keepalive_purchase_curve(self):
        prices = g.buy_product_prices("WHEAT", 9, 9999)
        self.assertEqual(prices, [26, 27, 27, 27, 27, 28, 28, 28, 28])
        self.assertEqual(sum(prices), 246)

    def test_day1_keepalive_is_not_a_cash_printer(self):
        row = g.day1_keepalive_ledger()
        self.assertEqual(row["day0_cash"], 299)
        self.assertEqual(row["day1_fertilizer_gross"], 893)
        self.assertEqual(row["day1_wheat_cost"], 246)
        self.assertEqual(row["day1_closing_cash"], 945)
        self.assertEqual(row["day1_last_service_step"], 45)
        self.assertEqual(row["liquid_cash_delta_vs_hold"], -2055)
        self.assertTrue(row["animals_survive_eod1"])
        self.assertEqual(row["egg_units_through_eod1"], 0)

    def test_source_pin_fails_closed_on_other_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "kaggriculture.py"
            p.write_text("ANIMALS = {}\n", encoding="utf-8")
            with self.assertRaisesRegex(g.GanderError, "official engine drift"):
                g.verify_engine_source(p)

    def test_exact_repo_engine_contract_when_available(self):
        if not g.DEFAULT_ENGINE.exists():
            self.skipTest("full repository checkout unavailable")
        c = g.verify_engine_source(g.DEFAULT_ENGINE)
        self.assertEqual(c["engine_blob"], g.EXPECTED_ENGINE_BLOB)
        self.assertTrue(c["fertilizer_direct_after_survival"])
        self.assertTrue(c["unit_actions_before_market"])
        self.assertEqual(c["goose_cost"], 300)


if __name__ == "__main__":
    unittest.main()
