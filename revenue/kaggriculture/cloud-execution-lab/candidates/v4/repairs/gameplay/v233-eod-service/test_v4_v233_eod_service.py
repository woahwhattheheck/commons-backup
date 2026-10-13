# SPDX-License-Identifier: Apache-2.0
"""Focused contracts for current-ABI V4 ``r04_v233_eod_service``.

Run after materializing this package beside the canonical candidate router:

    python -B -m unittest -v checks/test_v4_v233_eod_service.py
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_v233_eod_service as lane  # noqa: E402

CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
    "farmHandCostMult": 1,
}
STEP = 12 * 24 + 23
_DEFAULT_CONFIG = object()


def sheep(*, fed=False, cared=False):
    return {
        "kind": "PASTURE",
        "animal": "SHEEP",
        "placed_day": 10,
        "yield_units": 0,
        "consecutive_unfed": 0,
        "fed_today": fed,
        "cared_today": cared,
        "fertilizer_available": False,
        "pending_care_bonus": 0,
    }


def fixture(
    *,
    step=STEP,
    position=(3, 4),
    inventory=None,
    shed=None,
    fed=False,
    cared=False,
    farmer_position=(4, 4),
):
    inventory = copy.deepcopy(
        inventory if inventory is not None else {"WOOL": 2, "WHEAT": 1}
    )
    shed = copy.deepcopy(shed if shed is not None else {})
    tiles = [[None for _ in range(10)] for _ in range(10)]
    x, y = position
    tiles[y][x] = sheep(fed=fed, cared=cared)
    farm = {
        "tiles": tiles,
        "farmer": list(farmer_position),
        "hands": [list(position)],
        "money": 1000,
        "unlocked_quadrants": ["NW", "NE", "SW"],
        "hires_today": 1,
    }
    other = copy.deepcopy(farm)
    observation = {
        "step": step,
        "day": step // 24,
        "hour": step % 24,
        "player": 0,
        "farms": [farm, other],
        "private": {
            "inventories": [{}, copy.deepcopy(inventory)],
            "shed": copy.deepcopy(shed),
            "seeds": {},
        },
    }
    expected = lane._return_move(list(position), inventory)
    action = {"farmer": ["PASS"], "hands": [copy.deepcopy(expected)], "market": []}
    state = {
        "last_step": step,
        "day": step // 24,
        "workers": {1: [tuple(position)]},
        "work": {
            1: {
                "step": step,
                "command": copy.deepcopy(expected),
                "inventory": copy.deepcopy(inventory),
            }
        },
        "credit": {"WOOL": 0, "FERTILIZER": 0},
        "committed": True,
    }
    return action, observation, state


class V233EodService(unittest.TestCase):
    def setUp(self):
        self.saved_states = r04._V233_STATES
        r04._V233_STATES = {}

    def tearDown(self):
        r04._V233_STATES = self.saved_states

    def run_case(
        self,
        action,
        observation,
        state,
        *,
        enabled=True,
        configuration=_DEFAULT_CONFIG,
    ):
        r04._V233_STATES[0] = state
        resolved = dict(CONFIG) if configuration is _DEFAULT_CONFIG else configuration
        return lane.apply_v233_eod_service(
            action,
            observation,
            resolved,
            enabled=enabled,
        )

    def test_hour23_return_move_becomes_same_tile_feed(self):
        action, observation, state = fixture()
        original = copy.deepcopy(action)
        result = self.run_case(action, observation, state)
        self.assertIsNot(result, action)
        self.assertEqual(result["hands"], [["FEED"]])
        self.assertEqual(action, original)
        self.assertEqual(state["work"][1]["command"], ["FEED"])

    def test_hour23_return_move_becomes_care_when_already_fed(self):
        action, observation, state = fixture(
            inventory={"FERTILIZER": 2}, fed=True, cared=False
        )
        result = self.run_case(action, observation, state)
        self.assertEqual(result["hands"], [["CARE"]])
        self.assertEqual(state["work"][1]["command"], ["CARE"])

    def test_enabled_must_be_literal_true(self):
        for enabled in ("true", 1, 1.0, [True], {"enabled": True}, None):
            with self.subTest(enabled=enabled):
                action, observation, state = fixture()
                before = copy.deepcopy(action)
                result = self.run_case(
                    action, observation, state, enabled=enabled
                )
                self.assertIs(result, action)
                self.assertEqual(action, before)
                self.assertEqual(state["work"][1]["command"], action["hands"][0])

    def test_missing_or_nonstandard_configuration_fails_closed(self):
        cases = [None, {"episodeSteps": 720}]
        for missing in lane.STANDARD_CONFIG:
            config = dict(CONFIG)
            del config[missing]
            cases.append(config)
        cases += [
            dict(CONFIG, turnsPerDay="24"),
            dict(CONFIG, boardSize=True),
            dict(CONFIG, shedCapacity=99),
        ]
        for configuration in cases:
            with self.subTest(configuration=configuration):
                action, observation, state = fixture()
                self.assertIs(
                    self.run_case(
                        action,
                        observation,
                        state,
                        configuration=configuration,
                    ),
                    action,
                )

    def test_committed_same_callback_v233_state_is_required(self):
        for mutation in (
            ("committed", False),
            ("committed", "true"),
            ("last_step", STEP - 1),
            ("day", STEP // 24 - 1),
        ):
            with self.subTest(mutation=mutation):
                action, observation, state = fixture()
                state[mutation[0]] = mutation[1]
                self.assertIs(self.run_case(action, observation, state), action)

    def test_worker_must_be_assigned_to_current_sheep_site(self):
        action, observation, state = fixture()
        state["workers"][1] = [(6, 6)]
        self.assertIs(self.run_case(action, observation, state), action)

    def test_parent_must_match_v233_same_call_return_move(self):
        action, observation, state = fixture()
        action["hands"][0] = ["PASS"]
        self.assertIs(self.run_case(action, observation, state), action)

        action, observation, state = fixture()
        state["work"][1]["command"] = ["PASS"]
        self.assertIs(self.run_case(action, observation, state), action)

    def test_no_cargo_or_no_service_preserves_identity(self):
        action, observation, state = fixture(inventory={"WHEAT": 1})
        self.assertIs(self.run_case(action, observation, state), action)

        action, observation, state = fixture(
            inventory={"WOOL": 2}, fed=False, cared=False
        )
        self.assertIs(self.run_case(action, observation, state), action)

        action, observation, state = fixture(
            inventory={"WOOL": 2}, fed=True, cared=True
        )
        self.assertIs(self.run_case(action, observation, state), action)

    def test_only_nonfinal_hour23_is_eligible(self):
        for step in (12 * 24 + 22, 13 * 24, 29 * 24 + 23):
            with self.subTest(step=step):
                action, observation, state = fixture(step=step)
                self.assertIs(self.run_case(action, observation, state), action)

    def test_strict_sheep_snapshot_fails_closed(self):
        mutations = (
            ("kind", "COOP"),
            ("animal", "COW"),
            ("placed_day", "10"),
            ("yield_units", 0.0),
            ("yield_units", 7),
            ("consecutive_unfed", True),
            ("fed_today", 0),
            ("cared_today", 1),
            ("fertilizer_available", "false"),
            ("pending_care_bonus", 0.0),
        )
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                action, observation, state = fixture()
                observation["farms"][0]["tiles"][4][3][key] = value
                self.assertIs(self.run_case(action, observation, state), action)

    def test_capacity_upper_bound_blocks_eod_discard(self):
        action, observation, state = fixture(shed={"MILK": 98})
        self.assertIs(self.run_case(action, observation, state), action)

        action, observation, state = fixture(shed={"MILK": 97})
        result = self.run_case(action, observation, state)
        self.assertEqual(result["hands"], [["FEED"]])

    def test_other_actor_harvest_is_in_capacity_bound(self):
        action, observation, state = fixture(
            shed={"MILK": 94}, farmer_position=(2, 2)
        )
        observation["farms"][0]["tiles"][2][2] = {
            "kind": "PLANT",
            "crop": "WHEAT",
            "yield_units": 4,
        }
        action["farmer"] = ["HARVEST"]
        self.assertIs(self.run_case(action, observation, state), action)

    def test_collect_fertilizer_is_in_capacity_bound(self):
        action, observation, state = fixture(shed={"MILK": 97})
        action["farmer"] = ["COLLECT_FERTILIZER"]
        self.assertIs(self.run_case(action, observation, state), action)

    def test_executable_market_physical_inflow_blocks(self):
        for order in (
            ["BUY_PRODUCT", "WHEAT", 1],
            ["BUY_ANIMAL", "SHEEP", 1],
        ):
            with self.subTest(order=order):
                action, observation, state = fixture()
                action["market"] = [order]
                self.assertIs(self.run_case(action, observation, state), action)

    def test_buy_seed_is_nonphysical_and_does_not_block(self):
        action, observation, state = fixture()
        action["market"] = [["BUY_SEED", "WHEAT", 1]]
        result = self.run_case(action, observation, state)
        self.assertEqual(result["hands"], [["FEED"]])

    def test_market_suffix_beyond_official_order_cap_is_ignored(self):
        action, observation, state = fixture()
        action["market"] = [["SELL", "WOOL", 1] for _ in range(10)]
        action["market"].append(["BUY_PRODUCT", "WHEAT", 1])
        result = self.run_case(action, observation, state)
        self.assertEqual(result["hands"], [["FEED"]])

    def test_stacked_active_worker_blocks_ordering_ambiguity(self):
        action, observation, state = fixture(farmer_position=(3, 4))
        action["farmer"] = ["CARE"]
        self.assertIs(self.run_case(action, observation, state), action)

    def test_hidden_extra_actor_or_inventory_fails_closed(self):
        action, observation, state = fixture()
        observation["farms"][0]["hands"].append([2, 2])
        observation["private"]["inventories"].append({"FERTILIZER": 1})
        self.assertIs(self.run_case(action, observation, state), action)

    def test_malformed_inventory_fails_closed(self):
        for inventory in (
            {"WOOL": True, "WHEAT": 1},
            {"WOOL": -1, "WHEAT": 1},
            {1: 2, "WHEAT": 1},
        ):
            with self.subTest(inventory=inventory):
                action, observation, state = fixture(inventory=inventory)
                self.assertIs(self.run_case(action, observation, state), action)

    def test_malformed_worker_target_fails_closed(self):
        action, observation, state = fixture()
        state["workers"][1] = [("3", 4)]
        self.assertIs(self.run_case(action, observation, state), action)

    def test_parent_identity_and_state_preserved_on_no_match(self):
        action, observation, state = fixture()
        observation["farms"][0]["tiles"][4][3]["fed_today"] = True
        observation["farms"][0]["tiles"][4][3]["cared_today"] = True
        before_action = copy.deepcopy(action)
        before_state = copy.deepcopy(state)
        result = self.run_case(action, observation, state)
        self.assertIs(result, action)
        self.assertEqual(action, before_action)
        self.assertEqual(state, before_state)


if __name__ == "__main__":
    unittest.main()
