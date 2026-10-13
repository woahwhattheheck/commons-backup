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

class MixtureGateContractsB(unittest.TestCase):
    def test_no_action_and_no_economic_change_is_inactive(self):
        doc = build_document({"a": [(0, 0)] * 5}, strict=False)
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "INACTIVE")

    def test_action_change_without_economic_gain_is_hold_when_strict(self):
        doc = build_document({"a": [(0, 0)] * 5})
        for cell in doc["panel"]["cells"]:
            cell["action_changed"] = True
            cell["trace_changed"] = True
        result = gate.evaluate(doc)
        self.assertEqual(result["verdict"], "ROBUST_HOLD")

    def test_duplicate_cell_is_malformed(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["panel"]["cells"].append(copy.deepcopy(doc["panel"]["cells"][0]))
        with self.assertRaisesRegex(gate.ValidationError, "duplicate"):
            gate.evaluate(doc)

    def test_missing_mirrored_seat_is_malformed(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["panel"]["cells"] = [cell for cell in doc["panel"]["cells"] if not (cell["seed"] == "a-1" and cell["candidate_seat"] == 1)]
        with self.assertRaisesRegex(gate.ValidationError, "both candidate seats"):
            gate.evaluate(doc)

    def test_nonfinite_score_is_malformed(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["panel"]["cells"][0]["candidate_own"] = math.inf
        with self.assertRaises(gate.ValidationError) as caught:
            gate.evaluate(doc)
        self.assertEqual(caught.exception.code, "NONFINITE")

    def test_boolean_score_is_malformed(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["panel"]["cells"][0]["candidate_own"] = True
        with self.assertRaises(gate.ValidationError) as caught:
            gate.evaluate(doc)
        self.assertEqual(caught.exception.code, "TYPE")

    def test_infeasible_box_bounds_are_malformed(self):
        doc = build_document(
            {"a": [(10, 0)] * 5, "b": [(10, 0)] * 5},
            counts={"a": 1, "b": 1},
            bounds={"a": ("3/5", "4/5"), "b": ("3/5", "4/5")},
        )
        with self.assertRaises(gate.ValidationError) as caught:
            gate.evaluate(doc)
        self.assertEqual(caught.exception.code, "NOMINAL_BOUND")

    def test_family_set_mismatch_is_malformed(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["calibration"]["families"][0]["opponent_family"] = "b"
        with self.assertRaises(gate.ValidationError) as caught:
            gate.evaluate(doc)
        self.assertEqual(caught.exception.code, "FAMILY_CLOSURE")

    def test_case_variant_family_is_rejected_not_aliased(self):
        doc = build_document({"a": [(10, 0)] * 5})
        doc["panel"]["cells"][0]["opponent_family"] = "A"
        with self.assertRaises(gate.ValidationError) as caught:
            gate.evaluate(doc)
        self.assertEqual(caught.exception.code, "FAMILY_CASE")

    def test_order_independent_normalized_input_and_receipt(self):
        doc = build_document({"a": [(10, -1)] * 5, "b": [(9, -1)] * 5})
        result_a = gate.evaluate(doc)
        shuffled = copy.deepcopy(doc)
        shuffled["panel"]["cells"].reverse()
        shuffled["calibration"]["families"].reverse()
        shuffled["mixture"]["families"].reverse()
        result_b = gate.evaluate(shuffled)
        self.assertEqual(result_a["normalized_input_sha256"], result_b["normalized_input_sha256"])
        self.assertEqual(result_a["receipt_sha256"], result_b["receipt_sha256"])

    def test_fractional_values_remain_exact(self):
        doc = build_document({"a": [(10, 0)] * 5})
        for cell in doc["panel"]["cells"]:
            cell["candidate_own"] = str(cell["incumbent_own"] + 1) + "/3"
            cell["incumbent_own"] = str(cell["incumbent_own"]) + "/3"
        result = gate.evaluate(doc)
        family = result["evidence"]["family_summaries"]["a"]
        self.assertEqual(family["mean_own_delta"]["fraction"], "1/3")
