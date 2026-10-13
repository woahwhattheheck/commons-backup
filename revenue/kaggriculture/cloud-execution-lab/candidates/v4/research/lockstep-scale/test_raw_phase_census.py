from __future__ import annotations

import unittest

import raw_phase_census as census


def empty_tapes():
    return [[{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(719)] for _ in range(13)]


def contract():
    return {
        "ROUTE_STEP": 144,
        "FINAL_PLAN_STEP": 648,
        "LAST_STEP": 718,
        "MAX_ORDERS": 10,
        "REACHABLE_MIDGAME_PLANS": (0, 1, 3),
    }


class RawPhaseCensusTests(unittest.TestCase):
    def test_shared_prefix_candidate_is_deduped_across_selected_plans(self):
        tapes = empty_tapes()
        tapes[0][10]["market"] = [["BUY_PRODUCT", "WHEAT", 3], []]
        report = census.census_tapes(tapes, contract())
        self.assertFalse(report["current_native_reach_authority"])
        self.assertEqual(report["candidate_surface"], "authored_r01_tape_pre_transforms")
        self.assertEqual(report["unique_candidate_coordinates"], 1)
        self.assertEqual(report["candidates"][0]["selected_plans"], [0, 1, 3])

    def test_midgame_candidate_binds_its_selected_plan(self):
        tapes = empty_tapes()
        tapes[3][200]["market"] = [None, ["BUY_PRODUCT", "FERTILIZER", 2]]
        report = census.census_tapes(tapes, contract())
        self.assertEqual(report["unique_candidate_coordinates"], 1)
        row = report["candidates"][0]
        self.assertEqual(row["tape_plan"], 3)
        self.assertEqual(row["selected_plans"], [3])
        self.assertEqual(row["direction"], "advance_one_slot")

    def test_forced_final_plan_is_shared(self):
        tapes = empty_tapes()
        tapes[2][650]["market"] = [["BUY_PRODUCT", "WHEAT", 1], ["PASS"]]
        report = census.census_tapes(tapes, contract())
        self.assertEqual(report["unique_candidate_coordinates"], 1)
        self.assertEqual(report["candidates"][0]["selected_plans"], [0, 1, 3])

    def test_final_liquidation_step_is_excluded(self):
        tapes = empty_tapes()
        tapes[2][718]["market"] = [["BUY_PRODUCT", "WHEAT", 1], []]
        self.assertEqual(census.census_tapes(tapes, contract())["unique_candidate_coordinates"], 0)

    def test_cap_boundary_requires_both_slots_executable(self):
        tapes = empty_tapes()
        rows = [["HIRE"] for _ in range(11)]
        rows[9] = ["BUY_PRODUCT", "WHEAT", 1]
        rows[10] = []
        tapes[0][10]["market"] = rows
        self.assertEqual(census.census_tapes(tapes, contract())["unique_candidate_coordinates"], 0)

    def test_unsupported_buy_product_is_ignored(self):
        tapes = empty_tapes()
        tapes[0][10]["market"] = [["BUY_PRODUCT", "CARROT", 1], []]
        self.assertEqual(census.census_tapes(tapes, contract())["unique_candidate_coordinates"], 0)

    def test_two_empty_neighbors_yield_two_phase_directions(self):
        tapes = empty_tapes()
        tapes[0][10]["market"] = [[], ["BUY_PRODUCT", "WHEAT", 1], []]
        report = census.census_tapes(tapes, contract())
        self.assertEqual(report["unique_candidate_coordinates"], 2)
        self.assertEqual(report["by_direction"], {"advance_one_slot": 1, "delay_one_slot": 1})

    def test_router_contract_is_literal_and_derives_reachable_plans(self):
        source = b'''ROUTE_STEP = 144\nFINAL_PLAN_STEP = 648\nLAST_STEP = 718\nMAX_ORDERS = 10\nSHOP_PLANS = {("A", "B"): 3, ("B", "A"): 1}\n'''
        parsed = census.router_contract_from_bytes(source)
        self.assertEqual(parsed["REACHABLE_MIDGAME_PLANS"], (0, 1, 3))

    def test_dynamic_router_constant_fails_closed(self):
        source = b'''ROUTE_STEP = 72 * 2\nFINAL_PLAN_STEP = 648\nLAST_STEP = 718\nMAX_ORDERS = 10\nSHOP_PLANS = {}\n'''
        with self.assertRaises(ValueError):
            census.router_contract_from_bytes(source)

    def test_shape_must_be_canonical_13x719(self):
        with self.assertRaises(ValueError):
            census.census_tapes(empty_tapes()[:-1], contract())


if __name__ == "__main__":
    unittest.main()
