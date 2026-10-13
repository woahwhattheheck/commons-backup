import csv
import math
import tempfile
import unittest
from pathlib import Path

from submission_guard import (
    ContractError,
    ID_COLUMN,
    NOTEBOOK_RUNTIME_LIMIT_SECONDS,
    SUBMISSION_COLUMNS,
    TARGET_COLUMNS,
    binary_roc_auc,
    load_expected_ids,
    macro_auc,
    validate_runtime,
    validate_submission,
)


class SubmissionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_csv(self, name, fieldnames, rows):
        path = self.root / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def valid_row(self, uid, probability="0.5"):
        return {
            ID_COLUMN: uid,
            **{column: probability for column in TARGET_COLUMNS},
        }

    def test_exact_public_header_and_probabilities_pass(self):
        path = self.write_csv(
            "submission.csv",
            SUBMISSION_COLUMNS,
            [self.valid_row("study-a"), self.valid_row("study-b", "0.25")],
        )
        summary = validate_submission(path)
        self.assertEqual(summary.rows, 2)
        self.assertEqual(summary.ids, ("study-a", "study-b"))

    def test_header_order_is_exact(self):
        path = self.write_csv(
            "submission.csv",
            (ID_COLUMN, *reversed(TARGET_COLUMNS)),
            [self.valid_row("study-a")],
        )
        with self.assertRaisesRegex(ContractError, "header mismatch"):
            validate_submission(path)

    def test_duplicate_uid_is_rejected(self):
        path = self.write_csv(
            "submission.csv",
            SUBMISSION_COLUMNS,
            [self.valid_row("study-a"), self.valid_row("study-a")],
        )
        with self.assertRaisesRegex(ContractError, "duplicate StudyInstanceUID"):
            validate_submission(path)

    def test_nonfinite_and_out_of_range_probabilities_are_rejected(self):
        for bad in ("nan", "inf", "-0.01", "1.01"):
            with self.subTest(bad=bad):
                row = self.valid_row("study-a")
                row[TARGET_COLUMNS[0]] = bad
                path = self.write_csv("submission.csv", SUBMISSION_COLUMNS, [row])
                with self.assertRaises(ContractError):
                    validate_submission(path)

    def test_optional_test_csv_enforces_id_coverage(self):
        test_path = self.write_csv(
            "test.csv",
            (ID_COLUMN, "placeholder"),
            [
                {ID_COLUMN: "study-a", "placeholder": "x"},
                {ID_COLUMN: "study-b", "placeholder": "y"},
            ],
        )
        expected_ids = load_expected_ids(test_path)
        submission_path = self.write_csv(
            "submission.csv",
            SUBMISSION_COLUMNS,
            [self.valid_row("study-a"), self.valid_row("study-c")],
        )
        with self.assertRaisesRegex(ContractError, "ID set mismatch"):
            validate_submission(submission_path, expected_ids=expected_ids)

    def test_binary_auc_perfect_and_tied(self):
        self.assertEqual(binary_roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]), 1.0)
        self.assertEqual(binary_roc_auc([0, 1], [0.5, 0.5]), 0.5)

    def test_binary_auc_rejects_single_class(self):
        with self.assertRaisesRegex(ContractError, "one positive and one negative"):
            binary_roc_auc([1, 1], [0.2, 0.8])

    def test_macro_auc_averages_all_twelve_targets(self):
        labels = {column: [0, 0, 1, 1] for column in TARGET_COLUMNS}
        predictions = {
            column: [0.1, 0.2, 0.8, 0.9] for column in TARGET_COLUMNS
        }
        self.assertEqual(macro_auc(labels, predictions), 1.0)

    def test_runtime_ceiling_boundary(self):
        validate_runtime(float(NOTEBOOK_RUNTIME_LIMIT_SECONDS))
        with self.assertRaisesRegex(ContractError, "exceeds"):
            validate_runtime(float(NOTEBOOK_RUNTIME_LIMIT_SECONDS) + 0.001)

    def test_runtime_rejects_invalid_values(self):
        for bad in (-1.0, math.inf, math.nan):
            with self.subTest(bad=bad):
                with self.assertRaises(ContractError):
                    validate_runtime(bad)


if __name__ == "__main__":
    unittest.main()
