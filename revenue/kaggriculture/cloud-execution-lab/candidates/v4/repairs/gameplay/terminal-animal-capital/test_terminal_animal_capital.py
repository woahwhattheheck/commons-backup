# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from terminal_animal_capital import (
    EPISODE_STEPS,
    TURNS_PER_DAY,
    UNIT_ACTIONS_TO_PLACE_PURCHASED_ANIMAL,
    apply_terminal_animal_capital,
    plan_terminal_animal_capital,
)


CFG = {"turnsPerDay": TURNS_PER_DAY, "episodeSteps": EPISODE_STEPS}


def act(*rows):
    return {"farmer": ["PASS"], "hands": [], "market": list(rows)}


class H5V4Tests(unittest.TestCase):
    def test_disabled_exact_identity(self):
        a = act(["BUY_ANIMAL", "GOOSE", 1])
        self.assertIs(apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=False), a)

    def test_goose_suffix_is_removed_only_when_unplaceable(self):
        a = act(["SELL", "WHEAT", 1], ["BUY_ANIMAL", "GOOSE", 2], [])
        p = plan_terminal_animal_capital(a, {"step": 717}, CFG)
        self.assertTrue(p["eligible"])
        self.assertEqual(p["proof"], "INSUFFICIENT_FUTURE_UNIT_CALLBACKS_TO_PLACE")
        self.assertEqual(p["drop_indices"], [1])
        out = apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=True)
        self.assertEqual(out["market"], [["SELL", "WHEAT", 1], [], []])
        self.assertEqual(a["market"][1], ["BUY_ANIMAL", "GOOSE", 2])

    def test_all_standard_species_unplaceable_at_step717(self):
        for animal in ("GOOSE", "SHEEP", "COW"):
            with self.subTest(animal=animal):
                p = plan_terminal_animal_capital(
                    act(["BUY_ANIMAL", animal, 1]), {"step": 717}, CFG
                )
                self.assertTrue(p["eligible"])
                witness = p["witnesses"][0]
                self.assertEqual(witness["future_unit_callbacks"], 1)
                self.assertEqual(
                    witness["required_unit_actions_to_place"],
                    UNIT_ACTIONS_TO_PLACE_PURCHASED_ANIMAL,
                )

    def test_historical_fertilizer_killer_maturity_alone_never_suppresses(self):
        # Historical #12471 / merged #12949 falsely treated late species-product
        # maturity as proof of dead capital. At step648 there is ample time for
        # BUY -> later PICKUP -> PLACE -> EOD fertilizer -> later collection/use.
        for animal in ("GOOSE", "SHEEP", "COW"):
            with self.subTest(animal=animal):
                a = act(["BUY_ANIMAL", animal, 1])
                p = plan_terminal_animal_capital(a, {"step": 648}, CFG)
                self.assertFalse(p["eligible"])
                self.assertEqual(p["reason"], "NO_PROVABLY_DEAD_ANIMAL_CAPITAL")
                self.assertIs(
                    apply_terminal_animal_capital(a, {"step": 648}, CFG, enabled=True),
                    a,
                )

    def test_step716_two_later_callbacks_keep_buy_parent_owned(self):
        # BUY executes after step716 unit actions. Step717 can PICKUP and step718
        # can PLACE, so callback timing alone does not rule out animal-dependent
        # return. H5 must fail closed even though species yield is too late.
        a = act(["BUY_ANIMAL", "COW", 1])
        p = plan_terminal_animal_capital(a, {"step": 716}, CFG)
        self.assertFalse(p["eligible"])
        self.assertEqual(p["reason"], "NO_PROVABLY_DEAD_ANIMAL_CAPITAL")
        self.assertIs(apply_terminal_animal_capital(a, {"step": 716}, CFG, enabled=True), a)

    def test_before_final_plan_identity(self):
        a = act(["BUY_ANIMAL", "GOOSE", 1])
        self.assertIs(apply_terminal_animal_capital(a, {"step": 647}, CFG, enabled=True), a)

    def test_after_last_action_identity(self):
        a = act(["BUY_ANIMAL", "GOOSE", 1])
        self.assertIs(apply_terminal_animal_capital(a, {"step": 719}, CFG, enabled=True), a)

    def test_protected_later_spend_blocks_earlier_dead_buy(self):
        a = act(["BUY_ANIMAL", "GOOSE", 1], ["HIRE", 1])
        p = plan_terminal_animal_capital(a, {"step": 717}, CFG)
        self.assertFalse(p["eligible"])
        self.assertEqual(p["reason"], "DOWNSTREAM_AFFORDABILITY_AMBIGUITY")
        self.assertIs(apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=True), a)

    def test_only_dead_suffix_after_protected_row_changes(self):
        a = act(
            ["BUY_ANIMAL", "GOOSE", 1],
            ["BUY_SEED", "WHEAT", 2],
            ["BUY_ANIMAL", "COW", 1],
        )
        p = plan_terminal_animal_capital(a, {"step": 717}, CFG)
        self.assertEqual(p["drop_indices"], [2])
        out = apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=True)
        self.assertEqual(out["market"][0], ["BUY_ANIMAL", "GOOSE", 1])
        self.assertEqual(out["market"][1], ["BUY_SEED", "WHEAT", 2])
        self.assertEqual(out["market"][2], [])

    def test_sell_after_dead_buy_is_preserved(self):
        a = act(["BUY_ANIMAL", "SHEEP", 1], ["SELL", "WOOL", 3])
        out = apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=True)
        self.assertEqual(out["market"], [[], ["SELL", "WOOL", 3]])

    def test_unknown_animal_not_ours(self):
        a = act(["BUY_ANIMAL", "ALPACA", 1])
        self.assertIs(apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=True), a)

    def test_missing_timing_fails_closed(self):
        a = act(["BUY_ANIMAL", "GOOSE", 1])
        for cfg in (None, {}, {"turnsPerDay": 24}, {"episodeSteps": 720}):
            with self.subTest(cfg=cfg):
                self.assertIs(
                    apply_terminal_animal_capital(a, {"step": 717}, cfg, enabled=True),
                    a,
                )

    def test_type_poison_timing_fails_closed(self):
        a = act(["BUY_ANIMAL", "GOOSE", 1])
        for cfg in (
            {"turnsPerDay": True, "episodeSteps": 720},
            {"turnsPerDay": 24.0, "episodeSteps": 720},
            {"turnsPerDay": 24, "episodeSteps": "720"},
            {"turnsPerDay": 24, "episodeSteps": 720.0},
        ):
            with self.subTest(cfg=cfg):
                self.assertIs(
                    apply_terminal_animal_capital(a, {"step": 717}, cfg, enabled=True),
                    a,
                )

    def test_type_poison_step_fails_closed(self):
        a = act(["BUY_ANIMAL", "GOOSE", 1])
        for step in (True, 717.0, "717", None):
            with self.subTest(step=step):
                self.assertIs(
                    apply_terminal_animal_capital(a, {"step": step}, CFG, enabled=True),
                    a,
                )

    def test_bad_buy_quantity_fails_closed_whole_action(self):
        for qty in (True, 1.0, "1", 0, -1):
            a = act(["BUY_ANIMAL", "GOOSE", qty], ["BUY_ANIMAL", "COW", 1])
            with self.subTest(qty=qty):
                self.assertIs(
                    apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=True),
                    a,
                )

    def test_malformed_market_row_fails_closed(self):
        for row in (None, {}, ["BUY_ANIMAL"], [1, "GOOSE", 1]):
            a = act(row, ["BUY_ANIMAL", "GOOSE", 1])
            with self.subTest(row=row):
                self.assertIs(
                    apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=True),
                    a,
                )

    def test_worker_and_market_shape_preserved(self):
        a = {
            "farmer": ["MOVE", "NORTH"],
            "hands": [["PASS"]],
            "market": [["BUY_ANIMAL", "GOOSE", 1], []],
        }
        out = apply_terminal_animal_capital(a, {"step": 717}, CFG, enabled=True)
        self.assertEqual(out["farmer"], a["farmer"])
        self.assertEqual(out["hands"], a["hands"])
        self.assertEqual(len(out["market"]), len(a["market"]))
        self.assertEqual(out["market"][1], [])


if __name__ == "__main__":
    unittest.main()
