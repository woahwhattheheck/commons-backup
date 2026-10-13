from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from submission_contract import (
    COLUMNS,
    SubmissionError,
    read_submission,
    validate_rows,
    validate_submission,
    write_submission,
)
from synthetic_baseline import build_rows, link_nearest, synthetic_frames


def node_row(node_id: int, t: int, *, dataset: str = "d") -> dict[str, str]:
    return {
        "id": "",
        "dataset": dataset,
        "row_type": "node",
        "node_id": str(node_id),
        "t": str(t),
        "z": "1",
        "y": "1",
        "x": "1",
        "source_id": "-1",
        "target_id": "-1",
    }


def edge_row(source_id: int, target_id: int, *, dataset: str = "d") -> dict[str, str]:
    return {
        "id": "",
        "dataset": dataset,
        "row_type": "edge",
        "node_id": "-1",
        "t": "-1",
        "z": "-1",
        "y": "-1",
        "x": "-1",
        "source_id": str(source_id),
        "target_id": str(target_id),
    }


def with_ids(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for index, row in enumerate(rows):
        row["id"] = str(index)
    return rows


class SubmissionContractTests(unittest.TestCase):
    def test_synthetic_baseline_is_deterministic(self) -> None:
        rows_a = build_rows()
        rows_b = build_rows()
        self.assertEqual(rows_a, rows_b)
        with tempfile.TemporaryDirectory() as tmp:
            path_a = Path(tmp) / "submission-a.csv"
            path_b = Path(tmp) / "submission-b.csv"
            write_submission(path_a, rows_a)
            write_submission(path_b, rows_b)
            self.assertEqual(path_a.read_bytes(), path_b.read_bytes())
            parsed = read_submission(path_a)
            write_submission(path_b, parsed)
            self.assertEqual(path_a.read_bytes(), path_b.read_bytes())
            counts = validate_submission(path_a, expected_datasets=["synthetic_embryo_0001"])
        self.assertEqual(counts, {"rows": 14, "nodes": 8, "edges": 6, "datasets": 1, "divisions": 0})

    def test_linker_uses_physical_scale_and_is_one_to_one(self) -> None:
        nodes, edges = link_nearest(synthetic_frames(), radius_um=8.5)
        self.assertEqual(len(nodes), 8)
        self.assertEqual(len(edges), 6)
        self.assertEqual(edges, [(0, 2), (1, 3), (2, 4), (3, 5), (4, 6), (5, 7)])

    def test_explicit_division_fixture_is_byte_deterministic(self) -> None:
        rows = with_ids(
            [
                node_row(0, 0),
                node_row(1, 1),
                node_row(2, 1),
                edge_row(0, 1),
                edge_row(0, 2),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path_a = Path(tmp) / "division-a.csv"
            path_b = Path(tmp) / "division-b.csv"
            write_submission(path_a, rows)
            parsed = read_submission(path_a)
            self.assertEqual([row["id"] for row in parsed], ["0", "1", "2", "3", "4"])
            counts = validate_submission(path_a, expected_datasets=["d"])
            self.assertEqual(counts, {"rows": 5, "nodes": 3, "edges": 2, "datasets": 1, "divisions": 1})
            write_submission(path_b, parsed)
            self.assertEqual(path_a.read_bytes(), path_b.read_bytes())

    def test_missing_dataset_is_rejected(self) -> None:
        with self.assertRaisesRegex(SubmissionError, "missing datasets"):
            validate_rows([], expected_datasets=["wanted"])

    def test_whitespace_padded_dataset_is_rejected(self) -> None:
        rows = with_ids([node_row(1, 0, dataset=" d")])
        with self.assertRaisesRegex(SubmissionError, "dataset must not contain"):
            validate_rows(rows)

    def test_whitespace_padded_row_type_is_rejected(self) -> None:
        row = node_row(1, 0)
        row["row_type"] = "node "
        with self.assertRaisesRegex(SubmissionError, "row_type must not contain"):
            validate_rows(with_ids([row]))

    def test_edge_missing_node_is_rejected(self) -> None:
        rows = with_ids([node_row(1, 0), edge_row(1, 2)])
        with self.assertRaisesRegex(SubmissionError, "missing target node"):
            validate_rows(rows)

    def test_reverse_time_edge_is_rejected(self) -> None:
        rows = with_ids([node_row(1, 1), node_row(2, 0), edge_row(1, 2)])
        with self.assertRaisesRegex(SubmissionError, "move forward in time"):
            validate_rows(rows)

    def test_nonconsecutive_edge_is_rejected_by_default(self) -> None:
        rows = with_ids([node_row(1, 0), node_row(2, 2), edge_row(1, 2)])
        with self.assertRaisesRegex(SubmissionError, "connect consecutive frames"):
            validate_rows(rows)

    def test_duplicate_edge_is_strict_lineage_policy(self) -> None:
        rows = with_ids([node_row(0, 0), node_row(1, 1), edge_row(0, 1), edge_row(0, 1)])
        with self.assertRaisesRegex(SubmissionError, "duplicate edge"):
            validate_rows(rows)
        counts = validate_rows(rows, strict_lineage=False)
        self.assertEqual(counts, {"rows": 4, "nodes": 2, "edges": 2, "datasets": 1, "divisions": 0})

    def test_multiple_parents_are_strict_lineage_policy(self) -> None:
        rows = with_ids(
            [
                node_row(0, 0),
                node_row(1, 0),
                node_row(2, 1),
                edge_row(0, 2),
                edge_row(1, 2),
            ]
        )
        with self.assertRaisesRegex(SubmissionError, "more than one parent"):
            validate_rows(rows)
        counts = validate_rows(rows, strict_lineage=False)
        self.assertEqual(counts, {"rows": 5, "nodes": 3, "edges": 2, "datasets": 1, "divisions": 0})

    def test_more_than_two_children_is_strict_lineage_policy(self) -> None:
        rows = [node_row(0, 0)]
        for i in range(1, 4):
            row = node_row(i, 1)
            row["y"] = str(i)
            rows.append(row)
        for i in range(1, 4):
            rows.append(edge_row(0, i))
        rows = with_ids(rows)
        with self.assertRaisesRegex(SubmissionError, "more than two children"):
            validate_rows(rows)
        counts = validate_rows(rows, strict_lineage=False)
        self.assertEqual(counts, {"rows": 7, "nodes": 4, "edges": 3, "datasets": 1, "divisions": 0})

    def test_organizer_compatible_mode_keeps_timing_and_reference_checks(self) -> None:
        skipped = with_ids([node_row(0, 0), node_row(1, 2), edge_row(0, 1)])
        with self.assertRaisesRegex(SubmissionError, "consecutive frames"):
            validate_rows(skipped, strict_lineage=False)
        missing = with_ids([node_row(0, 0), edge_row(0, 1)])
        with self.assertRaisesRegex(SubmissionError, "missing target node"):
            validate_rows(missing, strict_lineage=False)

    def test_node_and_edge_sentinels_are_rejected(self) -> None:
        bad_node = node_row(0, 0)
        bad_node["source_id"] = "0"
        with self.assertRaisesRegex(SubmissionError, "node source_id must be -1"):
            validate_rows(with_ids([bad_node]))

        bad_edge = edge_row(0, 1)
        bad_edge["t"] = "0"
        with self.assertRaisesRegex(SubmissionError, "edge t must be -1"):
            validate_rows(with_ids([bad_edge]))

    def test_csv_round_trip_is_byte_deterministic(self) -> None:
        rows = build_rows()
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.csv"
            second = Path(tmp) / "second.csv"
            write_submission(first, rows)
            with first.open("r", encoding="utf-8", newline="") as handle:
                parsed = list(csv.DictReader(handle))
            write_submission(second, parsed)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(
                validate_submission(second, expected_datasets=["synthetic_embryo_0001"]),
                {"rows": 14, "nodes": 8, "edges": 6, "datasets": 1, "divisions": 0},
            )

    def test_header_must_be_exact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(COLUMNS[:-1])
            with self.assertRaisesRegex(SubmissionError, "header must exactly equal"):
                validate_submission(path)


if __name__ == "__main__":
    unittest.main()
