"""Focused contracts for the TITAN E09 public rival-response adapter."""
from __future__ import annotations

import unittest

from e09_rival_response import (
    build_response_branches,
    choose_response_robust_candidate,
    same_item_rival_plan,
)


class ResponseBranchTests(unittest.TestCase):
    def test_reaction_never_uses_the_simultaneous_current_turn(self):
        branches = build_response_branches(
            current_step=100,
            horizon_end=110,
            intervention_product="MILK",
            stress_quantity=3,
        )
        by_name = {branch.name: branch for branch in branches}
        self.assertEqual(by_name["fixed_path"].plan, ())
        self.assertEqual(by_name["next_turn_compete"].plan, ((101, 3),))
        self.assertTrue(by_name["next_turn_compete"].reacts_to_intervention)
        self.assertNotIn((100, 3), by_name["next_turn_compete"].plan)

    def test_fixed_path_preserves_current_turn_while_reaction_is_next_turn(self):
        branches = build_response_branches(
            current_step=100,
            horizon_end=110,
            intervention_product="MILK",
            stress_quantity=3,
            fixed_rival_plan=((100, 5),),
        )
        by_name = {branch.name: branch for branch in branches}
        self.assertEqual(by_name["fixed_path"].plan, ((100, 5),))
        self.assertFalse(by_name["fixed_path"].reacts_to_intervention)
        self.assertEqual(by_name["next_turn_compete"].plan, ((101, 3),))
        self.assertNotIn((100, 5), by_name["next_turn_compete"].plan)
        self.assertEqual(
            same_item_rival_plan(by_name["fixed_path"], "MILK"),
            ((100, 5),),
        )

    def test_delayed_branch_occurs_after_absorption_or_is_inapplicable(self):
        branches = build_response_branches(
            current_step=50,
            horizon_end=60,
            intervention_product="WOOL",
            stress_quantity=2,
            next_absorption_step=55,
        )
        by_name = {branch.name: branch for branch in branches}
        self.assertEqual(by_name["post_absorption_delay"].plan, ((56, 2),))

        clipped = build_response_branches(
            current_step=50,
            horizon_end=55,
            intervention_product="WOOL",
            stress_quantity=2,
            next_absorption_step=55,
        )
        self.assertNotIn("post_absorption_delay", {b.name for b in clipped})

    def test_switch_requires_explicit_public_production_support(self):
        branches = build_response_branches(
            current_step=10,
            horizon_end=20,
            intervention_product="MILK",
            stress_quantity=4,
            switch_products=("WOOL", "EGG", "MILK", "WOOL"),
            exposed_products=("WOOL",),
        )
        by_name = {branch.name: branch for branch in branches}
        self.assertIn("next_turn_switch_wool", by_name)
        self.assertNotIn("next_turn_switch_egg", by_name)
        self.assertEqual(by_name["next_turn_switch_wool"].product, "WOOL")
        self.assertEqual(by_name["next_turn_switch_wool"].plan, ((11, 4),))

    def test_zero_quantity_and_terminal_window_are_control_only(self):
        zero = build_response_branches(
            current_step=12,
            horizon_end=20,
            intervention_product="EGG",
            stress_quantity=0,
            fixed_rival_plan=((12, 2),),
        )
        terminal = build_response_branches(
            current_step=20,
            horizon_end=20,
            intervention_product="EGG",
            stress_quantity=3,
            fixed_rival_plan=((18, 1),),
        )
        self.assertEqual([b.name for b in zero], ["fixed_path"])
        self.assertEqual([b.name for b in terminal], ["fixed_path"])
        self.assertEqual(zero[0].plan, ((12, 2),))
        self.assertEqual(terminal[0].plan, ((18, 1),))

    def test_explicit_stress_quantity_is_bounded_not_inferred(self):
        with self.assertRaises(ValueError):
            build_response_branches(
                current_step=0,
                horizon_end=10,
                intervention_product="CARROT",
                stress_quantity=101,
                max_stress_quantity=100,
            )
        with self.assertRaises(ValueError):
            build_response_branches(
                current_step=0,
                horizon_end=10,
                intervention_product="CARROT",
                stress_quantity=-1,
            )
        with self.assertRaises(ValueError):
            build_response_branches(
                current_step=0,
                horizon_end=10,
                intervention_product="CARROT",
                stress_quantity=1,
                fixed_rival_plan=((0, 101),),
            )

    def test_single_product_adapter_rejects_cross_product_switch(self):
        branches = build_response_branches(
            current_step=1,
            horizon_end=5,
            intervention_product="MILK",
            stress_quantity=1,
            switch_products=("WOOL",),
            exposed_products=("WOOL",),
        )
        by_name = {branch.name: branch for branch in branches}
        self.assertEqual(
            same_item_rival_plan(by_name["next_turn_compete"], "MILK"),
            ((2, 1),),
        )
        self.assertIsNone(
            same_item_rival_plan(by_name["next_turn_switch_wool"], "MILK")
        )


class ResponseChoiceTests(unittest.TestCase):
    def test_identical_winner_across_responses_is_explicit_noop(self):
        decision = choose_response_robust_candidate(
            {
                "hold": {
                    "fixed_path": 100.0,
                    "next_turn_compete": 99.0,
                    "post_absorption_delay": 101.0,
                },
                "sell_now": {
                    "fixed_path": 90.0,
                    "next_turn_compete": 85.0,
                    "post_absorption_delay": 95.0,
                },
            }
        )
        self.assertEqual(decision.baseline_candidate, "hold")
        self.assertEqual(decision.chosen_candidate, "hold")
        self.assertFalse(decision.response_sensitive)
        self.assertFalse(decision.changed)

    def test_response_can_change_robust_choice_without_claiming_hidden_policy(self):
        decision = choose_response_robust_candidate(
            {
                "sell_now": {
                    "fixed_path": 110.0,
                    "next_turn_compete": 70.0,
                    "post_absorption_delay": 90.0,
                },
                "split": {
                    "fixed_path": 105.0,
                    "next_turn_compete": 100.0,
                    "post_absorption_delay": 101.0,
                },
                "hold": {
                    "fixed_path": 98.0,
                    "next_turn_compete": 96.0,
                    "post_absorption_delay": 97.0,
                },
            }
        )
        self.assertEqual(decision.baseline_candidate, "sell_now")
        self.assertTrue(decision.response_sensitive)
        self.assertTrue(decision.changed)
        self.assertEqual(decision.chosen_candidate, "split")
        self.assertEqual(decision.worst_value, 100.0)

    def test_incomparable_or_nonfinite_rows_fail_closed(self):
        with self.assertRaises(ValueError):
            choose_response_robust_candidate(
                {
                    "a": {"fixed_path": 1.0, "response": 2.0},
                    "b": {"fixed_path": 1.0},
                }
            )
        with self.assertRaises(ValueError):
            choose_response_robust_candidate(
                {"a": {"fixed_path": float("nan")}}
            )


if __name__ == "__main__":
    unittest.main()
