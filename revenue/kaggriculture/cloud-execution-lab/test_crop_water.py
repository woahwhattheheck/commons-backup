# SPDX-License-Identifier: Apache-2.0
import copy
import unittest

from crop_water import (
    WaterPolicyError,
    can_defer_water,
    classify_tiles,
    rank_water_obligations,
    water_obligation,
)

# Exact public constants from Kaggriculture engine pin
# 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c.
CROPS = {
    "WHEAT": {"first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT": {"first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO": {"first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON": {"first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}


def plant(crop="WHEAT", *, planted=0, day_watered=False, dry=0, yield_units=1, fertilized=-1):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted,
        "watered_today": day_watered,
        "consecutive_unwatered": dry,
        "yield_units": yield_units,
        "fertilized_until_day": fertilized,
    }


class WaterObligationTests(unittest.TestCase):
    def test_freshly_planted_crop_is_survival_due(self):
        # Engine initializes a new plant at consecutive_unwatered=1.
        o = water_obligation(plant(planted=3, dry=1), CROPS, 3)
        self.assertTrue(o.due_today)
        self.assertTrue(o.survival_due)
        self.assertEqual(o.latest_safe_day, 3)

    def test_second_same_day_water_is_noop(self):
        o = water_obligation(plant(day_watered=True, dry=1), CROPS, 3)
        self.assertFalse(o.due_today)
        self.assertIsNone(o.latest_safe_day)
        self.assertEqual(o.reason, "already_watered_today")

    def test_safe_single_dry_day_is_deferrable(self):
        o = water_obligation(plant(dry=0, planted=0), CROPS, 1)
        self.assertFalse(o.due_today)
        self.assertEqual(o.latest_safe_day, 2)
        self.assertEqual(o.reason, "deferrable_survival")

    def test_annual_bonus_window_adds_one_unfertilized_unit(self):
        # WHEAT max_yield_day=4 => bonus window begins age day 2.
        o = water_obligation(plant("WHEAT", planted=0, dry=0, yield_units=1), CROPS, 2)
        self.assertEqual(o.annual_yield_units, 1)
        self.assertTrue(o.due_today)
        self.assertIn("annual_yield", o.reason)

    def test_annual_fertilized_bonus_is_two_units_when_room(self):
        o = water_obligation(plant("MELON", planted=0, dry=0, yield_units=1, fertilized=8), CROPS, 6)
        self.assertEqual(o.annual_yield_units, 2)
        self.assertEqual(o.marginal_units, 2)

    def test_annual_bonus_is_clipped_by_yield_room(self):
        o = water_obligation(plant("WHEAT", planted=0, dry=0, yield_units=5, fertilized=9), CROPS, 2)
        self.assertEqual(o.annual_yield_units, 1)

    def test_annual_outside_bonus_window_has_no_current_yield_value(self):
        o = water_obligation(plant("WHEAT", planted=0, dry=0, yield_units=1), CROPS, 1)
        self.assertEqual(o.annual_yield_units, 0)
        self.assertFalse(o.due_today)

    def test_ongoing_unfertilized_production_does_not_make_water_due(self):
        # TOMATO first production arrives on next_day=8. At current day 7, base
        # production happens at refresh even when WATER is omitted.
        o = water_obligation(plant("TOMATO", planted=0, dry=0, yield_units=0), CROPS, 7)
        self.assertEqual(o.ongoing_bonus_units, 0)
        self.assertFalse(o.due_today)

    def test_ongoing_fertilized_due_refresh_has_one_marginal_water_unit(self):
        o = water_obligation(plant("TOMATO", planted=0, dry=0, yield_units=0, fertilized=7), CROPS, 7)
        self.assertEqual(o.ongoing_bonus_units, 1)
        self.assertTrue(o.due_today)
        self.assertEqual(o.reason, "fertilized_ongoing_bonus")

    def test_ongoing_bonus_needs_room_beyond_base_unit(self):
        o = water_obligation(plant("TOMATO", planted=0, dry=0, yield_units=3, fertilized=7), CROPS, 7)
        self.assertEqual(o.ongoing_bonus_units, 0)
        self.assertFalse(o.due_today)

    def test_ongoing_interval_is_respected(self):
        # STRAWBERRY produces on next days 10,12,14,16. current day 10 -> next 11 is not due.
        o = water_obligation(plant("STRAWBERRY", planted=0, dry=0, yield_units=0, fertilized=10), CROPS, 10)
        self.assertEqual(o.ongoing_bonus_units, 0)
        self.assertFalse(o.due_today)

    def test_survival_outranks_two_unit_annual_bonus(self):
        survival = water_obligation(plant("CARROT", dry=1, planted=0, yield_units=1), CROPS, 0)
        bonus = water_obligation(plant("MELON", dry=0, planted=0, yield_units=1, fertilized=6), CROPS, 6)
        ranked = rank_water_obligations([
            plant("MELON", dry=0, planted=0, yield_units=1, fertilized=6),
            plant("CARROT", dry=1, planted=0, yield_units=1),
        ], CROPS, 6)
        # Rebuild comparable day-6 survival crop to avoid day mismatch in direct values.
        self.assertTrue(ranked[0].survival_due)
        self.assertGreater(survival.priority[0], bonus.priority[0])

    def test_deferral_requires_existing_future_water(self):
        t = plant("WHEAT", dry=0, planted=0, yield_units=1)
        self.assertEqual(can_defer_water(t, CROPS, 1, next_water_day=None), (False, "no_incumbent_future_water"))
        self.assertEqual(can_defer_water(t, CROPS, 1, next_water_day=2), (True, "incumbent_water_meets_survival_deadline"))
        self.assertEqual(can_defer_water(t, CROPS, 1, next_water_day=3), (False, "future_water_after_survival_deadline"))

    def test_current_marginal_yield_cannot_be_deferred(self):
        t = plant("WHEAT", dry=0, planted=0, yield_units=1)
        ok, reason = can_defer_water(t, CROPS, 2, next_water_day=3)
        self.assertFalse(ok)
        self.assertEqual(reason, "annual_yield")

    def test_survival_due_cannot_be_deferred_even_with_future_water(self):
        t = plant("WHEAT", dry=1, planted=0, yield_units=1)
        ok, reason = can_defer_water(t, CROPS, 1, next_water_day=2)
        self.assertFalse(ok)
        self.assertEqual(reason, "survival")

    def test_removal_before_deadline_allows_deferral(self):
        t = plant("WHEAT", dry=0, planted=0, yield_units=1)
        self.assertEqual(can_defer_water(t, CROPS, 1, next_water_day=None, removal_day=2), (True, "removed_before_survival_deadline"))

    def test_classify_tiles_is_read_only_and_stable(self):
        farm = [[None, plant("CARROT", planted=0, dry=1)], [plant("TOMATO", planted=0, dry=0), "LOCKED"]]
        before = copy.deepcopy(farm)
        first = classify_tiles(farm, CROPS, 1)
        second = classify_tiles(farm, CROPS, 1)
        self.assertEqual(farm, before)
        self.assertEqual(first, second)
        self.assertEqual([x["tile"] for x in first], [[1, 0], [0, 1]])

    def test_malformed_states_fail_closed(self):
        bad = plant()
        bad["consecutive_unwatered"] = None
        with self.assertRaises(WaterPolicyError):
            water_obligation(bad, CROPS, 1)
        bad2 = plant()
        bad2["crop"] = "PRIVATE_GUESS"
        with self.assertRaises(WaterPolicyError):
            water_obligation(bad2, CROPS, 1)

    def test_boolean_is_not_accepted_as_integer_counter(self):
        bad = plant()
        bad["yield_units"] = True
        with self.assertRaises(WaterPolicyError):
            water_obligation(bad, CROPS, 1)


if __name__ == "__main__":
    unittest.main()
