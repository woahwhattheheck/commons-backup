# SPDX-License-Identifier: Apache-2.0
"""Focused contracts for V4 ``r04_h3b_sheep_clip``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_h3b_sheep_clip.py
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_h3b_sheep_clip as lane  # noqa: E402
from titan_runtime import Features  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}
STEP = 18 * 24 + 10
TARGETS = [(5, 5), (6, 5), (7, 5)]


def sheep(*, units=1, placed=13, fed=True, cared=True, bonus=1):
    return {"kind": "PASTURE", "animal": "SHEEP", "placed_day": placed,
            "yield_units": units, "consecutive_unfed": 0,
            "fed_today": fed, "cared_today": cared,
            "fertilizer_available": True, "pending_care_bonus": bonus}


def fixture(*, step=STEP, position=(5, 5), inventory=None, command=None):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[5][5] = sheep(units=1)
    tiles[5][6] = sheep(units=6)
    tiles[5][7] = sheep(units=1)
    emitted = list(command or ["HARVEST"])
    action = {"farmer": ["PASS"], "hands": [list(emitted)], "market": []}
    farm = {"farmer": [4, 4], "hands": [list(position)], "tiles": tiles,
            "money": 1000, "unlocked_quadrants": ["NW"], "hires_today": 0}
    observation = {"step": step, "player": 0,
                   "farms": [farm, copy.deepcopy(farm)],
                   "private": {"inventories": [{}, dict(inventory or {})], "shed": {}}}
    state = {"last_step": step, "day": step // 24,
             "workers": {1: list(TARGETS)},
             "work": {1: {"step": step, "command": list(emitted),
                            "inventory": dict(inventory or {})}},
             "credit": {"WOOL": 0, "FERTILIZER": 0}, "committed": True}
    return action, observation, state


class H3bSheepClip(unittest.TestCase):
    def setUp(self):
        self.saved_states = r04._V233_STATES
        r04._V233_STATES = {}
        r04.H3B_SHEEP_CLIP = False

    def tearDown(self):
        r04._V233_STATES = self.saved_states
        r04.H3B_SHEEP_CLIP = False

    def run_case(self, action, observation, state, *, enabled=True, configuration=None):
        r04._V233_STATES[0] = state
        return lane.apply_h3b_sheep_clip(
            action, observation, dict(CONFIG) if configuration is None else configuration,
            enabled=enabled)

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_h3b_sheep_clip"], False)
        self.assertIs(Features(**data).r04_h3b_sheep_clip, False)

    def test_disabled_is_exact_parent_identity(self):
        action, observation, state = fixture()
        result = self.run_case(action, observation, state, enabled=False)
        self.assertIs(result, action)
        self.assertEqual(state["work"][1]["command"], ["HARVEST"])

    def test_enabled_must_be_literal_true(self):
        poisons = ("false", 1, 1.0, [True], {"enabled": False}, None)
        for enabled in poisons:
            with self.subTest(enabled=enabled):
                action, observation, state = fixture()
                before_action = copy.deepcopy(action)
                before_command = list(state["work"][1]["command"])
                result = self.run_case(
                    action, observation, state, enabled=enabled
                )
                self.assertIs(result, action)
                self.assertEqual(action, before_action)
                self.assertEqual(state["work"][1]["command"], before_command)

    def test_v233_committed_marker_must_be_literal_true(self):
        poisons = ("false", 1, 1.0, [True], {"committed": True}, None)
        for committed in poisons:
            with self.subTest(committed=committed):
                action, observation, state = fixture()
                state["committed"] = committed
                before_action = copy.deepcopy(action)
                before_command = list(state["work"][1]["command"])
                result = self.run_case(action, observation, state)
                self.assertIs(result, action)
                self.assertEqual(action, before_action)
                self.assertEqual(state["work"][1]["command"], before_command)

    def test_malformed_farmer_action_vector_is_exact_parent_identity(self):
        for mode in ("missing", "empty"):
            with self.subTest(mode=mode):
                action, observation, state = fixture()
                if mode == "missing":
                    del action["farmer"]
                else:
                    action["farmer"] = []
                result = self.run_case(action, observation, state)
                self.assertIs(result, action)
                self.assertEqual(state["work"][1]["command"], ["HARVEST"])

    def test_overflowing_sheep_preempts_nearer_nonurgent_harvest(self):
        action, observation, state = fixture()
        result = self.run_case(action, observation, state)
        self.assertIsNot(result, action)
        self.assertEqual(action["hands"][0], ["HARVEST"])
        self.assertEqual(result["hands"][0], ["EAST"])
        self.assertEqual(state["work"][1]["command"], ["EAST"])

    def test_distance_two_reroute_fails_closed_without_persistent_target_lock(self):
        # V233 reselects min(tasks) afresh on every callback.  From h21 a move two tiles
        # toward urgent B can be reversed at h22 by the earlier nonurgent A,
        # losing the authored harvest while B still clips.  H3b therefore only
        # owns adjacent detours unless it grows a persistent target latch.
        action, observation, state = fixture(step=18 * 24 + 21, position=(5, 5))
        observation["farms"][0]["tiles"][5][6]["yield_units"] = 1
        observation["farms"][0]["tiles"][5][7]["yield_units"] = 6
        result = self.run_case(action, observation, state)
        self.assertIs(result, action)
        self.assertEqual(state["work"][1]["command"], ["HARVEST"])

    def test_nonharvest_parent_is_exact_identity(self):
        action, observation, state = fixture(command=["CARE"])
        result = self.run_case(action, observation, state)
        self.assertIs(result, action)
        self.assertEqual(state["work"][1]["command"], ["CARE"])

    def test_already_on_urgent_sheep_is_identity(self):
        action, observation, state = fixture(position=(6, 5))
        result = self.run_case(action, observation, state)
        self.assertIs(result, action)

    def test_no_imminent_overflow_is_identity(self):
        action, observation, state = fixture()
        observation["farms"][0]["tiles"][5][6]["yield_units"] = 4
        result = self.run_case(action, observation, state)
        self.assertIs(result, action)

    def test_feed_or_care_debt_blocks_override(self):
        for field in ("fed_today", "cared_today"):
            with self.subTest(field=field):
                action, observation, state = fixture()
                observation["farms"][0]["tiles"][5][7][field] = False
                self.assertIs(self.run_case(action, observation, state), action)

    def test_cargo_return_priority_blocks_override(self):
        for item in ("WOOL", "FERTILIZER"):
            with self.subTest(item=item):
                action, observation, state = fixture(inventory={item: 1})
                self.assertIs(self.run_case(action, observation, state), action)

    def test_setup_or_missing_sheep_blocks_override(self):
        action, observation, state = fixture()
        observation["farms"][0]["tiles"][5][7] = None
        self.assertIs(self.run_case(action, observation, state), action)

    def test_wrong_structure_kind_fails_closed_and_preserves_state(self):
        for kind in ("COOP", "PLANT", None, 1):
            with self.subTest(kind=kind):
                action, observation, state = fixture()
                observation["farms"][0]["tiles"][5][6]["kind"] = kind
                before_action = copy.deepcopy(action)
                before_command = list(state["work"][1]["command"])
                result = self.run_case(action, observation, state)
                self.assertIs(result, action)
                self.assertEqual(action, before_action)
                self.assertEqual(state["work"][1]["command"], before_command)

    def test_canonical_pasture_sheep_positive_remains_live(self):
        action, observation, state = fixture()
        result = self.run_case(action, observation, state)
        self.assertIsNot(result, action)
        self.assertEqual(result["hands"][0], ["EAST"])
        self.assertEqual(state["work"][1]["command"], ["EAST"])

    def test_malformed_json_scalar_types_fail_closed(self):
        mutations = (("yield_units", True), ("yield_units", 6.0),
                     ("placed_day", "13"), ("pending_care_bonus", 1.0),
                     ("fed_today", 1), ("cared_today", 1))
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                action, observation, state = fixture()
                observation["farms"][0]["tiles"][5][6][key] = value
                self.assertIs(self.run_case(action, observation, state), action)

    def test_nonstandard_configuration_fails_closed_without_coercion(self):
        for configuration in ({"episodeSteps": 456}, {"turnsPerDay": 12},
                              {"turnsPerDay": "24"}, {"turnsPerDay": 24.0},
                              {"turnsPerDay": True}, {"shedCapacity": 99}):
            with self.subTest(configuration=configuration):
                action, observation, state = fixture()
                self.assertIs(self.run_case(action, observation, state,
                                            configuration=configuration), action)

    def test_missing_standard_configuration_evidence_fails_closed(self):
        cases = [("none", None)]
        for missing in lane.STANDARD_CONFIG:
            configuration = dict(CONFIG)
            del configuration[missing]
            cases.append((missing, configuration))
        for label, configuration in cases:
            with self.subTest(missing=label):
                action, observation, state = fixture()
                r04._V233_STATES[0] = state
                result = lane.apply_h3b_sheep_clip(
                    action, observation, configuration, enabled=True)
                self.assertIs(result, action)
                self.assertEqual(state["work"][1]["command"], ["HARVEST"])

    def test_out_of_range_player_fails_closed_even_with_third_farm_and_state(self):
        action, observation, state = fixture()
        observation["farms"].append(copy.deepcopy(observation["farms"][0]))
        observation["player"] = 2
        r04._V233_STATES[2] = state
        result = lane.apply_h3b_sheep_clip(
            action, observation, dict(CONFIG), enabled=True)
        self.assertIs(result, action)
        self.assertEqual(state["work"][1]["command"], ["HARVEST"])

    def test_v233_same_call_snapshot_mismatch_fails_closed(self):
        action, observation, state = fixture()
        state["work"][1]["command"] = ["CARE"]
        self.assertIs(self.run_case(action, observation, state), action)

    def test_malformed_worker_position_fails_closed(self):
        action, observation, state = fixture(position=(-1, 5))
        self.assertIs(self.run_case(action, observation, state), action)
        self.assertEqual(state["work"][1]["command"], ["HARVEST"])

    def test_hour23_distance_one_declines_unrealizable_rescue(self):
        action, observation, state = fixture(step=18 * 24 + 23, position=(5, 5))
        result = self.run_case(action, observation, state)
        self.assertIs(result, action)
        self.assertEqual(state["work"][1]["command"], ["HARVEST"])

    def test_hour22_distance_one_has_move_then_harvest_budget(self):
        action, observation, state = fixture(step=18 * 24 + 22, position=(5, 5))
        result = self.run_case(action, observation, state)
        self.assertIsNot(result, action)
        self.assertEqual(result["hands"][0], ["EAST"])
        self.assertEqual(state["work"][1]["command"], ["EAST"])

    def test_hour23_on_urgent_target_preserves_harvest(self):
        action, observation, state = fixture(step=18 * 24 + 23, position=(6, 5))
        self.assertIs(self.run_case(action, observation, state), action)

    def test_final_day_is_identity(self):
        action, observation, state = fixture(step=29 * 24 + 10)
        self.assertIs(self.run_case(action, observation, state), action)

    def test_parent_action_is_not_mutated_on_override(self):
        action, observation, state = fixture()
        before = copy.deepcopy(action)
        result = self.run_case(action, observation, state)
        self.assertEqual(action, before)
        self.assertNotEqual(result, before)

    def test_install_setter_carries_key(self):
        r04.install(h3b_sheep_clip=True)
        self.assertIs(r04.H3B_SHEEP_CLIP, True)
        r04.install(h3b_sheep_clip=False)
        self.assertIs(r04.H3B_SHEEP_CLIP, False)


if __name__ == "__main__":
    unittest.main()