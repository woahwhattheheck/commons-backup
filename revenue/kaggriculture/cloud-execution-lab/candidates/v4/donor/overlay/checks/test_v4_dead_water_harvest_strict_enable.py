# SPDX-License-Identifier: Apache-2.0
"""Activation-custody regressions for V4 W1 dead-water harvest."""
from __future__ import annotations

import copy
import unittest

import r04_dead_water_harvest as lane


def _tile():
    return {
        "kind": "PLANT",
        "crop": "WHEAT",
        "planted_day": 24,
        "yield_units": 3,
        "watered_today": True,
        "max_lifespan_step": 696,
    }


def _observation():
    tiles = [[{"kind": "SOIL"} for _ in range(10)] for _ in range(10)]
    tiles[0][0] = _tile()
    farm = {"farmer": [0, 0], "hands": [], "tiles": tiles}
    return {
        "step": 695,
        "day": 28,
        "player": 0,
        "farms": [farm, copy.deepcopy(farm)],
        "private": {"inventories": [{}], "shed": {}},
    }


def _action():
    return {"farmer": ["WATER"], "hands": [], "market": []}


def _config():
    return {
        "episodeSteps": 720,
        "turnsPerDay": 24,
        "boardSize": 10,
        "shedCapacity": 100,
    }


class DeadWaterHarvestStrictEnableTest(unittest.TestCase):
    def setUp(self):
        lane.reset()

    def test_omitted_enabled_is_exact_identity_and_telemetry_inert(self):
        action = _action()
        before = lane.get_report()
        out = lane.apply_dead_water_harvest(_observation(), action, _config())
        self.assertIs(out, action)
        self.assertEqual(lane.get_report(), before)

    def test_omitted_enabled_returns_before_configuration_or_observation_access(self):
        action = _action()
        before = lane.get_report()
        self.assertIs(lane.apply_dead_water_harvest(None, action, None), action)
        self.assertEqual(lane.get_report(), before)

    def test_truthy_nonbool_tokens_are_exact_identity_and_telemetry_inert(self):
        poisons = (1, 1.0, "true", "false", [True], {"enabled": True})
        for poison in poisons:
            with self.subTest(poison=poison):
                lane.reset()
                action = _action()
                before = lane.get_report()
                out = lane.apply_dead_water_harvest(
                    _observation(), action, _config(), enabled=poison
                )
                self.assertIs(out, action)
                self.assertEqual(lane.get_report(), before)

    def test_literal_true_preserves_positive_w1_behavior(self):
        action = _action()
        out = lane.apply_dead_water_harvest(
            _observation(), action, _config(), enabled=True
        )
        self.assertIsNot(out, action)
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(lane.get_report()["recovered"], 1)


if __name__ == "__main__":
    unittest.main()
