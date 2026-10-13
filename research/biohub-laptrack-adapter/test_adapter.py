from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import adapter


class FakeGraph:
    def __init__(self, nodes, edges):
        self._nodes = list(nodes)
        self._edges = list(edges)

    @property
    def nodes(self):
        return self._nodes

    @property
    def edges(self):
        return self._edges


class FakeSolver:
    instances = []
    graph = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.predict_args = None
        self.__class__.instances.append(self)

    def predict(self, coords, connected_edges=None, split_merge_validation=True):
        self.predict_args = (coords, connected_edges, split_merge_validation)
        if self.__class__.graph is None:
            nodes = [(frame, i) for frame, values in enumerate(coords) for i in range(len(values))]
            edges = []
            for frame in range(len(coords) - 1):
                count = min(len(coords[frame]), len(coords[frame + 1]))
                edges.extend([((frame, i), (frame + 1, i)) for i in range(count)])
            return FakeGraph(nodes, edges)
        return self.__class__.graph


class AdapterTests(unittest.TestCase):
    def setUp(self):
        FakeSolver.instances.clear()
        FakeSolver.graph = None

    def rows(self):
        return [
            {"dataset": "demo", "detection_id": "20", "t": "1", "z": "3", "y": "5", "x": "7"},
            {"dataset": "demo", "detection_id": "10", "t": "0", "z": "2", "y": "4", "x": "6"},
            {"dataset": "demo", "detection_id": "30", "t": "1", "z": "9", "y": "8", "x": "7"},
        ]

    def test_parse_is_deterministic_by_dataset_time_and_detection_id(self):
        result = adapter.parse_detections(self.rows())
        self.assertEqual([(0, 10), (1, 20), (1, 30)], [(x.t, x.detection_id) for x in result])

    def test_duplicate_detection_id_is_rejected(self):
        rows = self.rows() + [{**self.rows()[0], "t": "2"}]
        with self.assertRaisesRegex(adapter.AdapterError, "duplicate detection_id"):
            adapter.parse_detections(rows)

    def test_dataset_suffix_and_surrounding_whitespace_are_rejected(self):
        for value in (" demo", "demo ", "demo.zarr"):
            rows = [{**self.rows()[0], "dataset": value}]
            with self.subTest(value=value), self.assertRaises(adapter.AdapterError):
                adapter.parse_detections(rows)

    def test_physical_coordinates_scale_zyx_but_keep_voxel_provenance(self):
        detections = adapter.parse_detections(self.rows())
        coords, provenance = adapter.build_coords(detections, adapter.Scale(z=4.0, y=2.0, x=0.5))
        np.testing.assert_array_equal(coords[0], np.asarray([[8.0, 8.0, 3.0]]))
        np.testing.assert_array_equal(coords[1], np.asarray([[12.0, 10.0, 3.5], [36.0, 16.0, 3.5]]))
        self.assertEqual((2, 4, 6), (provenance[(0, 0)].z, provenance[(0, 0)].y, provenance[(0, 0)].x))

    def test_empty_frames_are_preserved_for_laptrack_indexing(self):
        detections = adapter.parse_detections([
            {"dataset": "demo", "detection_id": "1", "t": "0", "z": "0", "y": "0", "x": "0"},
            {"dataset": "demo", "detection_id": "2", "t": "2", "z": "1", "y": "1", "x": "1"},
        ])
        coords, _ = adapter.build_coords(detections, adapter.Scale())
        self.assertEqual([(1, 3), (0, 3), (1, 3)], [item.shape for item in coords])

    def test_solver_configuration_disables_gaps_and_merges(self):
        detections = adapter.parse_detections(self.rows())
        adapter.solve_dataset(
            detections,
            scale=adapter.Scale(),
            cutoff=64.0,
            splitting_cutoff=25.0,
            solver_factory=FakeSolver,
        )
        instance = FakeSolver.instances[-1]
        self.assertEqual("sqeuclidean", instance.kwargs["metric"])
        self.assertEqual(64.0, instance.kwargs["cutoff"])
        self.assertIs(False, instance.kwargs["gap_closing_cutoff"])
        self.assertEqual(25.0, instance.kwargs["splitting_cutoff"])
        self.assertIs(False, instance.kwargs["merging_cutoff"])
        self.assertEqual("serial", instance.kwargs["parallel_backend"])
        self.assertIsNone(instance.predict_args[1])
        self.assertIs(True, instance.predict_args[2])

    def test_split_graph_becomes_one_source_with_two_children(self):
        detections = adapter.parse_detections(self.rows())
        FakeSolver.graph = FakeGraph(
            [(0, 0), (1, 0), (1, 1)],
            [((0, 0), (1, 1)), ((0, 0), (1, 0))],
        )
        rows = adapter.solve_all(
            detections,
            scale=adapter.Scale(),
            cutoff=225.0,
            splitting_cutoff=64.0,
            solver_factory=FakeSolver,
        )
        nodes = [r for r in rows if r["row_type"] == "node"]
        edges = [r for r in rows if r["row_type"] == "edge"]
        self.assertEqual([0, 1, 2], [r["node_id"] for r in nodes])
        self.assertEqual([(0, 1), (0, 2)], [(r["source_id"], r["target_id"]) for r in edges])
        self.assertEqual(list(range(5)), [r["id"] for r in rows])

    def test_gap_edge_is_rejected(self):
        detections = adapter.parse_detections([
            {"dataset": "demo", "detection_id": "1", "t": "0", "z": "0", "y": "0", "x": "0"},
            {"dataset": "demo", "detection_id": "2", "t": "2", "z": "1", "y": "1", "x": "1"},
        ])
        _, provenance = adapter.build_coords(detections, adapter.Scale())
        with self.assertRaisesRegex(adapter.AdapterError, "not consecutive"):
            adapter.graph_to_rows("demo", provenance, FakeGraph([(0, 0), (2, 0)], [((0, 0), (2, 0))]))

    def test_merge_is_rejected(self):
        detections = adapter.parse_detections([
            {"dataset": "demo", "detection_id": "1", "t": "0", "z": "0", "y": "0", "x": "0"},
            {"dataset": "demo", "detection_id": "2", "t": "0", "z": "2", "y": "0", "x": "0"},
            {"dataset": "demo", "detection_id": "3", "t": "1", "z": "1", "y": "0", "x": "0"},
        ])
        _, provenance = adapter.build_coords(detections, adapter.Scale())
        graph = FakeGraph([(0, 0), (0, 1), (1, 0)], [((0, 0), (1, 0)), ((0, 1), (1, 0))])
        with self.assertRaisesRegex(adapter.AdapterError, "merge"):
            adapter.graph_to_rows("demo", provenance, graph)

    def test_missing_solver_node_is_rejected(self):
        detections = adapter.parse_detections(self.rows())
        _, provenance = adapter.build_coords(detections, adapter.Scale())
        with self.assertRaisesRegex(adapter.AdapterError, "node mismatch"):
            adapter.graph_to_rows("demo", provenance, FakeGraph([(0, 0), (1, 0)], []))

    def test_multiple_datasets_get_global_consecutive_row_ids(self):
        parsed = adapter.parse_detections([
            {"dataset": "b", "detection_id": "1", "t": "0", "z": "0", "y": "0", "x": "0"},
            {"dataset": "a", "detection_id": "2", "t": "0", "z": "1", "y": "1", "x": "1"},
        ])
        rows = adapter.solve_all(parsed, scale=adapter.Scale(), cutoff=225.0, solver_factory=FakeSolver)
        self.assertEqual(["a", "b"], [r["dataset"] for r in rows])
        self.assertEqual([0, 1], [r["id"] for r in rows])

    def test_submission_csv_header_and_roundtrip(self):
        parsed = adapter.parse_detections(self.rows())
        rows = adapter.solve_all(parsed, scale=adapter.Scale(), cutoff=225.0, solver_factory=FakeSolver)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "submission.csv"
            adapter.write_submission(path, rows)
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(adapter.SUBMISSION_COLUMNS, tuple(reader.fieldnames or ()))
                loaded = list(reader)
            self.assertEqual(len(rows), len(loaded))
            self.assertEqual([str(i) for i in range(len(rows))], [row["id"] for row in loaded])


    def test_float_graph_indices_are_rejected_not_coerced(self):
        detections = adapter.parse_detections(self.rows())
        _, provenance = adapter.build_coords(detections, adapter.Scale())
        with self.assertRaisesRegex(adapter.AdapterError, "indices must be integers"):
            adapter.graph_to_rows("demo", provenance, FakeGraph([(0.0, 0), (1, 0), (1, 1)], []))

    def test_cli_rejects_input_output_alias_before_solver_import(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "detections.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=adapter.INPUT_COLUMNS)
                writer.writeheader()
                writer.writerow({"dataset": "demo", "detection_id": 1, "t": 0, "z": 0, "y": 0, "x": 0})
            with self.assertRaises(SystemExit) as result:
                adapter.main(["--detections", str(path), "--output", str(path)])
            self.assertEqual(2, result.exception.code)

    def test_absent_laptrack_fails_closed_without_claiming_execution(self):
        if importlib.util.find_spec("laptrack") is not None:
            self.skipTest("laptrack is installed in this environment")
        with self.assertRaisesRegex(adapter.AdapterError, "no solver run was performed"):
            adapter.load_pinned_laptrack()

    def test_version_drift_fails_closed(self):
        class FakeModule:
            __version__ = "99.0.0"
            LapTrack = object

        with patch("adapter.importlib.import_module", return_value=FakeModule()):
            with self.assertRaisesRegex(adapter.AdapterError, "version drift"):
                adapter.load_pinned_laptrack()

    def test_invalid_scale_and_cutoffs_fail_before_solver_output_is_trusted(self):
        detections = adapter.parse_detections(self.rows())
        for scale in (adapter.Scale(z=0), adapter.Scale(y=float("nan"))):
            with self.subTest(scale=scale), self.assertRaises(adapter.AdapterError):
                adapter.solve_dataset(detections, scale=scale, cutoff=225.0, solver_factory=FakeSolver)
        with self.assertRaises(adapter.AdapterError):
            adapter.solve_dataset(detections, scale=adapter.Scale(), cutoff=0, solver_factory=FakeSolver)
        with self.assertRaises(adapter.AdapterError):
            adapter.solve_dataset(
                detections,
                scale=adapter.Scale(),
                cutoff=225.0,
                splitting_cutoff=-1.0,
                solver_factory=FakeSolver,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
