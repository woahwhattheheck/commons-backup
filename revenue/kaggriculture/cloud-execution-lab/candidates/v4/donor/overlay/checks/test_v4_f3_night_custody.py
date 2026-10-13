# SPDX-License-Identifier: Apache-2.0
"""F3 calendar proof, independent of legacy router materialization.

Run against the sibling helper or set TITAN_F3_SOURCE to another exact source.
The calendar oracle mirrors the pinned interpreter's reset and terminal tests:
(step + 1) % 24 == 0; terminal at step >= 720 - 2.
"""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if HERE.name == "checks" else HERE
SOURCE = Path(os.environ.get("TITAN_F3_SOURCE", str(ROOT / "r04_v217_eod_tail.py")))
spec = importlib.util.spec_from_file_location("f3_night_under_test", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load F3 helper")
tail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tail)

CONFIG = dict(episodeSteps=720, turnsPerDay=24, boardSize=10,
              shedCapacity=100, maxMarketOrdersPerTurn=10)
TAPE = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(719)]


class View:
    def __init__(self, target=(7, 4), wheat=1):
        self.positions = [(4, 4)]
        self.inventories = [{"WHEAT": wheat}] if wheat else [{}]
        self.tiles = [[None for _ in range(10)] for _ in range(10)]
        x, y = target
        self.tiles[y][x] = dict(animal="SHEEP", kind="PASTURE",
                               fed_today=False, consecutive_unfed=1)

    def inventory(self, worker):
        return self.inventories[worker]

    def beside_shed(self, position):
        return tuple(position) in {(4, 4), (5, 4), (4, 5), (5, 5)}


class MustNotRead:
    def __iter__(self):
        raise AssertionError("invalid calendar reached pending actions")

    @property
    def positions(self):
        raise AssertionError("invalid calendar reached runtime view")


