# SPDX-License-Identifier: Apache-2.0
"""R01 key in the V3 tree: tape data, the published rules, the whole-route delegate, off-identity
of the wiring.  Standard library only:

    python -m unittest -v checks/test_v3_r01.py
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

import r01_shop_router as r01  # noqa: E402
from r01_tapes import load_tapes  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402


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
            "market": {"prices": {product: 10 for product in r01.PRODUCTS}},
            "town": {"unlocked_shops": list(shops)}}


class TapeTests(unittest.TestCase):
    def test_thirteen_complete_tapes(self):
        tapes = load_tapes()
        self.assertEqual(len(tapes), 13)
        for tape in tapes:
            self.assertEqual(len(tape), r01.LAST_STEP + 1)
            for entry in tape:
                self.assertEqual(set(entry), {"farmer", "hands", "market"})

    def test_plan_table_indexes_tapes(self):
        self.assertTrue(all(0 <= plan < 13 for plan in r01.SHOP_PLANS.values()))
        self.assertEqual(r01.SHOP_PLANS[("BAKERY", "YARN_STORE")], 3)
        self.assertEqual(r01.SHOP_PLANS[("YARN_STORE", "YARN_STORE")], 12)


class PolicyTests(unittest.TestCase):
    def test_step_zero_replays_plan_zero(self):
        policy = r01.RouterPolicy()
        action = policy.act(synthetic_observation(0))
        self.assertEqual(action["farmer"], ["PASS"])
        self.assertEqual(action["market"], load_tapes()[0][0]["market"])
        self.assertEqual(policy.policy.players[0].plan, 0)

    def test_plan_chosen_from_first_two_shops_at_route_step(self):
        policy = r01.RouterPolicy()
        for step in range(0, r01.ROUTE_STEP + 1):
            policy.act(synthetic_observation(step, shops=("PIZZA_SHOP", "YARN_STORE")))
        self.assertEqual(policy.policy.players[0].plan, 7)
        for step in range(r01.ROUTE_STEP + 1, r01.FINAL_PLAN_STEP + 1):
            policy.act(synthetic_observation(step, shops=("PIZZA_SHOP", "YARN_STORE")))
        self.assertEqual(policy.policy.players[0].plan, 2)

    def test_reconstruction_after_route_step_rederives_plan(self):
        policy = r01.RouterPolicy()
        policy.act(synthetic_observation(300, shops=("SMOOTHIE_SHOP", "YARN_STORE")))
        self.assertEqual(policy.policy.players[0].plan, 8)
        late = r01.RouterPolicy()
        late.act(synthetic_observation(700, shops=("SMOOTHIE_SHOP", "YARN_STORE")))
        self.assertEqual(late.policy.players[0].plan, 2)

    def test_last_step_liquidates(self):
        policy = r01.RouterPolicy()
        action = policy.act(synthetic_observation(r01.LAST_STEP))
        self.assertEqual(action["market"], [["SELL", "WHEAT", 5]])


class WiringTests(unittest.TestCase):
    def test_key_ships_off(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r01_shop_router"], False)
        self.assertIs(Features(**data).r01_shop_router, False)
        agent = TitanAgent(Features())
        self.assertFalse(agent._v3_active())
        self.assertFalse(hasattr(agent, "_v3_r01"))

    def test_delegate_runs_before_any_canonical_state(self):
        agent = TitanAgent(Features(r01_shop_router=True))
        self.assertTrue(agent._v3_active())
        action = agent.act(synthetic_observation(0), {"episodeSteps": 720, "turnsPerDay": 24})
        self.assertEqual(set(action), {"farmer", "hands", "market"})
        self.assertEqual(action["market"], load_tapes()[0][0]["market"])
        self.assertEqual(agent.diagnostics["status"], "completed")
        self.assertEqual(agent.diagnostics["route"], "r01_shop_router")
        self.assertEqual(agent.diagnostics["r01_plan"], 0)
        self.assertFalse(agent.ready)
        self.assertIsNone(getattr(agent, "controller", None))

    def test_notice_carries_attribution(self):
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("shop-router-0909", notice)
        self.assertIn("r01_shop_router", notice)


if __name__ == "__main__":
    unittest.main(verbosity=2)
