from __future__ import annotations

import copy
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import mixture_gate as gate
from test_support import (
    H64, H64B, H64C, H64D, H64E, H64F, H40, H40B,
    build_document, quantity_fraction,
)

class MixtureGateContractsA(unittest.TestCase):
    def test_robust_advance_on_uniform_positive_families(self):
        doc = build_document(
            {
                "arlene": [(10, -2)] * 5,
                "apex": [(8, -1)] * 5,
                "v1": [(6, 0)] * 5,
            },
            counts={"arlene": 6, "apex": 3, "v1": 1},
            bounds={"arlene": ("2/5", "4/5"), "apex": ("1/10", "1/2"), "v1": ("0", "2/5")},
        )
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "ROBUST_ADVANCE")
        self.assertGreater(quantity_fraction(result, "mixture_robustness", "own_cash", "worst_case_value"), 0)
        self.assertGreater(quantity_fraction(result, "mixture_robustness", "margin", "worst_case_value"), 0)

    def test_positive_nominal_mean_can_fail_under_legal_mixture_shift(self):
        doc = build_document(
            {
                "a": [(20, 0)] * 5,
                "b": [(2, 0)] * 5,
                "c": [(-30, 0)] * 5,
            },
            counts={"a": 80, "b": 15, "c": 5},
            bounds={"a": ("1/2", "4/5"), "b": ("1/10", "1/5"), "c": ("1/20", "7/20")},
            radius="3/10",
            own_floor=-100,
            margin_floor=-100,
        )
        result = gate.evaluate(doc)
        nominal = quantity_fraction(result, "mixture_robustness", "own_cash", "nominal_value")
        worst = quantity_fraction(result, "mixture_robustness", "own_cash", "worst_case_value")
        weights = result["mixture_robustness"]["own_cash"]["witness_weights"]
        self.assertGreater(nominal, 0)
        self.assertLess(worst, 0)
        self.assertEqual(result["verdict"], "ROBUST_HOLD")
        self.assertEqual(weights["a"]["fraction"], "1/2")
        self.assertEqual(weights["b"]["fraction"], "3/20")
        self.assertEqual(weights["c"]["fraction"], "7/20")

    def test_total_variation_zero_returns_nominal_distribution(self):
        doc = build_document(
            {"a": [(5, 0)] * 5, "b": [(-1, 0)] * 5},
            counts={"a": 3, "b": 1},
            radius="0",
            own_floor=-5,
            margin_floor=-5,
        )
        result = gate.evaluate(doc)
        robust = result["mixture_robustness"]["own_cash"]
        self.assertEqual(robust["nominal_value"], robust["worst_case_value"])
        self.assertEqual(robust["mass_moved"]["fraction"], "0/1")
        self.assertEqual(robust["witness_weights"]["a"]["fraction"], "3/4")
        self.assertEqual(robust["witness_weights"]["b"]["fraction"], "1/4")

    def test_leave_one_seed_out_floor_blocks_fragile_positive_mean(self):
        doc = build_document(
            {"a": [(30, 0), (30, 0), (30, 0), (30, 0), (-100, 0)]},
            radius="0",
            own_floor=-200,
            margin_floor=-200,
        )
        result = gate.evaluate(doc)
        family = result["evidence"]["family_summaries"]["a"]
        self.assertGreater(gate.Fraction(family["mean_own_delta"]["fraction"]), 0)
        self.assertLess(gate.Fraction(family["leave_one_seed_out_own_floor"]["fraction"]), 0)
        self.assertEqual(result["verdict"], "ROBUST_HOLD")

    def test_seed_tail_floor_counts_mirrored_seats_once(self):
        doc = build_document({"a": [(10, 0), (10, 0), (10, 0), (10, 0), (-1, 0)]})
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "ROBUST_HOLD")
        failures = [reason for reason in result["reasons"] if reason["reason"] == "seed_own_below_floor"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(result["evidence"]["family_summaries"]["a"]["seed_cluster_count"], 5)

    def test_worsened_outcome_is_never_hidden_by_cash_average(self):
        doc = build_document({"a": [(10, 0)] * 5})
        target = doc["panel"]["cells"][0]
        target.update(
            {
                "incumbent_own": 100,
                "incumbent_rival": 99,
                "candidate_own": 110,
                "candidate_rival": 119,
            }
        )
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "ROBUST_HOLD")
        self.assertEqual(len(result["evidence"]["outcome_regressions"]), 1)
        self.assertEqual(result["evidence"]["outcome_regressions"][0]["incumbent_outcome"], "W")
        self.assertEqual(result["evidence"]["outcome_regressions"][0]["candidate_outcome"], "L")

    def test_score_delta_without_action_change_blocks_evidence(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["panel"]["cells"][0]["action_changed"] = False
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "BLOCK_EVIDENCE")
        self.assertIn("score_delta_without_action_change", {row["reason"] for row in result["evidence"]["evidence_failures"]})

    def test_score_delta_without_trace_change_blocks_evidence(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["panel"]["cells"][0]["trace_changed"] = False
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "BLOCK_EVIDENCE")

    def test_nonpassing_upstream_causality_blocks_evidence(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["panel"]["causality_status"] = "SCREEN_ONLY"
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "BLOCK_EVIDENCE")

    def test_uncalibrated_family_has_precedence(self):
        doc = build_document({"a": [(10, 0)] * 5, "b": [(10, 0)] * 5})
        doc["calibration"]["families"][1]["status"] = "BLOCK_UNCALIBRATED"
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "BLOCK_UNCALIBRATED")
        self.assertEqual(result["reasons"][0]["families"], ["b"])

    def test_too_few_independent_seeds_requests_more_evidence(self):
        doc = build_document({"a": [(10, 0)] * 4}, minimum_seed_clusters=5)
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "MORE_EVIDENCE_REQUIRED")


