# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from types import SimpleNamespace

from terminal_animal_capital import apply_terminal_animal_capital, plan_terminal_animal_capital


BASE = {"turnsPerDay": 24, "episodeSteps": 720}


def action(*rows):
    return {"farmer": ["PASS"], "hands": [], "market": list(rows)}


class H5ExecutablePrefixTests(unittest.TestCase):
    def test_default_limit_preserves_and_ignores_nonexecuted_dead_suffix(self):
        rows = [["SELL", "WHEAT", 1] for _ in range(10)]
        rows.append(["BUY_ANIMAL", "COW", 1])
        a = action(*rows)
        plan = plan_terminal_animal_capital(a, {"step": 717}, BASE)
        self.assertFalse(plan["eligible"])
        self.assertEqual(plan["reason"], "NO_PROVABLY_DEAD_ANIMAL_CAPITAL")
        self.assertIs(
            apply_terminal_animal_capital(a, {"step": 717}, BASE, enabled=True), a
        )

    def test_custom_limit_drops_only_executable_dead_row_and_preserves_suffix(self):
        cfg = {**BASE, "maxMarketOrdersPerTurn": 1}
        suffix = ["BUY_SEED", "WHEAT", 999]
        a = action(["BUY_ANIMAL", "GOOSE", 1], suffix)
        plan = plan_terminal_animal_capital(a, {"step": 717}, cfg)
        self.assertTrue(plan["eligible"])
        self.assertEqual(plan["drop_indices"], [0])
        self.assertEqual(plan["max_market_orders"], 1)
        out = apply_terminal_animal_capital(a, {"step": 717}, cfg, enabled=True)
        self.assertEqual(out["market"], [[], suffix])
        self.assertEqual(a["market"], [["BUY_ANIMAL", "GOOSE", 1], suffix])

    def test_nonexecuted_protected_suffix_does_not_block_executable_drop(self):
        cfg = {**BASE, "maxMarketOrdersPerTurn": 1}
        a = action(["BUY_ANIMAL", "SHEEP", 1], ["HIRE", 1])
        plan = plan_terminal_animal_capital(a, {"step": 717}, cfg)
        self.assertTrue(plan["eligible"])
        self.assertEqual(plan["drop_indices"], [0])

    def test_nonexecuted_malformed_suffix_is_opaque_and_preserved(self):
        cfg = {**BASE, "maxMarketOrdersPerTurn": 1}
        malformed = {"not": "an executable market row"}
        a = action(["BUY_ANIMAL", "COW", 1], malformed)
        out = apply_terminal_animal_capital(a, {"step": 717}, cfg, enabled=True)
        self.assertEqual(out["market"], [[], malformed])

    def test_executable_protected_row_still_blocks(self):
        cfg = {**BASE, "maxMarketOrdersPerTurn": 2}
        a = action(["BUY_ANIMAL", "GOOSE", 1], ["HIRE", 1])
        plan = plan_terminal_animal_capital(a, {"step": 717}, cfg)
        self.assertFalse(plan["eligible"])
        self.assertEqual(plan["reason"], "DOWNSTREAM_AFFORDABILITY_AMBIGUITY")

    def test_nonpositive_plain_int_limit_uses_one_executable_row(self):
        for value in (0, -1, -99):
            with self.subTest(value=value):
                cfg = {**BASE, "maxMarketOrdersPerTurn": value}
                suffix = ["HIRE", 1]
                a = action(["BUY_ANIMAL", "GOOSE", 1], suffix)
                plan = plan_terminal_animal_capital(a, {"step": 717}, cfg)
                self.assertTrue(plan["eligible"])
                self.assertEqual(plan["max_market_orders"], 1)
                self.assertEqual(plan["drop_indices"], [0])
                out = apply_terminal_animal_capital(a, {"step": 717}, cfg, enabled=True)
                self.assertEqual(out["market"], [[], suffix])
                self.assertEqual(a["market"], [["BUY_ANIMAL", "GOOSE", 1], suffix])

    def test_explicit_bad_market_limit_fails_closed(self):
        a = action(["BUY_ANIMAL", "GOOSE", 1])
        for value in (None, True, False, 1.0, "10"):
            with self.subTest(value=value):
                cfg = {**BASE, "maxMarketOrdersPerTurn": value}
                plan = plan_terminal_animal_capital(a, {"step": 717}, cfg)
                self.assertFalse(plan["eligible"])
                self.assertEqual(plan["reason"], "BAD_MAX_MARKET_ORDERS")
                self.assertIs(
                    apply_terminal_animal_capital(a, {"step": 717}, cfg, enabled=True),
                    a,
                )

    def test_object_config_distinguishes_missing_from_explicit_none(self):
        a = action(["BUY_ANIMAL", "GOOSE", 1])
        missing = SimpleNamespace(turnsPerDay=24, episodeSteps=720)
        missing_plan = plan_terminal_animal_capital(a, {"step": 717}, missing)
        self.assertTrue(missing_plan["eligible"])
        self.assertEqual(missing_plan["max_market_orders"], 10)

        malformed = SimpleNamespace(
            turnsPerDay=24, episodeSteps=720, maxMarketOrdersPerTurn=None
        )
        bad_plan = plan_terminal_animal_capital(a, {"step": 717}, malformed)
        self.assertFalse(bad_plan["eligible"])
        self.assertEqual(bad_plan["reason"], "BAD_MAX_MARKET_ORDERS")


if __name__ == "__main__":
    unittest.main()
