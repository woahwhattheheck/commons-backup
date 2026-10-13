# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from types import SimpleNamespace
import unittest

from land_unlock_runtime import LandUnlockOverlay


class Cert:
    def __init__(self, original, target, plant=100, slot=0):
        self.original_step = original
        self.recommended_step = target
        self.first_plant_step = plant
        self.original_slot = slot
        self.quadrant = "NE"
        self.land_cost = 1000


class Analyzer:
    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = []

    def __call__(self, mechanics, obs, cfg, route, max_shift=4):
        self.calls.append((obs["step"], max_shift))
        if max_shift == 0:
            return Cert(obs["step"], obs["step"], obs["step"] + 1), {
                "certified": True,
                "reason": "recertified",
            }
        value = self.plans.pop(0) if self.plans else None
        return value, {
            "certified": value is not None,
            "reason": "planned" if value else "none",
        }


class Controller:
    def __init__(self, route):
        self.cur = "MAIN"
        self.R = {"MAIN": route}


def row(market=None):
    return {
        "farmer": ["PASS"],
        "hands": [],
        "market": [] if market is None else deepcopy(market),
    }


def obs(step, unlocked=1):
    farm = {
        "unlocked_quadrants": ["NW", "NE", "SW", "SE"][:unlocked],
        "money": 5000,
        "farmer": [4, 4],
        "hands": [],
        "tiles": [[None] * 10 for _ in range(10)],
    }
    return {
        "step": step,
        "player": 0,
        "farms": [farm, deepcopy(farm)],
        "private": {"seeds": {"WHEAT": 1}, "inventories": [{}], "shed": {}},
    }


def agent(route):
    return SimpleNamespace(
        controller=Controller(route),
        diagnostics={"status": "completed"},
        features=SimpleNamespace(consumer="frozen", terminal_route=False),
        spatial=None,
        quadrant=None,
    )


class StepZeroReplayTests(unittest.TestCase):
    def test_step_zero_replay_preserves_receipt_through_original_suppression(self):
        route = [row() for _ in range(3)]
        route[1] = row([["BUY_LAND"]])
        analyzer = Analyzer([Cert(1, 0)])
        overlay = LandUnlockOverlay(
            analyzer=analyzer,
            mechanics=object(),
            decision_steps=(),
        )
        a = agent(route)
        base = row()

        first, report = overlay.apply(a, obs(0), {}, base)
        self.assertEqual(report["reason"], "advance_inserted")
        self.assertEqual(first["market"], [["BUY_LAND"]])
        pending = deepcopy(overlay.pending)
        self.assertIsNotNone(pending)
        self.assertEqual(analyzer.calls, [(0, 4), (0, 0)])

        second, report = overlay.apply(a, obs(0), {}, base)
        self.assertEqual(second, first)
        self.assertEqual(report["reason"], "insert_replay")
        self.assertEqual(overlay.pending, pending)
        self.assertEqual(analyzer.calls, [(0, 4), (0, 0)])

        result, report = overlay.apply(a, obs(1, unlocked=2), {}, route[1])
        self.assertEqual(report["reason"], "original_suppressed")
        self.assertEqual(result["market"], [[]])
        self.assertIsNone(overlay.pending)


if __name__ == "__main__":
    unittest.main()
