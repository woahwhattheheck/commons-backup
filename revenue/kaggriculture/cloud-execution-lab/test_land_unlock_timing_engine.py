# SPDX-License-Identifier: Apache-2.0
"""P02 contracts against the repository's extracted Kaggriculture mechanics."""
from copy import deepcopy
import unittest

import mechanics as m


def state(money=1000):
    board = 10
    tiles = [[None if x < 5 and y < 5 else "LOCKED" for x in range(board)] for y in range(board)]
    farm = {"farmer": [4, 4], "hands": [], "money": money, "hires_today": 0,
            "unlocked_quadrants": ["NW"], "tiles": tiles}
    private = {"shed": {}, "inventories": [{}], "seeds": {"WHEAT": 1}}
    return farm, private


class LandUnlockTimingEngineTests(unittest.TestCase):
    def test_actual_land_cost_and_unlock_order_are_ne_first(self):
        farm, private = state(999)
        m._do_buy_land(farm, 10)
        self.assertEqual(farm["unlocked_quadrants"], ["NW"])
        self.assertEqual(farm["tiles"][4][5], "LOCKED")
        self.assertEqual(farm["money"], 999)

        farm["money"] = 1000
        m._do_buy_land(farm, 10)
        self.assertEqual(farm["unlocked_quadrants"], ["NW", "NE"])
        self.assertIsNone(farm["tiles"][4][5])
        self.assertEqual(farm["money"], 0)

    def test_movement_on_locked_land_is_legal_but_plant_is_not(self):
        farm, private = state(1000)
        m._apply_unit_action(farm, private, 0, ["EAST"], 10, 0, 24, 100)
        self.assertEqual(farm["farmer"], [5, 4])
        self.assertEqual(farm["tiles"][4][5], "LOCKED")
        m._apply_unit_action(farm, private, 0, ["PLANT", "WHEAT"], 10, 0, 24, 100)
        self.assertEqual(farm["tiles"][4][5], "LOCKED")
        self.assertEqual(private["seeds"]["WHEAT"], 1)

        # BUY_LAND is a market-stage operation. After it has executed, the next
        # unit stage can use the tile without any path-access special case.
        m._do_buy_land(farm, 10)
        self.assertIsNone(farm["tiles"][4][5])
        m._apply_unit_action(farm, private, 0, ["PLANT", "WHEAT"], 10, 0, 24, 100)
        self.assertEqual(farm["tiles"][4][5]["kind"], "PLANT")
        self.assertEqual(private["seeds"].get("WHEAT", 0), 0)

    def test_new_plant_requires_same_day_water_to_survive_refresh(self):
        farm, private = state(1000)
        m._do_buy_land(farm, 10)
        m._apply_unit_action(farm, private, 0, ["EAST"], 10, 0, 24, 100)
        m._apply_unit_action(farm, private, 0, ["PLANT", "WHEAT"], 10, 0, 24, 100)

        dry = deepcopy(farm)
        m._daily_refresh_plants(dry, 0, 24)
        self.assertEqual(dry["tiles"][4][5], {"kind": "WEED"})

        m._apply_unit_action(farm, private, 0, ["WATER"], 10, 0, 24, 100)
        m._daily_refresh_plants(farm, 0, 24)
        self.assertEqual(farm["tiles"][4][5]["kind"], "PLANT")
        self.assertEqual(farm["tiles"][4][5]["consecutive_unwatered"], 0)


if __name__ == "__main__":
    unittest.main()
