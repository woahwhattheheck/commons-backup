from __future__ import annotations

from copy import deepcopy
import unittest

from .acceptance import _h, synthetic_run, synthetic_suite, run_acceptance
from .benchmark import AUTHORITY, BenchmarkError, build_board, score_run, verify_board, verify_receipt


class BenchmarkCoreTests(unittest.TestCase):
    def setUp(self):
        self.suite = synthetic_suite()
        self.run = synthetic_run(0, self.suite)

    def test_clean_run_ready(self):
        r = score_run(self.suite, self.run)
        self.assertEqual(r["status"], "READY")
        self.assertEqual(r["authority"], AUTHORITY)
        self.assertEqual(r["expected_item_count"], 24)
        self.assertEqual(r["prediction_count"], 24)
        self.assertEqual(set(r["metrics"]), {"accuracy", "macro_f1", "brier", "log_loss"})

    def test_replay_order_and_exact_duplicate_invariant(self):
        a = score_run(self.suite, self.run)
        b = deepcopy(self.run); b["predictions"] = list(reversed(b["predictions"])) + [deepcopy(b["predictions"][3])]
        self.assertEqual(a, score_run(self.suite, b))

    def test_changed_duplicate_holds_order_invariant(self):
        x = deepcopy(self.run); x["run_id"] = "conflict"
        p = deepcopy(x["predictions"][0]); labels = sorted(p["probabilities"]); p["probabilities"] = {labels[0]: "0.200000", labels[1]: "0.800000"}
        forward = deepcopy(x); forward["predictions"].append(deepcopy(p))
        reverse = deepcopy(forward); reverse["predictions"] = list(reversed(reverse["predictions"]))
        a, b = score_run(self.suite, forward), score_run(self.suite, reverse)
        self.assertEqual(a, b)
        self.assertEqual(a["status"], "HOLD")
        self.assertIn("PREDICTION_IDENTITY_CONFLICT", a["reasons"])

    def test_missing_prediction_holds(self):
        x = deepcopy(self.run); x["predictions"].pop()
        r = score_run(self.suite, x)
        self.assertIn("MISSING_PREDICTIONS", r["reasons"])
        self.assertIsNone(r["metrics"])

    def test_unknown_prediction_holds(self):
        x = deepcopy(self.run); p = deepcopy(x["predictions"][0]); p["item_id"] = "unknown"; x["predictions"].append(p)
        self.assertIn("UNKNOWN_PREDICTIONS", score_run(self.suite, x)["reasons"])

    def test_suite_identity_mismatch_holds(self):
        x = deepcopy(self.run); x["suite_id"] = "other-suite"
        self.assertIn("SUITE_ID_MISMATCH", score_run(self.suite, x)["reasons"])

    def test_suite_version_mismatch_holds(self):
        x = deepcopy(self.run); x["suite_version"] = "other-version"
        self.assertIn("SUITE_VERSION_MISMATCH", score_run(self.suite, x)["reasons"])

    def test_dataset_digest_mismatch_holds(self):
        x = deepcopy(self.run); x["dataset_sha256"] = _h("other")
        self.assertIn("DATASET_DIGEST_MISMATCH", score_run(self.suite, x)["reasons"])

    def test_label_set_mismatch_holds(self):
        x = deepcopy(self.run); first = x["predictions"][0]; labels = sorted(first["probabilities"]); first["probabilities"] = {labels[0]: "1.000000", "EXTRA": "0.000000"}
        self.assertIn("LABEL_SET_MISMATCH", score_run(self.suite, x)["reasons"])

    def test_probabilities_must_sum_exactly(self):
        x = deepcopy(self.run); labels = list(x["predictions"][0]["probabilities"]); x["predictions"][0]["probabilities"][labels[0]] = "0.840000"
        with self.assertRaises(BenchmarkError): score_run(self.suite, x)

    def test_probability_must_be_decimal_string(self):
        x = deepcopy(self.run); labels = list(x["predictions"][0]["probabilities"]); x["predictions"][0]["probabilities"][labels[0]] = 0.85
        with self.assertRaises(BenchmarkError): score_run(self.suite, x)

    def test_unknown_suite_field_rejected(self):
        s = deepcopy(self.suite); s["surprise"] = True
        with self.assertRaises(BenchmarkError): score_run(s, self.run)

    def test_unknown_run_field_rejected(self):
        x = deepcopy(self.run); x["surprise"] = True
        with self.assertRaises(BenchmarkError): score_run(self.suite, x)

    def test_weights_must_sum_to_one(self):
        s = deepcopy(self.suite); s["tasks"][0]["weight"] = "0.300000"
        with self.assertRaises(BenchmarkError): score_run(s, self.run)

    def test_gold_label_must_be_declared(self):
        s = deepcopy(self.suite); s["tasks"][0]["items"][0]["gold_label"] = "UNDECLARED"
        with self.assertRaises(BenchmarkError): score_run(s, self.run)

    def test_dataset_provenance_required(self):
        s = deepcopy(self.suite); s["provenance_url"] = ""
        with self.assertRaises(BenchmarkError): score_run(s, self.run)

    def test_dataset_license_required(self):
        s = deepcopy(self.suite); s["dataset_license"] = ""
        with self.assertRaises(BenchmarkError): score_run(s, self.run)

    def test_receipt_tamper_rejected(self):
        r = score_run(self.suite, self.run); r["status"] = "HOLD"
        self.assertFalse(verify_receipt(r, self.suite, self.run, require_ready=False))

    def test_receipt_wrong_run_rejected(self):
        r = score_run(self.suite, self.run); other = synthetic_run(1, self.suite)
        self.assertFalse(verify_receipt(r, self.suite, other))

    def test_confidence_intervals_repeat(self):
        a = score_run(self.suite, self.run); b = score_run(deepcopy(self.suite), deepcopy(self.run))
        self.assertEqual(a["confidence_intervals"], b["confidence_intervals"])

    def test_board_ranks_ready_receipts(self):
        receipts = [score_run(self.suite, synthetic_run(i, self.suite)) for i in range(7)]
        board = build_board(self.suite, receipts)
        self.assertEqual(board["entry_count"], 7)
        self.assertTrue(verify_board(board, self.suite, receipts))
        accuracies = [float(x["metrics"]["accuracy"]) for x in board["entries"]]
        self.assertEqual(accuracies, sorted(accuracies, reverse=True))

    def test_board_rejects_hold(self):
        x = deepcopy(self.run); x["predictions"].pop(); hold = score_run(self.suite, x)
        with self.assertRaises(BenchmarkError): build_board(self.suite, [hold])

    def test_board_tamper_rejected(self):
        receipts = [score_run(self.suite, synthetic_run(i, self.suite)) for i in range(2)]
        board = build_board(self.suite, receipts); board["entry_count"] = 99
        self.assertFalse(verify_board(board, self.suite, receipts))

    def test_board_order_invariant_to_receipt_order(self):
        receipts = [score_run(self.suite, synthetic_run(i, self.suite)) for i in range(4)]
        self.assertEqual(build_board(self.suite, receipts), build_board(self.suite, list(reversed(receipts))))

    def test_primary_lower_is_better_for_log_loss(self):
        s = deepcopy(self.suite); s["metric_policy"]["primary_metric"] = "log_loss"
        receipts = [score_run(s, synthetic_run(i, s)) for i in range(3)]
        board = build_board(s, receipts)
        vals = [float(e["metrics"]["log_loss"]) for e in board["entries"]]
        self.assertEqual(vals, sorted(vals))

    def test_zero_gold_probability_is_floored_for_log_loss(self):
        x = deepcopy(self.run); p = x["predictions"][0]; task = next(t for t in self.suite["tasks"] if t["task_id"] == p["task_id"]); item = next(i for i in task["items"] if i["item_id"] == p["item_id"]); gold = item["gold_label"]; labels = sorted(p["probabilities"])
        if len(labels) == 2:
            other = next(l for l in labels if l != gold); p["probabilities"] = {gold: "0.000000", other: "1.000000"}
        else:
            others = [l for l in labels if l != gold]; p["probabilities"] = {gold: "0.000000", others[0]: "1.000000", others[1]: "0.000000"}
        r = score_run(self.suite, x)
        self.assertEqual(r["status"], "READY")
        self.assertGreater(float(r["metrics"]["log_loss"]), 0)

    def test_acceptance_matrix(self):
        a = run_acceptance()
        self.assertEqual(a["ready_models"], 7)
        self.assertEqual(a["board_entries"], 7)
        self.assertTrue(a["replay_order_invariant"])
        self.assertTrue(a["receipt_verifies"])
        self.assertTrue(a["board_verifies"])
        self.assertEqual(a["hostile_statuses"], ["HOLD"] * 4)
        self.assertIn("MISSING_PREDICTIONS", a["hostile_reasons"][0])
        self.assertIn("UNKNOWN_PREDICTIONS", a["hostile_reasons"][1])
        self.assertIn("PREDICTION_IDENTITY_CONFLICT", a["hostile_reasons"][2])
        self.assertIn("DATASET_DIGEST_MISMATCH", a["hostile_reasons"][3])


if __name__ == "__main__":
    unittest.main()
