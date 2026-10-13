# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


OVERLAY = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "e20_hire_guard",
    OVERLAY / "e20_hire_guard.py",
)
assert SPEC is not None and SPEC.loader is not None
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


if __name__ == "__main__":
    unittest.main()
