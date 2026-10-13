# SPDX-License-Identifier: Apache-2.0
"""A4 second-wave melons (idea-hunt A4): day-12 planting lane.

    python -m unittest -v checks/test_v3_a4_second_melons.py

Covers off-identity (flag off returns the action object untouched), the active
day window, seed buying (money floor, market-room cap), crew hiring (never
alongside a parent HIRE, detection-based crew claiming), the plant/water/
harvest/place worker program, the harvest age gate, install() wiring and
validation, and reset() isolation. Standard library only.
"""
from __future__ import annotations

import copy
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import a4_second_melons as a4  # noqa: E402


def melon_tile(planted_day, watered=False, yield_units=1):
    return {"kind": "PLANT", "crop": "MELON", "planted_day": planted_day,
            "watered_today": watered, "consecutive_unwatered": 0,
            "yield_units": yield_units, "fertilized_until_day": -1}


def synthetic_observation(step, money=5000, seeds=None, tile_fn=None,
                          hands=(), inventories=None, player=0):
    size = 10
    tiles = [["LOCKED"] * size for _ in range(size)]
    for y in range(2, 8):
        for x in range(2, 8):
            tiles[y][x] = None
    if tile_fn:
        for y in range(size):
            for x in range(size):
                v = tile_fn(x, y, tiles[y][x])
                if v is not None:
                    tiles[y][x] = v
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [list(h) for h in hands],
            "money": money, "unlocked_quadrants": ["NW"], "hires_today": 0}
    invs = [dict(i) for i in inventories] if inventories is not None \
        else [{} for _ in range(len(hands) + 1)]
    return {"step": step, "day": step // 24, "hour": step % 24, "player": player,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": invs,
                        "shed": {"WHEAT": 5},
                        "seeds": dict(seeds or {})},
            "market": {"prices": {p: 10 for p in r04.PRODUCTS}},
            "town": {"unlocked_shops": []}}


def empty_action(hands=0):
    return {"farmer": ["PASS"], "hands": [["PASS"]] * hands, "market": []}


class OffIdentityTests(unittest.TestCase):
    def setUp(self):
        a4.reset()

    def tearDown(self):
        a4.reset()

    def test_flag_off_returns_action_untouched(self):
        obs = synthetic_observation(289)
        action = empty_action()
        self.assertIs(a4.apply_a4(obs, action, enabled=False), action)

    def test_before_plant_day_is_noop(self):
        obs = synthetic_observation(200, money=5000)
        action = empty_action()
        out = a4.apply_a4(obs, action, enabled=True)
        self.assertEqual(out["market"], [])

    def test_after_last_day_is_noop(self):
        obs = synthetic_observation(25 * 24, money=5000)
        action = empty_action()
        out = a4.apply_a4(obs, action, enabled=True)
        self.assertEqual(out["market"], [])

    def test_zero_count_is_noop(self):
        obs = synthetic_observation(289, money=5000)
        action = empty_action()
        out = a4.apply_a4(obs, action, enabled=True, count=0)
        self.assertEqual(out["market"], [])


class SeedBuyingTests(unittest.TestCase):
    def setUp(self):
        a4.reset()

    def tearDown(self):
        a4.reset()

    def test_buys_seeds_on_plant_day(self):
        obs = synthetic_observation(289, money=5000, seeds={})
        out = a4.apply_a4(obs, empty_action(), enabled=True)
        buys = [o for o in out["market"] if o[0] == "BUY_SEED"]
        self.assertEqual(buys, [["BUY_SEED", "MELON", 6]])

    def test_no_buy_below_money_floor(self):
        obs = synthetic_observation(289, money=100, seeds={})
        out = a4.apply_a4(obs, empty_action(), enabled=True)
        self.assertEqual([o for o in out["market"] if o[0] == "BUY_SEED"], [])

    def test_no_buy_when_market_full(self):
        obs = synthetic_observation(289, money=5000, seeds={})
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "WHEAT", 1]] * 10}
        out = a4.apply_a4(obs, action, enabled=True)
        self.assertEqual(len(out["market"]), 10)

    def test_no_buy_when_seeds_on_hand(self):
        obs = synthetic_observation(289, money=5000, seeds={"MELON": 6})
        out = a4.apply_a4(obs, empty_action(), enabled=True)
        self.assertEqual([o for o in out["market"] if o[0] == "BUY_SEED"], [])

    def test_no_buy_after_plant_day(self):
        obs = synthetic_observation(13 * 24, money=5000, seeds={})
        out = a4.apply_a4(obs, empty_action(), enabled=True)
        self.assertEqual([o for o in out["market"] if o[0] == "BUY_SEED"], [])


