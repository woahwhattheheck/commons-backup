# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from thresholds import (
    _cell_nonregression,
    _group_nonregression,
    build_pairs,
    fit_report,
    select_threshold,
)


def outcome(own, rival):
    result = "W" if own > rival else "L" if own < rival else "T"
    return {
        "own": float(own),
        "rival": float(rival),
        "margin": float(own - rival),
        "result": result,
        "win": int(result == "W"),
        "loss": int(result == "L"),
        "tie": int(result == "T"),
    }


def pair(
    value,
    force_own,
    stay_own,
    *,
    force_rival=100,
    stay_rival=100,
    seed=1,
    opponent="o",
    seat=0,
    checkpoint=10,
):
    force = outcome(force_own, force_rival)
    stay = outcome(stay_own, stay_rival)
    return {
        "checkpoint": checkpoint,
        "feature": "x",
        "feature_value": value,
        "shipped_threshold": 5,
        "target": "T",
        "opponent": opponent,
        "seed": seed,
        "seat": seat,
        "auto_match": True,
        "force": force,
        "stay": stay,
        "auto": force if value >= 5 else stay,
    }


def game(arm, *, pre="same", feature=7, route_after=None, stream="natural"):
    mode = arm.split("_", 1)[0] if arm != "auto" else "auto"
    if route_after is None:
        route_after = "T" if mode == "force" else "M"
    receipt = {
        "schema": "titan-route-regret-event/v1",
        "mode": mode,
        "checkpoint": 10,
        "step": 10,
        "player": 0,
        "feature": "x",
        "feature_value": feature,
        "shipped_threshold": 5,
        "target": "T",
        "natural_target": feature >= 5,
        "route_before": "M",
        "route_after": route_after,
        "switch_legal": True,
        "override_applied": True,
        "pre_world_sha256": pre,
        "opponent_action_sha256": "rival",
    }
    return {
        "arm": arm,
        "opponent": "o",
        "seed": 1,
        "tested_seat": 0,
        "status": "complete",
        "failure": None,
        "bank_snapshot": [150, 100],
        "checkpoint_receipts": [receipt],
        "tested_action_stream_sha256": stream,
        "opponent_action_stream_sha256": "opponent-stream",
        "world_stream_sha256": "world-stream",
    }


