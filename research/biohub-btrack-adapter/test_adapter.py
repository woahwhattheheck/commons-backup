from __future__ import annotations

import csv
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from adapter import (
    AdapterError,
    Detection,
    Scale,
    VoxelBounds,
    build_btrack_payload,
    parse_detections,
    solve_all,
    solve_dataset,
    tracks_to_rows,
    write_submission,
)


@dataclass
class FakeTrack:
    ID: int
    refs: list[int]
    dummy: list[bool]
    t: list[int]
    x: list[float]
    y: list[float]
    z: list[float]
    detection_tags: list[int | float]
    parent: int | None = None
    children: list[int] | None = None

    @property
    def properties(self):
        return {"commons_detection_id": self.detection_tags}


@dataclass
class FakeConfig:
    features: list[str]


class FakeTracker:
    def __init__(self, builder: Callable[[dict[str, list[Any]]], list[FakeTrack]], registry: list["FakeTracker"]):
        self.builder = builder
        self.registry = registry
        self.registry.append(self)
        self.appended: dict[str, list[Any]] | None = None
        self.configuration = None
        self.max_search_radius = None
        self.volume = None
        self.optimised = False
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True
        return False

    def configure(self, configuration):
        self.configuration = configuration if hasattr(configuration, "features") else FakeConfig([])

    def append(self, objects):
        self.appended = {key: list(value) for key, value in objects.items()}

    def track(self):
        return None

    def optimise(self, options=None):
        self.optimised = True
        return []

    @property
    def tracks(self):
        assert self.appended is not None
        return self.builder(self.appended)


def factory_for(builder, registry):
    return lambda: FakeTracker(builder, registry)