class HiringTests(unittest.TestCase):
    def setUp(self):
        a4.reset()

    def tearDown(self):
        a4.reset()

    def test_hires_crew_on_plant_day(self):
        obs = synthetic_observation(289, money=5000, seeds={"MELON": 6})
        out = a4.apply_a4(obs, empty_action(), enabled=True)
        self.assertIn(["HIRE"], out["market"])

    def test_no_hire_alongside_parent_hire(self):
        obs = synthetic_observation(289, money=5000, seeds={"MELON": 6})
        action = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
        out = a4.apply_a4(obs, action, enabled=True)
        self.assertEqual(out["market"], [["HIRE"]])

    def test_crew_claimed_by_detection(self):
        # Step 1: hire requested.
        obs1 = synthetic_observation(289, money=5000, seeds={"MELON": 6})
        a4.apply_a4(obs1, empty_action(), enabled=True)
        # Step 2: one new hand appeared -> claimed as crew (command index 1).
        obs2 = synthetic_observation(290, money=5000, seeds={"MELON": 6},
                                     hands=[[4, 4]])
        out = a4.apply_a4(obs2, empty_action(hands=1), enabled=True)
        self.assertNotEqual(out["hands"][0], ["PASS"])

    def test_failed_hire_claims_nothing(self):
        obs1 = synthetic_observation(289, money=5000, seeds={"MELON": 6})
        a4.apply_a4(obs1, empty_action(), enabled=True)
        # No new hand: nothing claimed, worker commands stay PASS.
        obs2 = synthetic_observation(290, money=5000, seeds={"MELON": 6},
                                     hands=[])
        out = a4.apply_a4(obs2, empty_action(hands=0), enabled=True)
        self.assertEqual(out["hands"], [])

    def test_late_second_hire_gets_queue(self):
        # Hire 1 lands on step 290 -> crew [1], queues built for one worker.
        obs1 = synthetic_observation(289, money=5000, seeds={"MELON": 6})
        a4.apply_a4(obs1, empty_action(), enabled=True)
        obs2 = synthetic_observation(290, money=5000, seeds={"MELON": 6},
                                     hands=[[6, 6]])
        out2 = a4.apply_a4(obs2, empty_action(hands=1), enabled=True)
        self.assertNotEqual(out2["hands"][0], ["PASS"])
        # Hire 2 lands a step later -> crew grows mid-day; queues rebuild so
        # the second worker is not left idle.
        obs3 = synthetic_observation(291, money=5000, seeds={"MELON": 6},
                                     hands=[[6, 6], [6, 5]])
        out3 = a4.apply_a4(obs3, empty_action(hands=2), enabled=True)
        self.assertNotEqual(out3["hands"][1], ["PASS"])


