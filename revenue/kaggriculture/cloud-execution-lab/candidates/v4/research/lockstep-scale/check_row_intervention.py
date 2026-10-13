"""Independent assertions for paired row intervention controls (normal and -O).

python check_row_intervention.py --runtime EXPANDED_RUNTIME
No fixture is a live-game sample; no test result authorizes a feature flip.
"""
from __future__ import annotations
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tested_row_intervention", HERE / "row_intervention_controls.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
RUNTIME = None


class RowInterventionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RUNTIME is None:
            raise RuntimeError("Provide --runtime; missing dependencies are failures, not skipped suites")
        cls.e, cls.Struct, _ = m.load_official(RUNTIME)

    def pair(self, case, seat=0):
        return m.compare_pair(self.e, self.Struct, case, seat)

    def test_01_actual_dump_collateral_loss_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                r = self.pair(m.collateral(), seat)
                self.assertEqual(r["before_cash"], [112468, 112659])
                self.assertEqual(r["after_cash"], [111816, 113278])
                self.assertEqual((r["delta_own"], r["delta_rival"], r["delta_margin"]), (-652, 619, -1271))
                self.assertTrue(r["final_assets_equal"])

    def test_02_opponent_buy_reversal_both_seats(self):
        for seat in (0, 1):
            r = self.pair(m.named_cases()[1], seat)
            self.assertEqual((r["delta_own"], r["delta_rival"], r["delta_margin"]), (-60, 60, -120))
            self.assertTrue(r["final_assets_equal"])

    def test_03_original_pure_sale_mechanism_retained(self):
        for seat in (0, 1):
            r = self.pair(m.named_cases()[2], seat)
            self.assertEqual((r["delta_own"], r["delta_rival"], r["delta_margin"]), (100, -91, 191))
            self.assertTrue(r["final_assets_equal"])

    def test_04_existing_vacant_raw_slot_retains_collateral_pairing(self):
        for seat in (0, 1):
            r = self.pair(m.named_cases()[3], seat)
            self.assertEqual((r["delta_own"], r["delta_rival"], r["delta_margin"]), (191, -191, 382))
            self.assertTrue(r["final_assets_equal"])

    def test_05_second_join_can_displace_incumbent_hire(self):
        case = m.named_cases()[4]
        for seat in (0, 1):
            r = self.pair(case, seat)
            self.assertFalse(r["final_assets_equal"])
            self.assertEqual(r["delta_margin"], 1)  # Positive cash is NOT a safe disposition.
            b = m.run_world(self.e, self.Struct, case, seat, "before")
            a = m.run_world(self.e, self.Struct, case, seat, "after")
            self.assertEqual(len(b["final"]["assets"]["farms"][0]["hands"]), 1)
            self.assertEqual(len(a["final"]["assets"]["farms"][0]["hands"]), 0)

    def test_06_terminal_asset_identity_does_not_imply_zero_cash_effect(self):
        r = self.pair(m.collateral())
        self.assertEqual(r["before_assets_sha256"], r["after_assets_sha256"])
        self.assertNotEqual(r["before_trace_sha256"], r["after_trace_sha256"])
        self.assertLess(r["delta_margin"], 0)

    def test_07_cross_product_interactions_are_not_uniform(self):
        expected = {"CARROT": 186, "TOMATO": 82, "STRAWBERRY": -1215, "MELON": -151,
                    "MILK": -1271, "WOOL": -141}
        for item, delta in expected.items():
            for seat in (0, 1):
                with self.subTest(item=item, seat=seat):
                    self.assertEqual(self.pair(m.collateral(item), seat)["delta_margin"], delta)

    def test_08_slot1_and_slot2_rival_vectors_preserve_seat_symmetry(self):
        for slot in (1, 2):
            case = m.collateral("MILK", 25, 9700, slot)
            a, b = self.pair(case, 0), self.pair(case, 1)
            for key in ("before_cash", "after_cash", "delta_own", "delta_rival", "delta_margin"):
                self.assertEqual(a[key], b[key])

    def test_09_raw_capped_suffix_is_not_executed(self):
        rows = [["SELL", "WHEAT", 10], ["HIRE"]]
        case = m.fixture("cap", {"WHEAT": 10}, {}, {"WHEAT": 9899}, [rows], [rows], [[]], max_orders=1)
        for seat in (0, 1):
            world = m.run_world(self.e, self.Struct, case, seat, "before")
            self.assertEqual(len(world["final"]["assets"]["farms"][0]["hands"]), 0)
            self.assertEqual(world["final"]["assets"]["private"][0]["shed"]["WHEAT"], 0)

    def test_10_complete_interpreter_runs_town_on_the_actual_action_step(self):
        case = m.fixture("town", {}, {}, {"WHEAT": 10000}, [[]], [[]], [[]],
                         start_step=104, shops=["BAKERY"])
        world = m.run_world(self.e, self.Struct, case, 0, "before")
        self.assertEqual(world["final"]["assets"]["market"]["inventory"]["WHEAT"], 9999)
        case["start_step"] = 105
        world = m.run_world(self.e, self.Struct, case, 0, "before")
        self.assertEqual(world["final"]["assets"]["market"]["inventory"]["WHEAT"], 10000)

    def test_11_complete_interpreter_runs_end_of_day(self):
        case = m.fixture("eod", {}, {}, {}, [[]], [[]], [[]], start_step=143)
        world = m.run_world(self.e, self.Struct, case, 0, "before")
        self.assertEqual((world["final"]["assets"]["day"], world["final"]["assets"]["hour"]), (6, 0))
        self.assertEqual(len(world["final"]["assets"]["town"]["unlocked_shops"]), 1)

    def test_12_complete_interpreter_sets_done_at_official_boundary(self):
        case = m.fixture("terminal", {}, {}, {}, [[], []], [[], []], [[], []], start_step=717)
        world = m.run_world(self.e, self.Struct, case, 0, "before")
        self.assertEqual(world["final"]["assets"]["status"], ["DONE", "DONE"])
        self.assertEqual(world["interpreter_calls"], 3)

    def test_13_price_floor_sell_does_not_increment_market_inventory(self):
        sell = ["SELL", "FERTILIZER", 50]
        case = m.fixture("floor", {"FERTILIZER": 50}, {"FERTILIZER": 50}, {"FERTILIZER": 11000},
                         [[], [sell]], [[sell], []], [[sell], []])
        for seat in (0, 1):
            row = self.pair(case, seat)
            self.assertEqual(row["delta_margin"], 0)
            world = m.run_world(self.e, self.Struct, case, seat, "after")
            self.assertEqual(world["final"]["assets"]["market"]["inventory"]["FERTILIZER"], 11000)

    def test_14_same_action_control_matches_every_trace(self):
        for case in m.named_cases():
            case["after"] = copy.deepcopy(case["before"])
            for seat in (0, 1):
                row = self.pair(case, seat)
                self.assertEqual((row["delta_own"], row["delta_rival"], row["delta_margin"]), (0, 0, 0))
                self.assertEqual(row["before_trace_sha256"], row["after_trace_sha256"])
                self.assertTrue(row["final_assets_equal"])

    def test_15_repetition_is_deterministic_and_detached(self):
        case = m.collateral()
        original = copy.deepcopy(case)
        a = self.pair(case)
        a["before_cash"][0] = -10
        self.assertEqual(case, original)
        b = self.pair(case)
        self.assertEqual(b["before_cash"], [112468, 112659])
        self.assertEqual(b, self.pair(case))

    def test_16_fixture_integer_poison_is_rejected(self):
        for field in ("seed", "start_step", "max_orders"):
            for bad in (True, False, 1.0, "1", None, float("nan"), float("inf")):
                case = m.collateral()
                case[field] = bad
                with self.subTest(field=field, value=repr(bad)), self.assertRaises((ValueError, TypeError)):
                    self.pair(case)

    def test_17_invalid_capacity_products_and_horizon_fail(self):
        cases = []
        for key, value in (("own_stock", {"WHEAT": 101}), ("rival_stock", {"WHEAT": 60, "MILK": 60}),
                           ("own_stock", {"UNKNOWN": 1}), ("inventory", {"UNKNOWN": 5}),
                           ("shops", ["UNKNOWN"]), ("start_step", 718), ("money", [1, True])):
            c = m.collateral(); c[key] = value; cases.append(c)
        c = m.collateral(); c["rival"] = []; cases.append(c)
        for case in cases:
            with self.subTest(case=case["name"]), self.assertRaises((ValueError, TypeError)):
                self.pair(case)

    def test_18_missing_or_modified_engine_dependencies_fail_before_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(importlib.util, "spec_from_file_location", side_effect=AssertionError("import reached")):
                with self.assertRaises(ValueError):
                    m.load_official(root)
            for relative in m.PINS:
                target = root / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((RUNTIME / relative).read_bytes())
            for relative in m.PINS:
                target = root / relative; good = target.read_bytes(); target.write_bytes(good + b"\n")
                with patch.object(importlib.util, "spec_from_file_location", side_effect=AssertionError("import reached")):
                    with self.assertRaises(ValueError):
                        m.load_official(root)
                target.write_bytes(good)

    def test_19_pinned_loader_does_not_download_and_restores_modules(self):
        import urllib.request
        sentinel = object()
        with patch.dict(sys.modules, {"kaggle_environments": sentinel, "kaggle_environments.utils": sentinel}):
            with patch.object(urllib.request, "urlopen", side_effect=AssertionError("network attempted")):
                engine, _, _ = m.load_official(RUNTIME)
            self.assertIs(sys.modules["kaggle_environments"], sentinel)
            self.assertIs(sys.modules["kaggle_environments.utils"], sentinel)
            self.assertEqual(engine.PRODUCTS, self.e.PRODUCTS)

    def test_20_cash_report_poison_and_wrong_margin_fail(self):
        good = self.pair(m.collateral())
        m.validate_pair(good)
        for key in ("delta_own", "delta_rival", "delta_margin"):
            for bad in (True, -652.0, float("nan"), float("inf"), 999):
                row = copy.deepcopy(good); row[key] = bad
                with self.subTest(key=key, value=repr(bad)), self.assertRaises(ValueError):
                    m.validate_pair(row)
        row = copy.deepcopy(good); row["delta_margin"] = row["delta_own"]
        with self.assertRaises(ValueError): m.validate_pair(row)

    def test_21_report_hash_role_and_asset_poison_fail(self):
        good = self.pair(m.collateral())
        for key in ("fixture_sha256", "before_assets_sha256", "after_trace_sha256"):
            for bad in ("A" * 64, "z" * 64, "0" * 63, None, 1):
                row = copy.deepcopy(good); row[key] = bad
                with self.assertRaises(ValueError): m.validate_pair(row)
        for key, value in (("seat", True), ("final_assets_equal", 1), ("final_assets_equal", False),
                           ("before_cash", [True, 112659]), ("interpreter_calls", True)):
            row = copy.deepcopy(good); row[key] = value
            with self.assertRaises(ValueError): m.validate_pair(row)

    def test_22_full_deterministic_matrix_keeps_all_negative_and_asset_failures(self):
        report = m.report(self.e, self.Struct)
        self.assertEqual(report["matrix_summary"], {"pairs": 512, "negative_margin": 292,
            "positive_margin": 96, "zero_margin": 124, "all_final_assets_equal": False})
        self.assertEqual(sum(not r["final_assets_equal"] for r in report["matrix"]), 4)
        self.assertEqual(len(report["identity_controls"]), 12)
        self.assertEqual(report["interpreter_calls"], 12668)
        self.assertEqual(report["dependency_blobs"], m.PINS)
        for named in report["named_cases"]:
            self.assertEqual({p["seat"] for p in named["pairs"]}, {0, 1})

    def test_24_native_product_empty_row0_horizon_can_lose(self):
        case = m.native_horizon()
        self.assertEqual(case["start_step"], 301)
        self.assertEqual(len(case["before"]), 73)
        self.assertEqual(case["before"][0]["market"], [])
        self.assertEqual(case["after"][0]["market"], [["SELL", "MILK", 10]])
        self.assertEqual(case["rival"][0]["market"], [["SELL", "MILK", 10]])
        for seat in (0, 1):
            row = self.pair(case, seat)
            self.assertEqual(row["before_cash"], [5718, 5453])
            self.assertEqual(row["after_cash"], [5433, 5433])
            self.assertEqual((row["delta_own"], row["delta_rival"], row["delta_margin"]), (-285, -20, -265))
            self.assertTrue(row["final_assets_equal"])

    def test_25_positive_immediate_mechanism_does_not_certify_long_pull(self):
        for seat in (0, 1):
            immediate = self.pair(m.native_horizon(delay=1), seat)
            delayed = self.pair(m.native_horizon(delay=72), seat)
            self.assertEqual(immediate["delta_margin"], 44)
            self.assertEqual(delayed["delta_margin"], -265)
            self.assertTrue(immediate["final_assets_equal"] and delayed["final_assets_equal"])

    def test_26_full_native_horizon_matrix_keeps_negative_results(self):
        report = m.report(self.e, self.Struct)
        self.assertEqual(report["horizon_summary"], {"pairs": 120, "negative_margin": 54,
            "positive_margin": 66, "zero_margin": 0, "all_final_assets_equal": True})
        self.assertEqual(len({p["fixture_sha256"] for p in report["horizon"]}), 60)
        for row in report["horizon"]:
            self.assertIn(row["seat"], (0, 1))
            self.assertIn(row["interpreter_calls"], (6, 52, 100, 148))

    def test_27_horizon_guards_reject_unsupported_native_product_and_window(self):
        for item in ("WHEAT", "FERTILIZER", "UNKNOWN"):
            with self.assertRaises(ValueError): m.native_horizon(item=item)
        for delay in (0, 73, True, 1.0):
            with self.assertRaises(ValueError): m.native_horizon(delay=delay)
        for copies in (5, -1, True):
            with self.assertRaises(ValueError): m.native_horizon(shop_copies=copies)

    def test_23_cli_generates_parseable_complete_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report.json"
            cmd = [sys.executable] + (["-O"] if sys.flags.optimize else []) + [str(HERE / "row_intervention_controls.py"),
                       "--runtime", str(RUNTIME), "--output", str(output)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            parsed = json.loads(output.read_text())
            self.assertEqual(parsed["schema"], m.SCHEMA)
            self.assertEqual(json.loads(result.stdout)["interpreter_calls"], 12668)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    args, rest = parser.parse_known_args()
    RUNTIME = args.runtime.resolve()
    unittest.main(argv=[sys.argv[0]] + rest, verbosity=2)
