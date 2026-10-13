#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("agent_index", HERE / "analyze_agent_index.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def row(seed, opponent, seat, margin):
    return {"seed": seed, "opponent": opponent, "seat": seat, "margin": margin}


class AgentIndexPredictability(unittest.TestCase):
    def test_true_seat_effect_survives_exact_pairing(self):
        rows = []
        for seed in range(8):
            rows += [row(seed, "A", 0, 100 + seed), row(seed, "A", 1, 300 + seed)]
        report = mod.analyze(rows, require_complete=True)
        self.assertEqual(report["matched_pairs"], 8)
        self.assertEqual(report["paired_seat1_minus_seat0_mean"], 200)
        self.assertEqual(report["equal_opponent_weighted_mean_delta"], 200)
        self.assertEqual(report["sign_test"]["positive"], 8)
        self.assertLessEqual(report["sign_test"]["two_sided_p"], 0.01)

    def test_simpsons_paradox_opponent_mix_does_not_fake_paired_effect(self):
        rows = []
        for seed in range(4):
            rows += [row(f"A{seed}", "easy", 0, 1000), row(f"A{seed}", "easy", 1, 1000)]
            rows += [row(f"B{seed}", "hard", 0, -1000), row(f"B{seed}", "hard", 1, -1000)]
        for seed in range(20):
            rows.append(row(f"Ue{seed}", "easy", 1, 1000))
            rows.append(row(f"Uh{seed}", "hard", 0, -1000))
        report = mod.analyze(rows)
        self.assertEqual(report["paired_seat1_minus_seat0_mean"], 0)
        self.assertEqual(report["equal_opponent_weighted_mean_delta"], 0)
        self.assertGreater(report["raw_opponent_assignment_tv"], 0.7)
        self.assertLess(report["matched_pair_coverage"], 0.3)

    def test_require_complete_rejects_missing_seat(self):
        with self.assertRaises(mod.DataError):
            mod.analyze([row(1, "A", 0, 1), row(2, "A", 0, 1)], require_complete=True)

    def test_duplicate_exact_cell_rejected(self):
        with self.assertRaises(mod.DataError):
            mod.analyze([row(1, "A", 0, 1), row(1, "A", 0, 2), row(1, "A", 1, 3)])

    def test_seed_identifier_type_collision_fails_closed(self):
        with self.assertRaises(mod.DataError):
            mod.analyze(
                [row(1, "A", 0, 10), row("1", "A", 1, 20)],
                require_complete=True,
            )

    def test_opponent_identifier_type_collision_fails_closed(self):
        with self.assertRaises(mod.DataError):
            mod.analyze(
                [row(1, 7, 0, 10), row(1, "7", 1, 20)],
                require_complete=True,
            )

    def test_mixed_identifier_primitive_types_fail_even_without_text_collision(self):
        with self.assertRaises(mod.DataError):
            mod.analyze(
                [row(1, "A", 0, 10), row(1, "A", 1, 20),
                 row("2", "A", 0, 30), row("2", "A", 1, 40)]
            )

    def test_rewards_are_target_relative_by_seat(self):
        records = [
            {"seed": 1, "opponent": "A", "seat": 0, "rewards": [120, 20]},
            {"seed": 1, "opponent": "A", "seat": 1, "rewards": [20, 120]},
        ]
        report = mod.analyze(records, require_complete=True)
        self.assertEqual(report["seat0_mean_margin_matched"], 100)
        self.assertEqual(report["seat1_mean_margin_matched"], 100)
        self.assertEqual(report["paired_seat1_minus_seat0_mean"], 0)

    def test_bool_seat_and_nonfinite_margin_fail_closed(self):
        with self.assertRaises(mod.DataError):
            mod.analyze([{"seed": 1, "opponent": "A", "seat": True, "margin": 1}])
        with self.assertRaises(mod.DataError):
            mod.analyze([row(1, "A", 0, float("inf")), row(1, "A", 1, 0)])

    def test_huge_integer_overflow_fails_closed(self):
        with self.assertRaises(mod.DataError):
            mod.normalize_record(row(1, "A", 0, 10**1000), 0)

    def test_derived_float_overflow_fails_closed(self):
        with self.assertRaises(mod.DataError):
            mod.normalize_record({"seed": 1, "opponent": "A", "seat": 0,
                                  "rewards": [1e308, -1e308]}, 0)
        with self.assertRaises(mod.DataError):
            mod.normalize_record({"seed": 1, "opponent": "A", "seat": 0,
                                  "score": 1e308, "opponent_score": -1e308}, 0)

    def test_paired_delta_overflow_fails_closed(self):
        with self.assertRaises(mod.DataError):
            mod.analyze(
                [row(1, "A", 0, -1e308), row(1, "A", 1, 1e308)],
                require_complete=True,
            )

    def test_conflicting_margin_cannot_override_rewards(self):
        with self.assertRaises(mod.DataError):
            mod.normalize_record({"seed": 1, "opponent": "A", "seat": 0,
                                  "margin": 1e300, "rewards": [168572, 3550]}, 0)

    def test_conflicting_score_pair_cannot_override_rewards(self):
        with self.assertRaises(mod.DataError):
            mod.normalize_record({"seed": 1, "opponent": "A", "seat": 0,
                                  "rewards": [120, 20], "score": 121,
                                  "opponent_score": 20}, 0)

    def test_relative_tolerance_cannot_hide_large_absolute_conflict(self):
        with self.assertRaises(mod.DataError):
            mod.normalize_record({"seed": 1, "opponent": "A", "seat": 0,
                                  "margin": 1e20,
                                  "rewards": [1e20 + 50_000_000, 0]}, 0)

    def test_large_integer_consistency_is_not_collapsed_through_float(self):
        with self.assertRaises(mod.DataError):
            mod.normalize_record({"seed": 1, "opponent": "A", "seat": 0,
                                  "margin": 10**20,
                                  "rewards": [10**20 + 1, 0]}, 0)

    def test_redundant_consistent_outcomes_are_accepted(self):
        normalized = mod.normalize_record({"seed": 1, "opponent": "A", "seat": 1,
                                           "margin": 100, "rewards": [20, 120],
                                           "score": 120, "opponent_score": 20}, 0)
        self.assertEqual(normalized["margin"], 100)

    def test_legitimate_large_reward_margin_is_preserved(self):
        normalized = mod.normalize_record({"seed": 9922023, "opponent": "starter",
                                           "seat": 0, "rewards": [168572, 3550]}, 0)
        self.assertEqual(normalized["margin"], 165022)

    def test_no_universal_65000_cap_is_smuggled_in(self):
        normalized = mod.normalize_record({"seed": 9922023, "opponent": "starter",
                                           "seat": 0, "rewards": [168572, 3550]}, 0,
                                          authenticated_max_abs_margin=200000)
        self.assertEqual(normalized["margin"], 165022)
        with self.assertRaises(mod.DataError):
            mod.normalize_record({"seed": 9922023, "opponent": "starter",
                                  "seat": 0, "rewards": [168572, 3550]}, 0,
                                 authenticated_max_abs_margin=65000)

    def test_authenticated_margin_bound_rejects_never_clips(self):
        accepted = mod.normalize_record(row(1, "A", 0, 999), 0,
                                        authenticated_max_abs_margin=1000)
        self.assertEqual(accepted["margin"], 999)
        with self.assertRaises(mod.DataError):
            mod.normalize_record(row(1, "A", 0, 1001), 0,
                                 authenticated_max_abs_margin=1000)
        with self.assertRaises(mod.DataError):
            mod.normalize_record(row(1, "A", 0, 0), 0,
                                 authenticated_max_abs_margin=True)
        with self.assertRaises(mod.DataError):
            mod.normalize_record(row(1, "A", 0, 0), 0,
                                 authenticated_max_abs_margin=0)

    def test_structured_outcome_guard_rejects_margin_only(self):
        with self.assertRaises(mod.DataError):
            mod.normalize_record(row(1, "A", 0, 10), 0, require_structured_outcome=True)
        normalized = mod.normalize_record(
            {"seed": 1, "opponent": "A", "seat": 0, "rewards": [120, 20]},
            0,
            require_structured_outcome=True,
        )
        self.assertEqual(normalized["margin"], 100)

    def test_analyze_reports_non_clipping_input_guard(self):
        records = [
            {"seed": 1, "opponent": "A", "seat": 0, "rewards": [120, 20]},
            {"seed": 1, "opponent": "A", "seat": 1, "rewards": [20, 120]},
        ]
        report = mod.analyze(
            records,
            require_complete=True,
            require_structured_outcome=True,
            authenticated_max_abs_margin=1000,
        )
        self.assertEqual(
            report["input_guard"],
            {
                "require_structured_outcome": True,
                "authenticated_max_abs_margin": 1000,
                "margin_bound_policy": "reject_not_clip",
            },
        )

    def test_default_remains_no_guessed_magnitude_bound(self):
        normalized = mod.normalize_record(row(1, "A", 0, 1e300), 0)
        self.assertEqual(normalized["margin"], 1e300)

    def test_equal_opponent_weighting_blocks_frequency_domination(self):
        rows = []
        for seed in range(20):
            rows += [row(f"A{seed}", "A", 0, 0), row(f"A{seed}", "A", 1, 10)]
        rows += [row("B0", "B", 0, 0), row("B0", "B", 1, -100)]
        report = mod.analyze(rows, require_complete=True)
        self.assertGreater(report["paired_seat1_minus_seat0_mean"], 0)
        self.assertEqual(report["equal_opponent_weighted_mean_delta"], -45)

    def test_cohen_dz_zero_variance_is_strict_json_safe(self):
        zero = mod.analyze([row(1, "A", 0, 5), row(1, "A", 1, 5),
                            row(2, "A", 0, 7), row(2, "A", 1, 7)], require_complete=True)
        self.assertEqual(zero["cohen_dz"], 0)
        constant = mod.analyze([row(1, "A", 0, 0), row(1, "A", 1, 2),
                                row(2, "A", 0, 0), row(2, "A", 1, 2)], require_complete=True)
        self.assertIsNone(constant["cohen_dz"])
        json.dumps(constant, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
