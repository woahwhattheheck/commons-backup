# SPDX-License-Identifier: Apache-2.0
"""E20 input-domain and canonical-recovery regressions (no game-strength claim)."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from itertools import product
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
if not (ROOT / "e20_hire_guard.py").is_file():
    ROOT = ROOT.parent
SPEC = importlib.util.spec_from_file_location(
    "e20_input_domain_subject", ROOT / "e20_hire_guard.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load the sibling E20 helper")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
apply_hire_guard = MODULE.apply_hire_guard

BAD_INTEGERS = (None, True, False, 0.0, 1.0, 1.5, -0.5,
                float("inf"), float("-inf"), float("nan"),
                "", "0", "1", "2.5", "NaN", [], [1], {}, {"x": 1})


def fixture(seat=0):
    obs = {"step": 100, "player": seat, "farms": [
        {"hires_today": 3, "tiles": []},
        {"hires_today": 3, "tiles": []},
    ]}
    action = {"farmer": ["NORTH"], "hands": [["WATER"]],
              "market": [["HIRE"], [], ["SELL", "WOOL", 2], ["HIRE"]],
              "metadata": {"nested": [1, 2]}}
    cfg = {"episodeSteps": 720, "maxMarketOrdersPerTurn": 3,
           "e20_max_hires_per_day": 3, "e20_min_unwatered_crops": 3}
    return obs, action, cfg


class E20InputDomainTest(unittest.TestCase):
    def assert_parent(self, obs, action, cfg, reason=None):
        snapshot = deepcopy((obs, action, cfg))
        out, report = apply_hire_guard(obs, action, cfg, enabled=True)
        self.assertIs(out, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["dropped_indices"], [])
        if reason is not None:
            self.assertEqual(report["reason"], reason)
        self.assertEqual((obs, action, cfg), snapshot)

    def test_step_rejects_nonintegers_without_coercion(self):
        for seat, value in product((0, 1), BAD_INTEGERS + (-1,)):
            with self.subTest(seat=seat, value=repr(value)):
                obs, action, cfg = fixture(seat)
                obs["step"] = value
                self.assert_parent(obs, action, cfg, "BAD_STEP")

    def test_player_rejects_aliases_and_out_of_range(self):
        for value in BAD_INTEGERS + (-1, 2, 10**100):
            with self.subTest(value=repr(value)):
                obs, action, cfg = fixture()
                obs["player"] = value
                self.assert_parent(obs, action, cfg, "BAD_PLAYER_OR_FARM")

    def test_hire_counter_rejects_nonintegers_and_negative(self):
        for seat, value in product((0, 1), BAD_INTEGERS + (-1,)):
            with self.subTest(seat=seat, value=repr(value)):
                obs, action, cfg = fixture(seat)
                obs["farms"][seat]["hires_today"] = value
                self.assert_parent(obs, action, cfg, "BAD_HIRES_TODAY")

    def test_config_integer_fields_fail_closed(self):
        keys = tuple(fixture()[2])
        count = 0
        for seat, key, value in product((0, 1), keys, BAD_INTEGERS):
            with self.subTest(seat=seat, key=key, value=repr(value)):
                obs, action, cfg = fixture(seat)
                cfg[key] = value
                self.assert_parent(obs, action, cfg, "BAD_CONFIG_INTEGER")
                count += 1
        self.assertEqual(count, 152)

    def test_missing_observation_evidence_is_not_assumed_zero(self):
        for seat, key in product((0, 1), ("step", "player", "farms",
                                         "hires_today", "tiles")):
            with self.subTest(seat=seat, key=key):
                obs, action, cfg = fixture(seat)
                target = obs["farms"][seat] if key in ("hires_today", "tiles") else obs
                del target[key]
                self.assert_parent(obs, action, cfg)

    def test_malformed_containers_are_noops(self):
        for key, value in product(("farms", "tiles"),
                                  (None, True, 1, "", "farm", {}, {0: {}}, ())):
            with self.subTest(key=key, value=repr(value)):
                obs, action, cfg = fixture()
                target = obs if key == "farms" else obs["farms"][0]
                target[key] = value
                self.assert_parent(obs, action, cfg)
        for farm in (None, [], 1, "farm"):
            obs, action, cfg = fixture()
            obs["farms"][0] = farm
            self.assert_parent(obs, action, cfg, "BAD_PLAYER_OR_FARM")

    def test_malformed_board_cannot_prove_low_demand(self):
        boards = ([None], [1], ["row"], [{}], [( {}, )],
                  [["UNLOCKED"]], [[1]], [["tile"]], [[False]], [[[]]])
        for seat, board in product((0, 1), boards):
            with self.subTest(seat=seat, board=board):
                obs, action, cfg = fixture(seat)
                obs["farms"][seat]["tiles"] = deepcopy(board)
                self.assert_parent(obs, action, cfg, "BAD_TILES")

    def test_official_empty_and_locked_tiles_remain_valid(self):
        # Pinned engine _initial_tile returns None in NW, otherwise "LOCKED".
        # Mapping-only board validators silently disable E20 on every new farm.
        for seat in (0, 1):
            with self.subTest(seat=seat):
                obs, action, cfg = fixture(seat)
                obs["farms"][seat]["tiles"] = [
                    [None if x < 5 and y < 5 else "LOCKED" for x in range(10)]
                    for y in range(10)]
                out, report = apply_hire_guard(obs, action, cfg, enabled=True)
                self.assertEqual(report["dropped_indices"], [0])
                self.assertEqual(out["market"], [[], [], ["SELL", "WOOL", 2], ["HIRE"]])
                self.assertEqual(action["market"][0], ["HIRE"])
                obs["farms"][seat]["tiles"][0][:3] = [
                    {"kind": "PLANT", "watered_today": False} for _ in range(3)]
                self.assert_parent(obs, action, cfg, "DEMAND_JUSTIFIES_HIRES")

    def test_watered_flag_must_be_boolean_when_present(self):
        for value in (None, 0, 1, 0.0, 1.0, "false", "true", [], {}):
            with self.subTest(value=value):
                obs, action, cfg = fixture()
                obs["farms"][0]["tiles"] = [[{"kind": "PLANT", "watered_today": value}]]
                self.assert_parent(obs, action, cfg, "BAD_TILES")

    def test_disabled_does_not_inspect_any_inputs(self):
        obs, action, cfg = object(), object(), object()
        out, report = apply_hire_guard(obs, action, cfg, enabled=False)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "OFF")
        self.assertFalse(report["changed"])

    def test_top_level_containers(self):
        for index, bad in product(range(3), (None, True, 1, "data", [], ())):
            if index == 2 and bad is None:  # optional config is supported
                continue
            with self.subTest(index=index, bad=bad):
                data = list(fixture())
                data[index] = bad
                self.assert_parent(*data, reason="BAD_INPUT")

    def test_integer_extremes_are_safe_without_float_conversion(self):
        obs, action, cfg = fixture(1)
        cfg.update(episodeSteps=10**100, maxMarketOrdersPerTurn=10**100)
        obs["farms"][1]["hires_today"] = 10**100
        out, report = apply_hire_guard(obs, action, cfg, enabled=True)
        self.assertEqual(out["market"], [[], [], ["SELL", "WOOL", 2], []])
        self.assertEqual(report["dropped_indices"], [0, 3])
        self.assertEqual(action["market"][0], ["HIRE"])
        obs["step"] = 10**101
        self.assert_parent(obs, action, cfg, "NO_EDIT_TERMINAL_STEP")

    def test_default_config_and_absent_watered_flag_remain_compatible(self):
        obs, action, _ = fixture()
        out, report = apply_hire_guard(obs, action, None, enabled=True)
        self.assertEqual(report["dropped_indices"], [0, 3])
        self.assertEqual(out["market"], [[], [], ["SELL", "WOOL", 2], []])
        obs["farms"][0]["tiles"] = [[{"kind": "PLANT"} for _ in range(3)]]
        self.assert_parent(obs, action, None, "DEMAND_JUSTIFIES_HIRES")

    def test_both_seats_use_only_their_own_valid_farm(self):
        for seat in (0, 1):
            obs, action, cfg = fixture(seat)
            obs["farms"][1-seat] = {"hires_today": "broken", "tiles": 1}
            out, report = apply_hire_guard(obs, action, cfg, enabled=True)
            self.assertEqual(out["market"], [[], [], ["SELL", "WOOL", 2], ["HIRE"]])
            self.assertEqual(report["dropped_indices"], [0])
            self.assertEqual(action["market"][0], ["HIRE"])

    def test_valid_integer_domain_against_independent_policy_oracle(self):
        # 2 seats x 4 hours x 5 caps x 4 allowances x 4 demand values x 3
        # thresholds = 1,920 policy cases, including terminal/high-demand noops.
        count = 0
        for seat, step, cap, allowance, demand, threshold in product(
                (0, 1), (0, 100, 717, 718), (-2, 0, 1, 3, 10),
                (0, 1, 2, 3), (0, 1, 3, 5), (0, 1, 3)):
            obs, action, cfg = fixture(seat)
            obs["step"] = step
            obs["farms"][seat]["hires_today"] = 2
            obs["farms"][seat]["tiles"] = [[
                {"kind": "PLANT", "watered_today": False} for _ in range(demand)]]
            cfg.update(maxMarketOrdersPerTurn=cap, e20_max_hires_per_day=allowance+2,
                       e20_min_unwatered_crops=threshold)
            before = deepcopy((obs, action, cfg))
            expected = deepcopy(action)
            dropped = []
            if step < 718 and demand < threshold:
                budget = allowance
                for index, row in enumerate(expected["market"]):
                    if index >= max(1, cap):
                        break
                    if row and row[0] == "HIRE":
                        if budget:
                            budget -= 1
                        else:
                            expected["market"][index] = []
                            dropped.append(index)
            out, report = apply_hire_guard(obs, action, cfg, enabled=True)
            self.assertEqual(out, expected)
            self.assertEqual(report["dropped_indices"], dropped)
            self.assertIs(report["changed"], bool(dropped))
            self.assertEqual((obs, action, cfg), before)
            if dropped:
                self.assertIsNot(out, action)
                out["metadata"]["nested"].append(3)
                self.assertEqual(action["metadata"]["nested"], [1, 2])
                again, again_report = apply_hire_guard(obs, expected, cfg, enabled=True)
                self.assertIs(again, expected)
                self.assertFalse(again_report["changed"])
            else:
                self.assertIs(out, action)
            count += 1
        self.assertEqual(count, 1920)


if __name__ == "__main__":
    unittest.main()
