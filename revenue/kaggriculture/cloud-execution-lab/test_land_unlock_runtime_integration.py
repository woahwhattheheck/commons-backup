# SPDX-License-Identifier: Apache-2.0
"""Integration contracts joining the P02 certificate to its live state machine."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from land_unlock_runtime import LandUnlockOverlay
from land_unlock_timing_test_support import M, observation, row


def route_fixture(*, purchase, plant=100, water=101):
    route = [row() for _ in range(720)]
    route[purchase]["market"] = [["BUY_LAND"]]
    route[99]["farmer"] = ["EAST"]
    route[plant]["farmer"] = ["PLANT", "WHEAT"]
    route[water]["farmer"] = ["WATER"]
    return route


class Controller:
    def __init__(self, route):
        self.cur = "MAIN"
        self.R = {"MAIN": route}


def fake_agent(route):
    return SimpleNamespace(
        controller=Controller(route),
        diagnostics={"status": "completed"},
        features=SimpleNamespace(consumer="frozen", terminal_route=False),
        spatial=None,
        quadrant=None,
    )


def reached(step, *, unlocked=None, farmer=(4, 4), money=3000):
    obs = observation(step=step, money=money, unlocked=unlocked,
                      seeds={"WHEAT": 1}, farmer=farmer)
    return obs


class LiveP02IntegrationTests(unittest.TestCase):
    def test_real_certificate_advances_same_turn_purchase_before_plant(self):
        route = route_fixture(purchase=100)
        overlay = LandUnlockOverlay(mechanics=M, decision_steps=())
        agent = fake_agent(route)
        current = deepcopy(route[99])
        result, report = overlay.apply(agent, reached(99), {}, current)
        self.assertEqual(report["reason"], "advance_inserted")
        self.assertEqual(result["farmer"], ["EAST"])
        self.assertEqual(result["market"], [["BUY_LAND"]])

        original = deepcopy(route[100])
        result, report = overlay.apply(
            agent, reached(100, unlocked=["NW", "NE"], farmer=(5, 4)), {}, original)
        self.assertEqual(report["reason"], "original_suppressed")
        self.assertEqual(result["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(result["market"], [[]])

    def test_real_certificate_defers_early_purchase_to_latest_safe_turn(self):
        route = route_fixture(purchase=95)
        overlay = LandUnlockOverlay(mechanics=M, decision_steps=())
        agent = fake_agent(route)
        result, report = overlay.apply(agent, reached(95), {}, deepcopy(route[95]))
        self.assertEqual(report["reason"], "original_deferred")
        self.assertEqual(result["market"], [[]])

        for step in range(96, 99):
            result, _ = overlay.apply(agent, reached(step), {}, deepcopy(route[step]))
            self.assertEqual(result, route[step])
        result, report = overlay.apply(agent, reached(99), {}, deepcopy(route[99]))
        self.assertEqual(report["reason"], "deferred_inserted")
        self.assertEqual(result["farmer"], ["EAST"])
        self.assertEqual(result["market"], [["BUY_LAND"]])

    def test_real_certificate_refuses_unfunded_advance(self):
        route = route_fixture(purchase=100)
        overlay = LandUnlockOverlay(mechanics=M, decision_steps=())
        result, report = overlay.apply(
            fake_agent(route), reached(99, money=999), {}, deepcopy(route[99]))
        self.assertFalse(report["changed"])
        self.assertEqual(result, route[99])
        self.assertIn(report["reason"], {
            "no_funded_unlock_step_in_shift_window", "advance_recertification_failed"
        })


if __name__ == "__main__":
    unittest.main()
