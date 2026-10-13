# SPDX-License-Identifier: Apache-2.0
"""Canonical-name and focused behavior checks for V4 H3e cow-feed recycle."""
from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

import r04_full_router as r04
import r04_h3e_cow_feed_recycle as lane
from titan_runtime import Features

CFG = {
    "episodeSteps": 720,
    "boardSize": 10,
    "turnsPerDay": 24,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


def _cow(**overrides):
    tile = {
        "kind": "PASTURE",
        "animal": "COW",
        "placed_day": 0,
        "yield_units": 0,
        "consecutive_unfed": 1,
        "fed_today": False,
        "cared_today": True,
        "fertilizer_available": False,
        "pending_care_bonus": 0,
    }
    tile.update(overrides)
    return tile


def _obs(tile=None, *, step=695, farmer=(0, 0), hands=None, inventories=None):
    hands = hands or []
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[farmer[1]][farmer[0]] = tile
    farm0 = {"farmer": list(farmer), "hands": [list(p) for p in hands], "tiles": tiles}
    farm1 = {"farmer": [0, 0], "hands": [], "tiles": [[None for _ in range(10)] for _ in range(10)]}
    if inventories is None:
        inventories = [{"WHEAT": 1}, *({} for _ in hands)]
    return {
        "step": step,
        "player": 0,
        "farms": [farm0, farm1],
        "private": {"inventories": inventories},
    }


def _action(farmer=None, hands=None):
    return {"farmer": farmer or ["CARE"], "hands": hands or [], "market": []}


class H3eCanonicalNameAndBehavior(unittest.TestCase):
    def setUp(self):
        lane.telemetry.clear()

    def tearDown(self):
        if hasattr(r04, "H3E_COW_FEED_RECYCLE"):
            r04.H3E_COW_FEED_RECYCLE = False

    def test_key_ships_off_and_feature_accepts_it(self):
        with open("TITAN-CONFIG.json", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertIs(data["r04_h3e_cow_feed_recycle"], False)
        self.assertIs(Features(**data).r04_h3e_cow_feed_recycle, False)

    def test_router_uses_key_derived_name_only(self):
        self.assertTrue(hasattr(r04, "H3E_COW_FEED_RECYCLE"))
        self.assertFalse(hasattr(r04, "COW_FEED_RECYCLE"))
        r04.install(h3e_cow_feed_recycle=True)
        self.assertIs(r04.H3E_COW_FEED_RECYCLE, True)

    def test_dead_care_recycles_into_feed_without_mutating_parent(self):
        action = _action(["CARE"])
        before = copy.deepcopy(action)
        out = lane.apply_cow_feed_recycle(action, _obs(_cow()), CFG, enabled=True)
        self.assertEqual(out["farmer"], ["FEED"])
        self.assertEqual(action, before)
        self.assertEqual(lane.telemetry["recycled_care"], 1)
        self.assertEqual(lane.telemetry["escape_risk_cows_fed"], 1)

    def test_disabled_and_non_eod_are_identity(self):
        action = _action(["CARE"])
        self.assertIs(lane.apply_cow_feed_recycle(action, _obs(_cow()), CFG), action)
        self.assertIs(
            lane.apply_cow_feed_recycle(action, _obs(_cow(), step=694), CFG, enabled=True),
            action,
        )

    def test_productive_service_is_never_stolen(self):
        for tile, command in (
            (_cow(cared_today=False), ["CARE"]),
            (_cow(yield_units=2), ["HARVEST"]),
            (_cow(fertilizer_available=True), ["COLLECT_FERTILIZER"]),
        ):
            action = _action(command)
            self.assertIs(
                lane.apply_cow_feed_recycle(action, _obs(tile), CFG, enabled=True),
                action,
            )

    def test_outer_seam_sees_reconstructed_hidden_actor(self):
        observation = _obs(
            _cow(), hands=[(0, 0)], inventories=[{"WHEAT": 1}, {"WHEAT": 1}]
        )
        reconstructed = _action(["CARE"], [["FEED"]])
        old_flags = (
            r04.MIRROR_HORIZON,
            r04.TERMINAL_FERTILIZER,
            r04.GOOSE_RESCUE,
            r04.H3E_COW_FEED_RECYCLE,
        )
        try:
            r04.MIRROR_HORIZON = False
            r04.TERMINAL_FERTILIZER = False
            r04.GOOSE_RESCUE = False
            r04.H3E_COW_FEED_RECYCLE = True
            with mock.patch.object(r04, "_v3_core", return_value=reconstructed):
                out = r04.v3_agent(observation, CFG)
            self.assertIs(out, reconstructed)
            self.assertEqual(lane.telemetry["stacked_worker_block"], 1)
        finally:
            (
                r04.MIRROR_HORIZON,
                r04.TERMINAL_FERTILIZER,
                r04.GOOSE_RESCUE,
                r04.H3E_COW_FEED_RECYCLE,
            ) = old_flags

    def test_multiple_candidates_and_malformed_metadata_fail_closed(self):
        observation = _obs(
            _cow(), hands=[(2, 2)], inventories=[{"WHEAT": 1}, {"WHEAT": 1}]
        )
        observation["farms"][0]["tiles"][2][2] = _cow()
        action = _action(["CARE"], [["CARE"]])
        self.assertIs(
            lane.apply_cow_feed_recycle(action, observation, CFG, enabled=True), action
        )
        poisoned = _cow(placed_day="0")
        action = _action(["CARE"])
        self.assertIs(
            lane.apply_cow_feed_recycle(action, _obs(poisoned), CFG, enabled=True), action
        )


if __name__ == "__main__":
    unittest.main()
