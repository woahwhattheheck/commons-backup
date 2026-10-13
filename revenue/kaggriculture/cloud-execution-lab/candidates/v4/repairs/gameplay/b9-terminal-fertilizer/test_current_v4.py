#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("current_v4", HERE/"current_v4.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CurrentV4TerminalFertilizer = module.CurrentV4TerminalFertilizer

CFG = {"episodeSteps": 720, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 4}


def farm(*, animal=True, fert=True, hands=None):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    if animal:
        tiles[4][4] = {"animal": "COW", "fertilizer_available": fert}
    return {"tiles": tiles, "farmer": [4, 4], "hands": list(hands or [])}


def obs(step=716, player=0, *, hands=None, animal=True, fert=True):
    selected = farm(animal=animal, fert=fert, hands=hands)
    rival = farm(animal=False, hands=[])
    farms = [selected, rival] if player == 0 else [rival, selected]
    return {"step": step, "player": player, "farms": farms}


def action(*, hands=None, farmer=None, market=None):
    return {
        "farmer": ["PASS"] if farmer is None else farmer,
        "hands": list(hands or []),
        "market": [] if market is None else market,
    }


class CurrentV4Tests(unittest.TestCase):
    def test_disabled_is_exact_identity(self):
        t = CurrentV4TerminalFertilizer()
        a = action()
        self.assertIs(t.apply(obs(), a, CFG, enabled=False, completed=True), a)
        self.assertEqual(t.last_report["reason"], "disabled")

    def test_enable_requires_literal_true_and_clears_stale_provenance(self):
        poisons = ("false", 1, 1.0, [True], {"enabled": False}, None)
        for enabled in poisons:
            with self.subTest(enabled=enabled):
                t = CurrentV4TerminalFertilizer()
                primed = t.apply(obs(716), action(), CFG, enabled=True, completed=True)
                self.assertEqual(primed["farmer"], ["COLLECT_FERTILIZER"])

                parent = action()
                self.assertIs(
                    t.apply(None, parent, None, enabled=enabled, completed=True),
                    parent,
                )
                self.assertEqual(t.last_report["reason"], "disabled")

                terminal = action(market=[
                    ["SELL", "FERTILIZER", 1],
                    ["SELL", "MILK", 1],
                ])
                self.assertIs(
                    t.apply(obs(718), terminal, CFG, enabled=True, completed=True),
                    terminal,
                )

    def test_fallback_is_exact_identity_and_clears_provenance(self):
        t = CurrentV4TerminalFertilizer()
        first = t.apply(obs(716), action(), CFG, enabled=True, completed=True)
        self.assertEqual(first["farmer"], ["COLLECT_FERTILIZER"])
        fallback = action()
        self.assertIs(t.apply(obs(717), fallback, CFG, enabled=True, completed=False), fallback)
        terminal = action(market=[["SELL","FERTILIZER",1],["SELL","MILK",1]])
        self.assertIs(t.apply(obs(718), terminal, CFG, enabled=True, completed=True), terminal)

    def test_collect_then_trail_inside_prefix_only(self):
        t = CurrentV4TerminalFertilizer()
        base = action()
        result = t.apply(obs(716), base, CFG, enabled=True, completed=True)
        self.assertIsNot(result, base)
        self.assertEqual(result["farmer"], ["COLLECT_FERTILIZER"])
        self.assertEqual(base["farmer"], ["PASS"])

        market = [
            ["SELL","FERTILIZER",1],
            ["SELL","MILK",2],
            [],
            ["SELL","FERTILIZER",3],
            ["SELL","WOOL",4],
            ["SELL","EGG",5],
        ]
        terminal = action(market=copy.deepcopy(market))
        result = t.apply(obs(718), terminal, CFG, enabled=True, completed=True)
        self.assertEqual(result["market"][:4], [
            ["SELL","MILK",2], [],
            ["SELL","FERTILIZER",1], ["SELL","FERTILIZER",3],
        ])
        self.assertEqual(result["market"][4:], market[4:])
        self.assertEqual(terminal["market"], market)

    def test_no_terminal_reorder_without_same_episode_collection(self):
        t = CurrentV4TerminalFertilizer()
        a = action(market=[["SELL","FERTILIZER",1],["SELL","MILK",1]])
        self.assertIs(t.apply(obs(718), a, CFG, enabled=True, completed=True), a)

    def test_nonliteral_pass_not_rewritten(self):
        t = CurrentV4TerminalFertilizer()
        for farmer in ([], ["WAIT"], ["PASS", 1]):
            a = action(farmer=farmer)
            self.assertIs(t.apply(obs(716), a, CFG, enabled=True, completed=True), a)

    def test_cardinality_mismatch_is_identity(self):
        t = CurrentV4TerminalFertilizer()
        o = obs(716, hands=[[4, 4]])
        a = action(hands=[])
        self.assertIs(t.apply(o, a, CFG, enabled=True, completed=True), a)

    def test_strict_timing_and_cap(self):
        bad = [
            {"episodeSteps": True, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 4},
            {"episodeSteps": 720, "turnsPerDay": 23, "maxMarketOrdersPerTurn": 4},
            {"episodeSteps": 720, "turnsPerDay": 24, "maxMarketOrdersPerTurn": 4.0},
        ]
        for cfg in bad:
            t = CurrentV4TerminalFertilizer()
            a = action()
            self.assertIs(t.apply(obs(716), a, cfg, enabled=True, completed=True), a)

    def test_rewind_resets_collection_provenance(self):
        t = CurrentV4TerminalFertilizer()
        t.apply(obs(716), action(), CFG, enabled=True, completed=True)
        # Same/earlier step starts a new logical episode stream and clears collected.
        neutral = action(farmer=["WAIT"])
        t.apply(obs(716), neutral, CFG, enabled=True, completed=True)
        terminal = action(market=[["SELL","FERTILIZER",1],["SELL","MILK",1]])
        self.assertIs(t.apply(obs(718), terminal, CFG, enabled=True, completed=True), terminal)

    def test_state_is_player_scoped(self):
        t = CurrentV4TerminalFertilizer()
        t.apply(obs(716, player=0), action(), CFG, enabled=True, completed=True)
        terminal = action(market=[["SELL","FERTILIZER",1],["SELL","MILK",1]])
        self.assertIs(t.apply(obs(718, player=1), terminal, CFG, enabled=True, completed=True), terminal)

    def test_terminal_already_safe_is_identity(self):
        t = CurrentV4TerminalFertilizer()
        t.apply(obs(717), action(), CFG, enabled=True, completed=True)
        terminal = action(market=[["SELL","MILK",1],["SELL","FERTILIZER",1]])
        self.assertIs(t.apply(obs(718), terminal, CFG, enabled=True, completed=True), terminal)
        self.assertEqual(t.last_report["reason"], "terminal_sale_order_already_safe")

    def test_no_collection_on_ineligible_tile(self):
        for animal, fert in ((False, True), (True, False)):
            t = CurrentV4TerminalFertilizer()
            a = action()
            self.assertIs(t.apply(obs(716, animal=animal, fert=fert), a, CFG,
                                  enabled=True, completed=True), a)

if __name__ == "__main__":
    unittest.main()
