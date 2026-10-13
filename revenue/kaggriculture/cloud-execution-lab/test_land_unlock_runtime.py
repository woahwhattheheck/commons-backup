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
        self.calls.append((obs["step"], max_shift, deepcopy(route[obs["step"]])))
        if max_shift == 0:
            return Cert(obs["step"], obs["step"], obs["step"] + 1,
                        next(i for i,o in enumerate(route[obs["step"]]["market"]) if o == ["BUY_LAND"])), {"certified": True, "reason": "recertified"}
        key = (obs["step"], tuple(tuple(o) for o in route[obs["step"]]["market"]))
        value = self.plans.pop(0) if self.plans else None
        return (value, {"certified": value is not None, "reason": "planned" if value else "none"})


class RejectRecertification(Analyzer):
    def __call__(self, mechanics, obs, cfg, route, max_shift=4):
        if max_shift == 0:
            self.calls.append((obs["step"], max_shift, deepcopy(route[obs["step"]])))
            return None, {"certified": False, "reason": "target_cash_changed"}
        return super().__call__(mechanics, obs, cfg, route, max_shift=max_shift)


class Controller:
    def __init__(self, route):
        self.cur = "MAIN"
        self.R = {"MAIN": route}


def row(market=None):
    return {"farmer": ["PASS"], "hands": [], "market": [] if market is None else deepcopy(market)}


def obs(step, unlocked=1):
    farm = {"unlocked_quadrants": ["NW", "NE", "SW", "SE"][:unlocked], "money": 5000,
            "farmer": [4,4], "hands": [], "tiles": [[None]*10 for _ in range(10)]}
    return {"step": step, "player": 0, "farms": [farm, deepcopy(farm)],
            "private": {"seeds": {"WHEAT": 1}, "inventories": [{}], "shed": {}}}


def agent(route, status="completed"):
    return SimpleNamespace(controller=Controller(route), diagnostics={"status": status},
                           features=SimpleNamespace(consumer="frozen", terminal_route=False),
                           spatial=None, quadrant=None)


