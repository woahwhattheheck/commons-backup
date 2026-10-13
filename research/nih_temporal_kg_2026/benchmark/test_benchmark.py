from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.run_benchmark import BenchmarkError, load_dataset, run_benchmark, static_answer, temporal_answer, validate_dataset, verify_result

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases.json"


class DatasetContractTests(unittest.TestCase):
    def test_dataset_is_large_unique_and_deterministically_sorted(self):
        data = load_dataset(CASES)
        ids = [case["id"] for case in data["cases"]]
        self.assertGreaterEqual(len(ids), 12)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))

    def test_controls_exist_and_are_not_designed_to_force_static_failure(self):
        data = load_dataset(CASES)
        controls = [case for case in data["cases"] if case["error_class"] == "control"]
        self.assertGreaterEqual(len(controls), 4)
        for case in controls:
            self.assertEqual(case["expected"], static_answer(case))
            self.assertEqual(case["expected"], temporal_answer(case))

    def test_duplicate_case_ids_fail_closed(self):
        data = load_dataset(CASES)
        raw = copy.deepcopy(data)
        raw["cases"][1]["id"] = raw["cases"][0]["id"]
        with self.assertRaises(BenchmarkError):
            validate_dataset(raw)

    def test_expected_answer_shape_is_validated(self):
        data = load_dataset(CASES)
        raw = copy.deepcopy(data)
        snapshot = next(case for case in raw["cases"] if case["mode"] == "snapshot")
        snapshot["expected"] = {"objects": ["z", "a"]}
        with self.assertRaises(BenchmarkError):
            validate_dataset(raw)

    def test_event_cannot_reference_unknown_fact_name(self):
        data = load_dataset(CASES)
        raw = copy.deepcopy(data)
        case = next(case for case in raw["cases"] if case["events"])
        case["events"][0]["target"] = "missing"
        with self.assertRaises(BenchmarkError):
            validate_dataset(raw)


class BenchmarkOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.result = run_benchmark(CASES)
        self.rows = {row["id"]: row for row in self.result["cases"]}

    def test_temporal_system_solves_all_synthetic_cases(self):
        metrics = self.result["metrics"]["temporal"]
        self.assertEqual(metrics["total"], metrics["correct"])
        self.assertEqual(0, metrics["errors"])
        self.assertEqual(1.0, metrics["exact_accuracy"])

    def test_static_baseline_passes_controls_but_fails_temporal_adversaries(self):
        metrics = self.result["metrics"]["static"]
        self.assertEqual(1.0, metrics["control_accuracy"])
        self.assertGreater(metrics["errors"], 0)
        self.assertGreater(metrics["errors_by_class"]["future_leakage"], 0)
        self.assertGreater(metrics["errors_by_class"]["impossible_path"], 0)
        self.assertGreater(metrics["errors_by_class"]["stale_retracted_fact"], 0)
        self.assertGreater(metrics["errors_by_class"]["validity_window"], 0)

    def test_future_leakage_case_is_directionally_correct(self):
        row = self.rows["snapshot_known_before_future_update"]
        self.assertEqual({"objects": ["recommended"]}, row["expected"])
        self.assertEqual({"objects": ["not_recommended"]}, row["static"]["answer"])
        self.assertEqual(row["expected"], row["temporal"]["answer"])

    def test_impossible_path_case_catches_static_composition(self):
        row = self.rows["path_temporally_impossible_chain"]
        self.assertEqual({"path_exists": False}, row["expected"])
        self.assertEqual({"path_exists": True}, row["static"]["answer"])
        self.assertEqual(row["expected"], row["temporal"]["answer"])

    def test_historical_retraction_case_preserves_then_known_state(self):
        row = self.rows["path_historical_before_retraction"]
        self.assertEqual({"path_exists": True}, row["expected"])
        self.assertEqual({"path_exists": False}, row["static"]["answer"])
        self.assertEqual(row["expected"], row["temporal"]["answer"])

    def test_promotion_gate_passes_only_on_error_reduction_without_control_regression(self):
        gate = self.result["promotion"]
        self.assertTrue(gate["passed"])
        self.assertFalse(gate["falsifier_triggered"])
        self.assertFalse(gate["control_regression"])
        self.assertGreater(gate["static_adversarial_errors"], gate["temporal_adversarial_errors"])

    def test_abstention_metric_is_explicit(self):
        for system in ("static", "temporal"):
            metrics = self.result["metrics"][system]
            self.assertGreater(metrics["abstention_total"], 0)
            self.assertLessEqual(metrics["abstention_correct"], metrics["abstention_total"])


class ReceiptTests(unittest.TestCase):
    def test_semantic_digest_is_repeatable_even_when_runtime_changes(self):
        one = run_benchmark(CASES)
        two = run_benchmark(CASES)
        self.assertEqual(one["receipt_sha256"], two["receipt_sha256"])
        self.assertEqual(one["dataset_sha256"], two["dataset_sha256"])
        self.assertEqual(one["cases"], two["cases"])
        self.assertTrue(verify_result(one))
        self.assertTrue(verify_result(two))

    def test_runtime_is_not_part_of_semantic_digest(self):
        result = run_benchmark(CASES)
        changed = copy.deepcopy(result)
        changed["runtime_ns"]["static"] += 123456
        self.assertTrue(verify_result(changed))
        self.assertEqual(result["receipt_sha256"], changed["receipt_sha256"])

    def test_semantic_tamper_is_detected_even_with_same_runtime(self):
        result = run_benchmark(CASES)
        changed = copy.deepcopy(result)
        changed["cases"][0]["expected"] = {"path_exists": not changed["cases"][0]["expected"].get("path_exists", False)}
        self.assertFalse(verify_result(changed))

    def test_dataset_answer_tamper_changes_dataset_and_result_digest(self):
        data = json.loads(CASES.read_text(encoding="utf-8"))
        target = next(case for case in data["cases"] if case["id"] == "snapshot_validity_window_control")
        target["expected"] = {"objects": ["wrong"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            changed = run_benchmark(path)
        original = run_benchmark(CASES)
        self.assertNotEqual(original["dataset_sha256"], changed["dataset_sha256"])
        self.assertNotEqual(original["receipt_sha256"], changed["receipt_sha256"])
        self.assertLess(changed["metrics"]["temporal"]["exact_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