class MixtureGatePeerAssistContracts(unittest.TestCase):
    def test_family_seat_floor_blocks_mirrored_seat_cancellation(self):
        doc = build_document({"a": [(10, 0)] * 5})
        for cell in doc["panel"]["cells"]:
            if cell["candidate_seat"] == 0:
                cell["candidate_own"] = cell["incumbent_own"] - 5
                cell["action_changed"] = True
                cell["trace_changed"] = True
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "ROBUST_HOLD")
        family = result["evidence"]["family_summaries"]["a"]
        self.assertEqual(family["leave_one_seed_out_own_floor"]["fraction"], "5/2")
        seat_zero = next(row for row in family["family_seats"] if row["candidate_seat"] == 0)
        self.assertEqual(seat_zero["mean_own_delta"]["fraction"], "-5/1")
        reasons = {row["reason"] for row in result["reasons"]}
        self.assertIn("family_seat_own_below_floor", reasons)
        self.assertIn("family_seat_margin_below_floor", reasons)

    def test_uniform_family_reference_blocks_count_dominated_average(self):
        doc = build_document(
            {
                "a": [(10, 0)] * 5,
                "b": [(-8, 0)] * 5,
                "c": [(-8, 0)] * 5,
            },
            counts={"a": 98, "b": 1, "c": 1},
            radius="0",
            own_floor=-100,
            margin_floor=-100,
            family_seat_own_floor=-100,
            family_seat_margin_floor=-100,
            require_leave_one_family_out=False,
        )
        result = gate.evaluate(doc)
        self.assertGreater(
            quantity_fraction(result, "mixture_robustness", "own_cash", "worst_case_value"),
            0,
        )
        uniform = result["mixture_robustness"]["distribution_free_stress"]["own_cash"]["uniform_family_reference"]
        self.assertEqual(uniform["value"]["fraction"], "-2/1")
        self.assertFalse(uniform["gate_pass"])
        self.assertEqual(result["verdict"], "ROBUST_HOLD")
        self.assertIn("uniform_family_own_not_admissible", {row["reason"] for row in result["reasons"]})

    def test_leave_one_family_out_blocks_single_family_dependency(self):
        doc = build_document(
            {
                "a": [(100, 0)] * 5,
                "b": [(-1, 0)] * 5,
                "c": [(-1, 0)] * 5,
            },
            counts={"a": 98, "b": 1, "c": 1},
            radius="0",
            own_floor=-100,
            margin_floor=-100,
            family_seat_own_floor=-100,
            family_seat_margin_floor=-100,
        )
        result = gate.evaluate(doc)
        self.assertGreater(
            quantity_fraction(result, "mixture_robustness", "own_cash", "worst_case_value"),
            0,
        )
        stress = result["mixture_robustness"]["distribution_free_stress"]["own_cash"]
        self.assertGreater(gate.Fraction(stress["uniform_family_reference"]["value"]["fraction"]), 0)
        leave_one = stress["leave_one_family_out"]
        self.assertEqual(leave_one["minimum_value"]["fraction"], "-1/1")
        failed = [row["omitted_family"] for row in leave_one["rows"] if not row["sign_admissible"]]
        self.assertEqual(failed, ["a"])
        self.assertEqual(result["verdict"], "ROBUST_HOLD")
        self.assertIn("leave_one_family_out_own_not_admissible", {row["reason"] for row in result["reasons"]})