class OverlayTests(unittest.TestCase):
    def test_advance_is_inserted_then_only_observed_fill_suppresses_original(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        analyzer = Analyzer([Cert(100, 99)])
        overlay = LandUnlockOverlay(analyzer=analyzer, mechanics=object(), decision_steps=())
        a = agent(route)
        result, report = overlay.apply(a, obs(99), {}, row())
        self.assertEqual(report["reason"], "advance_inserted")
        self.assertEqual(result["market"], [["BUY_LAND"]])
        result, report = overlay.apply(a, obs(100, unlocked=2), {}, row([["BUY_LAND"]]))
        self.assertEqual(report["reason"], "original_suppressed")
        self.assertEqual(result["market"], [[]])

    def test_failed_advance_keeps_original(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        a = agent(route)
        overlay.apply(a, obs(99), {}, row())
        result, report = overlay.apply(a, obs(100, unlocked=1), {}, row([["BUY_LAND"]]))
        self.assertEqual(report["reason"], "fill_not_confirmed")
        self.assertEqual(result["market"], [["BUY_LAND"]])

    def test_deferral_removes_then_recertifies_and_inserts(self):
        route = [row() for _ in range(110)]
        route[95] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(95, 99)]), mechanics=object(), decision_steps=())
        a = agent(route)
        result, report = overlay.apply(a, obs(95), {}, route[95])
        self.assertEqual(report["reason"], "original_deferred")
        self.assertEqual(result["market"], [[]])
        for step in (96, 97, 98):
            result, report = overlay.apply(a, obs(step), {}, row())
            self.assertEqual(result, row())
        result, report = overlay.apply(a, obs(99), {}, row())
        self.assertEqual(report["reason"], "deferred_inserted")
        self.assertEqual(result["market"], [["BUY_LAND"]])
        result, report = overlay.apply(a, obs(100, unlocked=2), {}, row())
        self.assertEqual(report["reason"], "deferred_fill_confirmed")
        self.assertIsNone(overlay.pending)

    def test_route_decision_barrier_blocks_move(self):
        route = [row() for _ in range(110)]
        route[95] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(95, 99, plant=100)]), mechanics=object(), decision_steps=(98,))
        result, report = overlay.apply(agent(route), obs(95), {}, route[95])
        self.assertEqual(report["reason"], "route_decision_barrier")
        self.assertEqual(result, route[95])

    def test_deadline_fallback_does_not_start_new_move(self):
        route = [row() for _ in range(110)]
        route[95] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(95, 99)]), mechanics=object(), decision_steps=())
        result, report = overlay.apply(agent(route, status="deadline_fallback"), obs(95), {}, route[95])
        self.assertEqual(report["reason"], "producer_not_completed")
        self.assertEqual(result, route[95])

    def test_same_step_replays_deferral_without_duplicate_state(self):
        route = [row() for _ in range(110)]
        route[95] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(95, 99)]), mechanics=object(), decision_steps=())
        a = agent(route)
        first, _ = overlay.apply(a, obs(95), {}, route[95])
        second, report = overlay.apply(a, obs(95), {}, route[95])
        self.assertEqual(first, second)
        self.assertEqual(report["reason"], "defer_replay")

    def test_route_switch_releases_pending_without_touching_action(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        a = agent(route)
        overlay.apply(a, obs(99), {}, row())
        a.controller.R["ALT"] = route
        a.controller.cur = "ALT"
        action = row([["BUY_LAND"]])
        result, report = overlay.apply(a, obs(100, unlocked=2), {}, action)
        self.assertEqual(report["reason"], "route_changed")
        self.assertEqual(result, action)

    def test_advance_mode_never_defers(self):
        route = [row() for _ in range(110)]
        route[95] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(95, 99)]), mechanics=object(), decision_steps=(), mode="advance")
        result, report = overlay.apply(agent(route), obs(95), {}, route[95])
        self.assertEqual(report["reason"], "deferral_disabled")
        self.assertEqual(result, route[95])

    def test_insertion_preserves_existing_market_prefix_and_uses_trailing_slack(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        a = agent(route)
        current = row([["SELL", "WHEAT", 1], ["HIRE"]])
        result, report = overlay.apply(a, obs(99), {}, current)
        self.assertEqual(report["reason"], "advance_inserted")
        self.assertEqual(result["market"], [["SELL", "WHEAT", 1], ["HIRE"], ["BUY_LAND"]])
        self.assertEqual(current["market"], [["SELL", "WHEAT", 1], ["HIRE"]])

    def test_deferred_target_recertification_failure_does_not_mutate_target_action(self):
        route = [row() for _ in range(110)]
        route[95] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=RejectRecertification([Cert(95, 99)]), mechanics=object(), decision_steps=())
        a = agent(route)
        removed, report = overlay.apply(a, obs(95), {}, route[95])
        self.assertTrue(report["changed"])
        self.assertEqual(removed["market"], [[]])
        for step in (96, 97, 98):
            overlay.apply(a, obs(step), {}, row())
        target = row([["SELL", "WHEAT", 1]])
        result, report = overlay.apply(a, obs(99), {}, target)
        self.assertEqual(report["reason"], "deferred_recertification_failed")
        self.assertEqual(result, target)
        self.assertIsNone(overlay.pending)

    def test_same_step_replays_inserted_advance_exactly(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        a = agent(route)
        action = row([["SELL", "WHEAT", 1]])
        first, _ = overlay.apply(a, obs(99), {}, action)
        second, report = overlay.apply(a, obs(99), {}, action)
        self.assertEqual(first, second)
        self.assertEqual(report["reason"], "insert_replay")

    def test_backward_step_resets_pending_before_new_match_action(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        a = agent(route)
        overlay.apply(a, obs(99), {}, row())
        self.assertIsNotNone(overlay.pending)
        result, report = overlay.apply(a, obs(0), {}, row())
        self.assertEqual(result, row())
        self.assertIsNone(overlay.pending)
        self.assertIn(report["reason"], {"no_nearby_land_purchase", "none"})

    def test_zero_market_cap_matches_engine_effective_one_slot_for_advance(self):
        route = [row() for _ in range(110)]
        route[100] = row([["BUY_LAND"]])
        overlay = LandUnlockOverlay(analyzer=Analyzer([Cert(100, 99)]), mechanics=object(), decision_steps=())
        result, report = overlay.apply(
            agent(route), obs(99), {"maxMarketOrdersPerTurn": 0}, row())
        self.assertEqual(report["reason"], "advance_inserted")
        self.assertEqual(result["market"], [["BUY_LAND"]])

    def test_negative_market_cap_does_not_treat_tail_land_as_executable(self):
        route = [row() for _ in range(110)]
        route[95] = row([
            ["SELL", "WHEAT", 1],
            ["BUY_LAND"],
            ["SELL", "CARROT", 1],
        ])
        overlay = LandUnlockOverlay(
            analyzer=Analyzer([Cert(95, 99, slot=1)]), mechanics=object(), decision_steps=())
        original = deepcopy(route[95])
        result, report = overlay.apply(
            agent(route), obs(95), {"maxMarketOrdersPerTurn": -3}, original)
        self.assertEqual(report["reason"], "no_nearby_land_purchase")
        self.assertEqual(result, original)
        self.assertIsNone(overlay.pending)


if __name__ == "__main__":
    unittest.main()
