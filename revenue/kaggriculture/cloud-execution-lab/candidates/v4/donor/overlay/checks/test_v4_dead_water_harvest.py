# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_dead_water_harvest``."""
from __future__ import annotations

import copy
import unittest

import r04_dead_water_harvest as lane


def _tile(crop="WHEAT", planted_day=24, yield_units=3,
          watered_today=True, max_lifespan_step=696):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "yield_units": yield_units,
        "watered_today": watered_today,
        "max_lifespan_step": max_lifespan_step,
    }


def _board(tile):
    tiles = [[{"kind": "SOIL"} for _ in range(10)] for _ in range(10)]
    tiles[0][0] = tile
    return tiles


def _obs(tile, step=695, day=28, player=0):
    farm = {
        "farmer": [0, 0],
        "hands": [],
        "tiles": _board(tile),
    }
    return {
        "step": step,
        "day": day,
        "player": player,
        "farms": [farm, copy.deepcopy(farm)],
        "private": {"inventories": [{}], "shed": {}},
    }


def _action(command=None):
    return {"farmer": command or ["WATER"], "hands": [], "market": []}


def _config():
    return {
        "episodeSteps": 720,
        "turnsPerDay": 24,
        "boardSize": 10,
        "shedCapacity": 100,
    }


def _apply(observation, action, configuration=None, enabled=True):
    if configuration is None:
        configuration = _config()
    return lane.apply_dead_water_harvest(
        observation, action, configuration, enabled=enabled)


