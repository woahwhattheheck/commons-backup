# SPDX-License-Identifier: Apache-2.0
import unittest

from land_unlock_timing import analyze_unlock_timing
from land_unlock_timing_test_support import M, observation, row


def basic_route(*, purchase=95, plant=100, water=101, money_orders=None):
    route = [row() for _ in range(720)]
    route[purchase]["market"] = [["BUY_LAND"]]
    # farmer: (4,4) -> east into NE at 99, PLANT 100, WATER 101
    route[99]["farmer"] = ["EAST"]
    route[plant]["farmer"] = ["PLANT", "WHEAT"]
    route[water]["farmer"] = ["WATER"]
    for step, orders in (money_orders or {}).items():
        route[step]["market"].extend(orders)
    return route


class LandUnlockTimingTests(unittest.TestCase):
    def test_latest_safe_step_is_before_plant_market_ordering(self):
        obs = observation(seeds={"WHEAT": 1}, money=3000)
        result, report = analyze_unlock_timing(M, obs, {}, basic_route())
        self.assertTrue(report["certified"])
        self.assertEqual(result.quadrant, "NE")
        self.assertEqual(result.first_plant_step, 100)
        self.assertEqual(result.last_safe_purchase_step, 99)
        self.assertEqual(result.recommended_step, 99)

    def test_movement_through_locked_land_is_not_productive_use(self):
        obs = observation(seeds={"WHEAT": 1}, money=3000)
        route = basic_route(plant=104, water=105)
        route[100]["farmer"] = ["EAST"]
        route[101]["farmer"] = ["WEST"]
        result, _ = analyze_unlock_timing(M, obs, {}, route)
        self.assertEqual(result.first_plant_step, 104)
        self.assertEqual(result.last_safe_purchase_step, 103)


    def test_earlier_owned_tile_use_blocks_plant_only_timing_scope(self):
        obs = observation(seeds={"WHEAT": 1}, money=3000)
        route = basic_route()
        # Farmer enters NE and attempts a structure build before the represented PLANT.
        route[98]["farmer"] = ["EAST"]
        route[99]["farmer"] = ["BUILD_COOP"]
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "earlier_target_quadrant_use_out_of_scope")

    def test_same_turn_original_purchase_is_repaired_to_prior_turn(self):
        obs = observation(seeds={"WHEAT": 1}, money=3000)
        route = basic_route(purchase=100, plant=100, water=101)
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertTrue(report["certified"])
        self.assertEqual(result.original_step, 100)
        self.assertEqual(result.last_safe_purchase_step, 99)
        self.assertEqual(result.recommended_step, 99)

    def test_same_turn_seed_purchase_cannot_fund_plant(self):
        obs = observation(seeds={}, money=3000)
        route = basic_route()
        route[100]["market"] = [["BUY_SEED", "WHEAT", 1]]
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "first_plant_unfunded_seed")

    def test_prior_seed_purchase_is_available_for_plant(self):
        obs = observation(seeds={}, money=3000)
        route = basic_route(money_orders={94: [["BUY_SEED", "WHEAT", 1]]})
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertTrue(report["certified"])
        self.assertGreaterEqual(result.funded_cost_through_plant, 1010)

    def test_missing_same_day_water_rejects_bundle(self):
        obs = observation(seeds={"WHEAT": 1}, money=3000)
        route = basic_route(); route[101]["farmer"] = ["PASS"]
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "first_plant_missing_same_day_water")

    def test_future_sale_is_not_credited_to_fixed_prefix(self):
        obs = observation(seeds={"WHEAT": 1}, money=999)
        route = basic_route(money_orders={94: [["SELL", "WHEAT", 100]]})
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "no_funded_unlock_step_in_shift_window")

    def test_hire_and_seed_costs_are_protected(self):
        obs = observation(seeds={"WHEAT": 1}, money=1000)
        route = basic_route(money_orders={94: [["HIRE"]]})
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "no_funded_unlock_step_in_shift_window")

    def test_variable_price_purchase_fails_closed(self):
        obs = observation(seeds={"WHEAT": 1}, money=5000)
        route = basic_route(money_orders={94: [["BUY_PRODUCT", "WHEAT", 1]]})
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "no_funded_unlock_step_in_shift_window")

    def test_full_candidate_market_prefix_removes_that_shift(self):
        obs = observation(seeds={"WHEAT": 1}, money=3000)
        route = basic_route(purchase=95, plant=100, water=101)
        route[99]["market"] = [["BUY_SEED", "WHEAT", 1] for _ in range(10)]
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertTrue(report["certified"])
        self.assertLess(result.recommended_step, 99)

    def test_second_land_purchase_in_horizon_rejects_ambiguity(self):
        obs = observation(seeds={"WHEAT": 1}, money=8000)
        route = basic_route(); route[110]["market"] = [["BUY_LAND"]]
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "need_exactly_one_represented_land_purchase")

    def test_next_target_after_ne_is_sw(self):
        obs = observation(seeds={"WHEAT": 1}, money=5000, unlocked=["NW", "NE"], farmer=(4, 4))
        route = [row() for _ in range(720)]
        route[95]["market"] = [["BUY_LAND"]]
        # SW is x<5,y>=5
        route[99]["farmer"] = ["SOUTH"]
        route[100]["farmer"] = ["PLANT", "WHEAT"]
        route[101]["farmer"] = ["WATER"]
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertTrue(report["certified"])
        self.assertEqual(result.quadrant, "SW")
        self.assertEqual(result.land_cost, 2000)

    def test_too_late_melon_has_no_minimum_sale_path(self):
        obs = observation(step=499, seeds={"MELON": 1}, money=5000)
        route = [row() for _ in range(720)]
        route[500]["market"] = [["BUY_LAND"]]
        route[501]["farmer"] = ["EAST"]
        route[502]["farmer"] = ["PLANT", "MELON"]
        route[503]["farmer"] = ["WATER"]
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertIsNone(result)
        self.assertEqual(report["reason"], "crop_has_no_minimum_terminal_sale_path")

    def test_inactive_market_tail_does_not_block_insertion(self):
        obs = observation(seeds={"WHEAT": 1}, money=3000)
        route = basic_route()
        route[99]["market"] = [[] for _ in range(10)] + [["BUY_PRODUCT", "WHEAT", 9]]
        result, report = analyze_unlock_timing(M, obs, {}, route)
        self.assertTrue(report["certified"])
        self.assertEqual(result.recommended_step, 99)


if __name__ == "__main__":
    unittest.main()
