"""Run: TITAN_ENGINE=/path/to/kaggriculture.py python [-O] -m unittest -v."""
import os
from pathlib import Path
import random
import tempfile
import unittest

import lockstep_scale as l


class LockstepScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine_path = Path(os.environ.get("TITAN_ENGINE", "kaggriculture.py"))
        cls.engine = l.load_engine(cls.engine_path)

    def test_pin_and_real_commit_loaded(self):
        self.assertEqual(l.git_blob(self.engine_path.read_bytes()), l.ENGINE_BLOB)
        self.assertEqual(self.engine._commit_unit.__name__, "_commit_unit")
        self.assertEqual(self.engine._process_market.__code__.co_filename, str(self.engine_path))

    def test_mutated_engine_fails_even_optimized(self):
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "changed.py"
            altered.write_bytes(self.engine_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "pin mismatch"):
                l.load_engine(altered)

    def test_hunt2_exact_reproduction(self):
        row = l.compare(self.engine, "WHEAT", 9899, (50, 50))
        self.assertEqual(row["joined"]["cash"], [1594, 1594])
        self.assertEqual(row["p0_first"]["cash"], [1685, 1494])
        self.assertEqual(row["p1_join_vs_follow"], 100)
        self.assertEqual(row["p0_join_vs_lead"], -91)
        self.assertEqual(row["total_quote_surplus"], 9)

    def test_adjacent_integer_inventory_changes_quote_surplus(self):
        a = l.compare(self.engine, "WHEAT", 9899, (50, 50))
        b = l.compare(self.engine, "WHEAT", 9900, (50, 50))
        self.assertEqual(b["joined"]["cash"], [1585, 1585])
        self.assertNotEqual(a["total_quote_surplus"], b["total_quote_surplus"])

    def test_larger_quantity_is_not_two_dollars_per_unit(self):
        row = l.compare(self.engine, "WHEAT", 9900, (1000, 1000))
        self.assertEqual(row["p1_join_vs_follow"], 1157)
        self.assertNotEqual(row["p1_join_vs_follow"], 2000)
        self.assertFalse(row["capacity_valid"])

    def test_both_seats_share_identical_quotes(self):
        for item in self.engine.PRODUCTS:
            with self.subTest(item=item):
                row = l.compare(self.engine, item, 9900, (100, 100))
                self.assertEqual(*row["joined"]["cash"])
                self.assertEqual(row["p0_first"]["cash"], list(reversed(row["p1_first"]["cash"])))

    def test_unequal_quantities_are_seat_equivariant(self):
        for item in self.engine.PRODUCTS:
            with self.subTest(item=item):
                a = l.compare(self.engine, item, 9900, (10, 100))
                b = l.compare(self.engine, item, 9900, (100, 10))
                self.assertEqual(a["joined"]["cash"], list(reversed(b["joined"]["cash"])))
                self.assertEqual(a["joined"]["final_inventory"], b["joined"]["final_inventory"])

    def test_same_step_different_raw_rows_are_sequential(self):
        row = l.compare(self.engine, "WHEAT", 9899, (50, 50))
        self.assertGreater(row["p1_first"]["cash"][1], row["joined"]["cash"][1])
        self.assertEqual(row["p1_first"]["cash"], [1494, 1685])

    def test_aligned_later_rows_keep_lockstep(self):
        sale = ["SELL", "WHEAT", 50]
        shifted = [["PASS"]] * 3 + [sale]
        a = l.execute(self.engine, "WHEAT", 9899, (50, 50), (shifted, shifted))
        b = l.execute(self.engine, "WHEAT", 9899, (50, 50), ([sale], [sale]))
        self.assertEqual(a, b)

    def test_eleventh_raw_row_does_not_execute(self):
        rows = [["PASS"]] * 10 + [["SELL", "WHEAT", 100]]
        row = l.execute(self.engine, "WHEAT", 9900, (100, 100), (rows, rows))
        self.assertEqual(row["sold"], [0, 0])
        self.assertEqual(row["cash"], [0, 0])

    def test_tenth_raw_row_executes(self):
        rows = [["PASS"]] * 9 + [["SELL", "WHEAT", 100]]
        row = l.execute(self.engine, "WHEAT", 9900, (100, 100), (rows, rows))
        self.assertEqual(row["sold"], [100, 100])

    def test_large_request_cannot_sell_unheld_stock(self):
        rows = [["SELL", "WHEAT", 2000]]
        actual = l.execute(self.engine, "WHEAT", 9900, (100, 100), (rows, rows))
        expected = l.compare(self.engine, "WHEAT", 9900, (100, 100))["joined"]
        self.assertEqual(actual, expected)

    def test_floor_sales_do_not_change_inventory(self):
        row = l.compare(self.engine, "MILK", 11000, (100, 100))
        self.assertEqual(row["initial_quote"], 1)
        self.assertEqual(row["joined"]["cash"], [100, 100])
        self.assertEqual(row["joined"]["final_inventory"], 11000)
        self.assertEqual(row["p1_join_vs_follow"], 0)
        self.assertEqual(row["total_quote_surplus"], 0)

    def test_floor_crossing_respects_endpoint_bound(self):
        row = l.compare(self.engine, "MILK", 10000, (100, 100))
        self.assertEqual(row["joined"]["final_quote"], 1)
        self.assertLessEqual(row["total_quote_surplus"], 159)

    def test_public_inventory_can_be_negative(self):
        row = l.compare(self.engine, "WHEAT", -1, (10, 10))
        self.assertEqual(row["joined"]["sold"], [10, 10])
        self.assertGreater(row["initial_quote"], 25)

    def test_microstate_contract_rejects_poison_inputs(self):
        for held in ((True, 1), (1.0, 1), (-1, 1), (5001, 1), (1, 1, 1)):
            with self.subTest(held=held), self.assertRaises(ValueError):
                l.make_state(self.engine, "WHEAT", 10000, held)
        for inventory in (True, float("nan"), float("inf"), 10 ** 16):
            with self.subTest(inventory=inventory), self.assertRaises(ValueError):
                l.make_state(self.engine, "WHEAT", inventory, (1, 1))

    def test_unknown_product_rejected(self):
        with self.assertRaises(ValueError):
            l.make_state(self.engine, "NOT_A_PRODUCT", 10000, (1, 1))

    def test_reference_matches_randomized_real_market(self):
        rng = random.Random(20260911)
        for _ in range(200):
            item = rng.choice(self.engine.PRODUCTS)
            inv = rng.randint(8000, 12000)
            held = (rng.randint(0, 100), rng.randint(0, 100))
            row = l.compare(self.engine, item, inv, held)
            self.assertEqual(row["joined"], l.reference(self.engine, item, inv, held, True))

    def test_repeated_arrivals_are_labeled_not_full_game(self):
        row = l.multistep(self.engine, "WHEAT", 9900, 100, 10)
        self.assertEqual(row["total_units_per_seat"], 1000)
        self.assertEqual(row["p1_join_vs_follow"], 544)
        self.assertEqual(row["joined"]["cash"], [20157, 20157])
        self.assertIn("no farmer production", row["arrivals"])

    def test_repeated_arrival_cannot_exceed_capacity(self):
        with self.assertRaises(ValueError):
            l.multistep(self.engine, "WHEAT", 9900, 101, 10)

    def test_town_control_preserves_shared_tick_schedule(self):
        row = l.multistep(self.engine, "WHEAT", 9900, 100, 10, ("FARMERS_MARKET",) * 4)
        self.assertEqual(row["p1_join_vs_follow"], 548)
        self.assertEqual(row["joined"]["final_inventory"], row["follow"]["final_inventory"])

    def test_experiment_deterministic_and_all_products(self):
        a = l.build_report(self.engine)
        b = l.build_report(self.engine)
        self.assertEqual(a, b)
        self.assertEqual(a["case_count"], 414)
        self.assertEqual({r["item"] for r in a["cases"]}, set(self.engine.PRODUCTS))
        self.assertEqual(len(a["repeated_arrivals"]), 18)


if __name__ == "__main__":
    unittest.main()
