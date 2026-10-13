# SPDX-License-Identifier: Apache-2.0
"""Focused full-interpreter checks for the Gemini FERT floor-buy/apply witnesses."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import unittest

import fert_floor_apply as subject
import opportunity_cost as oc

ENGINE_DIR = None


class FertFloorApply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, cls.hashes = oc.load_engine(ENGINE_DIR)
        cls.threshold = subject.floor_buy_threshold(cls.engine)

    def test_reuses_exact_authenticated_engine_authority(self):
        for name, expected in oc.ENGINE_BLOBS.items():
            self.assertEqual(oc.git_blob((ENGINE_DIR / name).read_bytes()), expected)
        self.assertEqual(set(self.hashes), set(oc.ENGINE_BLOBS))

    def test_floor_boundary_is_postbuy_quote_exact(self):
        e = self.engine
        t = self.threshold
        self.assertGreater(e.market_price("FERTILIZER", t - 2), e.PRICE_FLOOR)
        self.assertEqual(e.market_price("FERTILIZER", t - 1), e.PRICE_FLOOR)
        self.assertFalse(subject.run_pair(e, fert_inventory=t - 1)["certificate"]["at_price_floor"])
        self.assertTrue(subject.run_pair(e, fert_inventory=t)["certificate"]["at_price_floor"])
        self.assertTrue(subject.run_pair(e, fert_inventory=t + 100)["certificate"]["at_price_floor"])

    def test_both_seats_real_floor_path_buys_custodies_applies_and_yields(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                pair = subject.run_pair(self.engine, seat=seat, fert_inventory=self.threshold)
                cert = pair["certificate"]
                candidate = pair["floor_apply"]
                control = pair["control"]
                self.assertEqual(cert["witness"], "MINIMAL_ONE_WATER_CARROT")
                self.assertTrue(cert["at_price_floor"])
                self.assertEqual(cert["fert_one_unit_postbuy_quote"], self.engine.PRICE_FLOOR)
                self.assertEqual(candidate["trace"][0]["cash_delta"], -self.engine.PRICE_FLOOR)
                self.assertEqual(candidate["trace"][0]["shed"]["FERTILIZER"], 1)
                self.assertEqual(candidate["trace"][1]["shed"]["FERTILIZER"], 0)
                self.assertEqual(candidate["trace"][1]["inventories"][0].get("FERTILIZER"), 1)
                self.assertNotIn("FERTILIZER", candidate["trace"][2]["inventories"][0])
                self.assertGreaterEqual(candidate["trace"][2]["tile"]["fertilized_until_day"], 3)
                self.assertEqual(cert["incremental_harvest_units"], 1)
                self.assertEqual(cert["candidate_harvest_units"], cert["control_harvest_units"] + 1)
                self.assertGreater(cert["own_cash_delta"], 0)
                self.assertEqual(cert["rival_cash_delta"], 0)
                self.assertTrue(cert["same_final_physical"])
                self.assertEqual(cert["extra_unit_callback_count"], 2)
                self.assertEqual(cert["extra_unit_callbacks"], ["PICKUP FERTILIZER", "FERTILIZE"])
                self.assertEqual(cert["market_buy_step"], 90)
                self.assertFalse(cert["current_native_engagement_claim"])
                self.assertFalse(cert["activation_claim"])
                self.assertEqual(candidate["physical"], control["physical"])

    def test_full_three_day_melon_window_is_source_planted_and_amortized(self):
        e = self.engine
        self.assertEqual(e.CROPS["MELON"]["max_yield"], 6)
        self.assertEqual(e.CROPS["MELON"]["first_yield_day"], 10)
        self.assertFalse(e.CROPS["MELON"]["ongoing"])
        self.assertEqual(e._new_plant("MELON", 4, 24)["yield_units"], 1)
        for seat in (0, 1):
            with self.subTest(seat=seat):
                pair = subject.run_amortized_pair(e, seat=seat, fert_inventory=self.threshold)
                cert = pair["certificate"]
                candidate = pair["floor_apply"]
                control = pair["control"]
                self.assertEqual(cert["schema"], subject.SCHEMA)
                self.assertEqual(cert["witness"], "AMORTIZED_THREE_DAY_MELON")
                self.assertTrue(cert["at_price_floor"])
                self.assertEqual(cert["fixture_step"], 90)
                self.assertEqual(cert["plant_day"], 4)
                self.assertEqual(cert["plant_step"], 96)
                self.assertEqual(cert["source_initial_yield_units"], 1)
                self.assertEqual(cert["fertilizer_active_water_days_used"], 3)
                self.assertEqual(cert["shared_survival_water_steps"], [97, 144, 192])
                self.assertEqual(cert["common_water_steps"], [243, 264, 288])
                self.assertEqual(cert["prefert_snapshot_step"], 239)
                self.assertEqual(cert["market_buy_step"], 240)
                self.assertEqual(cert["harvest_step"], 336)
                self.assertEqual(cert["liquidation_step"], 337)
                for arm in (candidate, control):
                    after_fixture_eod = subject._trace_at(arm, 95)
                    self.assertEqual(after_fixture_eod["action"]["farmer"], ["PASS"])
                    self.assertIsNone(after_fixture_eod["tile"])
                    self.assertEqual(after_fixture_eod["seeds"]["MELON"], 1)
                    planted = subject._trace_at(arm, 96)
                    self.assertEqual(planted["action"]["farmer"], ["PLANT", "MELON"])
                    self.assertEqual(planted["seeds"]["MELON"], 0)
                    self.assertEqual(planted["tile"]["kind"], "PLANT")
                    self.assertEqual(planted["tile"]["crop"], "MELON")
                    self.assertEqual(planted["tile"]["planted_day"], 4)
                    self.assertEqual(planted["tile"]["yield_units"], 1)
                    self.assertEqual(planted["tile"]["consecutive_unwatered"], 1)
                    self.assertFalse(planted["tile"]["watered_today"])
                    day4_water = subject._trace_at(arm, 97)
                    self.assertEqual(day4_water["action"]["farmer"], ["WATER"])
                    self.assertTrue(day4_water["tile"]["watered_today"])
                    self.assertEqual(day4_water["tile"]["yield_units"], 1)
                    prefert_row = subject._trace_at(arm, 239)
                    prefert = prefert_row["tile"]
                    self.assertEqual(prefert["kind"], "PLANT")
                    self.assertEqual(prefert["crop"], "MELON")
                    self.assertEqual(prefert["planted_day"], 4)
                    self.assertEqual(prefert["yield_units"], 1)
                    self.assertEqual(prefert["consecutive_unwatered"], 1)
                    self.assertFalse(prefert["watered_today"])
                    self.assertEqual(prefert_row["fert_market_inventory"], self.threshold)
                    self.assertEqual(
                        e.market_price("FERTILIZER", prefert_row["fert_market_inventory"] - 1),
                        e.PRICE_FLOOR,
                    )
                self.assertEqual(cert["prefert_candidate_tile"], cert["prefert_control_tile"])
                self.assertEqual(cert["prefert_candidate_tile"]["yield_units"], 1)
                self.assertEqual(subject._trace_at(candidate, 240)["cash_delta"], -1)
                self.assertEqual(subject._trace_at(candidate, 240)["shed"]["FERTILIZER"], 1)
                self.assertEqual(subject._trace_at(candidate, 241)["inventories"][0].get("FERTILIZER"), 1)
                self.assertNotIn("FERTILIZER", subject._trace_at(candidate, 242)["inventories"][0])
                self.assertEqual(subject._trace_at(candidate, 242)["tile"]["fertilized_until_day"], 12)
                for step, candidate_yield, control_yield in (
                    (243, 3, 2), (264, 5, 3), (288, 6, 4)
                ):
                    self.assertEqual(subject._trace_at(candidate, step)["tile"]["yield_units"], candidate_yield)
                    self.assertEqual(subject._trace_at(control, step)["tile"]["yield_units"], control_yield)
                self.assertEqual(subject._trace_at(candidate, 335)["tile"]["yield_units"], 6)
                self.assertEqual(subject._trace_at(control, 335)["tile"]["yield_units"], 4)
                self.assertEqual(subject._trace_at(candidate, 335)["tile"]["consecutive_unwatered"], 1)
                self.assertEqual(subject._trace_at(control, 335)["tile"]["consecutive_unwatered"], 1)
                self.assertEqual(cert["candidate_harvest_units"], 6)
                self.assertEqual(cert["control_harvest_units"], 4)
                self.assertEqual(cert["incremental_harvest_units"], 2)
                self.assertEqual(cert["extra_unit_callbacks_per_incremental_unit"], 1)
                self.assertEqual(cert["extra_unit_callback_count"], 2)
                self.assertGreater(cert["own_cash_delta"], 0)
                self.assertEqual(cert["rival_cash_delta"], 0)
                self.assertTrue(cert["same_final_physical"])
                self.assertEqual(candidate["physical"], control["physical"])

    def test_unfunded_buy_is_a_no_effect_control_in_both_witnesses(self):
        for runner in (subject.run_pair, subject.run_amortized_pair):
            with self.subTest(runner=runner.__name__):
                pair = runner(self.engine, fert_inventory=self.threshold, cash=0)
                cert = pair["certificate"]
                buy_row = subject._trace_at(pair["floor_apply"], cert["market_buy_step"])
                self.assertEqual(buy_row["cash_delta"], 0)
                self.assertEqual(cert["incremental_harvest_units"], 0)
                self.assertEqual(cert["own_cash_delta"], 0)
                self.assertTrue(cert["same_final_physical"])

    def test_panel_is_complete_declared_boundary_and_both_seats(self):
        before = oc.CALLBACKS
        report = subject.run_panel(self.engine)
        self.assertEqual(report["schema"], subject.SCHEMA)
        self.assertEqual(report["floor_prebuy_inventory_threshold"], self.threshold)
        self.assertEqual(len(report["minimal_cells"]), 6)
        keys = {(r["seat"], r["fert_inventory_before"]) for r in report["minimal_cells"]}
        self.assertEqual(keys, {
            (0, self.threshold - 1), (0, self.threshold), (0, self.threshold + 100),
            (1, self.threshold - 1), (1, self.threshold), (1, self.threshold + 100),
        })
        self.assertEqual(len(report["amortized_floor_cells"]), 2)
        self.assertEqual({r["seat"] for r in report["amortized_floor_cells"]}, {0, 1})
        # 6 minimal cells * 2 arms * 7 ticks = 84;
        # 2 amortized cells * 2 arms * (337-90+1=248) ticks = 992.
        self.assertEqual(oc.CALLBACKS - before, 1076)
        for row in report["minimal_cells"] + report["amortized_floor_cells"]:
            self.assertTrue(row["same_final_physical"])
            self.assertEqual(row["rival_cash_delta"], 0)
            self.assertFalse(row["policy_claim"])

    def test_invalid_inputs_fail_closed_instead_of_bool_coercion(self):
        for runner in (subject.run_pair, subject.run_amortized_pair):
            for kwargs in ({"seat": True}, {"seat": 2}, {"fert_inventory": True},
                           {"fert_inventory": -1}, {"cash": True}, {"cash": -1}):
                with self.subTest(runner=runner.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                    runner(self.engine, **kwargs)
        for row in ([], [1], "PASS", None):
            with self.subTest(row=row), self.assertRaises(ValueError):
                subject.unit_action(row)
        with self.assertRaises(ValueError):
            subject._unplanted_fixture(self.engine, 0, fert_inventory=True)
        with self.assertRaises(ValueError):
            subject._unplanted_fixture(self.engine, 0, fert_inventory=self.threshold, cash=True)
        with self.assertRaises(ValueError):
            subject._unplanted_fixture(self.engine, 0, fert_inventory=self.threshold, crop="NOPE")


def main():
    global ENGINE_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, required=True)
    args = parser.parse_args()
    ENGINE_DIR = args.engine_dir
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FertFloorApply)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "full_interpreter_callbacks": oc.CALLBACKS,
    }, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
