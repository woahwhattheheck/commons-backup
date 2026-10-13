# SPDX-License-Identifier: Apache-2.0
"""Focused regressions for S05 hosted-panel fail-closed completeness."""
import unittest

from s05_completeness import (
    completeness_errors,
    expected_per_variant,
    expected_total,
    nseeds_from,
    require_complete_panel,
    usable_scores,
)

VARIANTS = ("control", "shadow", "prior")


def row(variant, index, seat, status="complete", scores=None):
    if scores is None and status == "complete":
        scores = [10.0, -3.0]
    return {
        "variant": variant,
        "index": index,
        "seed": 1000 + index,
        "candidate_seat": seat,
        "status": status,
        "scores": scores,
    }


def panel(nseeds=16, mutate=None):
    games = [
        row(v, i, seat)
        for v in VARIANTS
        for i in range(nseeds)
        for seat in (0, 1)
    ]
    if mutate is not None:
        games = mutate(games)
    return {"schema": 1, "seeds": list(range(nseeds)), "games": games}


class Completeness(unittest.TestCase):
    def test_full_sixteen_seed_panel_is_96_and_32_per_variant(self):
        report = panel(16)
        self.assertEqual(expected_total(16), 96)
        self.assertEqual(expected_per_variant(16), 32)
        self.assertEqual(len(report["games"]), 96)
        self.assertEqual(completeness_errors(report, 16), [])
        require_complete_panel(report, 16)

    def test_one_seed_smoke_panel_is_six_complete_rows(self):
        report = panel(1)
        self.assertEqual(completeness_errors(report, 1), [])

    def test_launcher_error_row_fails_closed(self):
        def mutate(games):
            games[0]["status"] = "launcher_error"
            games[0]["scores"] = None
            games[0]["failure"] = "TimeoutError: agent"
            return games

        errors = completeness_errors(panel(16, mutate), 16)
        self.assertTrue(any(e.startswith("launcher_error:") for e in errors))
        self.assertTrue(any(e.startswith("missing_score:") for e in errors))
        with self.assertRaises(SystemExit) as caught:
            require_complete_panel(panel(16, mutate), 16)
        self.assertIn("S05_INCOMPLETE", str(caught.exception))

    def test_non_complete_status_fails_closed(self):
        def mutate(games):
            games[5]["status"] = "engine_error"
            return games

        errors = completeness_errors(panel(16, mutate), 16)
        self.assertTrue(any(e.startswith("non_complete:") for e in errors))

    def test_missing_scores_on_complete_row_fails_closed(self):
        def mutate(games):
            games[4]["scores"] = None
            return games

        errors = completeness_errors(panel(16, mutate), 16)
        self.assertTrue(any(e.startswith("missing_score:") for e in errors))
        self.assertFalse(usable_scores(None))
        self.assertFalse(usable_scores(["x", "y"]))
        self.assertTrue(usable_scores([1, 0]))

    def test_short_panel_fails_row_count(self):
        def mutate(games):
            return games[:-1]

        errors = completeness_errors(panel(16, mutate), 16)
        self.assertIn("row_count:95!=96", errors)

    def test_missing_variant_cells_fail_per_variant_count(self):
        def mutate(games):
            return [g for g in games if g["variant"] != "shadow"]

        errors = completeness_errors(panel(16, mutate), 16)
        self.assertIn("row_count:64!=96", errors)
        self.assertIn("variant_shadow:0!=32", errors)

    def test_nseeds_prefers_env_then_report_seeds(self):
        report = panel(16)
        self.assertEqual(nseeds_from(report, {"S05_SEEDS": "16"}), 16)
        self.assertEqual(nseeds_from(report, {}), 16)
        self.assertEqual(nseeds_from({"games": []}, {}), 0)
        self.assertEqual(completeness_errors({"games": []}, 0), ["nseeds_invalid"])


if __name__ == "__main__":
    unittest.main()