class DeadWaterHarvestTest(unittest.TestCase):
    def setUp(self):
        lane.reset()

    def test_already_watered_max_age_annual_recovers_harvest(self):
        out = _apply(_obs(_tile()), _action())
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(lane.get_report()["recovered"], 1)

    def test_mature_but_premax_annual_preserves_future_yield(self):
        tile = _tile(crop="WHEAT", planted_day=26, yield_units=3,
                     watered_today=True, max_lifespan_step=744)
        action = _action()
        out = _apply(_obs(tile), action)
        self.assertIs(out, action)
        self.assertEqual(lane.get_report()["future_yield_block"], 1)

    def test_already_watered_ongoing_crop_can_harvest_when_capacity_proven(self):
        tile = _tile(crop="TOMATO", planted_day=18, yield_units=2,
                     watered_today=True, max_lifespan_step=-1)
        out = _apply(_obs(tile), _action())
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(lane.get_report()["recovered"], 1)

    def test_hour23_full_shed_ongoing_crop_fails_closed(self):
        tile = _tile(crop="TOMATO", planted_day=18, yield_units=2,
                     watered_today=True, max_lifespan_step=-1)
        observation = _obs(tile)
        observation["private"] = {"inventories": [{}], "shed": {"WHEAT": 100}}
        action = _action()
        out = _apply(observation, action)
        self.assertIs(out, action)
        self.assertEqual(lane.get_report()["capacity_block"], 1)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_hour22_is_identity_even_with_room(self):
        tile = _tile(crop="TOMATO", planted_day=18, yield_units=2,
                     watered_today=True, max_lifespan_step=-1)
        action = _action()
        out = _apply(_obs(tile, step=694, day=28), action)
        self.assertIs(out, action)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_final_day_is_identity_without_delivery_theorem(self):
        tile = _tile(crop="TOMATO", planted_day=18, yield_units=2,
                     watered_today=True, max_lifespan_step=-1)
        action = _action()
        out = _apply(_obs(tile, step=719, day=29), action)
        self.assertIs(out, action)
        self.assertEqual(lane.get_report()["terminal_day_block"], 0)
        action2 = _action()
        out2 = _apply(_obs(tile, step=718, day=29), action2)
        self.assertIs(out2, action2)
        self.assertEqual(lane.get_report()["terminal_day_block"], 1)

    def test_unwatered_ongoing_negative_lifespan_sentinel_is_not_expiring(self):
        tile = _tile(crop="TOMATO", planted_day=18, yield_units=2,
                     watered_today=False, max_lifespan_step=-1)
        action = _action()
        out = _apply(_obs(tile), action)
        self.assertIs(out, action)
        self.assertEqual(lane.get_report()["expiring"], 0)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_expiring_unwatered_mature_plant_recovers_harvest(self):
        tile = _tile(crop="CARROT", planted_day=25, yield_units=4,
                     watered_today=False, max_lifespan_step=695)
        out = _apply(_obs(tile), _action())
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(lane.get_report()["expiring"], 1)

    def test_annual_yield_units_before_maturity_fails_closed(self):
        tile = _tile(crop="WHEAT", planted_day=28, yield_units=1,
                     watered_today=True, max_lifespan_step=792)
        action = _action()
        out = _apply(_obs(tile), action)
        self.assertIs(out, action)
        self.assertEqual(lane.get_report()["not_harvestable"], 1)

    def test_productive_water_is_untouched(self):
        tile = _tile(watered_today=False, max_lifespan_step=696)
        action = _action()
        self.assertIs(_apply(_obs(tile), action), action)

    def test_zero_yield_ongoing_crop_is_untouched(self):
        tile = _tile(crop="TOMATO", planted_day=18, yield_units=0,
                     watered_today=True, max_lifespan_step=-1)
        action = _action()
        self.assertIs(_apply(_obs(tile), action), action)

    def test_outside_window_and_disabled_are_identity(self):
        action = _action()
        self.assertIs(_apply(_obs(_tile(), step=671, day=27), action), action)
        self.assertIs(
            lane.apply_dead_water_harvest(_obs(_tile()), action, enabled=False),
            action,
        )

    def test_malformed_hands_bool_player_and_non_water_fail_closed(self):
        observation = _obs(_tile())
        observation["farms"][0]["farmer"] = [-1, 0]
        action = _action()
        self.assertIs(_apply(observation, action), action)

        pass_action = _action(["PASS"])
        self.assertIs(_apply(_obs(_tile()), pass_action), pass_action)

        bool_player = _action()
        self.assertIs(_apply(_obs(_tile(), player=True), bool_player), bool_player)

        malformed_hands = _action()
        malformed_hands["hands"] = (["WATER"],)
        self.assertIs(_apply(_obs(_tile()), malformed_hands), malformed_hands)

    def test_partial_actor_vectors_fail_closed(self):
        observation = _obs(_tile())
        observation["farms"][0]["hands"] = [[0, 0]]
        action = _action()
        self.assertIs(_apply(observation, action), action)

        observation = _obs(_tile())
        action = _action()
        action["hands"] = [["WATER"]]
        self.assertIs(_apply(observation, action), action)

    def test_nonvector_worker_position_fails_closed(self):
        observation = _obs(_tile())
        observation["farms"][0]["farmer"] = {0: "x", 1: "y"}
        action = _action()
        self.assertIs(_apply(observation, action), action)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_inconsistent_public_clock_fails_closed(self):
        action = _action()
        observation = _obs(_tile(), step=695, day=29)
        self.assertIs(_apply(observation, action), action)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_nonstandard_or_missing_configuration_fails_closed(self):
        observation = _obs(_tile())
        action = _action()
        self.assertIs(
            lane.apply_dead_water_harvest(observation, action, enabled=True),
            action,
        )
        for key, bad_value in (
            ("episodeSteps", 721),
            ("turnsPerDay", 25),
            ("boardSize", 11),
            ("shedCapacity", 101),
            ("turnsPerDay", True),
            ("shedCapacity", True),
        ):
            configuration = _config()
            configuration[key] = bad_value
            self.assertIs(_apply(observation, action, configuration=configuration), action)

    def test_attribute_configuration_matches_runtime_surface(self):
        class Configuration:
            episodeSteps = 720
            turnsPerDay = 24
            boardSize = 10
            shedCapacity = 100

        out = lane.apply_dead_water_harvest(
            _obs(_tile()), _action(), Configuration(), enabled=True)
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(lane.get_report()["recovered"], 1)

    def test_stacked_actor_candidate_fails_closed(self):
        observation = _obs(_tile())
        observation["farms"][0]["hands"] = [[0, 0]]
        action = _action()
        action["hands"] = [["HARVEST"]]
        self.assertIs(_apply(observation, action), action)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_malformed_inactive_actor_blocks_partial_mutation(self):
        observation = _obs(_tile())
        observation["farms"][0]["hands"] = [[99, 99]]
        action = _action()
        action["hands"] = [["PASS"]]
        self.assertIs(_apply(observation, action), action)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_malformed_sibling_command_blocks_partial_mutation(self):
        observation = _obs(_tile())
        observation["farms"][0]["hands"] = [[1, 0]]
        action = _action()
        action["hands"] = ["PASS"]
        self.assertIs(_apply(observation, action), action)
        self.assertEqual(lane.get_report()["recovered"], 0)

    def test_full_board_shape_is_required(self):
        observation = _obs(_tile())
        observation["farms"][0]["tiles"] = [[_tile()]]
        action = _action()
        self.assertIs(_apply(observation, action), action)

        observation = _obs(_tile())
        observation["farms"][0]["tiles"][9] = [{"kind": "SOIL"}] * 9
        action = _action()
        self.assertIs(_apply(observation, action), action)

    def test_existing_market_shed_inflow_blocks_rewrite(self):
        observation = _obs(_tile(crop="TOMATO", planted_day=18,
                                     yield_units=2, max_lifespan_step=-1))
        action = _action()
        action["market"] = [["BUY_PRODUCT", "WHEAT", 1]]
        self.assertIs(_apply(observation, action), action)
        self.assertEqual(lane.get_report()["capacity_block"], 1)

    def test_existing_sell_is_conservatively_safe(self):
        observation = _obs(_tile(crop="TOMATO", planted_day=18,
                                     yield_units=2, max_lifespan_step=-1))
        action = _action()
        action["market"] = [["SELL", "WHEAT", 1]]
        out = _apply(observation, action)
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(out["market"], action["market"])

    def test_sibling_harvest_inflow_is_included_in_capacity_bound(self):
        tile = _tile(crop="TOMATO", planted_day=18, yield_units=2,
                     max_lifespan_step=-1)
        observation = _obs(tile)
        observation["farms"][0]["hands"] = [[1, 0]]
        observation["farms"][0]["tiles"][0][1] = {
            "kind": "PLANT", "crop": "TOMATO", "planted_day": 18,
            "yield_units": 99, "watered_today": True,
            "max_lifespan_step": -1,
        }
        observation["private"]["inventories"] = [{}, {}]
        action = _action()
        action["hands"] = [["HARVEST"]]
        self.assertIs(_apply(observation, action), action)
        self.assertEqual(lane.get_report()["capacity_block"], 1)

    def test_current_carried_inventory_is_included_in_capacity_bound(self):
        tile = _tile(crop="TOMATO", planted_day=18, yield_units=2,
                     max_lifespan_step=-1)
        observation = _obs(tile)
        observation["private"] = {
            "inventories": [{"WHEAT": 9}],
            "shed": {"CARROT": 90},
        }
        action = _action()
        self.assertIs(_apply(observation, action), action)
        self.assertEqual(lane.get_report()["capacity_block"], 1)

    def test_market_rows_are_strict_before_water_to_harvest_mutation(self):
        observation = _obs(_tile())
        malformed = (
            [[]],
            [["SELL"]],
            [["SELL", "WHEAT"]],
            [["SELL", "WHEAT", 0]],
            [["SELL", "WHEAT", True]],
            [["SELL", "UNKNOWN", 1]],
            [["BUY_SEED"]],
            [["BUY_SEED", "TOMATO", -1]],
            [["BUY_SEED", "EGG", 1]],
            [["HIRE", "junk"]],
            [["BUY_LAND", 1]],
        )
        for market in malformed:
            with self.subTest(market=market):
                action = _action()
                action["market"] = copy.deepcopy(market)
                self.assertIs(_apply(observation, action), action)

        safe = (
            [["SELL", "WHEAT", 1]],
            [["HIRE"]],
            [["BUY_LAND"]],
            [["BUY_SEED", "TOMATO", 1]],
        )
        for market in safe:
            with self.subTest(market=market):
                action = _action()
                action["market"] = copy.deepcopy(market)
                out = _apply(observation, action)
                self.assertEqual(out["farmer"], ["HARVEST"])
                self.assertEqual(out["market"], action["market"])


if __name__ == "__main__":
    unittest.main()
