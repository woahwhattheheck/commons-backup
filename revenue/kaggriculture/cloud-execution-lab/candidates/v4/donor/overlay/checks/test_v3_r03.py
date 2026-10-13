# SPDX-License-Identifier: Apache-2.0
"""R03 key in the V3 tree: the complete published shop-router policy as a whole-route delegate.

    python -m unittest -v checks/test_v3_r03.py

Covers the tape data path, the nine published layers, the delegate seam (output identical to
calling the published agent directly), precedence over R01, and off-identity of the wiring.
Standard library only.
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

import r03_full_router as r03  # noqa: E402
from r01_tapes import load_tapes  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}


def synthetic_observation(step, shops=("BAKERY", "YARN_STORE"), player=0, money=1000):
    size = 10
    tiles = [["LOCKED"] * size for _ in range(size)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": money,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": player,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}], "shed": {"WHEAT": 5}},
            "market": {"prices": {product: 10 for product in r03.PRODUCTS}},
            "town": {"unlocked_shops": list(shops)}}


def play(callable_, steps, player=0):
    return [callable_(synthetic_observation(step, player=player), dict(CONFIG)) for step in steps]


class TapeTests(unittest.TestCase):
    def test_inline_tapes_come_from_r01_tapes(self):
        tapes = load_tapes()
        self.assertEqual(r03._INLINE_TAPES, tapes)
        self.assertEqual(len(tapes), 13)
        self.assertTrue(all(len(tape) == r03.LAST_STEP + 1 for tape in tapes))

    def test_published_constants(self):
        self.assertEqual((r03.ROUTE_STEP, r03.FINAL_PLAN_STEP, r03.LAST_STEP), (144, 648, 718))
        self.assertEqual(r03.SHOP_PLANS[("BAKERY", "YARN_STORE")], 3)
        self.assertEqual(r03.SHOP_PLANS[("YARN_STORE", "YARN_STORE")], 12)


class LayerTests(unittest.TestCase):
    def test_nine_layers_are_stacked(self):
        for name in ("_V216_PARENT", "_V217_PARENT", "_V218_PARENT", "_V219_PARENT", "_V224_PARENT",
                     "_V226_PARENT", "_V231_PARENT", "_V233_PARENT", "_v234_rescue"):
            self.assertTrue(hasattr(r03, name), name)
        self.assertEqual(len(r03.layers()), 9)

    def test_install_returns_the_last_bound_agent(self):
        self.assertIs(r03.install(), r03.agent)
        self.assertIs(r03.POLICY_AGENT, r03.agent)
        self.assertIs(r03.kaggle_agent, r03.agent)
        self.assertEqual(r03.KEY, "r03_full_router")

    def test_published_license_text_is_retained(self):
        source = (ROOT / "r03_full_router.py").read_text(encoding="utf-8")
        self.assertIn("Apache License", source)
        self.assertIn("Version 2.0, January 2004", source)
        self.assertIn("shop-router-0909", source)
        self.assertIn("soil-remembers-rain", source)


class PolicyTests(unittest.TestCase):
    def test_step_zero_replays_plan_zero_market(self):
        action = r03.agent(synthetic_observation(0), dict(CONFIG))
        self.assertEqual(set(action), {"farmer", "hands", "market"})
        self.assertEqual(action["market"], load_tapes()[0][0]["market"][:r03.MAX_ORDERS])

    def test_plan_chosen_at_route_step_and_final_plan(self):
        play(r03.agent, range(0, r03.ROUTE_STEP + 1))
        self.assertEqual(r03._POLICY.players[0].plan, r03.SHOP_PLANS[("BAKERY", "YARN_STORE")])
        play(r03.agent, range(r03.ROUTE_STEP + 1, r03.FINAL_PLAN_STEP + 1))
        self.assertEqual(r03._POLICY.players[0].plan, 2)

    def test_last_step_liquidates(self):
        play(r03.agent, range(0, 3))
        action = r03.agent(synthetic_observation(r03.LAST_STEP), dict(CONFIG))
        self.assertEqual(action["market"], [["SELL", "WHEAT", 5]])


class WiringTests(unittest.TestCase):
    def test_key_ships_off(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r03_full_router"], False)
        self.assertIs(Features(**data).r03_full_router, False)
        self.assertFalse(TitanAgent(Features())._v3_active())
        self.assertTrue(TitanAgent(Features(r03_full_router=True))._v3_active())

    def test_delegate_runs_before_any_canonical_state(self):
        agent = TitanAgent(Features(r03_full_router=True))
        action = agent.act(synthetic_observation(0), dict(CONFIG))
        self.assertEqual(set(action), {"farmer", "hands", "market"})
        self.assertEqual(agent.diagnostics["status"], "completed")
        self.assertEqual(agent.diagnostics["route"], "r03_full_router")
        self.assertFalse(agent.ready)
        self.assertIsNone(getattr(agent, "controller", None))

    def test_delegate_output_equals_the_published_agent(self):
        steps = list(range(0, 60)) + [143, 144, 145, 300, 647, 648, 700, 712, 713, 717, r03.LAST_STEP]
        direct = play(r03.agent, steps)
        agent = TitanAgent(Features(r03_full_router=True))
        delegated = play(lambda obs, cfg: agent.act(obs, cfg), steps)
        self.assertEqual(delegated, direct)
        self.assertEqual(agent.diagnostics["status"], "completed")

    def test_r03_takes_precedence_over_r01(self):
        agent = TitanAgent(Features(r01_shop_router=True, r03_full_router=True))
        agent.act(synthetic_observation(0), dict(CONFIG))
        self.assertEqual(agent.diagnostics["route"], "r03_full_router")

    def test_notice_carries_attribution(self):
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("r03_full_router", notice)
        self.assertIn("soil-remembers-rain", notice)
        self.assertIn("shop-router-0909", notice)


if __name__ == "__main__":
    unittest.main(verbosity=2)