class WorkerProgramTests(unittest.TestCase):
    def setUp(self):
        a4.reset()

    def tearDown(self):
        a4.reset()

    def _crew_on_tile(self, step, x, y, seeds, tiles_fn=None):
        # Two calls: hire, then crew detected with the worker standing on (x, y).
        obs1 = synthetic_observation(step, money=5000, seeds=seeds)
        a4.apply_a4(obs1, empty_action(), enabled=True)
        obs2 = synthetic_observation(step + 1, money=5000, seeds=seeds,
                                     hands=[[x, y]], tile_fn=tiles_fn)
        return a4.apply_a4(obs2, empty_action(hands=1), enabled=True)

    def test_walks_to_assigned_tile(self):
        out = self._crew_on_tile(289, 6, 6, {"MELON": 6})
        # Worker at (6,6); first assigned tile is (3,3) -> walks WEST.
        self.assertEqual(out["hands"][0], ["WEST"])

    def test_plant_then_water_sequence(self):
        # Worker standing exactly on its assigned tile plants immediately.
        a4.reset()
        obs1 = synthetic_observation(289, money=5000, seeds={"MELON": 6})
        a4.apply_a4(obs1, empty_action(), enabled=True)
        # Force the assigned tile: only one free tile on the whole board.
        def one_tile(x, y, cur):
            if (x, y) == (3, 3):
                return None
            return "LOCKED"
        obs2 = synthetic_observation(290, money=5000, seeds={"MELON": 6},
                                     hands=[[3, 3]], tile_fn=one_tile)
        out = a4.apply_a4(obs2, empty_action(hands=1), enabled=True)
        self.assertEqual(out["hands"][0], ["PLANT", "MELON"])

    def test_waters_unwatered_melon(self):
        def tiles(x, y, cur):
            if (x, y) == (3, 3):
                return melon_tile(12, watered=False, yield_units=1)
            return cur
        out = self._crew_on_tile(13 * 24 + 1, 3, 3, {"MELON": 0}, tiles_fn=tiles)
        # Day 13: watering program; the only melon tile is under the worker.
        self.assertEqual(out["hands"][0], ["WATER"])

    def test_skips_already_watered_tile(self):
        def tiles(x, y, cur):
            if (x, y) == (3, 3):
                return melon_tile(12, watered=True, yield_units=2)
            return cur
        out = self._crew_on_tile(13 * 24 + 1, 3, 3, {"MELON": 0}, tiles_fn=tiles)
        self.assertEqual(out["hands"][0], ["PASS"])

    def test_harvest_age_gate(self):
        def tiles(x, y, cur):
            if (x, y) == (3, 3):
                return melon_tile(12, watered=True, yield_units=6)
            return cur
        # Day 21 (age 9): no harvest, only water -> already watered -> PASS.
        out = self._crew_on_tile(21 * 24 + 1, 3, 3, {"MELON": 0}, tiles_fn=tiles)
        self.assertEqual(out["hands"][0], ["PASS"])
        # Day 22 (age 10): harvest.
        a4.reset()
        out = self._crew_on_tile(22 * 24 + 1, 3, 3, {"MELON": 0}, tiles_fn=tiles)
        # Water first (already watered) then harvest.
        self.assertEqual(out["hands"][0], ["HARVEST"])

    def test_place_at_shed(self):
        # Harvestable melon ON the shed tile: harvest fires, then PLACE.
        def tiles(x, y, cur):
            if (x, y) == (4, 4):
                return melon_tile(12, watered=True, yield_units=6)
            return cur
        a4.reset()
        obs1 = synthetic_observation(22 * 24 + 1, money=5000, seeds={})
        a4.apply_a4(obs1, empty_action(), enabled=True)
        obs2 = synthetic_observation(22 * 24 + 2, money=5000, seeds={},
                                     hands=[[4, 4]], tile_fn=tiles)
        out = a4.apply_a4(obs2, empty_action(hands=1), enabled=True)
        self.assertEqual(out["hands"][0], ["HARVEST"])
        # Next step: tile harvested, melons in hand, standing on the shed tile.
        def no_tiles(x, y, cur):
            return "LOCKED"
        obs3 = synthetic_observation(
            22 * 24 + 3, money=5000, seeds={}, hands=[[4, 4]],
            inventories=[{}, {"MELON": 6}], tile_fn=no_tiles)
        out = a4.apply_a4(obs3, empty_action(hands=1), enabled=True)
        self.assertEqual(out["hands"][0], ["PLACE", "MELON", 6])


class WiringTests(unittest.TestCase):
    def setUp(self):
        a4.reset()

    def tearDown(self):
        r04.install()  # restore published defaults
        r04.A4_SECOND_MELONS = False
        r04.A4_MELON_COUNT = a4.DEFAULT_COUNT
        r04.A4_PLANT_DAY = a4.DEFAULT_PLANT_DAY
        a4.reset()

    def test_a4_defaults_off(self):
        self.assertFalse(r04.A4_SECOND_MELONS)

    def test_install_wires_a4_params(self):
        r04.install(a4_second_melons=True, a4_melon_count=8, a4_plant_day=11)
        self.assertTrue(r04.A4_SECOND_MELONS)
        self.assertEqual(r04.A4_MELON_COUNT, 8)
        self.assertEqual(r04.A4_PLANT_DAY, 11)

    def test_install_rejects_negative_count(self):
        with self.assertRaises(ValueError):
            r04.install(a4_melon_count=-1)

    def test_install_rejects_bad_day(self):
        with self.assertRaises(ValueError):
            r04.install(a4_plant_day=99)

    def test_install_without_a4_keeps_defaults(self):
        r04.install(a4_second_melons=True)
        self.assertEqual(r04.A4_MELON_COUNT, a4.DEFAULT_COUNT)
        self.assertEqual(r04.A4_PLANT_DAY, a4.DEFAULT_PLANT_DAY)

    def test_reset_clears_state(self):
        obs = synthetic_observation(289, money=5000, seeds={"MELON": 6})
        a4.apply_a4(obs, empty_action(), enabled=True)
        self.assertTrue(a4._STATES)
        a4.reset()
        self.assertFalse(a4._STATES)
        self.assertEqual(a4.REPORT["seeds_bought"], 0)


if __name__ == "__main__":
    unittest.main()
