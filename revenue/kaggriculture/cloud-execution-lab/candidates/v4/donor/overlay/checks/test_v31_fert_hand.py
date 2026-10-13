# SPDX-License-Identifier: Apache-2.0
"""V3.1 `r04_fert_hand`: the endgame fertilizer hand around the R04 stack.

    python -m unittest -v checks/test_v31_fert_hand.py

The key ships on and acts only inside the R04 delegate. Covers the shipped config, the canonical
invariant, TitanAgent wiring, flag-off identity, the pinned-engine yield arithmetic the hand
relies on, the hire decision (price, parent hires, later authored hires, row room), the parent's
blind view with the hand's command re-indexed around it, and the hand's own commands. Standard
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

import r04_fert_hand as fh  # noqa: E402
import r04_full_router as r04  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}


def carrot(planted, fertilized_until=-1, yield_units=1, watered=False):
    return {"kind": "PLANT", "crop": "CARROT", "planted_day": planted, "yield_units": yield_units,
            "fertilized_until_day": fertilized_until, "watered_today": watered,
            "consecutive_unwatered": 0}


def observation(step, tiles=None, hands=(), carrot_price=300, fert_price=5, shed_fert=20, hires=10,
                money=5000, inventories=None):
    grid = [[None] * 10 for _ in range(10)]
    for (x, y), tile in (tiles or {}).items():
        grid[y][x] = tile
    farm = {"tiles": grid, "farmer": [4, 4], "hands": [list(h) for h in hands], "money": money,
            "unlocked_quadrants": ["NW", "NE", "SW", "SE"], "hires_today": hires}
    invs = inventories if inventories is not None else [{} for _ in range(len(hands) + 1)]
    prices = {product: 40 for product in r04.PRODUCTS}
    prices.update({"CARROT": carrot_price, "FERTILIZER": fert_price})
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": invs, "shed": {"FERTILIZER": shed_fert}, "seeds": {}},
            "market": {"prices": prices, "inventory": {}},
            "town": {"unlocked_shops": ["PET_CAFE"]}}


def tape_with(plant_steps=(), hire_steps=()):
    tape = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(719)]
    for s in plant_steps:
        tape[s] = {"farmer": ["PLANT", "CARROT"], "hands": [], "market": []}
    for s in hire_steps:
        tape[s] = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
    return tape


def reset():
    fh._STATE.clear()
    fh.FERT_HAND = False
    r04.FERT_HAND = False
    r04._FERT_HAND_AGENT = None
    r04.B5_CARROT_FERTILIZER = False
    r04.B5_JIT_FERTILIZE = False
    r04.STRAWBERRY_TOPUP = False
    r04.NO_LATE_SALE_ADVANCE = False
    r04.SALE_HORIZON = 8
    r04.OPEN_ROUNDTRIP = 0
    r04.ROW_ORDER = False
    if hasattr(r04, "ROW_SHED"):
        r04.ROW_SHED = False
    r04.EVENING_FLUSH = False
    r04.SALE_EXCLUDED = ("WHEAT", "FERTILIZER")
    r04._V231_EARLY = False
    r04._RIVAL_TAPE.update(same=0, seen=0, last=-1, decision=None, valid=True)


class ShippedKey(unittest.TestCase):
    def tearDown(self):
        reset()

    def test_key_ships_on(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_fert_hand"], True)

    def test_canonical_path_untouched_with_route_keys_off(self):
        self.assertFalse(TitanAgent(Features())._v3_active())

    def test_titan_passes_the_key_to_the_router(self):
        for on in (True, False):
            reset()
            agent = TitanAgent(Features(r04_sale_window=True, r04_fert_hand=on))
            agent.act(observation(0), dict(CONFIG))
            self.assertIs(r04.FERT_HAND, on)
            self.assertIs(agent.diagnostics["fert_hand"], on)


class EngineArithmetic(unittest.TestCase):
    def test_hire_price_is_fibonacci(self):
        self.assertEqual([fh._fib(n) for n in (0, 1, 2, 10, 12, 14)], [1, 1, 2, 89, 233, 610])

    def test_young_carrot_gains_one_unit(self):
        self.assertEqual(fh._gain(carrot(25), 25), 1)      # age 0: covers the day-27 WATER
        self.assertEqual(fh._gain(carrot(24), 25), 1)      # age 1
        self.assertEqual(fh._gain(carrot(23, yield_units=1), 25), 1)   # age 2, not yet watered

    def test_no_gain_once_the_window_is_spent_or_covered(self):
        self.assertEqual(fh._gain(carrot(22, yield_units=3), 25), 0)   # age 3 watered already
        self.assertEqual(fh._gain(carrot(23, yield_units=2, watered=True), 25), 1)  # day-26 WATER left
        self.assertEqual(fh._gain(carrot(21, yield_units=3), 25), 0)   # window over
        self.assertEqual(fh._gain(carrot(24, fertilized_until=26), 25), 0)
        self.assertEqual(fh._gain({"kind": "PLANT", "crop": "TOMATO", "planted_day": 20}, 25), 0)
        self.assertEqual(fh._gain(None, 25), 0)


class HireDecision(unittest.TestCase):
    def setUp(self):
        fh.FERT_HAND = True
        self.parent_market = []
        self.tape = tape_with(plant_steps=range(611, 620))
        self.agent = fh.wrap(lambda obs, cfg=None: {"farmer": ["PASS"], "hands": [],
                                                    "market": [list(o) for o in self.parent_market]},
                             lambda obs: self.tape)

    def tearDown(self):
        reset()

    def test_hires_when_the_carrot_price_pays(self):
        out = self.agent(observation(603, tiles={(1, 1): carrot(24)}), dict(CONFIG))
        self.assertEqual(out["market"][0], ["HIRE"])

    def test_declines_at_a_low_carrot_price(self):
        out = self.agent(observation(603, tiles={(1, 1): carrot(24)}, carrot_price=45, hires=13), dict(CONFIG))
        self.assertEqual(out["market"], [])

    def test_never_hires_outside_the_endgame_or_before_the_hire_hour(self):
        self.assertEqual(self.agent(observation(24 * 20 + 3), dict(CONFIG))["market"], [])
        fh._STATE.clear()
        self.assertEqual(self.agent(observation(24 * 25 + 1), dict(CONFIG))["market"], [])

    def test_waits_while_the_parent_hires(self):
        self.parent_market = [["HIRE"]]
        out = self.agent(observation(603, tiles={(1, 1): carrot(24)}), dict(CONFIG))
        self.assertEqual(out["market"], [["HIRE"]])
        self.assertFalse(fh._STATE[0].tried)

    def test_waits_while_the_tape_hires_later_today(self):
        self.tape = tape_with(plant_steps=range(611, 620), hire_steps=(610,))
        out = self.agent(observation(603, tiles={(1, 1): carrot(24)}), dict(CONFIG))
        self.assertEqual(out["market"], [])

    def test_buys_the_fertilizer_shortfall(self):
        out = self.agent(observation(603, tiles={(1, 1): carrot(24)}, shed_fert=1), dict(CONFIG))
        self.assertEqual(out["market"][0], ["HIRE"])
        self.assertEqual(out["market"][1][:2], ["BUY_PRODUCT", "FERTILIZER"])

    def test_flag_off_is_identity(self):
        fh.FERT_HAND = False
        out = self.agent(observation(603, tiles={(1, 1): carrot(24)}), dict(CONFIG))
        self.assertEqual(out["market"], [])


class HandAtWork(unittest.TestCase):
    def setUp(self):
        fh.FERT_HAND = True
        self.seen = []
        self.tape = tape_with()

        def parent(obs, cfg=None):
            self.seen.append(copy.deepcopy(obs))
            n = len(obs["farms"][obs["player"]]["hands"])
            return {"farmer": ["PASS"], "hands": [["WATER"] for _ in range(n)], "market": []}

        self.agent = fh.wrap(parent, lambda obs: self.tape)
        tiles = {(1, 1): carrot(24)}
        self.agent(observation(603, tiles=tiles, hands=[(2, 2)], carrot_price=500), dict(CONFIG))   # hire issued
        self.tiles = tiles

    def tearDown(self):
        reset()

    def test_parent_is_blind_and_the_hand_is_reindexed(self):
        obs = observation(604, tiles=self.tiles, hands=[(2, 2), (5, 5)])
        out = self.agent(obs, dict(CONFIG))
        self.assertEqual(len(self.seen[-1]["farms"][0]["hands"]), 1)
        self.assertEqual(len(self.seen[-1]["private"]["inventories"]), 2)
        self.assertEqual(out["hands"][0], ["WATER"])
        self.assertEqual(out["hands"][1][:2], ["PICKUP", "FERTILIZER"])

    def test_leaves_the_shed_then_fertilizes_a_target(self):
        self.agent(observation(604, tiles=self.tiles, hands=[(2, 2), (5, 5)]), dict(CONFIG))
        out = self.agent(observation(605, tiles=self.tiles, hands=[(2, 2), (5, 5)],
                                     inventories=[{}, {}, {"FERTILIZER": 3}]), dict(CONFIG))
        self.assertIn(out["hands"][1][0], ("NORTH", "WEST", "SOUTH", "EAST"))
        out = self.agent(observation(606, tiles=self.tiles, hands=[(2, 2), (1, 1)],
                                     inventories=[{}, {}, {"FERTILIZER": 3}]), dict(CONFIG))
        self.assertEqual(out["hands"][1], ["FERTILIZE"])

    def test_new_day_forgets_the_hand(self):
        out = self.agent(observation(24 * 26, tiles=self.tiles, hands=[(2, 2)]), dict(CONFIG))
        self.assertEqual(out["hands"], [["WATER"]])


class RouterSeam(unittest.TestCase):
    def setUp(self):
        self.saved = (r04.POLICY_AGENT, r04._POLICY)
        r04.POLICY_AGENT = lambda obs, cfg=None: {"farmer": ["PASS"], "hands": [], "market": []}

    def tearDown(self):
        r04.POLICY_AGENT, r04._POLICY = self.saved
        reset()

    def test_install_returns_the_dispatcher_and_off_runs_the_stack(self):
        self.assertIs(r04.install(None, 8, 0, False, False, fert_hand=False), r04.v3_agent)
        self.assertIs(r04.FERT_HAND, False)
        self.assertEqual(r04.v3_agent(observation(603), dict(CONFIG)),
                         r04._v3_stack(observation(603), dict(CONFIG)))

    def test_on_wraps_the_stack_once(self):
        state = type("State", (), {"plan": 0})()
        r04._POLICY = type("Policy", (), {"players": {0: state}, "tapes": {0: tape_with(range(611, 620))}})()
        r04.install(None, 8, 0, False, False, fert_hand=True)
        out = r04.v3_agent(observation(603, tiles={(1, 1): carrot(24)}), dict(CONFIG))
        self.assertEqual(out["market"][0], ["HIRE"])
        wrapped = r04._FERT_HAND_AGENT
        r04.v3_agent(observation(604, tiles={(1, 1): carrot(24)}, hands=[(5, 5)]), dict(CONFIG))
        self.assertIs(r04._FERT_HAND_AGENT, wrapped)


if __name__ == "__main__":
    unittest.main()
