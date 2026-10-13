# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_v233_eod_service``."""
from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_v233_eod_service as lane  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


class ConfigObject:
    pass


def _tile(*, fed=False, cared=False):
    return {"kind": "PASTURE", "animal": "SHEEP", "placed_day": 10,
            "yield_units": 0, "consecutive_unfed": 0,
            "fed_today": fed, "cared_today": cared,
            "fertilizer_available": False, "pending_care_bonus": 0}


def _fixture(*, step=311, position=(3, 4), inventory=None, shed=None,
             fed=False, cared=False, farmer_position=(4, 4)):
    inventory = copy.deepcopy(inventory if inventory is not None else {"WOOL": 2, "WHEAT": 1})
    shed = copy.deepcopy(shed if shed is not None else {})
    tiles = [[None for _ in range(10)] for _ in range(10)]
    x, y = position
    tiles[y][x] = _tile(fed=fed, cared=cared)
    farm = {"tiles": tiles, "farmer": list(farmer_position), "hands": [list(position)],
            "money": 1000, "unlocked_quadrants": ["NW", "NE", "SW"], "hires_today": 1}
    other = copy.deepcopy(farm)
    obs = {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
           "farms": [farm, other],
           "private": {"inventories": [{}, inventory], "shed": shed, "seeds": {}},
           "market": {"prices": {p: 10 for p in r04.PRODUCTS},
                      "inventory": {p: 10000 for p in r04.PRODUCTS}},
           "town": {"unlocked_shops": []}}
    expected = lane._return_move(list(position), inventory)
    action = {"farmer": ["PASS"], "hands": [copy.deepcopy(expected)], "market": []}
    r04._V233_STATES[0] = {
        "last_step": step, "day": step // 24,
        "workers": {1: [tuple(position)]},
        "work": {1: {"step": step, "command": copy.deepcopy(expected),
                      "inventory": copy.deepcopy(inventory)}},
        "credit": {"WOOL": 0, "FERTILIZER": 0},
    }
    return obs, action


def _router_smoke_observation(step=0):
    tiles = [["LOCKED"] * 10 for _ in range(10)]
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": 1000,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}], "shed": {}, "seeds": {}},
            "market": {"prices": {p: 10 for p in r04.PRODUCTS},
                       "inventory": {p: 10000 for p in r04.PRODUCTS}},
            "town": {"unlocked_shops": []}}