def track_from_refs(payload, *, track_id=1, refs=None, parent=None, children=None):
    refs = list(range(len(payload["t"]))) if refs is None else refs
    by_ref = {i: i for i in range(len(payload["t"]))}
    return FakeTrack(
        ID=track_id,
        refs=list(refs),
        dummy=[ref < 0 for ref in refs],
        t=[payload["t"][by_ref[ref]] if ref >= 0 else 0 for ref in refs],
        x=[payload["x"][by_ref[ref]] if ref >= 0 else 0.0 for ref in refs],
        y=[payload["y"][by_ref[ref]] if ref >= 0 else 0.0 for ref in refs],
        z=[payload["z"][by_ref[ref]] if ref >= 0 else 0.0 for ref in refs],
        detection_tags=[payload["commons_detection_id"][by_ref[ref]] if ref >= 0 else float("nan") for ref in refs],
        parent=parent,
        children=[] if children is None else children,
    )


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.scale = Scale()
        self.bounds = VoxelBounds(0, 100, 0, 100, 0, 100)

    def detections(self, dataset="a"):
        return [
            Detection(dataset, 0, 10, 2, 4, 6),
            Detection(dataset, 1, 11, 2, 5, 7),
            Detection(dataset, 2, 12, 3, 5, 8),
        ]

    def test_parse_is_deterministic_and_rejects_whitespace(self):
        rows = [
            {"dataset": "a", "detection_id": "11", "t": "1", "z": "2", "y": "5", "x": "7"},
            {"dataset": "a", "detection_id": "10", "t": "0", "z": "2", "y": "4", "x": "6"},
        ]
        parsed = parse_detections(rows)
        self.assertEqual([d.detection_id for d in parsed], [10, 11])
        rows[0]["dataset"] = " a"
        with self.assertRaisesRegex(AdapterError, "dataset"):
            parse_detections(rows)

    def test_payload_freezes_ref_map_and_scales_xyz(self):
        payload, refs = build_btrack_payload(self.detections(), self.scale, self.bounds)
        self.assertEqual(refs[0].detection_id, 10)
        self.assertEqual(payload["commons_detection_id"], [10, 11, 12])
        self.assertEqual(payload["x"][0], 6 * self.scale.x)
        self.assertEqual(payload["y"][0], 4 * self.scale.y)
        self.assertEqual(payload["z"][0], 2 * self.scale.z)
        self.assertEqual(
            self.bounds.physical_btrack(self.scale),
            ((0.0, 100 * self.scale.x), (0.0, 100 * self.scale.y), (0.0, 100 * self.scale.z)),
        )

    def test_solve_passes_physical_volume_radius_and_closes_engine(self):
        registry = []
        builder = lambda payload: [track_from_refs(payload)]
        rows = solve_dataset(
            self.detections(),
            scale=self.scale,
            bounds=self.bounds,
            configuration="cfg.json",
            max_search_radius=8.5,
            tracker_factory=factory_for(builder, registry),
        )
        self.assertEqual(len(registry), 1)
        tracker = registry[0]
        self.assertTrue(tracker.entered and tracker.exited)
        self.assertEqual(tracker.max_search_radius, 8.5)
        self.assertEqual(tracker.volume, self.bounds.physical_btrack(self.scale))
        self.assertEqual([r["row_type"] for r in rows].count("edge"), 2)

    def test_reserved_provenance_feature_rejects_before_append(self):
        registry = []
        with self.assertRaisesRegex(AdapterError, "commons_detection_id"):
            solve_dataset(
                self.detections(),
                scale=self.scale,
                bounds=self.bounds,
                configuration=FakeConfig(["commons_detection_id"]),
                max_search_radius=8.5,
                tracker_factory=factory_for(lambda payload: [track_from_refs(payload)], registry),
            )
        self.assertEqual(len(registry), 1)
        self.assertIsNone(registry[0].appended)

    def test_optimise_requires_physical_unit_attestation(self):
        with self.assertRaisesRegex(AdapterError, "optimizer_distance_units='physical'"):
            solve_dataset(
                self.detections(),
                scale=self.scale,
                bounds=self.bounds,
                configuration="cfg.json",
                max_search_radius=8.5,
                optimise=True,
                tracker_factory=factory_for(lambda payload: [track_from_refs(payload)], []),
            )

    def test_optimise_runs_only_after_attestation(self):
        registry = []
        solve_dataset(
            self.detections(),
            scale=self.scale,
            bounds=self.bounds,
            configuration="cfg.json",
            max_search_radius=8.5,
            optimise=True,
            optimizer_distance_units="physical",
            tracker_factory=factory_for(lambda payload: [track_from_refs(payload)], registry),
        )
        self.assertTrue(registry[0].optimised)

    def test_dummy_gap_fails_closed(self):
        detections = self.detections()
        payload, refs = build_btrack_payload(detections, self.scale, self.bounds)
        track = FakeTrack(
            ID=1,
            refs=[0, -1, 2],
            dummy=[False, True, False],
            t=[0, 1, 2],
            x=[payload["x"][0], 0.0, payload["x"][2]],
            y=[payload["y"][0], 0.0, payload["y"][2]],
            z=[payload["z"][0], 0.0, payload["z"][2]],
            detection_tags=[10, float("nan"), 12],
        )
        with self.assertRaisesRegex(AdapterError, "nonconsecutive"):
            tracks_to_rows("a", detections, [track], refs, self.scale)

    def test_hdf_style_id_mutation_is_detected_by_independent_tag(self):
        detections = self.detections()[:2]
        payload, refs = build_btrack_payload(detections, self.scale, self.bounds)
        # Ref 1 now points at detection 11, but the immutable property tag still says 10.
        mutated = FakeTrack(
            ID=1,
            refs=[1],
            dummy=[False],
            t=[0],
            x=[payload["x"][0]],
            y=[payload["y"][0]],
            z=[payload["z"][0]],
            detection_tags=[10],
        )
        with self.assertRaisesRegex(AdapterError, "IDs may have been mutated"):
            tracks_to_rows("a", detections, [mutated], refs, self.scale)

    def test_fractional_refs_fail_closed_instead_of_truncating(self):
        detections = self.detections()[:1]
        payload, refs = build_btrack_payload(detections, self.scale, self.bounds)
        fractional = FakeTrack(
            1,
            [0.5],
            [False],
            [0],
            [payload["x"][0]],
            [payload["y"][0]],
            [payload["z"][0]],
            [10],
        )
        with self.assertRaisesRegex(AdapterError, "must be an integer"):
            tracks_to_rows("a", detections, [fractional], refs, self.scale)

    def test_unknown_and_inconsistent_dummy_refs_fail_closed(self):
        detections = self.detections()[:1]
        payload, refs = build_btrack_payload(detections, self.scale, self.bounds)
        bad = FakeTrack(1, [99], [False], [0], [payload["x"][0]], [payload["y"][0]], [payload["z"][0]], [10])
        with self.assertRaisesRegex(AdapterError, "unknown object ID"):
            tracks_to_rows("a", detections, [bad], refs, self.scale)
        bad2 = FakeTrack(1, [-1], [False], [0], [0.0], [0.0], [0.0], [10])
        with self.assertRaisesRegex(AdapterError, "dummy/ref sign"):
            tracks_to_rows("a", detections, [bad2], refs, self.scale)

    def test_parent_children_make_exact_two_child_division(self):
        detections = [
            Detection("a", 0, 10, 10, 10, 10),
            Detection("a", 1, 11, 10, 11, 10),
            Detection("a", 1, 12, 10, 9, 10),
        ]
        payload, refs = build_btrack_payload(detections, self.scale, self.bounds)
        parent = track_from_refs(payload, track_id=1, refs=[0], parent=None, children=[2, 3])
        child1 = track_from_refs(payload, track_id=2, refs=[1], parent=1)
        child2 = track_from_refs(payload, track_id=3, refs=[2], parent=1)
        rows = tracks_to_rows("a", detections, [parent, child1, child2], refs, self.scale)
        edges = [(r["source_id"], r["target_id"]) for r in rows if r["row_type"] == "edge"]
        self.assertEqual(edges, [(0, 1), (0, 2)])

    def test_more_than_two_children_and_multiple_parents_reject(self):
        detections = [
            Detection("a", 0, 10, 1, 1, 1),
            Detection("a", 0, 13, 1, 2, 1),
            Detection("a", 1, 11, 1, 1, 2),
            Detection("a", 1, 12, 1, 1, 3),
            Detection("a", 1, 14, 1, 1, 4),
        ]
        payload, refs = build_btrack_payload(detections, self.scale, self.bounds)
        parent = track_from_refs(payload, track_id=1, refs=[0], children=[2, 3, 4])
        children = [
            track_from_refs(payload, track_id=2, refs=[2], parent=1),
            track_from_refs(payload, track_id=3, refs=[3], parent=1),
            track_from_refs(payload, track_id=4, refs=[4], parent=1),
        ]
        covering = track_from_refs(payload, track_id=5, refs=[1])
        with self.assertRaisesRegex(AdapterError, "more than two children"):
            tracks_to_rows("a", detections, [parent, *children, covering], refs, self.scale)

    def test_two_datasets_use_two_fresh_engines_and_match_isolated_runs(self):
        combined = self.detections("a")[:2] + self.detections("b")[:2]
        registry = []
        factory = factory_for(lambda payload: [track_from_refs(payload)], registry)
        rows = solve_all(
            combined,
            scale=self.scale,
            bounds=self.bounds,
            configuration="cfg.json",
            max_search_radius=8.5,
            tracker_factory=factory,
        )
        self.assertEqual(len(registry), 2)
        self.assertTrue(all(t.entered and t.exited for t in registry))
        by_dataset = {dataset: [r for r in rows if r["dataset"] == dataset] for dataset in ("a", "b")}
        self.assertEqual(len(by_dataset["a"]), 3)
        self.assertEqual(len(by_dataset["b"]), 3)
        # IDs are globally serialized, but dataset-local node/edge identity is identical.
        stripped_a = [{k: v for k, v in r.items() if k != "id"} for r in by_dataset["a"]]
        isolated_registry = []
        isolated = solve_all(
            self.detections("a")[:2],
            scale=self.scale,
            bounds=self.bounds,
            configuration="cfg.json",
            max_search_radius=8.5,
            tracker_factory=factory_for(lambda payload: [track_from_refs(payload)], isolated_registry),
        )
        self.assertEqual(stripped_a, [{k: v for k, v in r.items() if k != "id"} for r in isolated])

    def test_shuffled_input_serializes_identically(self):
        detections = self.detections()
        def solve(items):
            return solve_all(
                items,
                scale=self.scale,
                bounds=self.bounds,
                configuration="cfg.json",
                max_search_radius=8.5,
                tracker_factory=factory_for(lambda payload: [track_from_refs(payload)], []),
            )
        rows_a = solve(detections)
        rows_b = solve(list(reversed(detections)))
        self.assertEqual(rows_a, rows_b)
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.csv", Path(tmp) / "b.csv"
            write_submission(a, rows_a)
            write_submission(b, rows_b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with a.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames or ()), ("id", "dataset", "row_type", "node_id", "t", "z", "y", "x", "source_id", "target_id"))

    def test_physical_equivalence_across_axes(self):
        scale = Scale(z=2.0, y=1.0, x=0.5)
        detections = [
            Detection("a", 0, 1, 0, 0, 0),
            Detection("a", 1, 2, 1, 0, 0),  # 2 physical units in z
            Detection("a", 1, 3, 0, 2, 0),  # 2 physical units in y
            Detection("a", 1, 4, 0, 0, 4),  # 2 physical units in x
        ]
        payload, _ = build_btrack_payload(detections, scale, VoxelBounds(0, 5, 0, 5, 0, 5))
        origin = (payload["x"][0], payload["y"][0], payload["z"][0])
        squared = []
        for index in (1, 2, 3):
            point = (payload["x"][index], payload["y"][index], payload["z"][index])
            squared.append(sum((a - b) ** 2 for a, b in zip(point, origin)))
        self.assertEqual(squared, [4.0, 4.0, 4.0])


if __name__ == "__main__":
    unittest.main()
