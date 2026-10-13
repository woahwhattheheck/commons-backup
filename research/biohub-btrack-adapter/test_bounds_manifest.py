from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import adapter


class FakeTrack:
    def __init__(self, payload):
        refs = list(range(len(payload["t"])))
        self.ID = 1
        self.parent = None
        self.children = []
        self.refs = refs
        self.dummy = [False] * len(refs)
        self.t = list(payload["t"])
        self.x = list(payload["x"])
        self.y = list(payload["y"])
        self.z = list(payload["z"])
        self.properties = {"commons_detection_id": list(payload["commons_detection_id"])}


class FakeTracker:
    def __init__(self, registry):
        self.registry = registry
        registry.append(self)
        self.configuration = SimpleNamespace(features=[])
        self.volume = None
        self.max_search_radius = None
        self.appended = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def configure(self, configuration):
        self.configuration = SimpleNamespace(features=[])

    def append(self, objects):
        self.appended = {key: list(value) for key, value in objects.items()}

    def track(self):
        return None

    def optimise(self, options=None):
        return []

    @property
    def tracks(self):
        assert self.appended is not None
        return [FakeTrack(self.appended)]


class BoundsManifestTests(unittest.TestCase):
    def _write_inputs(self, root: Path) -> tuple[Path, Path, Path]:
        detections = root / "detections.csv"
        with detections.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=adapter.INPUT_COLUMNS)
            writer.writeheader()
            writer.writerow({"dataset": "b", "detection_id": 1, "t": 0, "z": 12, "y": 20, "x": 30})
            writer.writerow({"dataset": "a", "detection_id": 1, "t": 0, "z": 2, "y": 3, "x": 4})
        config = root / "config.json"
        config.write_text("{}\n", encoding="utf-8")
        bounds = root / "bounds.csv"
        with bounds.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=adapter.BOUNDS_COLUMNS)
            writer.writeheader()
            writer.writerow({"dataset": "b", "zlo": 0, "zhi": 20, "ylo": 0, "yhi": 30, "xlo": 0, "xhi": 40})
            writer.writerow({"dataset": "a", "zlo": 0, "zhi": 10, "ylo": 0, "yhi": 10, "xlo": 0, "xhi": 10})
        return detections, config, bounds

    def test_manifest_mapping_drives_distinct_tracker_volumes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detections_path, _, bounds_path = self._write_inputs(root)
            detections = adapter.read_detections(detections_path)
            bounds = adapter.read_bounds_manifest(bounds_path)
            registry = []
            rows = adapter.solve_all(
                detections,
                scale=adapter.Scale(),
                bounds=bounds,
                configuration="cfg.json",
                max_search_radius=8.5,
                tracker_factory=lambda: FakeTracker(registry),
            )
            self.assertEqual(len(registry), 2)
            self.assertEqual(registry[0].volume, bounds["a"].physical_btrack(adapter.Scale()))
            self.assertEqual(registry[1].volume, bounds["b"].physical_btrack(adapter.Scale()))
            self.assertNotEqual(registry[0].volume, registry[1].volume)
            self.assertEqual([row["dataset"] for row in rows], ["a", "b"])

    def test_cli_multi_dataset_rejects_shared_scalar_bounds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detections, config, _ = self._write_inputs(root)
            output = root / "submission.csv"
            argv = [
                "--detections", str(detections),
                "--output", str(output),
                "--config", str(config),
                "--max-search-radius", "8.5",
                "--zlo", "0", "--zhi", "40",
                "--ylo", "0", "--yhi", "40",
                "--xlo", "0", "--xhi", "40",
            ]
            with patch("adapter.solve_all", side_effect=AssertionError("solver must not run")):
                with self.assertRaises(SystemExit) as raised:
                    adapter.main(argv)
            self.assertEqual(raised.exception.code, 2)

    def test_cli_passes_exact_manifest_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detections, config, bounds_path = self._write_inputs(root)
            output = root / "submission.csv"
            argv = [
                "--detections", str(detections),
                "--output", str(output),
                "--config", str(config),
                "--max-search-radius", "8.5",
                "--bounds-csv", str(bounds_path),
            ]
            with patch("adapter.solve_all", return_value=[]) as solve:
                self.assertEqual(adapter.main(argv), 0)
            passed = solve.call_args.kwargs["bounds"]
            expected = adapter.read_bounds_manifest(bounds_path)
            self.assertEqual(passed, expected)
            self.assertEqual(set(passed), {"a", "b"})
            self.assertTrue(output.exists())

    def test_manifest_must_match_detection_datasets_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detections, config, bounds_path = self._write_inputs(root)
            with bounds_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            with bounds_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=adapter.BOUNDS_COLUMNS)
                writer.writeheader()
                writer.writerow(rows[0])
            output = root / "submission.csv"
            argv = [
                "--detections", str(detections),
                "--output", str(output),
                "--config", str(config),
                "--max-search-radius", "8.5",
                "--bounds-csv", str(bounds_path),
            ]
            with patch("adapter.solve_all", side_effect=AssertionError("solver must not run")):
                with self.assertRaises(SystemExit) as raised:
                    adapter.main(argv)
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
