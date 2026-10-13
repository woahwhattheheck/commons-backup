from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Callable

from adapter import AdapterError, Detection, Scale, VoxelBounds, solve_dataset


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
    def properties(self) -> dict[str, list[Any]]:
        return {"commons_detection_id": self.detection_tags}


@dataclass
class FakeConfig:
    features: list[str]


class FakeTracker:
    def __init__(
        self,
        builder: Callable[[dict[str, list[Any]]], list[FakeTrack]],
    ) -> None:
        self.builder = builder
        self.appended: dict[str, list[Any]] | None = None
        self.configuration = FakeConfig([])
        self.max_search_radius = 0.0
        self.volume: tuple[tuple[float, float], ...] | None = None
        self.optimised = False

    def __enter__(self) -> "FakeTracker":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def configure(self, configuration: Any) -> None:
        self.configuration = configuration

    def append(self, objects: dict[str, list[Any]]) -> None:
        self.appended = {key: list(value) for key, value in objects.items()}

    def track(self) -> None:
        return None

    def optimise(self, options: dict | None = None) -> list[Any]:
        self.optimised = True
        return []

    @property
    def tracks(self) -> list[FakeTrack]:
        assert self.appended is not None
        return self.builder(self.appended)


def track_from_refs(payload: dict[str, list[Any]], refs: list[int]) -> FakeTrack:
    return FakeTrack(
        ID=1,
        refs=refs,
        dummy=[False] * len(refs),
        t=[payload["t"][ref] for ref in refs],
        x=[payload["x"][ref] for ref in refs],
        y=[payload["y"][ref] for ref in refs],
        z=[payload["z"][ref] for ref in refs],
        detection_tags=[payload["commons_detection_id"][ref] for ref in refs],
        children=[],
    )


class OptimiseFilteringTests(unittest.TestCase):
    def test_optimise_mode_emits_only_refs_retained_by_optimizer(self) -> None:
        detections = [
            Detection("a", 0, 10, 5, 5, 5),
            Detection("a", 1, 11, 5, 6, 5),
            Detection("a", 2, 12, 5, 7, 5),
        ]
        trackers: list[FakeTracker] = []

        def factory() -> FakeTracker:
            tracker = FakeTracker(lambda payload: [track_from_refs(payload, [0, 1])])
            trackers.append(tracker)
            return tracker

        rows = solve_dataset(
            detections,
            scale=Scale(1.0, 1.0, 1.0),
            bounds=VoxelBounds(0, 10, 0, 10, 0, 10),
            configuration=FakeConfig([]),
            max_search_radius=2.0,
            optimise=True,
            optimizer_distance_units="physical",
            tracker_factory=factory,
        )

        self.assertEqual(1, len(trackers))
        self.assertTrue(trackers[0].optimised)
        node_rows = [row for row in rows if row["row_type"] == "node"]
        edge_rows = [row for row in rows if row["row_type"] == "edge"]
        self.assertEqual([0, 1], [row["node_id"] for row in node_rows])
        self.assertEqual([0, 1], [row["t"] for row in node_rows])
        self.assertEqual(1, len(edge_rows))
        self.assertEqual((0, 1), (edge_rows[0]["source_id"], edge_rows[0]["target_id"]))

    def test_optimise_mode_rejects_empty_retained_subset(self) -> None:
        detections = [
            Detection("a", 0, 10, 5, 5, 5),
            Detection("a", 1, 11, 5, 6, 5),
        ]
        trackers: list[FakeTracker] = []

        def factory() -> FakeTracker:
            tracker = FakeTracker(lambda payload: [])
            trackers.append(tracker)
            return tracker

        with self.assertRaisesRegex(
            AdapterError,
            "optimisation retained no real observations for non-empty dataset",
        ):
            solve_dataset(
                detections,
                scale=Scale(1.0, 1.0, 1.0),
                bounds=VoxelBounds(0, 10, 0, 10, 0, 10),
                configuration=FakeConfig([]),
                max_search_radius=2.0,
                optimise=True,
                optimizer_distance_units="physical",
                tracker_factory=factory,
            )

        self.assertEqual(1, len(trackers))
        self.assertTrue(trackers[0].optimised)


if __name__ == "__main__":
    unittest.main(verbosity=2)
