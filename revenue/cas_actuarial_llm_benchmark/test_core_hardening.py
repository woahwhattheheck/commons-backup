from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest

from revenue.cas_actuarial_llm_benchmark.core import (
    BenchmarkInputError,
    evaluate_benchmark,
    verify_snapshot,
)
from revenue.cas_actuarial_llm_benchmark.fixture import synthetic_evidence


def _readdress(snapshot: dict) -> None:
    body = copy.deepcopy(snapshot)
    body.pop("snapshot_sha256", None)
    snapshot["snapshot_sha256"] = hashlib.sha256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class CasActuarialBenchmarkHardeningTests(unittest.TestCase):
    def test_schema_bool_is_not_integer_one(self):
        evidence = synthetic_evidence()
        evidence["schema_version"] = True
        with self.assertRaises(BenchmarkInputError):
            evaluate_benchmark(evidence)


    def test_binary_metric_values_are_objective_strings(self):
        result = evaluate_benchmark(synthetic_evidence())
        binary = next(run for run in result["runs"] if run["task_id"] == "claim-triage")
        self.assertRegex(binary["metrics"]["accuracy"], r"^\d\.\d{12}$")
        self.assertRegex(binary["metrics"]["macro_f1"], r"^\d\.\d{12}$")
        self.assertRegex(binary["metrics"]["brier_score"], r"^\d\.\d{12}$")
        self.assertRegex(binary["metrics"]["log_loss"], r"^\d\.\d{12}$")


    def test_missing_evaluation_universe_fails_closed(self):
        evidence = synthetic_evidence()
        evidence["tasks"][0].pop("evaluation_universe")
        with self.assertRaisesRegex(BenchmarkInputError, "evaluation_universe"):
            evaluate_benchmark(evidence)


    def test_evaluation_universe_digest_tamper_fails_closed(self):
        evidence = synthetic_evidence()
        evidence["tasks"][0]["evaluation_universe"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(BenchmarkInputError, "universe digest"):
            evaluate_benchmark(evidence)


    def test_duplicate_evaluation_universe_item_fails_closed(self):
        evidence = synthetic_evidence()
        records = evidence["tasks"][0]["evaluation_universe"]["records"]
        records[1]["item_id"] = records[0]["item_id"]
        with self.assertRaisesRegex(BenchmarkInputError, "universe item_id values must be unique"):
            evaluate_benchmark(evidence)


    def test_evaluation_universe_truth_must_be_declared_label(self):
        evidence = synthetic_evidence()
        evidence["tasks"][0]["evaluation_universe"]["records"][0]["truth"] = "unknown"
        with self.assertRaisesRegex(BenchmarkInputError, "universe truth"):
            evaluate_benchmark(evidence)


    def test_run_cannot_drop_evaluation_item(self):
        evidence = synthetic_evidence()
        evidence["runs"][0]["records"].pop()
        with self.assertRaisesRegex(BenchmarkInputError, "missing evaluation universe"):
            evaluate_benchmark(evidence)


    def test_run_cannot_add_evaluation_item(self):
        evidence = synthetic_evidence()
        extra = copy.deepcopy(evidence["runs"][0]["records"][0])
        extra["item_id"] = "item-extra"
        evidence["runs"][0]["records"].append(extra)
        with self.assertRaisesRegex(BenchmarkInputError, "outside evaluation universe"):
            evaluate_benchmark(evidence)


    def test_run_cannot_substitute_evaluation_item(self):
        evidence = synthetic_evidence()
        evidence["runs"][0]["records"][0]["item_id"] = "item-substitute"
        with self.assertRaisesRegex(BenchmarkInputError, "missing evaluation universe"):
            evaluate_benchmark(evidence)


    def test_same_item_different_truth_across_models_fails_closed(self):
        evidence = synthetic_evidence()
        target_run = next(
            run
            for run in evidence["runs"]
            if run["task_id"] == "claim-triage" and run["model_id"] != "commercial-openai"
        )
        record = target_run["records"][0]
        record["truth"] = "escalate" if record["truth"] == "routine" else "routine"
        with self.assertRaisesRegex(BenchmarkInputError, "truth does not match evaluation universe"):
            evaluate_benchmark(evidence)


    def test_run_record_order_is_semantically_invariant(self):
        evidence = synthetic_evidence()
        first = evaluate_benchmark(evidence)
        permuted = copy.deepcopy(evidence)
        permuted["runs"][0]["records"].reverse()
        second = evaluate_benchmark(permuted)
        self.assertEqual(first, second)


    def test_task_universe_order_is_semantically_invariant(self):
        evidence = synthetic_evidence()
        first = evaluate_benchmark(evidence)
        permuted = copy.deepcopy(evidence)
        permuted["tasks"][0]["evaluation_universe"]["records"].reverse()
        second = evaluate_benchmark(permuted)
        self.assertEqual(first, second)


    def test_top_level_run_order_is_semantically_invariant(self):
        evidence = synthetic_evidence()
        first = evaluate_benchmark(evidence)
        permuted = copy.deepcopy(evidence)
        permuted["runs"].reverse()
        second = evaluate_benchmark(permuted)
        self.assertEqual(first, second)


    def test_prediction_change_changes_record_manifest(self):
        evidence = synthetic_evidence()
        first = evaluate_benchmark(evidence)
        changed = copy.deepcopy(evidence)
        record = changed["runs"][0]["records"][0]
        labels = changed["tasks"][0]["labels"]
        record["prediction"] = labels[(labels.index(record["prediction"]) + 1) % len(labels)]
        record["probabilities"] = {
            label: ("0.80" if label == record["prediction"] else "0.20")
            for label in labels
        }
        second = evaluate_benchmark(changed)
        first_run = next(run for run in first["runs"] if run["run_id"] == changed["runs"][0]["run_id"])
        second_run = next(run for run in second["runs"] if run["run_id"] == changed["runs"][0]["run_id"])
        self.assertNotEqual(
            first_run["record_manifest_sha256"],
            second_run["record_manifest_sha256"],
        )
        self.assertNotEqual(first["snapshot_sha256"], second["snapshot_sha256"])


    def test_equivalent_probability_spelling_has_one_manifest(self):
        evidence = synthetic_evidence()
        first = evaluate_benchmark(evidence)
        equivalent = copy.deepcopy(evidence)
        record = equivalent["runs"][0]["records"][0]
        record["probabilities"] = {
            label: str(float(value)) for label, value in record["probabilities"].items()
        }
        second = evaluate_benchmark(equivalent)
        self.assertEqual(first, second)


    def test_every_run_for_task_uses_identical_universe_digest_and_count(self):
        result = evaluate_benchmark(synthetic_evidence())
        for task in result["tasks"]:
            matching = [
                run
                for run in result["runs"]
                if (run["task_id"], run["task_version"])
                == (task["task_id"], task["version"])
            ]
            self.assertEqual(len(matching), 6)
            self.assertEqual(
                {run["evaluation_universe_sha256"] for run in matching},
                {task["evaluation_universe"]["sha256"]},
            )
            self.assertEqual(
                {run["record_count"] for run in matching},
                {task["evaluation_universe"]["record_count"]},
            )


    def test_high_precision_probability_change_cannot_round_to_same_manifest(self):
        first_evidence = synthetic_evidence()
        second_evidence = copy.deepcopy(first_evidence)
        first_record = first_evidence["runs"][0]["records"][0]
        second_record = second_evidence["runs"][0]["records"][0]
        labels = first_evidence["tasks"][0]["labels"]
        first_record["probabilities"] = {
            labels[0]: "0.1234567890123456789012345678901",
            labels[1]: "0.8765432109876543210987654321099",
        }
        second_record["probabilities"] = {
            labels[0]: "0.1234567890123456789012345678902",
            labels[1]: "0.8765432109876543210987654321098",
        }
        first = evaluate_benchmark(first_evidence)
        second = evaluate_benchmark(second_evidence)
        run_id = first_evidence["runs"][0]["run_id"]
        first_run = next(run for run in first["runs"] if run["run_id"] == run_id)
        second_run = next(run for run in second["runs"] if run["run_id"] == run_id)
        self.assertNotEqual(
            first_run["record_manifest_sha256"],
            second_run["record_manifest_sha256"],
        )


    def test_readdressed_noncanonical_universe_order_fails_verification(self):
        result = evaluate_benchmark(synthetic_evidence())
        task = result["tasks"][0]
        task["evaluation_universe"]["records"].reverse()
        universe_payload = {
            "task_id": task["task_id"],
            "task_version": task["version"],
            "dataset_sha256": task["dataset"]["sha256"],
            "split_sha256": task["dataset"]["split_sha256"],
            "records": task["evaluation_universe"]["records"],
        }
        universe_sha = hashlib.sha256(
            json.dumps(
                universe_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        task["evaluation_universe"]["sha256"] = universe_sha
        for run in result["runs"]:
            if (run["task_id"], run["task_version"]) == (task["task_id"], task["version"]):
                run["evaluation_universe_sha256"] = universe_sha
        _readdress(result)
        self.assertFalse(verify_snapshot(result))


    def test_readdressed_run_dataset_drift_fails_verification(self):
        result = evaluate_benchmark(synthetic_evidence())
        result["runs"][0]["dataset_sha256"] = "0" * 64
        _readdress(result)
        self.assertFalse(verify_snapshot(result))


    def test_readdressed_duplicate_matrix_cell_fails_verification(self):
        result = evaluate_benchmark(synthetic_evidence())
        duplicate = copy.deepcopy(result["runs"][0])
        duplicate["run_id"] = "duplicate-snapshot-run"
        result["runs"].append(duplicate)
        _readdress(result)
        self.assertFalse(verify_snapshot(result))


    def test_readdressed_authority_boolean_type_confusion_fails_verification(self):
        result = evaluate_benchmark(synthetic_evidence())
        result["authority"]["payment"] = 0
        _readdress(result)
        self.assertFalse(verify_snapshot(result))


    def test_task_evaluation_protocol_must_be_sha256(self):
        evidence = synthetic_evidence()
        evidence["tasks"][0]["evaluation_protocol_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(BenchmarkInputError, "evaluation protocol sha256"):
            evaluate_benchmark(evidence)


    def test_run_protocol_must_match_task_evaluation_protocol(self):
        evidence = synthetic_evidence()
        evidence["runs"][0]["protocol_sha256"] = "0" * 64
        with self.assertRaisesRegex(BenchmarkInputError, "protocol digest does not match"):
            evaluate_benchmark(evidence)


    def test_readdressed_run_protocol_drift_fails_verification(self):
        result = evaluate_benchmark(synthetic_evidence())
        result["runs"][0]["protocol_sha256"] = "0" * 64
        _readdress(result)
        self.assertFalse(verify_snapshot(result))



if __name__ == "__main__":
    unittest.main()
