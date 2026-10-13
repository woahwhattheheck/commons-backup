# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import unittest

from audit import audit_cell, panel_verdict


def game(action, *, score=100, rival=90, trace="a" * 64, observation=None):
    return {
        "episode_steps": 720,
        "steps": 719,
        "terminal_step": 718,
        "terminal_candidate_observation": observation or {"step": 718, "player": 0},
        "terminal_configuration": {"episodeSteps": 720},
        "terminal_candidate_action": deepcopy(action),
        "terminal_opponent_action": {"farmer": ["PASS"], "hands": [], "market": []},
        "trace_sha256": trace,
        "scores": [score, rival],
        "candidate_seat": 0,
    }


class AuditCellTests(unittest.TestCase):
    def test_changed_action_is_bound_to_positive_observed_delta(self):
        baseline_action = {"farmer": ["PASS"], "hands": [], "market": []}
        expected = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 2]]}
        baseline = game(baseline_action)
        candidate = game(expected, score=103, trace="b" * 64)

        def compose(*_args, **_kwargs):
            return expected, {
                "changed": True,
                "certified": True,
                "reason": "certified_terminal_cash_gain",
                "guaranteed_min_cash_gain": 2,
                "added_sell_units": {"WHEAT": 2},
                "dropped_actor_indices": [],
                "baseline_sell_units": 0,
                "candidate_sell_units": 2,
            }

        receipt = audit_cell(baseline, candidate, compose=compose, project_units=lambda: None)
        self.assertTrue(receipt["activated"])
        self.assertEqual(receipt["observed_own_delta"], 3)
        self.assertEqual(receipt["observed_margin_delta"], 3)
        self.assertEqual(receipt["bound_slack"], 1)
        self.assertFalse(receipt["outcome_regressed"])

    def test_rejects_candidate_action_not_equal_to_recomputed_certificate(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        baseline = game(action)
        candidate = game({**action, "market": [["SELL", "WHEAT", 1]]}, score=101, trace="b" * 64)
        with self.assertRaisesRegex(ValueError, "does not equal"):
            audit_cell(
                baseline,
                candidate,
                compose=lambda *_args, **_kwargs: (action, {"guaranteed_min_cash_gain": 0}),
                project_units=lambda: None,
            )

    def test_rejects_preterminal_drift(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        baseline = game(action, observation={"step": 718, "money": 100})
        candidate = game(action, observation={"step": 718, "money": 99})
        with self.assertRaisesRegex(ValueError, "drifted before"):
            audit_cell(
                baseline,
                candidate,
                compose=lambda *_args, **_kwargs: (action, {"guaranteed_min_cash_gain": 0}),
                project_units=lambda: None,
            )

    def test_rejects_lower_bound_violation(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        expected = {**action, "market": [["SELL", "WHEAT", 2]]}
        with self.assertRaisesRegex(ValueError, "below certified minimum"):
            audit_cell(
                game(action),
                game(expected, score=101, trace="b" * 64),
                compose=lambda *_args, **_kwargs: (
                    expected,
                    {
                        "changed": True,
                        "certified": True,
                        "guaranteed_min_cash_gain": 2,
                    },
                ),
                project_units=lambda: None,
            )


def rows(*, own=1.0, margin=1.0, base_outcome="W", candidate_outcome="W"):
    result = []
    for opponent in ("arlene", "v1"):
        for seat in (0, 1):
            for seed in range(8):
                result.append(
                    {
                        "opponent": opponent,
                        "candidate_seat": seat,
                        "seed": seed,
                        "own_delta": own,
                        "margin_delta": margin,
                        "baseline_outcome": base_outcome,
                        "candidate_outcome": candidate_outcome,
                        "terminal_audit": {
                            "valid": True,
                            "activated": True,
                            "observed_own_delta": own,
                            "observed_rival_delta": own - margin,
                            "observed_margin_delta": margin,
                            "guaranteed_min_cash_gain": 1,
                            "episode_steps": 720,
                            "actions_executed": 719,
                            "terminal_step": 718,
                            "observation_equal": True,
                            "configuration_equal": True,
                            "opponent_terminal_action_equal": True,
                        },
                    }
                )
    return result


class VerdictTests(unittest.TestCase):
    def test_accepts_complete_positive_own_and_margin_panel(self):
        panel_rows = rows()
        summary = {
            "mean_own_delta": 1.0,
            "median_own_delta": 1.0,
            "min_own_delta": 1.0,
            "mean_margin_delta": 1.0,
            "min_margin_delta": 1.0,
        }
        verdict = panel_verdict(panel_rows, summary)
        self.assertEqual(verdict["decision"], "ADVANCE")
        self.assertEqual(verdict["outcome_regressions"], 0)

    def test_rejects_one_negative_own_cell(self):
        panel_rows = rows()
        panel_rows[-1]["own_delta"] = -9.0
        summary = {
            "mean_own_delta": 0.6875,
            "median_own_delta": 1.0,
            "min_own_delta": -9.0,
            "mean_margin_delta": 1.0,
            "min_margin_delta": 1.0,
        }
        rejected = panel_verdict(panel_rows, summary)
        self.assertEqual(rejected["decision"], "REJECT")
        self.assertFalse(rejected["checks"]["no_negative_own_cash_cell"])

    def test_rejects_own_gain_that_helps_rival_more(self):
        panel_rows = rows(own=1.0, margin=-9.0)
        summary = {
            "mean_own_delta": 1.0,
            "median_own_delta": 1.0,
            "min_own_delta": 1.0,
            "mean_margin_delta": -9.0,
            "min_margin_delta": -9.0,
        }
        rejected = panel_verdict(panel_rows, summary)
        self.assertEqual(rejected["decision"], "REJECT")
        self.assertFalse(rejected["checks"]["positive_global_mean_margin"])
        self.assertFalse(rejected["checks"]["no_negative_opponent_seat_margin_stratum"])

    def test_rejects_win_to_tie_even_when_cash_and_margin_positive(self):
        panel_rows = rows()
        panel_rows[-1]["candidate_outcome"] = "T"
        summary = {
            "mean_own_delta": 1.0,
            "median_own_delta": 1.0,
            "min_own_delta": 1.0,
            "mean_margin_delta": 1.0,
            "min_margin_delta": 1.0,
        }
        rejected = panel_verdict(panel_rows, summary)
        self.assertEqual(rejected["decision"], "REJECT")
        self.assertFalse(rejected["checks"]["zero_outcome_regressions"])


if __name__ == "__main__":
    unittest.main()
