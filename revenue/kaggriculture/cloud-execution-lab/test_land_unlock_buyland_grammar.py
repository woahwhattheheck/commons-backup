# SPDX-License-Identifier: Apache-2.0
"""Pinned-engine BUY_LAND grammar at the P02 live-overlay boundary."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from land_unlock_runtime import LandUnlockOverlay


class _Cert:
    def __init__(self, original, target, slot=0):
        self.original_step = original
        self.recommended_step = target
        self.first_plant_step = original + 1
        self.original_slot = slot
        self.quadrant = "NE"
        self.land_cost = 1000


class _Analyzer:
    def __init__(self):
        self.recertified_route = None

    def __call__(self, mechanics, observation, configuration, route, max_shift=4):
        now = observation["step"]
        if max_shift == 0:
            self.recertified_route = deepcopy(route)
            slot = next(
                i for i, order in enumerate(route[now]["market"])
                if isinstance(order, list) and order and order[0] == "BUY_LAND"
            )
            return _Cert(now, now, slot), {"certified": True, "reason": "recertified"}
        return _Cert(100, 99, 0), {"certified": True, "reason": "planned"}


class _Controller:
    def __init__(self, route):
        self.cur = "MAIN"
        self.R = {"MAIN": route}


def _row(market=None):
    return {
        "farmer": ["PASS"],
        "hands": [],
        "market": [] if market is None else deepcopy(market),
    }


def _observation(step, unlocked=1):
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
        "private": {"seeds": {}, "inventories": [{}], "shed": {}},
    }


def _agent(route):
    return SimpleNamespace(
        controller=_Controller(route),
        diagnostics={"status": "completed"},
        features=SimpleNamespace(consumer="frozen", terminal_route=False),
        spatial=None,
        quadrant=None,
    )


class LandUnlockBuyLandGrammarTests(unittest.TestCase):
    def test_trailing_fields_survive_parser_identity_and_fill_suppression(self):
        route = [_row() for _ in range(110)]
        represented = ["BUY_LAND", "receipt-tag", {"opaque": True}]
        route[100] = _row([represented])
        analyzer = _Analyzer()
        overlay = LandUnlockOverlay(
            analyzer=analyzer, mechanics=object(), decision_steps=()
        )
        actor = _agent(route)

        advanced, report = overlay.apply(actor, _observation(99), {}, _row())
        self.assertEqual(report["reason"], "advance_inserted")
        self.assertEqual(advanced["market"], [["BUY_LAND"]])
        self.assertEqual(route[100]["market"], [represented])
        self.assertIsNotNone(analyzer.recertified_route)
        self.assertEqual(analyzer.recertified_route[100]["market"], [[]])

        original_action = _row([represented])
        suppressed, report = overlay.apply(
            actor, _observation(100, unlocked=2), {}, original_action
        )
        self.assertEqual(report["reason"], "original_suppressed")
        self.assertEqual(suppressed["market"], [[]])
        self.assertEqual(original_action["market"], [represented])


if __name__ == "__main__":
    unittest.main()
