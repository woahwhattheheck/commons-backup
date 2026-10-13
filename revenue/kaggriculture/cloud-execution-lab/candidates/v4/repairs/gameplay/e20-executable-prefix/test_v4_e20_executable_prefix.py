# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import importlib.util
from itertools import product
from pathlib import Path
import unittest


# Canonical recovery keeps helper and tests as siblings. Legacy packaging
# places this test under overlay/checks; support that layout without a rewrite.
OVERLAY = Path(__file__).resolve().parent
if not (OVERLAY / "e20_hire_guard.py").is_file():
    OVERLAY = OVERLAY.parent
SPEC = importlib.util.spec_from_file_location(
    "e20_hire_guard",
    OVERLAY / "e20_hire_guard.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load the sibling E20 helper")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
apply_hire_guard = MODULE.apply_hire_guard


def _obs(*, hires_today: int = 0):
    return {
        "step": 100,
        "player": 0,
        "farms": [
            {
                "hires_today": hires_today,
                "tiles": [],
            }
        ],
    }


def _config(*, market_limit: int, max_hires: int = 0):
    return {
        "episodeSteps": 720,
        "maxMarketOrdersPerTurn": market_limit,
        "e20_max_hires_per_day": max_hires,
        "e20_min_unwatered_crops": 1,
    }


