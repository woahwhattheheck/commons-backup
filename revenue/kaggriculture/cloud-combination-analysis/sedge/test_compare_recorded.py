# SPDX-License-Identifier: Apache-2.0
"""Post-processing regressions; synthetic mutations are not game evidence."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from compare_recorded import analyze, compare_paths, InvalidResult

HERE = Path(__file__).resolve().parent


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "retained_case.json").read_text())

    def test_retained_development_discriminator(self):
        result = analyze(self.data)
        self.assertEqual(result["total_policy"]["mean_delta"],
                         {"own_cash": 1087.0, "rival_cash": 84.0, "margin": 1003.0})
        path = result["pairs"][0]["path_diagnostics"]
        self.assertEqual(path["counter_only_days"], [27, 28])
        self.assertEqual(path["changed_logged_event_days"], [])
        self.assertEqual(path["spatial_weed_equivalence"], "not_recorded")
        self.assertFalse(result["trace_scope"]["full_match_trace"])
        self.assertEqual(result["total_policy"]["outcome_transitions"], {"W->W": 1})

    def test_changed_shop_is_retained_in_total(self):
        self.data["rows"][1]["path"][0]["shop_unlocked"] = "BAKERY"
        result = analyze(self.data)
        self.assertEqual(result["total_policy"]["pairs"], 1)
        self.assertEqual(result["diagnostics"]["changed_logged_events"]["pairs"], 1)
        self.assertEqual(result["pairs"][0]["path_diagnostics"]["changed_logged_event_days"], [27])

    def test_changed_weed_count_is_event_change(self):
        self.data["rows"][1]["path"][1]["farms"][0]["weeds_spawned"] = 1
        path = analyze(self.data)["pairs"][0]["path_diagnostics"]
        self.assertEqual(path["changed_logged_event_days"], [28])
        self.assertEqual(path["counter_only_days"], [27])

    def test_equal_nonzero_weed_counts_do_not_prove_coordinates(self):
        for row in self.data["rows"]:
            row["path"][0]["farms"][0]["weeds_spawned"] = 1
        path = analyze(self.data)["pairs"][0]["path_diagnostics"]
        self.assertEqual(path["spatial_weed_equivalence"], "not_recorded")
        self.assertEqual(path["rng_state_equivalence"], "not_recorded")

    def test_missing_path_is_unknown_not_equal(self):
        del self.data["rows"][1]["path"]
        result = analyze(self.data)
        self.assertEqual(result["total_policy"]["pairs"], 1)
        self.assertEqual(result["diagnostics"]["incomplete_paths"]["pairs"], 1)
        self.assertEqual(result["diagnostics"]["equal_logged_events"]["pairs"], 0)

    def test_mismatched_day_coverage_is_incomplete(self):
        self.data["rows"][1]["path"].pop()
        path = analyze(self.data)["pairs"][0]["path_diagnostics"]
        self.assertEqual(path["missing_candidate_days"], [28])
        self.assertEqual(path["status"], "incomplete_recorded_days")

    def test_duplicate_rows_are_not_more_evidence(self):
        self.data["rows"].append(deepcopy(self.data["rows"][0]))
        with self.assertRaises(InvalidResult):
            analyze(self.data)

    def test_duplicate_days_rejected(self):
        self.data["rows"][0]["path"].append(deepcopy(self.data["rows"][0]["path"][0]))
        with self.assertRaises(InvalidResult):
            analyze(self.data)

    def test_inconsistent_draw_total_rejected(self):
        self.data["rows"][0]["path"][0]["draws_before_shop"] += 1
        with self.assertRaises(InvalidResult):
            analyze(self.data)

    def test_nonfinite_cash_rejected(self):
        for value in (float("nan"), float("inf"), True):
            self.data["rows"][0]["own_cash"] = value
            with self.assertRaises(InvalidResult):
                analyze(self.data)

    def test_inconsistent_margin_rejected(self):
        self.data["rows"][0]["margin"] += 1
        with self.assertRaises(InvalidResult):
            analyze(self.data)

    def test_missing_cell_not_zero_filled(self):
        self.data["rows"].pop()
        result = analyze(self.data)
        self.assertEqual(result["total_policy"]["pairs"], 0)
        self.assertEqual(result["missing_cells"][0]["absent"], "candidate")
        self.assertIsNone(result["total_policy"]["mean_delta"]["own_cash"])

    def test_failed_cell_not_scored_as_win(self):
        self.data["rows"][1]["error"] = "retained synthetic failure"
        result = analyze(self.data)
        self.assertEqual(result["total_policy"]["pairs"], 0)
        self.assertEqual(len(result["failed_cells"]), 1)

    def test_source_mismatch_not_joined(self):
        self.data["rows"][1]["opponent_id"]["sha256"] = "different"
        with self.assertRaises(InvalidResult):
            analyze(self.data)

    def test_malformed_opponent_metadata_rejected(self):
        self.data["rows"][1]["opponent_id"] = None
        with self.assertRaises(InvalidResult):
            analyze(self.data)

    def test_different_round_counts_rejected(self):
        self.data["rows"][1]["rounds"] -= 1
        with self.assertRaises(InvalidResult):
            analyze(self.data)

    def test_other_arms_are_explicit_and_inputs_unchanged(self):
        self.data["rows"].append(dict(arm="other"))
        original = deepcopy(self.data)
        result = analyze(self.data)
        self.assertEqual(result["ignored_arms"], {"other": 1})
        self.assertEqual(self.data, original)

    def test_negative_delta_and_loss_are_retained(self):
        self.data["rows"][1].update(own_cash=10, rival_cash=20, margin=-10)
        result = analyze(self.data)
        self.assertEqual(result["total_policy"]["outcome_transitions"], {"W->L": 1})
        self.assertLess(result["total_policy"]["mean_delta"]["own_cash"], 0)


if __name__ == "__main__":
    unittest.main()
