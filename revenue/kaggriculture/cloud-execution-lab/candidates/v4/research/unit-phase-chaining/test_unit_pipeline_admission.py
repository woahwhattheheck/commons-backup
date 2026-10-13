#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import unittest

from unit_phase_chaining import ENGINE_GIT_BLOB as SOURCE_ENGINE_GIT_BLOB
from unit_pipeline_admission import ENGINE_GIT_BLOB, reorder_unit_pipeline


def observation(tile, *, hands=1, seeds=None, positions=None):
    board = [[None for _ in range(10)] for _ in range(10)]
    board[4][4] = deepcopy(tile)
    if positions is None:
        positions = [[4, 4] for _ in range(hands + 1)]
    farm = {
        "tiles": board,
        "farmer": list(positions[0]),
        "hands": [list(p) for p in positions[1:]],
    }
    return {
        "player": 0,
        "farms": [farm],
        "private": {"seeds": dict(seeds or {})},
    }


def plant_rows(action):
    rows = [action["farmer"], *action["hands"]]
    return sorted(tuple(row) for row in rows if isinstance(row, list) and row and row[0] == "PLANT")


class UnitPipelineAdmissionTests(unittest.TestCase):
    def test_engine_pin_is_shared_with_source_oracle(self):
        self.assertEqual(SOURCE_ENGINE_GIT_BLOB, ENGINE_GIT_BLOB)

    def test_disabled_is_exact_action_identity(self):
        obs = observation(None, hands=1, seeds={"STRAWBERRY": 1})
        action = {
            "farmer": ["WATER"],
            "hands": [["PLANT", "STRAWBERRY"]],
            "market": [["HIRE"]],
            "other": {"keep": True},
        }
        got, report = reorder_unit_pipeline(obs, action, enabled=False)
        self.assertEqual(action, got)
        self.assertFalse(report["changed"])
        self.assertEqual(1, report["refusals"]["disabled"])

    def test_missing_unit_rows_preserves_shape(self):
        obs = observation(None, hands=1, seeds={"WHEAT": 1})
        action = {"market": [["BUY_SEED", "WHEAT", 1]]}
        got, report = reorder_unit_pipeline(obs, action, enabled=True)
        self.assertEqual(action, got)
        self.assertFalse(report["changed"])
        self.assertEqual(1, report["refusals"]["missing_unit_rows"])

    def test_empty_tile_reorders_existing_plant_then_water(self):
        obs = observation(None, hands=1, seeds={"STRAWBERRY": 1})
        action = {
            "farmer": ["WATER"],
            "hands": [["PLANT", "STRAWBERRY"]],
            "market": [["BUY_PRODUCT", "WHEAT", 2]],
        }
        got, report = reorder_unit_pipeline(obs, action, enabled=True)
        self.assertEqual(["PLANT", "STRAWBERRY"], got["farmer"])
        self.assertEqual([["WATER"]], got["hands"])
        self.assertEqual(action["market"], got["market"])
        self.assertEqual(plant_rows(action), plant_rows(got))
        self.assertTrue(report["changed"])
        self.assertEqual(1, report["changed_groups"])

    def test_weed_chain_reorders_existing_dig_plant_water(self):
        obs = observation({"kind": "WEED"}, hands=2, seeds={"TOMATO": 1})
        action = {
            "farmer": ["WATER"],
            "hands": [["PLANT", "TOMATO"], ["DIG"]],
            "market": [],
        }
        got, report = reorder_unit_pipeline(obs, action, enabled=True)
        self.assertEqual(["DIG"], got["farmer"])
        self.assertEqual([["PLANT", "TOMATO"], ["WATER"]], got["hands"])
        self.assertEqual(plant_rows(action), plant_rows(got))
        self.assertTrue(report["changed"])

    def test_different_positions_do_not_form_pipeline(self):
        obs = observation(None, hands=1, seeds={"WHEAT": 1}, positions=[[4, 4], [3, 4]])
        action = {"farmer": ["WATER"], "hands": [["PLANT", "WHEAT"]], "market": []}
        got, report = reorder_unit_pipeline(obs, action, enabled=True)
        self.assertEqual(action, got)
        self.assertFalse(report["changed"])

    def test_global_same_crop_seed_overshoot_refuses_local_reorder(self):
        obs = observation(None, hands=2, seeds={"WHEAT": 1}, positions=[[4, 4], [4, 4], [3, 4]])
        action = {
            "farmer": ["WATER"],
            "hands": [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]],
            "market": [],
        }
        got, report = reorder_unit_pipeline(obs, action, enabled=True)
        self.assertEqual(action, got)
        self.assertFalse(report["changed"])
        self.assertEqual(1, report["refusals"]["atomic_seed_collateral_unmet"])

    def test_inventory_or_service_dependent_group_refuses(self):
        obs = observation(None, hands=2, seeds={"WHEAT": 1})
        action = {
            "farmer": ["WATER"],
            "hands": [["PLANT", "WHEAT"], ["FEED"]],
            "market": [],
        }
        got, report = reorder_unit_pipeline(obs, action, enabled=True)
        self.assertEqual(action, got)
        self.assertFalse(report["changed"])
        self.assertEqual(1, report["refusals"]["noncanonical_or_impure_row"])

    def test_existing_live_plant_is_not_destroyed_for_reorder(self):
        tile = {
            "kind": "PLANT",
            "crop": "WHEAT",
            "planted_day": 0,
            "watered_today": False,
            "consecutive_unwatered": 0,
            "yield_units": 6,
            "max_lifespan_step": 200,
            "fertilized_until_day": -1,
        }
        obs = observation(tile, hands=1, seeds={"WHEAT": 1})
        action = {"farmer": ["PLANT", "WHEAT"], "hands": [["DIG"]], "market": []}
        got, report = reorder_unit_pipeline(obs, action, enabled=True)
        self.assertEqual(action, got)
        self.assertFalse(report["changed"])
        self.assertEqual(1, report["refusals"]["tile_not_safe_for_pipeline"])

    def test_already_causal_order_is_eligible_but_unchanged(self):
        obs = observation(None, hands=1, seeds={"WHEAT": 1})
        action = {"farmer": ["PLANT", "WHEAT"], "hands": [["WATER"]], "market": []}
        got, report = reorder_unit_pipeline(obs, action, enabled=True)
        self.assertEqual(action, got)
        self.assertEqual(1, report["eligible_groups"])
        self.assertEqual(0, report["changed_groups"])
        self.assertFalse(report["changed"])


if __name__ == "__main__":
    unittest.main()