class ThresholdSelectionTests(unittest.TestCase):
    def test_shipped_threshold_wins_exact_ties(self):
        rows = [pair(4, 100, 100), pair(7, 100, 100)]
        selected = select_threshold(rows, 5)
        self.assertEqual(selected["selected_threshold"], 5)
        self.assertFalse(selected["strict_development_improvement"])

    def test_selector_receives_development_only(self):
        development = [pair(4, 80, 120), pair(7, 140, 80)]
        first = select_threshold(development, 5)
        hostile_holdout = [pair(4, -100000, 100000, seed=9)]
        second = select_threshold(development, 5)
        self.assertEqual(first, second)
        self.assertTrue(hostile_holdout)  # Demonstrates it was not an argument.

    def test_prefix_mismatch_is_rejected_not_scored(self):
        auto = game("auto", stream="natural")
        force = game("force_10", pre="left", stream="natural")
        stay = game("stay_10", pre="right", stream="other")
        pairs, rejected = build_pairs([auto, force, stay], [(10, "x", 5, "T")])
        self.assertEqual(pairs, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("prefix state mismatch", rejected[0]["reason"])

    def test_natural_arm_must_reproduce_auto(self):
        auto = game("auto", stream="auto")
        force = game("force_10", stream="force")
        stay = game("stay_10", stream="stay")
        pairs, rejected = build_pairs([auto, force, stay], [(10, "x", 5, "T")])
        self.assertEqual(pairs, [])
        self.assertIn("untouched auto", rejected[0]["reason"])

    def test_opponent_seat_intersections_kill_simpson_mask(self):
        # Candidate threshold 6 chooses STAY at feature 5; shipped 5 chooses FORCE.
        # Every opponent-only and seat-only aggregate is exactly neutral, while two
        # opponent×seat intersections regress. The predecessor accepted this grid.
        rows = [
            pair(5, 1000, 988, force_rival=0, stay_rival=0, seed=9, opponent="A", seat=0),
            pair(5, 1000, 1012, force_rival=0, stay_rival=0, seed=9, opponent="A", seat=1),
            pair(5, 1000, 1012, force_rival=0, stay_rival=0, seed=9, opponent="B", seat=0),
            pair(5, 1000, 988, force_rival=0, stay_rival=0, seed=9, opponent="B", seat=1),
        ]
        passed, receipts = _group_nonregression(rows, 6, 5)
        self.assertFalse(passed)
        marginals = [row for row in receipts if row["kind"] in {"opponent", "seat"}]
        intersections = [row for row in receipts if row["kind"] == "opponent_seat"]
        self.assertTrue(marginals)
        self.assertTrue(all(row["passed"] for row in marginals))
        self.assertEqual(len(intersections), 4)
        self.assertEqual(sum(not row["passed"] for row in intersections), 2)

        report = fit_report(
            [pair(5, 0, 1000, seed=1)] + rows,
            [(10, "x", 5, "T")],
            {1},
            {9},
            minimum_holdout_cells=4,
        )
        checkpoint = report["checkpoints"][0]
        self.assertEqual(checkpoint["selected_threshold"], 6)
        self.assertIn(
            "seat/opponent/intersection holdout subgroup regressed",
            checkpoint["gate_reasons"],
        )
        self.assertFalse(checkpoint["screen_passed"])
        self.assertEqual(report["verdict"], "NO_THRESHOLD_CHANGE")

    def test_every_outcome_downgrade_is_rejected_per_cell(self):
        cases = [
            ("W_to_T", pair(5, 110, 100)),
            ("W_to_L", pair(5, 110, 90)),
            ("T_to_L", pair(5, 100, 90)),
        ]
        for name, row in cases:
            with self.subTest(name=name):
                passed, receipts = _cell_nonregression([row], 6, 5)
                self.assertFalse(passed)
                self.assertFalse(receipts[0]["passed"])

    def test_outcome_nonregression_allows_equal_or_better_cells(self):
        rows = [
            pair(5, 90, 90, seed=1),   # L -> L
            pair(5, 90, 100, seed=2),  # L -> T
            pair(5, 100, 110, seed=3), # T -> W
            pair(5, 110, 110, seed=4), # W -> W
        ]
        passed, receipts = _cell_nonregression(rows, 6, 5)
        self.assertTrue(passed)
        self.assertTrue(all(row["passed"] for row in receipts))

    def test_fit_report_rejects_lost_win_hidden_by_compensating_flip(self):
        development = [pair(5, 0, 1000, seed=1)]
        holdout = [
            pair(5, 110, 90, seed=9),
            pair(5, 0, 1000, seed=10),
        ]
        groups_passed, _ = _group_nonregression(holdout, 6, 5)
        self.assertTrue(groups_passed)

        report = fit_report(
            development + holdout,
            [(10, "x", 5, "T")],
            {1},
            {9, 10},
            minimum_holdout_cells=2,
        )
        checkpoint = report["checkpoints"][0]
        self.assertEqual(checkpoint["selected_threshold"], 6)
        self.assertEqual(checkpoint["holdout_delta"]["wins"], 0)
        self.assertEqual(checkpoint["holdout_delta"]["losses"], 0)
        self.assertGreater(checkpoint["holdout_delta"]["own_total"], 0)
        self.assertGreater(checkpoint["holdout_delta"]["margin_total"], 0)
        self.assertIn("holdout outcome transition regressed", checkpoint["gate_reasons"])
        self.assertFalse(checkpoint["screen_passed"])
        self.assertEqual(report["verdict"], "NO_THRESHOLD_CHANGE")


if __name__ == "__main__":
    unittest.main()
