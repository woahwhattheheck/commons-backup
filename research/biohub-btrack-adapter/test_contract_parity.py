from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapter import Detection, Scale, SUBMISSION_COLUMNS, VoxelBounds, solve_all, write_submission


def load_canonical_contract():
    contract_path = (
        Path(__file__).resolve().parents[1]
        / "biohub-cell-tracking-readiness"
        / "submission_contract.py"
    )
    spec = importlib.util.spec_from_file_location("biohub_submission_contract_parity", contract_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical submission contract from {contract_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONTRACT = load_canonical_contract()


@dataclass
class FakeConfig:
    features: list[str]


@dataclass
class FakeTrack:
    ID: int
    refs: list[int]
    dummy: list[bool]
    t: list[int]
    x: list[float]
    y: list[float]
    z: list[float]
    detection_tags: list[int]
    parent: int | None = None
    children: list[int] | None = None

    @property
    def properties(self):
        return {"commons_detection_id": self.detection_tags}


class FakeTracker:
    def __init__(self):
        self.configuration = FakeConfig([])
        self.appended: dict[str, list[Any]] | None = None
        self.max_search_radius = None
        self.volume = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def configure(self, configuration):
        self.configuration = FakeConfig([])

    def append(self, objects):
        self.appended = {key: list(value) for key, value in objects.items()}

    def track(self):
        return None

    def optimise(self, options=None):
        return []

    @property
    def tracks(self):
        assert self.appended is not None
        refs = list(range(len(self.appended["t"])))
        return [
            FakeTrack(
                ID=1,
                refs=refs,
                dummy=[False] * len(refs),
                t=list(self.appended["t"]),
                x=list(self.appended["x"]),
                y=list(self.appended["y"]),
                z=list(self.appended["z"]),
                detection_tags=list(self.appended["commons_detection_id"]),
                children=[],
            )
        ]


class ContractParityTests(unittest.TestCase):
    def fake_rows(self):
        detections = [
            Detection("contract-parity", 0, 10, 2, 4, 6),
            Detection("contract-parity", 1, 11, 2, 5, 7),
            Detection("contract-parity", 2, 12, 3, 5, 8),
        ]
        return solve_all(
            detections,
            scale=Scale(),
            bounds=VoxelBounds(0, 100, 0, 100, 0, 100),
            configuration="fake-config.json",
            max_search_radius=8.5,
            tracker_factory=FakeTracker,
        )

    def test_fake_tracker_output_matches_canonical_contract_and_rewrites_exactly(self):
        rows = self.fake_rows()
        self.assertEqual(SUBMISSION_COLUMNS, CONTRACT.COLUMNS)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "adapter-first.csv"
            second = root / "adapter-second.csv"
            canonical = root / "canonical-rewrite.csv"

            write_submission(first, rows)
            write_submission(second, rows)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            with first.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames or ()), CONTRACT.COLUMNS)

            counts = CONTRACT.validate_submission(first, expected_datasets={"contract-parity"})
            self.assertEqual(
                counts,
                {"rows": 5, "nodes": 3, "edges": 2, "datasets": 1, "divisions": 0},
            )

            parsed = CONTRACT.read_submission(first)
            CONTRACT.write_submission(canonical, parsed)
            self.assertEqual(first.read_bytes(), canonical.read_bytes())


if __name__ == "__main__":
    unittest.main()
