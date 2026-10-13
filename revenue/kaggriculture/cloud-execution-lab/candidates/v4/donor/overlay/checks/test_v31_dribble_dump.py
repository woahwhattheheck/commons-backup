# SPDX-License-Identifier: Apache-2.0
"""V3.1 lane E1 `r04_dribble_dump`: per-step caps on the fragile goods' SELL rows.

    python -m unittest -v checks/test_v31_dribble_dump.py

The key ships off and acts only inside the R04 delegate. Covers the shipped config, the canonical
invariant, TitanAgent wiring, the seam (after H4, right before ROW_ORDER; flag off leaves the
stack untouched) and the lane itself: cumulative per-good caps, the days 0-2 ban, the $1 floor
pass-through, untouched safe goods and non-SELL rows, the step-718 liquidation and malformed
input. Standard library only.
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

import r04_dribble_dump as e1  # noqa: E402
import r04_full_router as r04  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}


def synthetic_observation(step, prices=None):
    tiles = [["LOCKED"] * 10 for _ in range(10)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": 1000,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    quotes = {product: 100 for product in r04.PRODUCTS}
    quotes.update(prices or {})
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}], "shed": {"WHEAT": 5}},
            "market": {"prices": quotes},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def action(*rows):
    return {"farmer": ["PASS"], "hands": [], "market": [list(r) for r in rows]}


def reset():
    r04.DRIBBLE_DUMP = False
    r04.STRAWBERRY_TOPUP = False
    r04.NO_LATE_SALE_ADVANCE = False
    r04.NO_LATE_SALE_ADVANCE_STEP = 648
    r04.ROW_SHED = False
    r04.ROW_ORDER = False
    r04.EVENING_FLUSH = False
    r04.SALE_HORIZON = 8
    r04.OPEN_ROUNDTRIP = 0
    r04.SALE_EXCLUDED = ("WHEAT", "FERTILIZER")
    r04._V231_EARLY = False
    r04.B5_CARROT_FERTILIZER = False
    r04.B5_JIT_FERTILIZE = False
    r04.FERT_HAND = False
    r04._FERT_HAND_AGENT = None
    r04._RIVAL_TAPE.update(same=0, seen=0, last=-1, decision=None, valid=True)
    e1.reset()


class ShippedKey(unittest.TestCase):
    def tearDown(self):
        reset()

    def test_key_ships_off(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_dribble_dump"], False)
        self.assertIs(Features(**data).r04_dribble_dump, False)
        self.assertIs(Features().r04_dribble_dump, False)

    def test_canonical_path_untouched_with_route_keys_off(self):
        self.assertFalse(TitanAgent(Features())._v3_active())
        self.assertFalse(TitanAgent(Features(r04_dribble_dump=True))._v3_active())

    def test_titan_passes_the_key_to_the_router(self):
        for on in (True, False):
            agent = TitanAgent(Features(r04_sale_window=True, r04_dribble_dump=on))
            agent.act(synthetic_observation(0), dict(CONFIG))
            self.assertIs(r04.DRIBBLE_DUMP, on)
            self.assertIs(agent.diagnostics["dribble_dump"], on)
            reset()


class Seam(unittest.TestCase):
    def setUp(self):
        self.saved = r04.POLICY_AGENT

    def tearDown(self):
        r04.POLICY_AGENT = self.saved
        reset()

    def stack(self, parent, step, **keys):
        r04.POLICY_AGENT = lambda obs, cfg=None: copy.deepcopy(parent)
        r04.install(None, 8, 0, False, False, **keys)
        return r04.v3_agent(synthetic_observation(step), dict(CONFIG))

    def test_flag_off_leaves_the_stack_untouched(self):
        parent = action(("SELL", "MILK", 40), ("SELL", "WHEAT", 90))
        self.assertEqual(self.stack(parent, 300, dribble_dump=False), parent)

    def test_flag_on_caps_the_fragile_row(self):
        parent = action(("SELL", "MILK", 40), ("SELL", "WHEAT", 90))
        out = self.stack(parent, 300, dribble_dump=True)
        self.assertEqual(out["market"], [["SELL", "MILK", 15], ["SELL", "WHEAT", 90]])

    def test_runs_before_row_order(self):
        # With ROW_ORDER on, the order is ranked on the capped quantity.
        parent = action(("SELL", "WOOL", 50), ("SELL", "EGG", 3))
        r04.POLICY_AGENT = lambda obs, cfg=None: copy.deepcopy(parent)
        r04.install(None, 8, 0, True, False, dribble_dump=True)
        out = r04.v3_agent(synthetic_observation(300), dict(CONFIG))
        self.assertIn(["SELL", "WOOL", 12], out["market"])
        self.assertIn(["SELL", "EGG", 3], out["market"])


class Lane(unittest.TestCase):
    def tearDown(self):
        e1.reset()

    def test_caps_are_cumulative_across_rows(self):
        out = e1.apply_dribble_dump(synthetic_observation(300),
                                    action(("SELL", "STRAWBERRY", 10), ("SELL", "STRAWBERRY", 10),
                                           ("SELL", "STRAWBERRY", 4)))
        self.assertEqual(out["market"], [["SELL", "STRAWBERRY", 10], ["SELL", "STRAWBERRY", 5]])

    def test_each_fragile_good_has_its_own_cap(self):
        out = e1.apply_dribble_dump(synthetic_observation(400),
                                    action(("SELL", "MILK", 99), ("SELL", "WOOL", 99),
                                           ("SELL", "MELON", 99), ("SELL", "STRAWBERRY", 99)))
        self.assertEqual(out["market"], [["SELL", "MILK", 15], ["SELL", "WOOL", 12],
                                         ["SELL", "MELON", 30], ["SELL", "STRAWBERRY", 15]])

    def test_days_zero_to_two_drop_fragile_rows(self):
        parent = action(("SELL", "MILK", 2), ("SELL", "WHEAT", 13), ("BUY_ANIMAL", "COW", 1))
        out = e1.apply_dribble_dump(synthetic_observation(71), parent)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 13], ["BUY_ANIMAL", "COW", 1]])
        self.assertEqual(e1.apply_dribble_dump(synthetic_observation(72), parent), parent)

    def test_floor_price_passes_through(self):
        parent = action(("SELL", "WOOL", 80))
        out = e1.apply_dribble_dump(synthetic_observation(300, {"WOOL": 1}), parent)
        self.assertIs(out, parent)

    def test_safe_goods_and_non_sell_rows_untouched(self):
        parent = action(("SELL", "WHEAT", 500), ("SELL", "EGG", 200), ("SELL", "CARROT", 90),
                        ("SELL", "TOMATO", 90), ("SELL", "FERTILIZER", 90), ("HIRE",), [])
        self.assertIs(e1.apply_dribble_dump(synthetic_observation(300), parent), parent)

    def test_terminal_liquidation_untouched(self):
        parent = action(("SELL", "MILK", 60))
        self.assertIs(e1.apply_dribble_dump(synthetic_observation(718), parent), parent)
        self.assertIsNot(e1.apply_dribble_dump(synthetic_observation(717), parent), parent)

    def test_malformed_input_is_returned_unchanged(self):
        parent = action(("SELL", "MILK", "many"), ("SELL", "MILK", 0), ("SELL", "MILK", -3))
        self.assertIs(e1.apply_dribble_dump(synthetic_observation(300), parent), parent)
        self.assertEqual(e1.apply_dribble_dump({}, parent), parent)
        self.assertEqual(e1.apply_dribble_dump(synthetic_observation(300), None), None)
        self.assertEqual(e1.apply_dribble_dump(synthetic_observation(300), {"market": []}),
                         {"market": []})

    def test_input_action_is_not_mutated(self):
        parent = action(("SELL", "MILK", 40))
        before = copy.deepcopy(parent)
        e1.apply_dribble_dump(synthetic_observation(300), parent)
        self.assertEqual(parent, before)


if __name__ == "__main__":
    unittest.main()
