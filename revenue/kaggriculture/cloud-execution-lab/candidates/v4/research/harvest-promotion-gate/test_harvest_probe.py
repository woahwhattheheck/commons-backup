# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


def load_probe():
    path = Path(__file__).with_name("harvest_probe.py")
    spec = importlib.util.spec_from_file_location("harvest_probe_tested", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def blank_tiles():
    return [[{"kind": "EMPTY"} for _ in range(10)] for _ in range(10)]


def configuration():
    return {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100}


def observation(step=695, *, watered=True, lifespan=695, yield_units=2, planted_day=20,
                crop="WHEAT", shed=0):
    tiles = blank_tiles()
    tiles[0][0] = {
        "kind": "PLANT", "crop": crop, "watered_today": watered,
        "max_lifespan_step": lifespan, "yield_units": yield_units,
        "planted_day": planted_day,
    }
    farm0 = {"tiles": tiles, "farmer": [0, 0], "hands": []}
    farm1 = {"tiles": blank_tiles(), "farmer": [9, 9], "hands": []}
    return {
        "step": step, "day": step // 24, "hour": step % 24, "player": 0,
        "farms": [farm0, farm1],
        "private": {"shed": {"WHEAT": shed}, "inventories": [{}]},
    }


def action(command=None):
    return {"farmer": list(command or ["WATER"]), "hands": [], "market": []}


class HarvestProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_probe()
        cls.probe = cls.mod.HarvestProbe()

    def setUp(self):
        if hasattr(self.probe.w1, "reset"):
            self.probe.w1.reset()
        if hasattr(self.probe.h1, "reset"):
            self.probe.h1.reset()

    def test_day28_eod_capacity_safe_is_executable_w1(self):
        obs = observation()
        parent = action()
        report = self.probe.inspect(obs, configuration(), parent)
        self.assertTrue(report["w1_changed"])
        self.assertTrue(report["h1_changed"])
        self.assertEqual(report["w1_actor_indices"], [0])
        candidate = self.probe.apply_candidate(obs, configuration(), parent)
        self.assertEqual(candidate["farmer"], ["HARVEST"])
        self.assertEqual(parent["farmer"], ["WATER"])

    def test_w1_capacity_block_can_expose_h1_only_risk(self):
        obs = observation(shed=100)
        report = self.probe.inspect(obs, configuration(), action())
        self.assertFalse(report["w1_changed"])
        self.assertTrue(report["h1_changed"])
        self.assertTrue(report["h1_only"])
        self.assertEqual(self.probe.apply_candidate(obs, configuration(), action())["farmer"], ["WATER"])

    def test_final_day_h1_is_shadow_only(self):
        obs = observation(step=718, watered=False, lifespan=718, planted_day=20)
        report = self.probe.inspect(obs, configuration(), action())
        self.assertFalse(report["w1_changed"])
        self.assertTrue(report["h1_changed"])
        self.assertTrue(report["h1_only"])
        self.assertEqual(self.probe.apply_candidate(obs, configuration(), action())["farmer"], ["WATER"])

    def test_non_water_identity(self):
        obs = observation()
        parent = action(["PASS"])
        report = self.probe.inspect(obs, configuration(), parent)
        self.assertFalse(report["w1_changed"])
        self.assertFalse(report["h1_changed"])
        self.assertIs(self.probe.apply_candidate(obs, configuration(), parent), parent)

    def test_malformed_action_fails_closed(self):
        report = self.probe.inspect(observation(), configuration(), {"farmer": "WATER"})
        self.assertFalse(report["valid_action"])
        self.assertFalse(report["w1_changed"])
        self.assertFalse(report["h1_changed"])


if __name__ == "__main__":
    unittest.main()
