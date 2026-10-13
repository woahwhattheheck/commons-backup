# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_v217_eod_tail``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_v217_eod_tail.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
from titan_runtime import Features  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


class _StructConfig:
    def __init__(self, values):
        for key, value in values.items():
            setattr(self, key, value)


class _Policy:
    def __init__(self, tape):
        self.tapes = [tape]


class _View:
    def __init__(self, target=(7, 4), wheat=1, primary_unfed=1, extra_targets=()):
        self.positions = [(4, 4)]
        self.inventories = [{"WHEAT": wheat} if wheat else {}]
        self.shed = {"WHEAT": 8}
        self.tiles = [[None for _ in range(10)] for _ in range(10)]
        x, y = target
        self.tiles[y][x] = {"kind": "PASTURE", "animal": "SHEEP",
                            "fed_today": False, "consecutive_unfed": primary_unfed}
        for ex, ey, unfed in extra_targets:
            self.tiles[ey][ex] = {"kind": "PASTURE", "animal": "SHEEP",
                                  "fed_today": False, "consecutive_unfed": unfed}

    def inventory(self, worker):
        return self.inventories[worker]

    def beside_shed(self, position):
        return tuple(position) in {(4, 4), (5, 4), (4, 5), (5, 5)}


def _tape():
    return [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(719)]


def _plan(step=500, target=(7, 4), tape=None, config=CONFIG,
          primary_unfed=1, extra_targets=()):
    tape = tape or _tape()
    r04._POLICY = _Policy(tape)
    return r04._v217_plan(
        _View(target=target, primary_unfed=primary_unfed, extra_targets=extra_targets),
        {"plan": 0, "v217_used": 0}, step,
        {"farmer": ["PASS"], "hands": [], "market": []}, [], config)


class V217EodTail(unittest.TestCase):
    def setUp(self):
        self._policy = r04._POLICY
        r04.V217_EOD_TAIL = False

    def tearDown(self):
        r04.V217_EOD_TAIL = False
        r04._POLICY = self._policy

    def test_key_ships_off_and_features_accept_it(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_v217_eod_tail"], False)
        self.assertIs(Features(**data).r04_v217_eod_tail, False)

    def test_disabled_keeps_existing_roundtrip_even_without_config(self):
        plan = _plan(target=(5, 4), config=None)
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], False)
        self.assertEqual(plan["commands"], [["EAST"], ["FEED"], ["WEST"]])
        self.assertEqual(plan["positions"], [(4, 4), (5, 4), (5, 4)])

    def test_enabled_reclaims_only_otherwise_unreachable_reverse_walk(self):
        r04.V217_EOD_TAIL = True
        plan = _plan(step=500, target=(7, 4))  # hour 20: four callbacks remain tonight
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], True)
        self.assertEqual(plan["commands"],
                         [["EAST"], ["EAST"], ["EAST"], ["FEED"]])
        self.assertEqual(plan["positions"],
                         [(4, 4), (5, 4), (6, 4), (7, 4)])

    def test_enabled_preserves_incumbent_roundtrip_when_it_already_fits(self):
        r04.V217_EOD_TAIL = True
        plan = _plan(target=(5, 4))
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], False)
        self.assertEqual(plan["commands"], [["EAST"], ["FEED"], ["WEST"]])

    def test_multiple_targets_cannot_tail_preempt_a_valid_incumbent_rescue(self):
        r04.V217_EOD_TAIL = True
        plan = _plan(target=(7, 4), primary_unfed=2, extra_targets=((5, 4, 1),))
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], False)
        self.assertEqual(plan["target"], (5, 4))
        self.assertEqual(plan["commands"], [["EAST"], ["FEED"], ["WEST"]])

    def test_same_far_route_is_unreachable_with_key_off(self):
        self.assertIsNone(_plan(step=500, target=(7, 4)))

    def test_future_native_farmer_work_blocks_tail(self):
        r04.V217_EOD_TAIL = True
        tape = _tape()
        tape[503]["farmer"] = ["WATER"]
        self.assertIsNone(_plan(step=500, target=(7, 4), tape=tape))

    def test_nonstandard_configuration_disables_new_tail_path(self):
        r04.V217_EOD_TAIL = True
        bad = dict(CONFIG)
        bad["episodeSteps"] = 696
        self.assertIsNone(_plan(target=(7, 4), config=bad))

    def test_bool_configuration_poison_disables_new_tail_path(self):
        r04.V217_EOD_TAIL = True
        bad = dict(CONFIG)
        bad["turnsPerDay"] = True
        self.assertIsNone(_plan(target=(7, 4), config=bad))

    def test_struct_standard_configuration_is_live_compatible(self):
        r04.V217_EOD_TAIL = True
        plan = _plan(step=500, target=(7, 4), config=_StructConfig(CONFIG))
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], True)

    def test_final_day_has_no_reset_credit(self):
        r04.V217_EOD_TAIL = True
        # Day 29 hour 20 has only steps 716..718; there is no next-day callback
        # on which a farmer reset can safely rejoin the authored route.
        self.assertIsNone(_plan(step=716, target=(6, 4)))

    def test_install_controls_flag(self):
        r04.install(v217_eod_tail=True)
        self.assertIs(r04.V217_EOD_TAIL, True)
        r04.install(v217_eod_tail=False)
        self.assertIs(r04.V217_EOD_TAIL, False)


if __name__ == "__main__":
    unittest.main()