class E20ExecutablePrefixTest(unittest.TestCase):
    def test_suffix_hire_outside_engine_prefix_is_ignored(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [[], ["HIRE"]],
        }
        out, report = apply_hire_guard(
            _obs(), action, _config(market_limit=1), enabled=True
        )
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_HIRE")
        self.assertEqual(action["market"], [[], ["HIRE"]])

    def test_zero_market_limit_uses_official_minimum_one_prefix(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [[], ["HIRE"]],
        }
        out, report = apply_hire_guard(
            _obs(), action, _config(market_limit=0), enabled=True
        )
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "NO_HIRE")
        self.assertEqual(action["market"], [[], ["HIRE"]])

    def test_only_active_prefix_hires_are_limited(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["HIRE"], ["HIRE"], ["HIRE"]],
        }
        out, report = apply_hire_guard(
            _obs(), action, _config(market_limit=2, max_hires=1), enabled=True
        )
        self.assertIsNot(out, action)
        self.assertEqual(out["market"], [["HIRE"], [], ["HIRE"]])
        self.assertEqual(report["dropped_indices"], [1])
        self.assertEqual(action["market"], [["HIRE"], ["HIRE"], ["HIRE"]])

    def test_disabled_path_preserves_exact_parent_identity(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["HIRE"], ["HIRE"]],
        }
        out, report = apply_hire_guard(
            _obs(), action, _config(market_limit=1), enabled=False
        )
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "OFF")

    def test_nonpositive_cap_still_limits_first_hire(self):
        for cap in (-2, 0):
            with self.subTest(cap=cap):
                action = {"market": [["HIRE"], ["HIRE"]]}
                out, report = apply_hire_guard(
                    _obs(), action, _config(market_limit=cap), enabled=True
                )
                self.assertEqual(out["market"], [[], ["HIRE"]])
                self.assertEqual(report["dropped_indices"], [0])
                self.assertEqual(action["market"], [["HIRE"], ["HIRE"]])

    def test_differential_raw_slot_matrix(self):
        # Independent streaming oracle: visit raw slots in order and spend
        # allowance only on a literal HIRE inside the executable prefix.
        # 7**3 layouts * 7 caps * 4 budgets = 9,604 deterministic cases.
        rows = ([], None, False, ["HIRE"], ["SELL", "WOOL", 2],
                ["BUY_PRODUCT", "WHEAT", 1], ("HIRE",))
        cases = 0
        for layout in product(rows, repeat=3):
            for cap in (-2, 0, 1, 2, 3, 4, 10):
                for max_hires, hires_today in ((0, 0), (1, 0), (3, 1), (1, 3)):
                    with self.subTest(layout=layout, cap=cap,
                                      budget=(max_hires, hires_today)):
                        action = {"farmer": ["PASS"], "hands": [["WATER"]],
                                  "market": deepcopy(list(layout)),
                                  "untouched": {"nested": [1, 2]}}
                        obs = _obs(hires_today=hires_today)
                        cfg = _config(market_limit=cap, max_hires=max_hires)
                        snapshots = deepcopy((obs, action, cfg))
                        expected = deepcopy(action)
                        remaining = max(0, max_hires - hires_today)
                        dropped = []
                        for index, row in enumerate(expected["market"]):
                            if index >= max(1, cap):
                                break
                            if not isinstance(row, list) or not row or row[0] != "HIRE":
                                continue
                            if remaining:
                                remaining -= 1
                            else:
                                expected["market"][index] = []
                                dropped.append(index)
                        out, report = apply_hire_guard(obs, action, cfg, enabled=True)
                        self.assertEqual(out, expected)
                        self.assertEqual(report["dropped_indices"], dropped)
                        self.assertIs(report["changed"], bool(dropped))
                        self.assertEqual((obs, action, cfg), snapshots)
                        self.assertEqual(len(out["market"]), len(action["market"]))
                        if dropped:
                            self.assertIsNot(out, action)
                        else:
                            self.assertIs(out, action)
                        cases += 1
        self.assertEqual(cases, 9604)

    def test_default_cap_preserves_the_eleventh_raw_slot(self):
        action = {"farmer": ["PASS"], "hands": [],
                  "market": [["HIRE"]] + [[] for _ in range(9)] + [["HIRE"]]}
        snapshot = deepcopy(action)
        cfg = _config(market_limit=10)
        del cfg["maxMarketOrdersPerTurn"]
        out, report = apply_hire_guard(_obs(), action, cfg, enabled=True)
        self.assertEqual(out["market"], [[] for _ in range(10)] + [["HIRE"]])
        self.assertEqual(report["dropped_indices"], [0])
        self.assertEqual(action, snapshot)

    def test_daily_allowance_keeps_first_hires_without_compacting_gaps(self):
        action = {"farmer": ["NORTH"], "hands": [["PASS"]],
                  "market": [None, ["HIRE"], ["SELL", "WOOL", 2],
                             [], ["HIRE"], ["HIRE"]]}
        snapshot = deepcopy(action)
        out, report = apply_hire_guard(
            _obs(hires_today=1), action,
            _config(market_limit=5, max_hires=2), enabled=True
        )
        self.assertEqual(out["market"],
                         [None, ["HIRE"], ["SELL", "WOOL", 2], [], [], ["HIRE"]])
        self.assertEqual(report["dropped_indices"], [4])
        self.assertEqual(out["farmer"], action["farmer"])
        self.assertEqual(out["hands"], action["hands"])
        self.assertEqual(action, snapshot)

    def test_high_demand_at_threshold_preserves_parent(self):
        obs = _obs(hires_today=99)
        obs["farms"][0]["tiles"] = [[
            {"kind": "PLANT", "watered_today": False},
            {"kind": "PLANT", "watered_today": True},
            {"kind": "PASTURE", "watered_today": False},
        ]]
        action = {"market": [["HIRE"], [], ["HIRE"]]}
        cfg = _config(market_limit=3)
        snapshot = deepcopy((obs, action, cfg))
        out, report = apply_hire_guard(obs, action, cfg, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "DEMAND_JUSTIFIES_HIRES")
        self.assertEqual(report["unwatered_crops"], 1)
        self.assertFalse(report["changed"])
        self.assertEqual((obs, action, cfg), snapshot)

    def test_watered_plants_and_nonplants_do_not_create_demand(self):
        obs = _obs()
        obs["farms"][0]["tiles"] = [[
            {"kind": "PLANT", "watered_today": True},
            {"kind": "PASTURE", "watered_today": False},
        ]]
        action = {"market": [["HIRE"]]}
        out, report = apply_hire_guard(obs, action, _config(market_limit=1), enabled=True)
        self.assertEqual(out["market"], [[]])
        self.assertEqual(report["unwatered_crops"], 0)
        self.assertEqual(action["market"], [["HIRE"]])

    def test_terminal_boundary_is_configuration_relative(self):
        for episode_steps in (24, 720, 1000):
            last = episode_steps - 2
            for step in (last - 1, last, last + 1):
                with self.subTest(episode_steps=episode_steps, step=step):
                    obs = _obs()
                    obs["step"] = step
                    action = {"market": [["HIRE"], ["HIRE"]]}
                    cfg = _config(market_limit=1)
                    cfg["episodeSteps"] = episode_steps
                    snapshot = deepcopy((obs, action, cfg))
                    out, report = apply_hire_guard(obs, action, cfg, enabled=True)
                    if step >= last:
                        self.assertIs(out, action)
                        self.assertEqual(report["reason"], "NO_EDIT_TERMINAL_STEP")
                    else:
                        self.assertEqual(out["market"], [[], ["HIRE"]])
                        self.assertEqual(report["dropped_indices"], [0])
                    self.assertEqual((obs, action, cfg), snapshot)

    def test_fixed_prefix_is_idempotent(self):
        action = {"market": [["HIRE"], [], ["HIRE"], ["HIRE"]]}
        cfg = _config(market_limit=3, max_hires=1)
        first, first_report = apply_hire_guard(_obs(), action, cfg, enabled=True)
        snapshot = deepcopy(first)
        second, second_report = apply_hire_guard(_obs(), first, cfg, enabled=True)
        self.assertTrue(first_report["changed"])
        self.assertIs(second, first)
        self.assertFalse(second_report["changed"])
        self.assertEqual(second_report["dropped_indices"], [])
        self.assertEqual(first, snapshot)

    def test_disabled_does_not_read_observation_or_configuration(self):
        action = {"market": [["HIRE"]]}
        out, report = apply_hire_guard(object(), action, object(), enabled=False)
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "OFF")
        self.assertFalse(report["changed"])

    def test_nonlist_market_preserves_exact_parent(self):
        for market in (None, {}, "HIRE", (["HIRE"],)):
            with self.subTest(market=market):
                action = {"market": market}
                snapshot = deepcopy(action)
                out, report = apply_hire_guard(
                    _obs(), action, _config(market_limit=1), enabled=True
                )
                self.assertIs(out, action)
                self.assertEqual(report["reason"], "BAD_MARKET_QUEUE")
                self.assertFalse(report["changed"])
                self.assertEqual(action, snapshot)


if __name__ == "__main__":
    unittest.main()