class F3NightCustody(unittest.TestCase):
    def plan(self, step=500, *, view=None, tape=None, config=None,
             projected_wheat=8, enabled=True, state=None, pending=None):
        return tail.plan_v217_eod_tail(
            View() if view is None else view,
            {"plan": 7, "v217_used": 0} if state is None else state,
            step, {"farmer": ["PASS"], "hands": [], "market": []},
            [] if pending is None else pending,
            tape=TAPE if tape is None else tape,
            projected_wheat=projected_wheat,
            configuration=CONFIG if config is None else config,
            enabled=enabled,
        )

    def select(self, step, end, *, enabled=True, config=None):
        count = end - step if type(step) is int and type(end) is int else 4
        count = max(1, min(32, count))
        forward = [["EAST"] for _ in range(count - 1)] + [["FEED"]]
        roundtrip = forward + [["WEST"]]
        before = copy.deepcopy((forward, roundtrip))
        result, selected = tail.apply_v217_eod_tail(
            forward, roundtrip, targets=[(3, 4, 7)], step=step, end=end,
            farmer_rows=[["PASS"] for _ in forward],
            configuration=CONFIG if config is None else config, enabled=enabled,
        )
        self.assertEqual((forward, roundtrip), before)
        self.assertIs(result, forward if selected else roundtrip)
        return selected

    def test_forged_early_night_is_rejected(self):
        self.assertFalse(self.select(500, 503))

    def test_forged_late_night_is_rejected(self):
        self.assertFalse(self.select(500, 505))

    def test_negative_step_cannot_index_tape_from_end(self):
        self.assertIsNone(self.plan(-4))

    def test_exhaustive_calendar_selector(self):
        # 816 steps x 7 alleged night boundaries = 5,712 determinate cases.
        for step in range(-48, 768):
            actual_end = (step // 24 + 1) * 24
            for delta in range(-3, 4):
                end = actual_end + delta
                expected = (0 <= step <= 718 and 16 <= step % 24 <= 21
                            and end == actual_end and end < 719)
                with self.subTest(step=step, end=end):
                    self.assertEqual(self.select(step, end), expected)

    def test_entire_actionable_calendar_planner(self):
        # A distance-three held-WHEAT route has four callbacks. Only hour20
        # across the 29 real-reset days can meet the exact tail theorem.
        admitted = []
        for step in range(719):
            result = self.plan(step)
            expected = step % 24 == 20 and step < 696
            with self.subTest(step=step):
                self.assertEqual(result is not None, expected)
            if result is not None:
                admitted.append(step)
                self.assertEqual(result["step"], step)
                self.assertEqual(result["commands"][-1], ["FEED"])
                last_callback = step + len(result["commands"]) - 1
                self.assertEqual((last_callback + 1) % 24, 0)
                self.assertLess(last_callback, 718)
        self.assertEqual(len(admitted), 29)

    def test_invalid_time_fails_before_stateful_work(self):
        for step in (-52, -28, -4, -1, 712, 713, 714, 715, 716, 717,
                     718, 719, 720, 740, 10**100, True, False, 500.0,
                     "500", None, [], {}):
            with self.subTest(step=step):
                self.assertIsNone(self.plan(step, view=MustNotRead(),
                                            pending=MustNotRead()))

    def test_exact_types_and_off_identity(self):
        for value in (True, False, 500.0, "500", None, [], {}):
            with self.subTest(value=value):
                self.assertFalse(self.select(value, 504))
                self.assertFalse(self.select(500, value))
        self.assertFalse(self.select(500, 504, enabled=False))
        self.assertIsNone(self.plan(-4, view=MustNotRead(), enabled=False))

    def test_last_real_night_and_final_partial_day(self):
        self.assertTrue(self.select(692, 696))
        self.assertFalse(self.select(716, 719))
        self.assertFalse(self.select(716, 720))
        self.assertIsNotNone(self.plan(692))
        self.assertIsNone(self.plan(716))

    def test_held_wheat_route_and_task_shape_preserved(self):
        result = self.plan()
        self.assertEqual(result, {
            "step": 500, "route": 7,
            "commands": [["EAST"], ["EAST"], ["EAST"], ["FEED"]],
            "positions": [(4, 4), (5, 4), (6, 4), (7, 4)],
            "target": (7, 4),
        })
        self.assertIsNone(self.plan(view=View(target=(6, 4))))

    def test_pickup_route_and_reserve_preserved(self):
        result = self.plan(view=View(target=(6, 4), wheat=0))
        self.assertIsNotNone(result)
        self.assertEqual(result["commands"],
                         [["PICKUP", "WHEAT"], ["EAST"], ["EAST"], ["FEED"]])
        self.assertIsNone(self.plan(view=View(target=(6, 4), wheat=0),
                                    projected_wheat=1))

    def test_standard_config_and_struct_retained(self):
        self.assertIsNotNone(self.plan(config=SimpleNamespace(**CONFIG)))
        for key in CONFIG:
            for invalid in (True, False, None, str(CONFIG[key]), CONFIG[key] + 1):
                cfg = dict(CONFIG, **{key: invalid})
                with self.subTest(key=key, value=invalid):
                    self.assertIsNone(self.plan(config=cfg))
        self.assertIsNone(self.plan(config={}))

    def test_admission_and_input_nonmutation_preserved(self):
        view, tape, state, pending = View(), copy.deepcopy(TAPE), {"plan": 7}, []
        before = copy.deepcopy((vars(view), tape, state, pending))
        self.assertIsNotNone(self.plan(view=view, tape=tape, state=state, pending=pending))
        self.assertEqual((vars(view), tape, state, pending), before)
        self.assertIsNone(self.plan(state={"v217_used": 2}))
        tape[502]["farmer"] = ["WATER"]
        self.assertIsNone(self.plan(tape=tape))
        self.assertIsNone(self.plan(tape=TAPE[:503]))
        view.tiles[3][3] = dict(animal="SHEEP", fed_today=False, consecutive_unfed=1)
        self.assertIsNone(self.plan(view=view))


if __name__ == "__main__":
    unittest.main()
