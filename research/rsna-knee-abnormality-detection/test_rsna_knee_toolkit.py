from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rsna_knee_toolkit import (
    LABELS,
    SUBMISSION_COLUMNS,
    ContractError,
    binary_auc,
    build_deterministic_zip,
    deterministic_group_split,
    macro_auc,
    validate_submission,
    write_submission,
)


class ContractTests(unittest.TestCase):
    def _predictions(self, count: int, value: float = 0.5):
        return {label: [value] * count for label in LABELS}

    def test_public_label_contract_has_exact_twelve_targets(self):
        self.assertEqual(len(LABELS), 12)
        self.assertEqual(LABELS[-1], "Fracture")
        self.assertEqual(SUBMISSION_COLUMNS[0], "StudyInstanceUID")

    def test_submission_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "submission.csv"
            write_submission(["study-a", "study-b"], self._predictions(2), path)
            result = validate_submission(path)
            self.assertEqual(result["rows"], 2)
            with path.open(encoding="utf-8", newline="") as handle:
                self.assertEqual(tuple(next(csv.reader(handle))), SUBMISSION_COLUMNS)

    def test_rejects_duplicate_study_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "submission.csv"
            with self.assertRaises(ContractError):
                write_submission(["same", "same"], self._predictions(2), path)

    def test_rejects_probability_outside_unit_interval(self):
        predictions = self._predictions(1)
        predictions["ACL"] = [1.01]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ContractError):
                write_submission(["study"], predictions, Path(directory) / "x.csv")

    def test_rejects_nonfinite_probability(self):
        predictions = self._predictions(1)
        predictions["ACL"] = [float("nan")]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ContractError):
                write_submission(["study"], predictions, Path(directory) / "x.csv")

    def test_binary_auc_perfect(self):
        self.assertEqual(binary_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]), 1.0)

    def test_binary_auc_reversed(self):
        self.assertEqual(binary_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]), 0.0)

    def test_binary_auc_ties(self):
        self.assertEqual(binary_auc([0, 1], [0.5, 0.5]), 0.5)

    def test_macro_auc_averages_all_twelve(self):
        targets = {label: [0, 1] for label in LABELS}
        scores = {label: [0.1, 0.9] for label in LABELS}
        self.assertEqual(macro_auc(targets, scores), 1.0)

    def test_group_split_is_deterministic_and_leak_free(self):
        groups = ["p1", "p1", "p2", "p3", "p4", "p4", "p5"]
        first = deterministic_group_split(groups, validation_fraction=0.4, seed="x")
        second = deterministic_group_split(reversed(groups), validation_fraction=0.4, seed="x")
        self.assertEqual(first, second)
        self.assertEqual(set(first), {"p1", "p2", "p3", "p4", "p5"})
        self.assertIn("train", set(first.values()))
        self.assertIn("validation", set(first.values()))

    def test_group_split_rejects_single_group(self):
        with self.assertRaises(ContractError):
            deterministic_group_split(["only", "only"])

    def test_zip_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.zip"
            second = Path(directory) / "b.zip"
            _, digest_a = build_deterministic_zip(
                {"z.txt": "last", "a.txt": b"first"}, first
            )
            _, digest_b = build_deterministic_zip(
                {"a.txt": b"first", "z.txt": "last"}, second
            )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(digest_a, digest_b)

    def test_zip_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ContractError):
                build_deterministic_zip(
                    {"../escape.txt": "nope"}, Path(directory) / "bad.zip"
                )


if __name__ == "__main__":
    unittest.main()
