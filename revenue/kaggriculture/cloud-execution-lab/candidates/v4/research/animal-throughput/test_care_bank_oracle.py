from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("care_bank_oracle.py")
spec = importlib.util.spec_from_file_location("care_bank_oracle", MODULE_PATH)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def state(
    animal="COW",
    *,
    placed_day=0,
    yield_units=0,
    consecutive_unfed=0,
    fed_today=True,
    cared_today=True,
    pending_care_bonus=0,
):
    return {
        "animal": animal,
        "placed_day": placed_day,
        "yield_units": yield_units,
        "consecutive_unfed": consecutive_unfed,
        "fed_today": fed_today,
        "cared_today": cared_today,
        "pending_care_bonus": pending_care_bonus,
    }


class CareBankOracleTests(unittest.TestCase):
    def test_production_calendar_matches_species_intervals(self):
        # Placed day 0: first production is EOD day first_yield_day-1.
        self.assertTrue(m.is_production_eod("GOOSE", 0, 3))
        self.assertTrue(m.is_production_eod("COW", 0, 7))
        self.assertTrue(m.is_production_eod("SHEEP", 0, 5))
        self.assertFalse(m.is_production_eod("COW", 0, 6))
        self.assertTrue(m.is_production_eod("COW", 0, 9))
        self.assertFalse(m.is_production_eod("COW", 0, 8))

    def test_same_day_care_never_changes_current_production(self):
        s = state(animal="COW", placed_day=0, pending_care_bonus=3, yield_units=0)
        result = m.care_today_marginal(s, 7)
        self.assertEqual(result["same_day_yield_delta"], 0)
        self.assertEqual(result["bank_after_delta"], 1)
        self.assertEqual(result["on"]["realized_production_units"], 4)
        self.assertEqual(result["on"]["bank_after"], 1)

    def test_nonproduction_feed_and_care_banks_one(self):
        out = m.refresh_animal_day(state(pending_care_bonus=2), 2)
        self.assertFalse(out["production_eod"])
        self.assertEqual(out["bank_before"], 2)
        self.assertEqual(out["bank_after"], 3)
        self.assertEqual(out["yield_after"], 0)

    def test_care_without_feed_banks_nothing(self):
        out = m.refresh_animal_day(
            state(fed_today=False, cared_today=True, pending_care_bonus=2), 2
        )
        self.assertFalse(out["production_eod"])
        self.assertEqual(out["bank_after"], 2)
        marginal = m.care_today_marginal(
            state(fed_today=False, cared_today=True, pending_care_bonus=2), 2
        )
        self.assertEqual(marginal["classification"], "NO_FEED_NO_NEW_CARE_BANK")
        self.assertEqual(marginal["bank_after_delta"], 0)

    def test_fed_production_consumes_prior_bank_then_clips(self):
        out = m.refresh_animal_day(
            state(animal="COW", placed_day=0, yield_units=4, pending_care_bonus=4), 7
        )
        self.assertTrue(out["production_eod"])
        self.assertEqual(out["raw_production_units"], 5)
        self.assertEqual(out["realized_production_units"], 2)
        self.assertEqual(out["clipped_total_units"], 3)
        self.assertEqual(out["clipped_care_bonus_units"], 3)
        self.assertEqual(out["bank_consumed_for_yield"], 4)
        self.assertEqual(out["bank_after"], 1)  # today's CARE is for a later cycle
        self.assertEqual(out["yield_after"], 6)

    def test_unfed_production_keeps_base_but_erases_care_bank(self):
        out = m.refresh_animal_day(
            state(
                animal="COW",
                placed_day=0,
                yield_units=0,
                consecutive_unfed=0,
                fed_today=False,
                cared_today=True,
                pending_care_bonus=5,
            ),
            7,
        )
        self.assertTrue(out["production_eod"])
        self.assertFalse(out["escaped"])
        self.assertEqual(out["realized_production_units"], 1)
        self.assertEqual(out["bank_erased_unfed_production"], 5)
        self.assertEqual(out["bank_after"], 0)

    def test_second_consecutive_unfed_escapes_before_production(self):
        out = m.refresh_animal_day(
            state(
                animal="SHEEP",
                placed_day=0,
                yield_units=4,
                consecutive_unfed=1,
                fed_today=False,
                cared_today=True,
                pending_care_bonus=5,
            ),
            5,
        )
        self.assertTrue(out["escaped"])
        self.assertFalse(out["production_eod"])
        self.assertEqual(out["bank_destroyed_on_escape"], 5)
        self.assertEqual(out["next_state"], {"kind": "PASTURE"})

    def test_first_yield_bound_finds_cow_only_daily_care_clipping(self):
        goose = m.first_yield_care_bound("GOOSE")
        cow = m.first_yield_care_bound("COW")
        sheep = m.first_yield_care_bound("SHEEP")
        self.assertEqual(goose["guaranteed_clipped_care_units_if_daily_feed_care_and_no_prior_harvest"], 0)
        self.assertEqual(cow["daily_feed_care_bank_entering_first_yield"], 7)
        self.assertEqual(cow["max_useful_care_bank_at_empty_first_yield"], 5)
        self.assertEqual(cow["guaranteed_clipped_care_units_if_daily_feed_care_and_no_prior_harvest"], 2)
        self.assertEqual(sheep["guaranteed_clipped_care_units_if_daily_feed_care_and_no_prior_harvest"], 0)

    def test_daily_care_pre_first_cow_yield_reproduces_two_clipped_units(self):
        s = state(animal="COW", placed_day=0, cared_today=True, fed_today=True)
        reports = []
        for day in range(8):
            # final daily state has FEED+CARE satisfied each day
            s["fed_today"] = True
            s["cared_today"] = True
            out = m.refresh_animal_day(s, day)
            reports.append(out)
            s = dict(out["next_state"])
        first = reports[7]
        self.assertTrue(first["production_eod"])
        self.assertEqual(first["bank_before"], 7)
        self.assertEqual(first["raw_production_units"], 8)
        self.assertEqual(first["realized_production_units"], 6)
        self.assertEqual(first["clipped_care_bonus_units"], 2)
        self.assertEqual(first["bank_after"], 1)

    def test_harvest_headroom_can_make_a_large_bank_useful(self):
        # Explicit state with empty yield storage: five prior CARE units + base fit a cow exactly.
        out = m.refresh_animal_day(
            state(animal="COW", placed_day=0, yield_units=0, pending_care_bonus=5), 7
        )
        self.assertEqual(out["realized_production_units"], 6)
        self.assertEqual(out["clipped_care_bonus_units"], 0)

    def test_authored_pressure_is_target_agnostic_and_deterministic(self):
        route = []
        for step in range(240):
            farmer = ["PASS"]
            hands = []
            if step == 1:
                farmer = ["PLACE", "COW"]
            if step in (2, 26, 50, 74, 98, 122, 146):
                hands = [["FEED"], ["CARE"]]
            route.append({"farmer": farmer, "hands": hands, "market": []})
        out = m.census_authored_care_pressure(route, "synthetic")
        self.assertEqual(out["care_rows"], 7)
        self.assertEqual(out["feed_rows"], 7)
        self.assertEqual(len(out["authored_cow_place_windows"]), 1)
        window = out["authored_cow_place_windows"][0]
        self.assertEqual(window["pre_first_yield_days"], [0, 6])
        self.assertEqual(window["all_animal_care_rows_in_window"], 7)
        self.assertFalse(window["target_specific"])
        self.assertFalse(window["realized_placement"])

    def test_malformed_state_fails_closed(self):
        bad = state()
        bad["yield_units"] = 7
        with self.assertRaises(m.CareBankError):
            m.refresh_animal_day(bad, 7)
        bad2 = state()
        bad2["fed_today"] = 1
        with self.assertRaises(m.CareBankError):
            m.refresh_animal_day(bad2, 7)
        with self.assertRaises(m.CareBankError):
            m.is_production_eod("COW", 3, 2)
        bad3 = state()
        bad3["consecutive_unfed"] = 2
        with self.assertRaises(m.CareBankError):
            m.refresh_animal_day(bad3, 7)

    def test_engine_checkout_pin_if_present(self):
        if not m.ENGINE_PATH.exists():
            self.skipTest("repository engine source not mounted")
        receipt = m.verify_engine_source()
        self.assertEqual(receipt["engine_blob"], m.EXPECTED_ENGINE_BLOB)


if __name__ == "__main__":
    unittest.main()
