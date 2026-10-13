# SPDX-License-Identifier: Apache-2.0
"""V3.1 lane L2 (r04_strawberry_endgame): bounded late wheat->strawberry conversion.

    python -m unittest -v checks/test_v3_r04_strawberry.py

Covers the seed gate, the [576, 648] window, the per-game and per-step caps, the
per-player game-reset counters, that non-WHEAT plantings and market rows are never
touched, that malformed observations never raise, off-identity through install()
defaults, and the TitanAgent wiring (keys ship off, delegate passes the parameters,
diagnostics). Standard library only.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_strawberry_endgame as sb  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}
DEFAULT_HORIZON = r04.SALE_HORIZON
DEFAULT_ENDGAME = False
DEFAULT_MAX_PLANTS = 8


def synthetic_observation(step, shed=None, seeds=None, shops=("BAKERY", "YARN_STORE"),
                          player=0, money=1000):
    size = 10
    tiles = [["LOCKED"] * size for _ in range(size)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": money,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": player,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}], "shed": dict(shed or {"WHEAT": 5}),
                        "seeds": dict(seeds or {})},
            "market": {"prices": {product: 10 for product in r04.PRODUCTS}},
            "town": {"unlocked_shops": list(shops)}}


def wheat_action():
    return {"farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"], ["PASS"], ["PLANT", "CARROT"]],
            "market": [["BUY_SEED", "WHEAT", 2], ["SELL", "WHEAT", 1]]}


class StrawberryHorizon(unittest.TestCase):
    def tearDown(self):
        r04.SALE_HORIZON = DEFAULT_HORIZON
        r04.STRAWBERRY_ENDGAME = DEFAULT_ENDGAME
        r04.STRAWBERRY_MAX_PLANTS = DEFAULT_MAX_PLANTS
        sb.reset()


def run_with_stub(step, action, seeds, endgame=True, max_plants=8, player=0):
    """Run r04.v3_agent with POLICY_AGENT stubbed to return a copy of `action`."""
    def stub(observation, configuration=None):
        return copy.deepcopy(action)
    saved = r04.POLICY_AGENT
    r04.POLICY_AGENT = stub
    try:
        agent = r04.install(None, DEFAULT_HORIZON, 0, False, False, None, None,
                            strawberry_endgame=endgame,
                            strawberry_max_plants=max_plants)
        return agent(synthetic_observation(step, seeds=seeds, player=player), dict(CONFIG))
    finally:
        r04.POLICY_AGENT = saved


class ConversionTests(StrawberryHorizon):
    def test_converts_late_wheat_plantings_with_seeds(self):
        out = run_with_stub(600, wheat_action(), {"STRAWBERRY": 5})
        self.assertEqual(out["farmer"], ["PLANT", "STRAWBERRY"])
        # Per-step cap is 2: farmer + first hand convert, the rest are untouched.
        self.assertEqual(out["hands"],
                         [["PLANT", "STRAWBERRY"], ["PASS"], ["PLANT", "CARROT"]])
        self.assertEqual(out["market"], [["BUY_SEED", "WHEAT", 2], ["SELL", "WHEAT", 1]])

    def test_no_seeds_leaves_the_action_untouched(self):
        action = wheat_action()
        out = run_with_stub(600, action, {"STRAWBERRY": 0})
        self.assertEqual(out, action)
        out = run_with_stub(600, action, {})
        self.assertEqual(out, action)

    def test_seed_stock_caps_the_step_conversions(self):
        out = run_with_stub(600, wheat_action(), {"STRAWBERRY": 1})
        self.assertEqual(out["farmer"], ["PLANT", "STRAWBERRY"])
        self.assertEqual(out["hands"][0], ["PLANT", "WHEAT"])

    def test_window_boundaries(self):
        for step in (575, 649):
            out = run_with_stub(step, wheat_action(), {"STRAWBERRY": 5})
            self.assertEqual(out, wheat_action(), step)
        for step in (576, 648):
            out = run_with_stub(step, wheat_action(), {"STRAWBERRY": 5})
            self.assertEqual(out["farmer"], ["PLANT", "STRAWBERRY"], step)

    def test_per_game_cap_is_enforced(self):
        def stub(observation, configuration=None):
            return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
        saved = r04.POLICY_AGENT
        r04.POLICY_AGENT = stub
        try:
            agent = r04.install(None, DEFAULT_HORIZON, 0, False, False, None, None,
                                strawberry_endgame=True,
                                strawberry_max_plants=2)
            first = agent(synthetic_observation(600, seeds={"STRAWBERRY": 5}), dict(CONFIG))
            second = agent(synthetic_observation(601, seeds={"STRAWBERRY": 5}), dict(CONFIG))
            third = agent(synthetic_observation(602, seeds={"STRAWBERRY": 5}), dict(CONFIG))
        finally:
            r04.POLICY_AGENT = saved
        self.assertEqual(first["farmer"], ["PLANT", "STRAWBERRY"])
        self.assertEqual(second["farmer"], ["PLANT", "STRAWBERRY"])
        # Cap of 2 reached: the third step is untouched.
        self.assertEqual(third["farmer"], ["PLANT", "WHEAT"])

    def test_per_step_cap_is_two(self):
        action = {"farmer": ["PLANT", "WHEAT"],
                  "hands": [["PLANT", "WHEAT"], ["PLANT", "WHEAT"], ["PLANT", "WHEAT"]],
                  "market": []}
        out = run_with_stub(600, action, {"STRAWBERRY": 10})
        converted = ([out["farmer"]] + out["hands"]).count(["PLANT", "STRAWBERRY"])
        self.assertEqual(converted, 2)

    def test_non_wheat_plantings_are_untouched(self):
        action = {"farmer": ["PLANT", "CARROT"],
                  "hands": [["PLANT", "TOMATO"], ["PLANT", "MELON"], ["PLANT"]],
                  "market": []}
        out = run_with_stub(600, action, {"STRAWBERRY": 5})
        self.assertEqual(out, action)

    def test_counter_resets_when_the_step_decreases(self):
        def stub(observation, configuration=None):
            return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
        saved = r04.POLICY_AGENT
        r04.POLICY_AGENT = stub
        try:
            agent = r04.install(None, DEFAULT_HORIZON, 0, False, False, None, None,
                                strawberry_endgame=True,
                                strawberry_max_plants=1)
            one = agent(synthetic_observation(648, seeds={"STRAWBERRY": 5}), dict(CONFIG))
            capped = agent(synthetic_observation(649 - 1, seeds={"STRAWBERRY": 5}), dict(CONFIG))
            # Step 600 < 648: a new game resets the counter.
            reset = agent(synthetic_observation(600, seeds={"STRAWBERRY": 5}), dict(CONFIG))
        finally:
            r04.POLICY_AGENT = saved
        self.assertEqual(one["farmer"], ["PLANT", "STRAWBERRY"])
        self.assertEqual(capped["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(reset["farmer"], ["PLANT", "STRAWBERRY"])

    def test_counters_are_per_player(self):
        out0 = run_with_stub(600, wheat_action(), {"STRAWBERRY": 8}, max_plants=2, player=0)
        out1 = run_with_stub(600, wheat_action(), {"STRAWBERRY": 8}, max_plants=2, player=1)
        self.assertEqual(out0["farmer"], ["PLANT", "STRAWBERRY"])
        self.assertEqual(out1["farmer"], ["PLANT", "STRAWBERRY"])


class MalformedTests(StrawberryHorizon):
    def test_malformed_observation_never_raises(self):
        action = wheat_action()
        for obs in ({},
                    {"step": "not-a-step"},
                    {"step": 600},
                    {"step": 600, "private": None},
                    {"step": 600, "private": {"seeds": "nope"}},
                    {"step": 600, "private": {"seeds": {"STRAWBERRY": "many"}}},
                    None):
            out = sb.apply_strawberry_endgame(obs, copy.deepcopy(action), 8)
            self.assertEqual(out, action, obs)

    def test_unreadable_player_falls_back_to_player_zero(self):
        obs = {"step": 600, "private": {"seeds": {"STRAWBERRY": 3}}, "player": "x"}
        out = sb.apply_strawberry_endgame(obs, copy.deepcopy(wheat_action()), 8)
        self.assertEqual(out["farmer"], ["PLANT", "STRAWBERRY"])

    def test_malformed_action_never_raises(self):
        obs = synthetic_observation(600, seeds={"STRAWBERRY": 3})
        for action in ({}, {"farmer": None}, {"hands": None},
                       {"farmer": ["PLANT"], "hands": [["PLANT", "WHEAT", "EXTRA"]]}):
            out = sb.apply_strawberry_endgame(obs, copy.deepcopy(action), 8)
            self.assertEqual(out, action, action)

    def test_tuple_commands_are_handled(self):
        obs = synthetic_observation(600, seeds={"STRAWBERRY": 3})
        action = {"farmer": ("PLANT", "WHEAT"), "hands": [("PLANT", "WHEAT")], "market": []}
        out = sb.apply_strawberry_endgame(obs, action, 8)
        self.assertEqual(out["farmer"], ["PLANT", "STRAWBERRY"])
        self.assertEqual(out["hands"], [["PLANT", "STRAWBERRY"]])

    def test_zero_or_negative_cap_converts_nothing(self):
        obs = synthetic_observation(600, seeds={"STRAWBERRY": 3})
        for cap in (0, -1):
            out = sb.apply_strawberry_endgame(obs, copy.deepcopy(wheat_action()), cap)
            self.assertEqual(out, wheat_action(), cap)


class OffIdentityTests(StrawberryHorizon):
    def test_install_defaults_leave_the_action_byte_identical(self):
        off = r04.install(None, DEFAULT_HORIZON, 0, False, False)
        self.assertIs(r04.STRAWBERRY_ENDGAME, False)
        steps = [575, 576, 600, 648, 649]
        observations = [synthetic_observation(t, seeds={"STRAWBERRY": 9}) for t in steps]
        direct = [r04.agent(obs, dict(CONFIG)) for obs in observations]
        wrapped = [off(obs, dict(CONFIG)) for obs in observations]
        self.assertEqual(wrapped, direct)
        # The module was never even consulted: no per-game state exists.
        self.assertEqual(sb._STATE, {})

    def test_endgame_none_keeps_the_published_globals(self):
        r04.install(None, DEFAULT_HORIZON)
        self.assertIs(r04.STRAWBERRY_ENDGAME, DEFAULT_ENDGAME)
        self.assertEqual(r04.STRAWBERRY_MAX_PLANTS, DEFAULT_MAX_PLANTS)

    def test_install_sets_both_parameters(self):
        r04.install(None, DEFAULT_HORIZON, 0, False, False, None, None,
                    strawberry_endgame=True, strawberry_max_plants=3)
        self.assertIs(r04.STRAWBERRY_ENDGAME, True)
        self.assertEqual(r04.STRAWBERRY_MAX_PLANTS, 3)
        with self.assertRaises(ValueError):
            r04.install(None, DEFAULT_HORIZON, 0, False, False, None, None,
                    strawberry_endgame=True, strawberry_max_plants=-1)


class WiringTests(StrawberryHorizon):
    def test_keys_ship_off(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_strawberry_endgame"], False)
        self.assertEqual(data["r04_strawberry_max_plants"], DEFAULT_MAX_PLANTS)
        features = Features(**data)
        self.assertIs(features.r04_strawberry_endgame, False)
        self.assertEqual(features.r04_strawberry_max_plants, DEFAULT_MAX_PLANTS)
        self.assertFalse(TitanAgent(Features())._v3_active())
        self.assertTrue(TitanAgent(Features(r04_strawberry_endgame=True))._v3_active())

    def test_parameters_reach_the_policy(self):
        for on, cap in ((True, 3), (False, 8)):
            agent = TitanAgent(Features(r04_sale_window=True, r04_strawberry_endgame=on,
                                        r04_strawberry_max_plants=cap))
            agent.act(synthetic_observation(0), dict(CONFIG))
            self.assertIs(r04.STRAWBERRY_ENDGAME, on)
            self.assertEqual(r04.STRAWBERRY_MAX_PLANTS, cap)
            self.assertIs(agent.diagnostics["strawberry_endgame"], on)
            self.assertEqual(agent.diagnostics["strawberry_max_plants"], cap)


if __name__ == "__main__":
    unittest.main(verbosity=2)
