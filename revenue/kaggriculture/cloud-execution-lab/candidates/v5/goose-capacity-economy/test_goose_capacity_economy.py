# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent

fake = types.ModuleType("r04_full_router")
fake._POLICY = None
def _native_day(native, day):
    return native.days[day]
fake._v219_native_day = _native_day
sys.modules["r04_full_router"] = fake

spec = importlib.util.spec_from_file_location("p02", HERE / "goose_capacity_economy.py")
p02 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p02)


class Native:
    def __init__(self, days):
        self.days = days


def day(hands=2, hire_hour=0, market_extra=0, hire_count=None):
    cards = []
    hire_count = hands if hire_count is None else hire_count
    for hour in range(24):
        market = [["SELL", "CARROT", 1] for _ in range(market_extra)]
        if hour == hire_hour:
            market = market + [["HIRE"] for _ in range(hire_count)]
        cards.append({"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hands)], "market": market})
    return cards


class P02Contracts(unittest.TestCase):
    def setUp(self):
        p02.reset()

    def test_projected_eggs_care_bound(self):
        self.assertEqual(p02._eggs(12), 30)
        self.assertEqual(p02._eggs(18), 18)

    def test_corrected_yield_blocks_old_phantom_payback(self):
        obs = {"market": {"prices": {"EGG": 50, "WHEAT": 22}}}
        with mock.patch.object(p02, "_schedule", return_value=({}, 0, 0)):
            record = p02._econ(obs, object(), 18, (4, 4), 0)
        self.assertEqual(record["eggs"], 18)
        self.assertEqual(record["margin"], 68)
        self.assertLess(record["margin"], p02.PAYBACK_MARGIN)
        old_two_unit_phantom = 2 * ((50 * 4) // 5)
        self.assertGreaterEqual(record["margin"] + old_two_unit_phantom, p02.PAYBACK_MARGIN)

    def test_schedule_rejects_late_route_hire(self):
        native = Native({d: day(hands=2, hire_hour=(22 if d == 13 else 0)) for d in range(12, 30)})
        self.assertIsNone(p02._schedule(native, 12, (7, 4), 0))

    def test_schedule_places_our_hires_after_parent_workforce(self):
        native = Native({d: day(hands=3, hire_hour=1) for d in range(12, 30)})
        schedule, hire_cost, _distance = p02._schedule(native, 12, (7, 4), 3)
        self.assertEqual(schedule[12], {"hour": 4, "expected": 3, "hire_ordinal": 3})
        self.assertGreater(hire_cost, 0)

    def test_schedule_prices_same_day_hires_not_standing_hands(self):
        native = Native({d: day(hands=8, hire_hour=1, hire_count=1) for d in range(12, 30)})
        schedule, hire_cost, _distance = p02._schedule(native, 12, (7, 4), 1)
        self.assertEqual(schedule[12]["expected"], 8)
        self.assertEqual(schedule[12]["hire_ordinal"], 1)
        self.assertEqual(schedule[13]["hire_ordinal"], 1)
        self.assertGreater(hire_cost, 0)

    def test_schedule_rejects_market_slot_exhaustion(self):
        native = Native({d: day(hands=2, hire_hour=0, market_extra=(7 if d == 12 else 0)) for d in range(12, 30)})
        self.assertIsNone(p02._schedule(native, 12, (5, 4), 2))

    def test_walk_is_deterministic(self):
        self.assertEqual(p02._walk([4, 4], (6, 5)), ["EAST"])
        self.assertEqual(p02._walk([6, 4], (6, 5)), ["SOUTH"])
        self.assertEqual(p02._walk([6, 5], (6, 5)), ["PASS"])

    def test_empty_coop_and_goose_count(self):
        tiles = [[None for _ in range(10)] for _ in range(10)]
        tiles[1][2] = {"kind": "COOP"}
        tiles[2][2] = {"kind": "COOP", "animal": "GOOSE"}
        farm = {"tiles": tiles}
        private = {"shed": {"GOOSE": 1}, "inventories": [{"GOOSE": 2}]}
        self.assertEqual(p02._empty_coops(farm), [(2, 1)])
        self.assertEqual(p02._geese(farm, private), 4)

    def test_disabled_identity(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertIs(p02.apply_goose_capacity_economy(action, {}, {}, enabled=False), action)

    def test_nonstandard_config_identity(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        cfg = dict(p02.CFG)
        cfg["shedCapacity"] = 99
        obs = {"step": 200, "player": 0, "farms": [{}, {}], "private": {}}
        self.assertIs(p02.apply_goose_capacity_economy(action, obs, cfg, enabled=True), action)

    def test_identical_same_step_replays_transformed_action_without_reentry(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        cfg = dict(p02.CFG)
        obs = {"step": 200, "player": 0, "farms": [{}, {}], "private": {}}

        def request(parent, _obs, state):
            state["phase"] = "requested"
            out = copy.deepcopy(parent)
            out["market"].append(["HIRE"])
            return out

        with mock.patch.object(p02, "_request", side_effect=request) as patched:
            first = p02.apply_goose_capacity_economy(action, obs, cfg, enabled=True)
            second = p02.apply_goose_capacity_economy(copy.deepcopy(action), copy.deepcopy(obs), cfg, enabled=True)
        self.assertEqual(first, second)
        self.assertEqual(first["market"], [["HIRE"]])
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(p02.STATE[0]["phase"], "requested")
        self.assertEqual(p02.telemetry["same_step_replay"], 1)

    def test_changed_same_step_bool_int_observation_is_not_replayed(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        cfg = dict(p02.CFG)
        obs = {
            "step": 200,
            "player": 0,
            "farms": [{"hires_today": 1}, {}],
            "private": {},
        }

        def request(parent, _obs, state):
            state["phase"] = "requested"
            out = copy.deepcopy(parent)
            out["market"].append(["HIRE"])
            return out

        changed = copy.deepcopy(obs)
        changed["farms"][0]["hires_today"] = True
        with mock.patch.object(p02, "_request", side_effect=request) as patched:
            first = p02.apply_goose_capacity_economy(action, obs, cfg, enabled=True)
            second = p02.apply_goose_capacity_economy(copy.deepcopy(action), changed, cfg, enabled=True)
        self.assertEqual(first["market"], [["HIRE"]])
        self.assertEqual(second, action)
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(p02.telemetry["same_step_changed"], 1)
        self.assertEqual(p02.telemetry["same_step_replay"], 0)

    def test_changed_same_step_restores_pre_step_state(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        cfg = dict(p02.CFG)
        obs = {"step": 200, "player": 0, "farms": [{}, {}], "private": {}}

        def request(parent, _obs, state):
            state["phase"] = "requested"
            state["target"] = (2, 2)
            out = copy.deepcopy(parent)
            out["market"].append(["HIRE"])
            return out

        changed = copy.deepcopy(obs)
        changed["private"] = {"revision": 1}
        with mock.patch.object(p02, "_request", side_effect=request) as patched:
            first = p02.apply_goose_capacity_economy(action, obs, cfg, enabled=True)
            second = p02.apply_goose_capacity_economy(copy.deepcopy(action), changed, cfg, enabled=True)
            third = p02.apply_goose_capacity_economy(copy.deepcopy(action), copy.deepcopy(changed), cfg, enabled=True)
            next_obs = copy.deepcopy(changed)
            next_obs["step"] = 201
            fourth = p02.apply_goose_capacity_economy(copy.deepcopy(action), next_obs, cfg, enabled=True)
        self.assertEqual(first["market"], [["HIRE"]])
        self.assertEqual(second, action)
        self.assertEqual(third, action)
        self.assertEqual(fourth["market"], [["HIRE"]])
        self.assertEqual(patched.call_count, 2)
        self.assertEqual(p02.STATE[0]["phase"], "requested")
        self.assertNotIn("target", p02.STATE[0].get("_retry_before", {}))

    def test_changed_same_step_discards_gameplay_telemetry(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        cfg = dict(p02.CFG)
        obs = {"step": 200, "player": 0, "farms": [{}, {}], "private": {}}

        def request(parent, _obs, state):
            state["phase"] = "requested"
            p02.telemetry["commit_requests"] += 1
            out = copy.deepcopy(parent)
            out["market"].append(["HIRE"])
            return out

        changed = copy.deepcopy(obs)
        changed["private"] = {"revision": 1}
        with mock.patch.object(p02, "_request", side_effect=request):
            first = p02.apply_goose_capacity_economy(action, obs, cfg, enabled=True)
            self.assertEqual(first["market"], [["HIRE"]])
            self.assertEqual(p02.telemetry["commit_requests"], 1)
            second = p02.apply_goose_capacity_economy(copy.deepcopy(action), changed, cfg, enabled=True)
        self.assertEqual(second, action)
        self.assertEqual(p02.telemetry["commit_requests"], 0)
        self.assertEqual(p02.telemetry["same_step_changed"], 1)


if __name__ == "__main__":
    unittest.main()
