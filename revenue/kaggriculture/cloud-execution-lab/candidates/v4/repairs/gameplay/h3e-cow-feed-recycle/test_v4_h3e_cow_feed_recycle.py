# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 H3e ``r04_h3e_cow_feed_recycle``."""
from __future__ import annotations

import copy
import unittest
from unittest import mock

import r04_full_router as r04
import r04_h3e_cow_feed_recycle as lane

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


class CowFeedRecycleTest(unittest.TestCase):
    def setUp(self):
        lane.telemetry.clear()

    def test_dead_care_recycles_into_feed(self):
        action = _action(["CARE"])
        out = lane.apply_cow_feed_recycle(action, _obs(_cow()), CFG, enabled=True)
        self.assertEqual(out["farmer"], ["FEED"])
        self.assertEqual(lane.telemetry["recycled_care"], 1)
        self.assertEqual(lane.telemetry["escape_risk_cows_fed"], 1)
        self.assertEqual(action["farmer"], ["CARE"])

    def test_dead_harvest_and_fertilizer_recycle(self):
        for command, key in ((["HARVEST"], "recycled_harvest"),
                             (["COLLECT_FERTILIZER"], "recycled_collect_fertilizer")):
            lane.telemetry.clear()
            action = _action(command)
            out = lane.apply_cow_feed_recycle(action, _obs(_cow()), CFG, enabled=True)
            self.assertEqual(out["farmer"], ["FEED"])
            self.assertEqual(lane.telemetry[key], 1)

    def test_productive_service_is_never_stolen(self):
        cases = [
            (_cow(cared_today=False), ["CARE"]),
            (_cow(yield_units=2), ["HARVEST"]),
            (_cow(fertilizer_available=True), ["COLLECT_FERTILIZER"]),
        ]
        for tile, command in cases:
            action = _action(command)
            self.assertIs(
                lane.apply_cow_feed_recycle(action, _obs(tile), CFG, enabled=True),
                action,
            )

    def test_only_imminent_second_unfed_eod_qualifies(self):
        for tile in (
            _cow(consecutive_unfed=0),
            _cow(consecutive_unfed=2),
            _cow(fed_today=True),
        ):
            action = _action(["CARE"])
            self.assertIs(
                lane.apply_cow_feed_recycle(action, _obs(tile), CFG, enabled=True),
                action,
            )

    def test_actor_must_already_carry_wheat(self):
        action = _action(["CARE"])
        self.assertIs(
            lane.apply_cow_feed_recycle(
                action, _obs(_cow(), inventories=[{}]), CFG, enabled=True
            ),
            action,
        )

    def test_key_off_wrong_hour_and_terminal_partial_day_are_identity(self):
        action = _action(["CARE"])
        self.assertIs(lane.apply_cow_feed_recycle(action, _obs(_cow()), CFG), action)
        self.assertIs(
            lane.apply_cow_feed_recycle(action, _obs(_cow(), step=694), CFG, enabled=True),
            action,
        )
        self.assertIs(
            lane.apply_cow_feed_recycle(action, _obs(_cow(), step=718), CFG, enabled=True),
            action,
        )

    def test_hand_actor_can_recycle_without_using_farmer(self):
        observation = _obs(None, hands=[(2, 2)], inventories=[{}, {"WHEAT": 1}])
        observation["farms"][0]["tiles"][2][2] = _cow()
        action = _action(["PASS"], [["CARE"]])
        out = lane.apply_cow_feed_recycle(action, observation, CFG, enabled=True)
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(out["hands"], [["FEED"]])

    def test_multiple_independent_candidates_fail_closed(self):
        observation = _obs(
            _cow(), hands=[(2, 2)], inventories=[{"WHEAT": 1}, {"WHEAT": 1}]
        )
        observation["farms"][0]["tiles"][2][2] = _cow()
        action = _action(["CARE"], [["CARE"]])
        self.assertIs(
            lane.apply_cow_feed_recycle(action, observation, CFG, enabled=True),
            action,
        )
        self.assertEqual(lane.telemetry["multiple_candidate_block"], 1)

    def test_stacked_active_actor_blocks_order_ambiguity(self):
        observation = _obs(_cow(), hands=[(0, 0)], inventories=[{"WHEAT": 1}, {}])
        action = _action(["CARE"], [["HARVEST"]])
        self.assertIs(
            lane.apply_cow_feed_recycle(action, observation, CFG, enabled=True),
            action,
        )
        self.assertEqual(lane.telemetry["stacked_worker_block"], 1)

    def test_outer_seam_sees_reconstructed_hidden_actor(self):
        # r04_fert_hand hides its owned hand from _v3_stack and reinserts that
        # command in _v3_core. Model the reconstructed whole action directly:
        # the visible farmer's CARE is dead, but the hidden hand already FEEDs
        # the same cow. H3e must run outside _v3_core so the stacked-worker veto
        # sees that FEED rather than spending a second WHEAT.
        observation = _obs(
            _cow(), hands=[(0, 0)], inventories=[{"WHEAT": 1}, {"WHEAT": 1}]
        )
        reconstructed = _action(["CARE"], [["FEED"]])
        old_flags = (
            r04.MIRROR_HORIZON,
            r04.TERMINAL_FERTILIZER,
            r04.GOOSE_RESCUE,
            r04.COW_FEED_RECYCLE,
        )
        try:
            r04.MIRROR_HORIZON = False
            r04.TERMINAL_FERTILIZER = False
            r04.GOOSE_RESCUE = False
            r04.COW_FEED_RECYCLE = True
            with mock.patch.object(r04, "_v3_core", return_value=reconstructed):
                out = r04.v3_agent(observation, CFG)
            self.assertIs(out, reconstructed)
            self.assertEqual(lane.telemetry["stacked_worker_block"], 1)
        finally:
            (r04.MIRROR_HORIZON,
             r04.TERMINAL_FERTILIZER,
             r04.GOOSE_RESCUE,
             r04.COW_FEED_RECYCLE) = old_flags

    def test_eod_read_metadata_poison_fails_closed(self):
        action = _action(["CARE"])
        malformed = [
            _cow(placed_day=True),
            _cow(placed_day="0"),
            _cow(placed_day=29),  # step 695 is day 28
            _cow(pending_care_bonus=-1),
            _cow(pending_care_bonus="0"),
        ]
        missing_placed = _cow()
        del missing_placed["placed_day"]
        missing_bonus = _cow()
        del missing_bonus["pending_care_bonus"]
        malformed.extend((missing_placed, missing_bonus))
        for tile in malformed:
            self.assertIs(
                lane.apply_cow_feed_recycle(action, _obs(tile), CFG, enabled=True),
                action,
            )

    def test_non_cow_and_other_commands_are_untouched(self):
        goose = _cow(animal="GOOSE", kind="COOP")
        for tile, command in ((goose, ["CARE"]), (_cow(), ["PASS"]), (_cow(), ["WATER"])):
            action = _action(command)
            self.assertIs(
                lane.apply_cow_feed_recycle(action, _obs(tile), CFG, enabled=True),
                action,
            )

    def test_malformed_state_and_nonstandard_config_fail_closed(self):
        action = _action(["CARE"])
        bad_obs = _obs(_cow())
        bad_obs["private"]["inventories"] = [{"WHEAT": "1"}]
        self.assertIs(lane.apply_cow_feed_recycle(action, bad_obs, CFG, enabled=True), action)

        bad_pos = _obs(_cow())
        bad_pos["farms"][0]["farmer"] = [True, 0]
        self.assertIs(lane.apply_cow_feed_recycle(action, bad_pos, CFG, enabled=True), action)

        for key, bad_value in (
            ("turnsPerDay", 25),
            ("episodeSteps", 696),
            ("episodeSteps", True),
        ):
            bad_cfg = dict(CFG)
            bad_cfg[key] = bad_value
            self.assertIs(
                lane.apply_cow_feed_recycle(action, _obs(_cow()), bad_cfg, enabled=True),
                action,
            )

    def test_parent_action_is_not_mutated(self):
        action = _action(["CARE"])
        before = copy.deepcopy(action)
        lane.apply_cow_feed_recycle(action, _obs(_cow()), CFG, enabled=True)
        self.assertEqual(action, before)


if __name__ == "__main__":
    unittest.main()
