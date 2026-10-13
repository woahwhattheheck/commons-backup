# SPDX-License-Identifier: Apache-2.0
"""Boundary regression for the V4 V217 EOD-tail reset theorem."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402

CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


class _Policy:
    def __init__(self, tape):
        self.tapes = [tape]


class _View:
    def __init__(self, target):
        self.positions = [(4, 4)]
        self.inventories = [{"WHEAT": 1}]
        self.shed = {"WHEAT": 8}
        self.tiles = [[None for _ in range(10)] for _ in range(10)]
        x, y = target
        self.tiles[y][x] = {
            "kind": "PASTURE",
            "animal": "SHEEP",
            "fed_today": False,
            "consecutive_unfed": 1,
        }

    def inventory(self, worker):
        return self.inventories[worker]

    def beside_shed(self, position):
        return tuple(position) in {(4, 4), (5, 4), (4, 5), (5, 5)}


def _plan(target):
    tape = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(719)]
    r04._POLICY = _Policy(tape)
    return r04._v217_plan(
        _View(target),
        {"plan": 0, "v217_used": 0},
        500,  # day 20, hour 20: callbacks 500..503 remain before EOD reset
        {"farmer": ["PASS"], "hands": [], "market": []},
        [],
        CONFIG,
    )


class V217EodTailResetBoundary(unittest.TestCase):
    def setUp(self):
        self._policy = r04._POLICY
        self._flag = r04.V217_EOD_TAIL
        r04.V217_EOD_TAIL = True

    def tearDown(self):
        r04.V217_EOD_TAIL = self._flag
        r04._POLICY = self._policy

    def test_feed_must_land_on_final_pre_reset_callback(self):
        # Distance two gives EAST,EAST,FEED: the rescue would finish at hour 22,
        # leaving hour 23 to observe the farmer stranded at the sheep. The
        # nightly reset cannot justify dropping the return leg in that case.
        self.assertIsNone(_plan((6, 4)))

    def test_exact_boundary_tail_remains_reachable(self):
        # Distance three gives EAST,EAST,EAST,FEED: FEED executes on hour 23 and
        # the engine resets the farmer immediately after that callback.
        plan = _plan((7, 4))
        self.assertIsNotNone(plan)
        self.assertIs(plan["eod_tail"], True)
        self.assertEqual(
            plan["commands"],
            [["EAST"], ["EAST"], ["EAST"], ["FEED"]],
        )


if __name__ == "__main__":
    unittest.main()
