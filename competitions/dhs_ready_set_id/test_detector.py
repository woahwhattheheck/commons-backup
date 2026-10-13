from __future__ import annotations

import copy
import math
import unittest

from detector import ValidationError, canonical_sha256, fit_reference, score_sample, validate_manifest
from synthetic_eval import evaluate


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.baseline = [
            {"a": float(i % 5), "b": float((i * 3) % 7), "c": float((i * 5) % 11)}
            for i in range(40)
        ]

    def test_fit_and_score_are_deterministic(self):
        model_a = fit_reference(self.baseline)
        model_b = fit_reference(copy.deepcopy(self.baseline))
        self.assertEqual(model_a, model_b)
        sample = {"a": 1.0, "b": 3.0, "c": 5.0}
        self.assertEqual(score_sample(model_a, sample), score_sample(model_b, sample))

    def test_strong_abstract_shift_is_flagged_and_explained(self):
        model = fit_reference(self.baseline)
        result = score_sample(model, {"a": 100.0, "b": -100.0, "c": 5.0}, top_k=2)
        self.assertTrue(result["flagged_for_follow_on"])
        self.assertGreater(result["risk_score"], 0.99)
        self.assertEqual(len(result["explanations"]), 2)
        self.assertEqual({x["feature"] for x in result["explanations"]}, {"a", "b"})
        self.assertEqual(len(result["result_sha256"]), 64)

    def test_feature_mismatch_and_nonfinite_values_fail_closed(self):
        model = fit_reference(self.baseline)
        with self.assertRaises(ValidationError):
            score_sample(model, {"a": 1.0, "b": 2.0})
        with self.assertRaises(ValidationError):
            score_sample(model, {"a": 1.0, "b": 2.0, "c": math.inf})
        poisoned = copy.deepcopy(self.baseline)
        poisoned[2]["a"] = float("nan")
        with self.assertRaises(ValidationError):
            fit_reference(poisoned)

    def test_constant_feature_is_safe_not_divide_by_zero(self):
        baseline = [{"constant": 7.0, "moving": float(i)} for i in range(12)]
        model = fit_reference(baseline)
        result = score_sample(model, {"constant": 7.0, "moving": 5.0})
        self.assertTrue(math.isfinite(result["risk_score"]))

    def test_manifest_contract_rejects_unknown_or_bad_digest(self):
        manifest = {
            "schema": "ready-set-id.dataset-manifest.v1",
            "dataset_id": "synthetic-fixture",
            "split": "validation",
            "feature_names": ["a", "b"],
            "rows_sha256": canonical_sha256([{"a": 1.0, "b": 2.0}]),
        }
        self.assertEqual(validate_manifest(manifest), manifest)
        bad = dict(manifest, rows_sha256="abc")
        with self.assertRaises(ValidationError):
            validate_manifest(bad)
        extra = dict(manifest, command="curl example.test")
        with self.assertRaises(ValidationError):
            validate_manifest(extra)

    def test_synthetic_eval_separates_shift_without_claiming_domain_performance(self):
        report = evaluate()
        self.assertLessEqual(report["false_positive_rate"], 0.08)
        self.assertGreaterEqual(report["detection_rate"], 0.90)
        self.assertIn("not biological/challenge performance", report["note"])


if __name__ == "__main__":
    unittest.main()
