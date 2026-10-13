# SPDX-License-Identifier: Apache-2.0
"""V3.1 B5: `r04_b5_carrot_fertilizer` and `r04_b5_jit_fertilize` in the R04 route.

    python -m unittest -v checks/test_v31_b5_fertilize.py

Both keys ship on and act only inside the R04 delegate. v3_agent() applies the CARROT
top-up, then the just-in-time fertilizer with the tape's next authored step, after every
market-row layer. Covers the shipped config, the canonical invariant, TitanAgent wiring,
flag-off identity, the call order, and one live replacement per transform. Standard
library only.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import b5_fertilize  # noqa: E402
import jit_pass_fertilize  # noqa: E402
import r04_full_router as r04  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}


def observation(step, tile=None, fertilizer=3, player=0):
    tiles = [["LOCKED"] * 10 for _ in range(10)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    if tile is not None:
        tiles[4][4] = tile
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": 1000,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": player,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{"FERTILIZER": fertilizer}], "shed": {"WHEAT": 5}},
            "market": {"prices": {product: 10 for product in r04.PRODUCTS}},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def carrot(day, fertilized_until=-1):
    return {"kind": "PLANT", "crop": "CARROT", "fertilized_until_day": fertilized_until,
            "planted_day": day - 2, "yield_units": 0, "watered_today": False}


def reset():
    r04.B5_CARROT_FERTILIZER = False
    r04.B5_JIT_FERTILIZE = False
    r04.STRAWBERRY_TOPUP = False
    r04.ROW_SHED = False
    r04.NO_LATE_SALE_ADVANCE = False
    r04.SALE_HORIZON = 8
    r04.OPEN_ROUNDTRIP = 0
    r04.ROW_ORDER = False
    r04.EVENING_FLUSH = False
    r04.SALE_EXCLUDED = ("WHEAT", "FERTILIZER")
    r04._V231_EARLY = False
    r04._RIVAL_TAPE.update(same=0, seen=0, last=-1, decision=None, valid=True)


class ShippedKeys(unittest.TestCase):
    def tearDown(self):
        reset()

    def test_both_keys_ship_on(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_b5_carrot_fertilizer"], True)
        self.assertIs(data["r04_b5_jit_fertilize"], True)

    def test_canonical_path_untouched_with_route_keys_off(self):
        self.assertFalse(TitanAgent(Features())._v3_active())

    def test_titan_passes_both_keys_to_the_router(self):
        for on in (True, False):
            agent = TitanAgent(Features(r04_sale_window=True, r04_b5_carrot_fertilizer=on,
                                        r04_b5_jit_fertilize=on))
            agent.act(observation(0), dict(CONFIG))
            self.assertIs(r04.B5_CARROT_FERTILIZER, on)
            self.assertIs(r04.B5_JIT_FERTILIZE, on)
            self.assertIs(agent.diagnostics["b5_carrot_fertilizer"], on)
            self.assertIs(agent.diagnostics["b5_jit_fertilize"], on)


class V3AgentHook(unittest.TestCase):
    def setUp(self):
        self.saved = (r04.POLICY_AGENT, r04._POLICY)
        r04.POLICY_AGENT = lambda obs, cfg=None: {"farmer": ["PASS"], "hands": [], "market": []}

    def tearDown(self):
        r04.POLICY_AGENT, r04._POLICY = self.saved
        reset()

    def test_flags_off_is_identity(self):
        r04.install(None, 8, 0, False, False, b5_carrot_fertilizer=False, b5_jit_fertilize=False)
        obs = observation(50, tile=carrot(2))
        self.assertEqual(r04.v3_agent(obs, dict(CONFIG))["farmer"], ["PASS"])

    def test_carrot_top_up_replaces_the_pass(self):
        r04.install(None, 8, 0, False, False, b5_carrot_fertilizer=True, b5_jit_fertilize=False)
        obs = observation(50, tile=carrot(2))
        self.assertEqual(r04.v3_agent(obs, dict(CONFIG))["farmer"], ["FERTILIZE"])

    def test_carrot_covered_tile_keeps_the_pass(self):
        r04.install(None, 8, 0, False, False, b5_carrot_fertilizer=True, b5_jit_fertilize=False)
        obs = observation(50, tile=carrot(2, fertilized_until=4))
        self.assertEqual(r04.v3_agent(obs, dict(CONFIG))["farmer"], ["PASS"])

    def test_jit_reads_the_next_authored_step(self):
        state = type("State", (), {"plan": 0})()
        tape = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(720)]
        tape[51] = {"farmer": ["WATER"], "hands": [], "market": []}
        r04._POLICY = type("Policy", (), {"players": {0: state}, "tapes": {0: tape}})()
        r04.install(None, 8, 0, False, False, b5_carrot_fertilizer=False, b5_jit_fertilize=True)
        wheat = {"kind": "PLANT", "crop": "WHEAT", "fertilized_until_day": -1, "planted_day": 0,
                 "yield_units": 0, "watered_today": False}
        obs = observation(50, tile=wheat)     # day 2, age 2: inside WHEAT's window
        self.assertEqual(r04.v3_agent(obs, dict(CONFIG))["farmer"], ["FERTILIZE"])
        tape[51] = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertEqual(r04.v3_agent(obs, dict(CONFIG))["farmer"], ["PASS"])

    def test_applied_after_the_market_layers(self):
        calls = []
        saved = r04._b5_fertilize
        try:
            r04._b5_fertilize = lambda obs, action: calls.append(action["market"]) or action
            r04.POLICY_AGENT = lambda obs, cfg=None: {"farmer": ["PASS"], "hands": [],
                                                      "market": [["SELL", "EGG", 1], ["SELL", "WOOL", 5]]}
            r04.install(None, 8, 0, True, False, b5_carrot_fertilizer=True)
            r04.v3_agent(observation(300), dict(CONFIG))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], ["SELL", "WOOL", 5])   # row order already applied
        finally:
            r04._b5_fertilize = saved

    def test_modules_are_the_gated_bytes(self):
        self.assertTrue(callable(b5_fertilize.apply_carrot_fertilizer))
        self.assertTrue(callable(jit_pass_fertilize.apply_jit_pass_fertilize))


if __name__ == "__main__":
    unittest.main()