class V233EodService(unittest.TestCase):
    def tearDown(self):
        r04._V233_STATES.pop(0, None)
        if hasattr(r04, "V233_EOD_SERVICE"):
            r04.V233_EOD_SERVICE = False

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_v233_eod_service"], False)
        self.assertIs(Features(**data).r04_v233_eod_service, False)

    def test_full_actor_seam_is_outer_of_fert_hand(self):
        stack_source = inspect.getsource(r04._v3_stack)
        outer_source = inspect.getsource(r04.v3_agent)
        self.assertNotIn("V233_EOD_SERVICE", stack_source)
        self.assertIn("V233_EOD_SERVICE", outer_source)
        self.assertIn("apply_v233_eod_service", outer_source)

    def test_hour23_return_move_becomes_same_tile_feed(self):
        obs, parent = _fixture()
        original = copy.deepcopy(parent)
        out = lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True)
        self.assertIsNot(out, parent)
        self.assertEqual(out["hands"], [["FEED"]])
        self.assertEqual(parent, original)
        self.assertEqual(r04._V233_STATES[0]["work"][1]["command"], ["FEED"])

    def test_struct_configuration_matches_live_path(self):
        obs, parent = _fixture()
        cfg = ConfigObject()
        for name, value in CONFIG.items():
            setattr(cfg, name, value)
        out = lane.apply_v233_eod_service(parent, obs, cfg, enabled=True)
        self.assertEqual(out["hands"], [["FEED"]])

    def test_hour23_return_move_becomes_care_only_when_already_fed(self):
        obs, parent = _fixture(inventory={"FERTILIZER": 2}, fed=True, cared=False)
        out = lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True)
        self.assertEqual(out["hands"], [["CARE"]])

    def test_rescue_feed_validates_refresh_fields_baseline_escape_can_skip(self):
        poisoned = {
            "placed_day": "10",
            "yield_units": "0",
            "consecutive_unfed": "1",
            "fertilizer_available": "false",
            "pending_care_bonus": "0",
        }
        for field, value in poisoned.items():
            obs, parent = _fixture()
            tile = obs["farms"][0]["tiles"][4][3]
            tile["consecutive_unfed"] = 1
            tile[field] = value
            with self.subTest(field=field):
                self.assertIs(
                    lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True),
                    parent,
                )

    def test_hungry_without_wheat_is_not_care_salvage(self):
        obs, parent = _fixture(inventory={"WOOL": 2}, fed=False, cared=False)
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)

    def test_parent_must_be_exact_v233_return_move(self):
        obs, parent = _fixture()
        parent["hands"][0] = ["PASS"]
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)

    def test_shed_adjacent_place_is_never_rewritten(self):
        obs, parent = _fixture(position=(4, 4))
        parent["hands"][0] = ["PLACE", "WOOL", 2]
        r04._V233_STATES[0]["work"][1]["command"] = ["PLACE", "WOOL", 2]
        out = lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True)
        self.assertIs(out, parent)
        self.assertEqual(out["hands"], [["PLACE", "WOOL", 2]])

    def test_hidden_extra_hand_is_visible_to_stack_guard(self):
        obs, parent = _fixture()
        obs["farms"][0]["hands"].append([3, 4])
        obs["private"]["inventories"].append({"FERTILIZER": 1})
        parent["hands"].append(["FERTILIZE"])
        out = lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True)
        self.assertIs(out, parent)

    def test_hidden_extra_hand_inventory_is_in_capacity_bound(self):
        obs, parent = _fixture(shed={"MILK": 96})
        obs["farms"][0]["hands"].append([2, 2])
        obs["private"]["inventories"].append({"FERTILIZER": 2})
        parent["hands"].append(["PASS"])
        out = lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True)
        self.assertIs(out, parent)  # 96 shed + 3 candidate inventory + 2 extra-hand inventory > 100.

    def test_no_cargo_no_activation(self):
        obs, parent = _fixture(inventory={"WHEAT": 1})
        parent["hands"][0] = ["PASS"]
        r04._V233_STATES[0]["work"][1]["command"] = ["PASS"]
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)

    def test_only_nonfinal_hour23_is_eligible(self):
        for step in (287, 310, 719):
            obs, parent = _fixture(step=step)
            with self.subTest(step=step):
                self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)

    def test_capacity_upper_bound_blocks_eod_discard(self):
        obs, parent = _fixture(shed={"MILK": 98})
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)
        obs, parent = _fixture(shed={"MILK": 97})
        out = lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True)
        self.assertEqual(out["hands"], [["FEED"]])

    def test_same_turn_market_inflow_blocks(self):
        obs, parent = _fixture()
        parent["market"] = [["BUY_PRODUCT", "WHEAT", 1]]
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)

    def test_other_actor_current_harvest_is_in_capacity_bound(self):
        obs, parent = _fixture(shed={"MILK": 94}, farmer_position=(2, 2))
        obs["farms"][0]["tiles"][2][2] = {"kind": "PLANT", "crop": "WHEAT", "yield_units": 4}
        parent["farmer"] = ["HARVEST"]
        out = lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True)
        self.assertIs(out, parent)  # 94 shed + 3 carried + 4 possible harvest > 100

    def test_stacked_active_worker_blocks_ordering_ambiguity(self):
        obs, parent = _fixture(farmer_position=(3, 4))
        parent["farmer"] = ["CARE"]
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)

    def test_nonstandard_or_inconsistent_clock_fails_closed(self):
        obs, parent = _fixture()
        bad = dict(CONFIG, episodeSteps=696)
        self.assertIs(lane.apply_v233_eod_service(parent, obs, bad, enabled=True), parent)
        obs["day"] += 1
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)

    def test_bool_player_and_partial_actor_vectors_fail_closed(self):
        obs, parent = _fixture()
        obs["player"] = True
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)
        obs, parent = _fixture()
        parent["hands"] = []
        self.assertIs(lane.apply_v233_eod_service(parent, obs, dict(CONFIG), enabled=True), parent)

    def test_install_and_titan_diagnostics_carry_key(self):
        r04.install(v233_eod_service=True)
        self.assertIs(r04.V233_EOD_SERVICE, True)
        r04.install(v233_eod_service=False)
        self.assertIs(r04.V233_EOD_SERVICE, False)

        agent = TitanAgent(Features(r04_sale_window=True, r04_v233_eod_service=True))
        agent.act(_router_smoke_observation(), dict(CONFIG))
        self.assertIs(r04.V233_EOD_SERVICE, True)
        self.assertIs(agent.diagnostics["v233_eod_service"], True)


if __name__ == "__main__":
    unittest.main()
