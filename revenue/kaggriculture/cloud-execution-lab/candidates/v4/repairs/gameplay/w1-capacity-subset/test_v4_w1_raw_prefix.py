# SPDX-License-Identifier: Apache-2.0
"""W1 raw-market-prefix regression and exact official-interpreter checks.

Run beside the W1 helper with TITAN_W1_ENGINE=/path/to/kaggriculture.py.
The adjacent official kaggriculture.json is also mandatory. Missing or drifted
engine inputs are errors, never skips. Tests construct public day-28 states;
there are no full-game, packaged-router, or competitive-economics claims.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

import r04_dead_water_harvest as lane

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SPEC_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
CONFIG = {"episodeSteps": 720, "turnsPerDay": 24,
          "boardSize": 10, "shedCapacity": 100}
ABSENT = object()
BAD_ROWS = [None, [], ["BUY_PRODUCT", "WHEAT", 100],
            ["BUY_ANIMAL", "COW", 1], ["SELL"],
            ["HIRE", "extra"], "BUY_PRODUCT", {"unknown": 1}]
COUNTS = {"interpreter_calls": 0, "paired_worlds": 0,
          "suffix_equivalence_worlds": 0, "prefix_contract_cases": 0}


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_engine():
    value = os.environ.get("TITAN_W1_ENGINE")
    if not value:
        raise RuntimeError("TITAN_W1_ENGINE is required; no engine tests were skipped")
    path = Path(value).resolve(strict=True)
    data = path.read_bytes()
    if blob(data) != ENGINE_BLOB:
        raise RuntimeError("Official engine byte identity mismatch")
    spec_path = path.with_name("kaggriculture.json")
    if not spec_path.is_file() or blob(spec_path.read_bytes()) != SPEC_BLOB:
        raise RuntimeError("Exact adjacent official kaggriculture.json is required")
    # Only the unused initializer's seed resolver needs an import adapter.
    # Every tested market/unit/EOD transition executes the full official module.
    utils = types.ModuleType("kaggle_environments.utils")
    def unused_seed_resolver(*args, **kwargs):
        raise AssertionError("These constructed-state tests must not call initialization")
    utils.resolve_episode_seed = unused_seed_resolver
    package = types.ModuleType("kaggle_environments")
    package.__path__ = []
    spec = importlib.util.spec_from_file_location("w1_official_engine", path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"kaggle_environments": package,
                                      "kaggle_environments.utils": utils}):
        spec.loader.exec_module(module)
    return module


def fixture(weights=(2, 2), room=2, *, seat=0):
    board = [[None for _ in range(10)] for _ in range(10)]
    positions = [[i % 5, i // 5] for i in range(len(weights))]
    for (x, y), units in zip(positions, weights):
        board[y][x] = {"kind": "PLANT", "crop": "TOMATO", "planted_day": 18,
                       "yield_units": units, "watered_today": True,
                       "max_lifespan_step": -1, "consecutive_unwatered": 0,
                       "fertilized_until_day": -1}
    farm = {"tiles": board, "farmer": positions[0], "hands": positions[1:],
            "money": 3000.0, "unlocked_quadrants": ["NW"],
            "hires_today": len(weights) - 1}
    private = {"shed": {"WHEAT": 100 - room}, "seeds": {},
               "inventories": [{} for _ in weights]}
    obs = {"step": 695, "day": 28, "hour": 23, "player": seat,
           "farms": [copy.deepcopy(farm), copy.deepcopy(farm)], "private": private}
    action = {"farmer": ["WATER"], "hands": [["WATER"] for _ in weights[1:]],
              "market": []}
    return obs, action


def configuration(cap=ABSENT):
    result = dict(CONFIG)
    if cap is not ABSENT:
        result["maxMarketOrdersPerTurn"] = cap
    return result


def selected(action):
    return tuple(i for i, row in enumerate([action["farmer"]] + action["hands"])
                 if row == ["HARVEST"])


def run_world(engine, observation, action, cfg, rival_market=None):
    """One full unit -> market -> town -> EOD interpreter callback, no substitutes."""
    seat = observation["player"]
    farms = copy.deepcopy(observation["farms"])
    market = engine._new_market()
    town = engine._new_town()
    town["unlocked_shops"] = ["PIZZA_SHOP", "FARMERS_MARKET"]
    states = []
    for player in (0, 1):
        private = (copy.deepcopy(observation["private"]) if player == seat
                   else engine._new_private())
        if player != seat:
            private["inventories"] = [{} for _ in range(1 + len(farms[player]["hands"]))]
        own_action = copy.deepcopy(action) if player == seat else {
            "farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rival_market or [])}
        obs = types.SimpleNamespace(step=695, day=28, hour=23, player=player,
                                    farms=farms, market=market, town=town, private=private)
        states.append(types.SimpleNamespace(observation=obs, action=own_action,
                                            status="ACTIVE", reward=0))
    env = types.SimpleNamespace(configuration=types.SimpleNamespace(**cfg),
                                info={"seed": 911}, done=False)
    engine.interpreter(states, env)
    COUNTS["interpreter_calls"] += 1
    return {"farms": copy.deepcopy(farms), "market": copy.deepcopy(market),
            "town": copy.deepcopy(town),
            "privates": [copy.deepcopy(s.observation.private) for s in states],
            "clock": [(s.observation.day, s.observation.hour) for s in states]}


class RawPrefixTest(unittest.TestCase):
    def setUp(self):
        lane.reset()

    def apply(self, obs, action, cap=ABSENT):
        return lane.apply_dead_water_harvest(obs, action, configuration(cap), enabled=True)

    def test_suffix_inflow_and_junk_do_not_veto_recovery(self):
        for seat, cap, bad in itertools.product((0, 1), (ABSENT, -7, 0, 1, 2, 10, 11), BAD_ROWS):
            with self.subTest(seat=seat, cap=cap, row=bad):
                obs, action = fixture(seat=seat)
                n = 10 if cap is ABSENT else max(1, cap)
                action["market"] = [["BUY_SEED", "WHEAT", 1] for _ in range(n)] + [bad]
                before = copy.deepcopy((obs, action))
                out = self.apply(obs, action, cap)
                self.assertEqual(selected(out), (0,))
                self.assertIs(out["market"], action["market"])
                self.assertEqual((obs, action), before)
                COUNTS["prefix_contract_cases"] += 1

    def test_same_suffix_row_becomes_a_veto_when_inside_prefix(self):
        for bad in BAD_ROWS:
            obs, action = fixture()
            action["market"] = [["BUY_SEED", "WHEAT", 1], bad]
            self.assertEqual(selected(self.apply(obs, action, 1)), (0,))
            self.assertIs(self.apply(obs, action, 2), action)

    def test_zero_and_negative_caps_execute_one_raw_slot(self):
        for cap in (0, -1, -100):
            obs, action = fixture()
            action["market"] = [["BUY_PRODUCT", "WHEAT", 1]]
            self.assertIs(self.apply(obs, action, cap), action)

    def test_raw_placeholders_are_not_filtered_or_treated_as_safe(self):
        for blank in ([], None, False, "", {}):
            obs, action = fixture()
            action["market"] = [blank, ["BUY_SEED", "WHEAT", 1]]
            self.assertIs(self.apply(obs, action, 1), action)

    def test_explicit_noninteger_caps_fail_closed(self):
        class IntSubclass(int):
            pass
        for cap in (True, False, 1.0, "1", None, [], {}, IntSubclass(1)):
            obs, action = fixture()
            self.assertIs(self.apply(obs, action, cap), action)
            self.assertEqual(lane.get_report()["recovered"], 0)

    def test_missing_cap_and_attribute_configuration_use_engine_default(self):
        for cap in (ABSENT, 1, 2, 10):
            obs, action = fixture()
            n = 10 if cap is ABSENT else cap
            action["market"] = [["BUY_SEED", "WHEAT", 1] for _ in range(n)] + BAD_ROWS
            cfg = types.SimpleNamespace(**configuration(cap))
            out = lane.apply_dead_water_harvest(obs, action, cfg)
            self.assertEqual(selected(out), (0,))

    def test_unreadable_cap_is_not_silently_defaulted(self):
        class BrokenConfig:
            episodeSteps, turnsPerDay, boardSize, shedCapacity = 720, 24, 10, 100
            @property
            def maxMarketOrdersPerTurn(self):
                raise RuntimeError("configuration unavailable")
        obs, action = fixture()
        self.assertIs(lane.apply_dead_water_harvest(obs, action, BrokenConfig()), action)

    def test_huge_cap_does_not_allocate_or_hide_an_active_bad_row(self):
        obs, action = fixture()
        action["market"] = [["BUY_SEED", "WHEAT", 1]]
        self.assertEqual(selected(self.apply(obs, action, 10 ** 1000)), (0,))
        action["market"].append(["BUY_PRODUCT", "WHEAT", 1])
        self.assertIs(self.apply(obs, action, 10 ** 1000), action)

    def test_disabled_key_preserves_identity_without_consulting_cap(self):
        obs, action = fixture()
        self.assertIs(lane.apply_dead_water_harvest(obs, action, configuration(None),
                                                  enabled=False), action)
        self.assertEqual(lane.get_report()["steps_active"], 0)

    def test_capacity_and_day_guards_still_bind(self):
        for room, step in ((1, 695), (2, 694), (2, 696), (2, 718)):
            obs, action = fixture(room=room)
            obs.update(step=step, day=step // 24)
            action["market"] = [["BUY_SEED", "WHEAT", 1], BAD_ROWS[2]]
            self.assertIs(self.apply(obs, action, 1), action)

    def test_bounded_and_empty_markets_keep_the_original_contract(self):
        for market in ([], [["SELL", "WHEAT", 1]], [["BUY_SEED", "WHEAT", 1]],
                       [["HIRE"]], [["BUY_LAND"]]):
            obs, action = fixture()
            action["market"] = market
            self.assertEqual(selected(self.apply(obs, action)), (0,))
        for market in (None, (), "market", {"SELL": 1}):
            obs, action = fixture()
            action["market"] = market
            self.assertIs(self.apply(obs, action), action)

    def test_no_future_sale_or_suffix_room_credit(self):
        obs, action = fixture(room=1)
        action["market"] = [["SELL", "WHEAT", 98], ["SELL", "WHEAT", 98]]
        self.assertIs(self.apply(obs, action, 1), action)


class OfficialEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine()

    def test_both_seat_eod_delivery_and_suffix_equivalence(self):
        cases = 0
        for seat, cap, bad, weights in itertools.product(
                (0, 1), (ABSENT, -7, 0, 1, 2, 10, 11), BAD_ROWS,
                ((2, 2), (3, 2), (1, 1), (4, 4))):
            with self.subTest(seat=seat, cap=cap, row=bad, weights=weights):
                room = 2 if weights != (4, 4) else 4
                obs, action = fixture(weights, room, seat=seat)
                cfg = configuration(cap)
                n = 10 if cap is ABSENT else max(1, cap)
                action["market"] = [["BUY_SEED", "WHEAT", 1] for _ in range(n)] + [bad]
                before = copy.deepcopy((obs, action))
                lane.reset()
                out = lane.apply_dead_water_harvest(obs, action, cfg)
                self.assertTrue(selected(out))
                baseline = run_world(self.engine, obs, action, cfg, [["BUY_PRODUCT", "WHEAT", 1]])
                actual = run_world(self.engine, obs, out, cfg, [["BUY_PRODUCT", "WHEAT", 1]])
                truncated = copy.deepcopy(out)
                truncated["market"] = truncated["market"][:n]
                reference = run_world(self.engine, obs, truncated, cfg, [["BUY_PRODUCT", "WHEAT", 1]])
                self.assertEqual(actual, reference)
                recovered = sum(weights[i] for i in selected(out))
                expected = copy.deepcopy(baseline["privates"][seat])
                expected["shed"]["TOMATO"] = expected["shed"].get("TOMATO", 0) + recovered
                self.assertEqual(actual["privates"][seat], expected)
                self.assertLessEqual(sum(actual["privates"][seat]["shed"].values()), 100)
                self.assertEqual(actual["privates"][1 - seat], baseline["privates"][1 - seat])
                self.assertEqual(actual["farms"][1 - seat], baseline["farms"][1 - seat])
                self.assertEqual([f["money"] for f in actual["farms"]],
                                 [f["money"] for f in baseline["farms"]])
                self.assertEqual(actual["market"], baseline["market"])
                self.assertEqual(actual["town"], baseline["town"])
                self.assertEqual(actual["clock"], [(29, 0), (29, 0)])
                self.assertEqual((obs, action), before)
                cases += 1
        self.assertEqual(cases, 448)
        COUNTS["paired_worlds"] += cases
        COUNTS["suffix_equivalence_worlds"] += cases

    def test_raw_slot_limit_precedes_engine_order_parsing(self):
        for seat in (0, 1):
            obs, action = fixture(seat=seat)
            cfg = configuration(1)
            action["market"] = [[], ["BUY_PRODUCT", "WHEAT", 1]]
            actual = run_world(self.engine, obs, action, cfg)
            base = copy.deepcopy(action)
            base["market"] = [[]]
            reference = run_world(self.engine, obs, base, cfg)
            self.assertEqual(actual, reference)
            self.assertEqual(actual["privates"][seat]["shed"]["WHEAT"], 98)

    def test_active_inflow_would_consume_reserved_harvest_room(self):
        for seat in (0, 1):
            obs, action = fixture(seat=seat)
            action["market"] = [["BUY_SEED", "WHEAT", 1], ["BUY_PRODUCT", "WHEAT", 1]]
            cfg = configuration(2)
            self.assertIs(lane.apply_dead_water_harvest(obs, action, cfg), action)
            unsafe = copy.deepcopy(action)
            unsafe["farmer"] = ["HARVEST"]
            actual = run_world(self.engine, obs, unsafe, cfg)
            self.assertEqual(actual["privates"][seat]["shed"]["TOMATO"], 1)
            self.assertEqual(sum(actual["privates"][seat]["shed"].values()), 100)


if __name__ == "__main__":
    result = unittest.main(exit=False)
    print("W1_RAW_PREFIX_COUNTS", COUNTS, flush=True)
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
