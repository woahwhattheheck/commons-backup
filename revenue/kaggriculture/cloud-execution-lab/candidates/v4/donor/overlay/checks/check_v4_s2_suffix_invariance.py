# SPDX-License-Identifier: Apache-2.0
"""Independent S2 suffix-invariance gate; no gameplay implementation lives here.

Run directly, or with unittest discovery, from the canonical donor workspace.
S2_SOURCE may point at a historical helper for predecessor/mutation checks.
This compares action AND full transaction state across 1,040 two-seat cells.
It is a raw-prefix metamorphic proof suite, not an engine match/strength panel.
"""
from __future__ import annotations

import copy
import importlib.util
import itertools
import os
from pathlib import Path
import unittest

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "r04_s2_sheep_swap.py"
SOURCE = Path(os.environ.get("S2_SOURCE", str(DEFAULT_SOURCE)))
SPEC = importlib.util.spec_from_file_location("_s2_suffix_subject", SOURCE)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Cannot load S2 source: {SOURCE}")
S2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S2)
CFG = dict(episodeSteps=720, boardSize=10, turnsPerDay=24,
           shedCapacity=100, maxMarketOrdersPerTurn=10)
POISONS = (["HIRE"], ["BUY_LAND"], ["BUY_PRODUCT", "WHEAT", 1],
           ["BUY_SEED", "WHEAT", 1], ["BUY_ANIMAL", "SHEEP", 1],
           ["MYSTERY", 1, 1], "not-a-row", ["SELL", "WOOL", "invalid"])


def action(market=None):
    return {"farmer": ["PASS"], "hands": [["PASS"]],
            "market": [] if market is None else copy.deepcopy(market)}


def observation(player, step, wool):
    farms = [{"money": 1000, "farmer": [4, 4], "hands": [[4, 4]],
              "hires_today": 0, "tiles": [[None] * 10 for _ in range(10)]}
             for _ in range(2)]
    return {"player": player, "step": step, "farms": farms,
            "private": {"shed": {"WOOL": wool}, "inventories": [{}, {}]},
            "town": {"unlocked_shops": ["YARN_STORE"]},
            "market": {"prices": {"WOOL": 200, "MILK": 100}}}


def evaluate(parent, native, *, player, step=100, credit=0, wool=0):
    state = S2.new_state()
    state["wool_credit"] = credit
    before_parent, before_native = copy.deepcopy(parent), copy.deepcopy(native)
    result = S2.apply_s2_swap(observation(player, step, wool), parent, state,
                              enabled=True, configuration=CFG, native_tape=native)
    if parent != before_parent or native != before_native:
        raise AssertionError("S2 mutated caller-owned parent/tape")
    return result, state


class S2SuffixInvariance(unittest.TestCase):
    def test_current_suffix_invariance_entire_state_both_seats(self):
        # 2 seats x 2 mechanisms x 13 raw slots x 8 inert suffixes = 416.
        count = 0
        native = [action() for _ in range(120)]
        for player, mode, index, poison in itertools.product(
                (0, 1), ("buy", "sale"), range(13), POISONS):
            with self.subTest(player=player, mode=mode, index=index, poison=poison):
                row = ["BUY_ANIMAL", "COW", 1] if mode == "buy" else ["SELL", "WOOL", 1]
                market = [[] for _ in range(index)] + [row]
                market.extend([] for _ in range(max(0, 10 - len(market))))
                market.append(copy.deepcopy(poison))
                kwargs = dict(player=player, credit=3 if mode == "sale" else 0,
                              wool=5 if mode == "sale" else 0)
                self.assertEqual(evaluate(action(market), native, **kwargs),
                                 evaluate(action(market[:10]), native, **kwargs))
                count += 1
        self.assertEqual(count, 416)

    def test_future_suffix_invariance_entire_state_both_seats(self):
        # 2 seats x 3 future positions x 13 raw slots x 8 suffixes = 624.
        count = 0
        parent = action([["BUY_ANIMAL", "COW", 1]])
        for player, future_step, index, poison in itertools.product(
                (0, 1), (101, 119, 120), range(13), POISONS):
            with self.subTest(player=player, future_step=future_step, index=index, poison=poison):
                market = [[] for _ in range(index)] + [copy.deepcopy(poison)]
                market.extend([] for _ in range(max(0, 10 - len(market))))
                market.append(copy.deepcopy(poison))
                full = [action() for _ in range(121)]
                full[future_step] = action(market)
                projected = copy.deepcopy(full)
                projected[future_step] = action(market[:10])
                self.assertEqual(evaluate(parent, full, player=player),
                                 evaluate(parent, projected, player=player))
                count += 1
        self.assertEqual(count, 624)

    def test_live_activation_and_veto_controls(self):
        # Prevent vacuous success by a disabled/no-op implementation.
        native = [action() for _ in range(120)]
        for player in (0, 1):
            with self.subTest(player=player):
                out, state = evaluate(action([["BUY_ANIMAL", "COW", 1]]), native, player=player)
                self.assertEqual(out["market"], [["BUY_ANIMAL", "SHEEP", 1]])
                self.assertEqual(state["pending_buy"], {"before": 0, "quantity": 1})
                out, state = evaluate(action([["SELL", "WOOL", 1]]), native,
                                      player=player, credit=3, wool=5)
                self.assertEqual(out["market"], [["SELL", "WOOL", 4]])
                self.assertEqual(state["wool_credit"], 0)
                self.assertEqual(state["extra_wool_sale_requests"], 3)
                blocked = copy.deepcopy(native)
                blocked[119] = action([["HIRE"]])
                parent = action([["BUY_ANIMAL", "COW", 1]])
                out, state = evaluate(parent, blocked, player=player)
                self.assertEqual(out, parent)
                self.assertIsNone(state["pending_buy"])
                out, state = evaluate(parent, native[:119], player=player)
                self.assertEqual(out, parent)
                self.assertIsNone(state["pending_buy"])


if __name__ == "__main__":
    unittest.main()
