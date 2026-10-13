# SPDX-License-Identifier: Apache-2.0
"""Executable regression checks for the existing FWD research mechanism proof."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import py_compile
import shutil
import sys
import tempfile
import unittest

import opportunity_cost as subject

ENGINE_DIR = None


class OpportunityCost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, cls.hashes = subject.load_engine(ENGINE_DIR)

    def test_exact_engine_inputs(self):
        for name, expected in subject.ENGINE_BLOBS.items():
            self.assertEqual(subject.git_blob((ENGINE_DIR / name).read_bytes()), expected)
        self.assertEqual(set(self.hashes), set(subject.ENGINE_BLOBS))

    def test_each_missing_input_fails_closed(self):
        for omitted in subject.ENGINE_BLOBS:
            with self.subTest(name=omitted), tempfile.TemporaryDirectory() as tmp:
                for name in subject.ENGINE_BLOBS:
                    if name != omitted:
                        shutil.copyfile(ENGINE_DIR / name, Path(tmp) / name)
                with self.assertRaises(FileNotFoundError):
                    subject.load_engine(tmp)

    def test_each_changed_input_fails_closed(self):
        for changed in subject.ENGINE_BLOBS:
            with self.subTest(name=changed), tempfile.TemporaryDirectory() as tmp:
                for name in subject.ENGINE_BLOBS:
                    data = (ENGINE_DIR / name).read_bytes()
                    (Path(tmp) / name).write_bytes(data + (b"\n" if name == changed else b""))
                with self.assertRaisesRegex(ValueError, "official source mismatch"):
                    subject.load_engine(tmp)

    def test_loading_does_not_replace_existing_imports(self):
        keys = ("kaggle_environments", "kaggle_environments.utils")
        before = {k: sys.modules.get(k) for k in keys}
        subject.load_engine(ENGINE_DIR)
        for k, value in before.items():
            self.assertIs(sys.modules.get(k), value)

    def test_ignores_stale_compiled_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in subject.ENGINE_BLOBS:
                shutil.copyfile(ENGINE_DIR / name, Path(tmp) / name)
            source = Path(tmp) / "kaggriculture.py"
            good = source.read_bytes()
            # Unchecked hash bytecode executes even when source content changes
            # under a normal import loader. The authenticated-byte loader ignores it.
            source.write_text("raise RuntimeError('STALE BYTECODE EXECUTED')\n")
            py_compile.compile(str(source), doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            source.write_bytes(good)
            engine, _ = subject.load_engine(tmp)
            self.assertEqual(engine.market_price("WHEAT", 10000), 25)

    def test_actual_harvest_is_carried_then_displaced_at_eod(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                pair = subject.headroom_pair(self.engine, seat=seat)
                early, jit = pair["early_hold"], pair["jit"]
                self.assertEqual(early["trace"][0]["inventories"], [{"CARROT": 4}])
                self.assertEqual(jit["trace"][0]["inventories"], [{"CARROT": 4}])
                self.assertEqual(early["trace"][3]["shed"]["CARROT"], 96)
                self.assertEqual(jit["trace"][3]["shed"]["CARROT"], 100)
                self.assertEqual(early["trace"][3]["inventories"], [{}])
                self.assertEqual(jit["trace"][3]["inventories"], [{}])
                self.assertEqual(early["physical"], jit["physical"])

    def test_input_price_savings_are_not_total_economics(self):
        stats = subject.summary(subject.headroom_pair(self.engine))
        self.assertEqual(stats["early_hold"]["cash_deltas_by_tick"][0], -106)
        self.assertEqual(stats["jit"]["cash_deltas_by_tick"][-1], -109)
        self.assertEqual(stats["early_hold"]["cash_deltas_by_tick"][4], 2642)
        self.assertEqual(stats["jit"]["cash_deltas_by_tick"][4], 2738)
        self.assertEqual(stats["early_hold"]["delta_own"], -93)
        self.assertEqual(stats["early_hold"]["delta_margin"], -93)
        self.assertEqual(stats["early_hold"]["delta_rival"], 0)

    def test_unwind_control_does_not_claim_all_early_buying_is_dominated(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                pair = subject.headroom_pair(self.engine, seat=seat)
                stats = subject.summary(pair)["early_unwind"]
                self.assertEqual(stats["delta_margin"], 1)
                self.assertTrue(stats["same_final_physical"])
                self.assertEqual(pair["early_unwind"]["market_inventory"], pair["jit"]["market_inventory"])

    def test_exact_room_boundary_preserves_the_harvest(self):
        pair = subject.headroom_pair(self.engine, room=8)
        self.assertEqual(pair["early_hold"]["trace"][3]["shed"]["CARROT"], 96)
        self.assertEqual(pair["jit"]["trace"][3]["shed"]["CARROT"], 96)
        self.assertEqual(subject.summary(pair)["early_hold"]["delta_margin"], 3)

    def test_partial_overflow_counts_only_displaced_units(self):
        pair = subject.headroom_pair(self.engine, room=5)
        self.assertEqual(pair["jit"]["trace"][3]["shed"]["CARROT"] -
                         pair["early_hold"]["trace"][3]["shed"]["CARROT"], 3)

    def test_no_harvest_has_no_headroom_opportunity_cost(self):
        stats = subject.summary(subject.headroom_pair(self.engine, harvest=0))
        self.assertEqual(stats["early_hold"]["delta_margin"], 3)
        self.assertTrue(stats["early_hold"]["same_final_physical"])

    def test_zero_quantity_identity(self):
        for room in (0, 4, 100):
            with self.subTest(room=room):
                pair = subject.headroom_pair(self.engine, quantity=0, room=room)
                for row in pair.values():
                    self.assertEqual(row, pair["jit"])

    def test_invalid_experiment_domains_are_not_silently_coerced(self):
        for cfg in ({"quantity": True}, {"quantity": -1}, {"quantity": 1.5},
                    {"quantity": 5, "room": 4}, {"room": 101},
                    {"harvest": 5}, {"harvest": -1}, {"seat": True}, {"seat": 2}):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                subject.headroom_pair(self.engine, **cfg)

    def test_one_dollar_cash_reservation_changes_real_hire_outcome(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                pair = subject.capital_pair(self.engine, seat=seat, cash=26)
                early, jit = pair["early_hold"], pair["jit"]
                self.assertEqual(early["trace"][1]["hands"], [])
                self.assertEqual(jit["trace"][1]["hands"], [[4, 4]])
                self.assertEqual(early["cash"], 0)
                self.assertEqual(jit["cash"], 134)
                self.assertEqual(early["physical"], jit["physical"])
                self.assertEqual(early["rival_cash"], jit["rival_cash"])
                self.assertEqual(early["trace"][-1]["shed"]["WHEAT"], 1)
                self.assertEqual(jit["trace"][-1]["shed"]["WHEAT"], 1)

    def test_funded_hire_control_is_not_a_blanket_procurement_veto(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                pair = subject.capital_pair(self.engine, seat=seat, cash=27)
                self.assertEqual(pair["early_hold"]["cash"], 135)
                self.assertEqual(pair["early_hold"]["cash"], pair["jit"]["cash"])
                self.assertEqual(pair["early_hold"]["physical"], pair["jit"]["physical"])

    def test_capital_trace_preserves_raw_nonexistent_hand_rows(self):
        pair = subject.capital_pair(self.engine)
        self.assertEqual(pair["early_hold"]["trace"][2]["action"]["hands"], [["HARVEST"]])
        self.assertEqual(pair["early_hold"]["trace"][2]["hands"], [])
        self.assertEqual(pair["early_hold"]["trace"][2]["inventories"], [{}])

    def test_full_declared_panel_not_cherry_picked(self):
        before = subject.CALLBACKS
        try:
            rows = subject.run_panel(self.engine)
        except RuntimeError as exc:
            self.fail(str(exc))
        self.assertEqual(len(rows), 540)
        self.assertEqual(len({json.dumps(r["configuration"], sort_keys=True) for r in rows}), 540)
        self.assertEqual(subject.CALLBACKS-before, 9720)
        self.assertTrue(any(r["arms"]["early_hold"]["delta_margin"] < 0 for r in rows))
        self.assertTrue(any(r["arms"]["early_hold"]["delta_margin"] > 0 for r in rows))
        self.assertTrue(any(r["arms"]["early_hold"]["delta_margin"] == 0 for r in rows))
        for row in rows:
            self.assertTrue(all(a["same_final_physical"] for a in row["arms"].values()))
            self.assertTrue(all(a["delta_rival"] == 0 for a in row["arms"].values()))


def main():
    global ENGINE_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, required=True)
    args = parser.parse_args()
    ENGINE_DIR = args.engine_dir
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OpportunityCost)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"tests": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "full_interpreter_callbacks": subject.CALLBACKS}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
