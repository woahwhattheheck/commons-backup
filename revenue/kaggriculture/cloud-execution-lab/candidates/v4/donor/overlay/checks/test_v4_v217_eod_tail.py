# SPDX-License-Identifier: Apache-2.0
"""Focused checks for V4 ``r04_v217_eod_tail``.

Run in a materialised candidate package:

    python -B -m unittest -v checks/test_v4_v217_eod_tail.py
"""
from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_v217_eod_tail as tail  # noqa: E402
from titan_runtime import Features  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
          "farmHandCostMult": 1}


class _StructConfig:
    def __init__(self, values):
        for key, value in values.items():
            setattr(self, key, value)


class _ExplodingConfig:
    def __getattr__(self, _name):
        raise RuntimeError("poison config access")


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
    view = _View(target=target, primary_unfed=primary_unfed, extra_targets=extra_targets)
    state = {"plan": 0, "v217_used": 0}
    action = {"farmer": ["PASS"], "hands": [], "market": []}
    pending = []
    incumbent = r04._v217_plan(view, state, step, action, pending)
    if r04.V217_EOD_TAIL and incumbent is None:
        incumbent = tail.plan_v217_eod_tail(
            view, state, step, action, pending, tape=tape,
            projected_wheat=r04.projected_shed(action, view).get("WHEAT", 0),
            configuration=config, enabled=True,
        )
    return incumbent


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

    def test_predecessor_private_planner_signature_and_body_stay_v3_exact(self):
        self.assertEqual(
            tuple(inspect.signature(r04._v217_plan).parameters),
            ("view", "st", "step", "action", "pending"),
        )
        source = inspect.getsource(r04._v217_plan)
        self.assertNotIn("V217_EOD_TAIL", source)
        self.assertNotIn("configuration", source)
        self.assertNotIn("eod_tail", source)

    def test_matching_module_seam_is_positive_and_additive(self):
        source = (ROOT / "r04_full_router.py").read_text(encoding="utf-8")
        self.assertIn("if V217_EOD_TAIL and task is None:", source)
        self.assertIn("r04_v217_eod_tail.plan_v217_eod_tail(", source)

    def test_disabled_keeps_existing_roundtrip_even_without_config(self):
        plan = _plan(target=(5, 4), config=None)
        self.assertIsNotNone(plan)
        self.assertNotIn("eod_tail", plan)
        self.assertEqual(plan["commands"], [["EAST"], ["FEED"], ["WEST"]])
        self.assertEqual(plan["positions"], [(4, 4), (5, 4), (5, 4)])

    def test_enabled_reclaims_only_otherwise_unreachable_reverse_walk(self):
        r04.V217_EOD_TAIL = True
        plan = _plan(step=500, target=(7, 4))
        self.assertIsNotNone(plan)
        self.assertEqual(plan["commands"],
                         [["EAST"], ["EAST"], ["EAST"], ["FEED"]])
        self.assertEqual(plan["positions"],
                         [(4, 4), (5, 4), (6, 4), (7, 4)])

    def test_enabled_preserves_incumbent_roundtrip_when_it_already_fits(self):
        r04.V217_EOD_TAIL = True
        plan = _plan(target=(5, 4))
        self.assertIsNotNone(plan)
        self.assertEqual(plan["commands"], [["EAST"], ["FEED"], ["WEST"]])

    def test_multiple_targets_cannot_tail_preempt_a_valid_incumbent_rescue(self):
        r04.V217_EOD_TAIL = True
        plan = _plan(target=(7, 4), primary_unfed=2, extra_targets=((5, 4, 1),))
        self.assertIsNotNone(plan)
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

    def test_hostile_configuration_access_fails_closed_to_exact_roundtrip(self):
        forward = [["EAST"], ["EAST"], ["EAST"], ["FEED"]]
        roundtrip = forward + [["WEST"], ["WEST"], ["WEST"]]
        commands, eod_tail = tail.apply_v217_eod_tail(
            forward, roundtrip, targets=[(3, 4, 7)], step=500, end=504,
            farmer_rows=[["PASS"]] * 4,
            configuration=_ExplodingConfig(), enabled=True,
        )
        self.assertIs(commands, roundtrip)
        self.assertIs(eod_tail, False)

    def test_malformed_worker_wheat_fails_closed_in_additive_planner(self):
        tape = _tape()
        state = {"plan": 0, "v217_used": 0}
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        for bad_wheat in ("bad", True, 1.0, -1, None):
            view = _View(target=(7, 4), wheat=1)
            view.inventories = [{"WHEAT": bad_wheat}]
            with self.subTest(wheat=bad_wheat):
                self.assertIsNone(tail.plan_v217_eod_tail(
                    view, state, 500, action, [], tape=tape,
                    projected_wheat=8, configuration=CONFIG, enabled=True,
                ))

    def test_struct_standard_configuration_is_live_compatible(self):
        r04.V217_EOD_TAIL = True
        plan = _plan(step=500, target=(7, 4), config=_StructConfig(CONFIG))
        self.assertIsNotNone(plan)

    def test_final_day_has_no_reset_credit(self):
        r04.V217_EOD_TAIL = True
        self.assertIsNone(_plan(step=716, target=(6, 4)))

    def test_install_controls_flag(self):
        r04.install(v217_eod_tail=True)
        self.assertIs(r04.V217_EOD_TAIL, True)
        r04.install(v217_eod_tail=False)
        self.assertIs(r04.V217_EOD_TAIL, False)


if __name__ == "__main__":
    unittest.main()