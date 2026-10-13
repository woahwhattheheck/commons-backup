#!/usr/bin/env python3
"""Data-free LapTrack adapter for the Biohub cell-tracking submission contract.

This module does not download or read competition data. It accepts detections from a
small explicit CSV, runs a caller-supplied solver (or pinned LapTrack 0.17.1 when
installed), and emits deterministic Commons node/edge rows. Tracking distances use
physical coordinates; emitted node coordinates remain the original integer voxels.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import operator
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

import numpy as np

PINNED_LAPTRACK_VERSION = "0.17.1"
PINNED_LAPTRACK_COMMIT = "13acf99fee57eaae0db84b0205142cd079a1d098"
PINNED_LAPTRACK_TREE = "71d8bc8a500456bc75a9add7fb497a917e756d52"
INPUT_COLUMNS = ("dataset", "detection_id", "t", "z", "y", "x")
SUBMISSION_COLUMNS = (
    "id",
    "dataset",
    "row_type",
    "node_id",
    "t",
    "z",
    "y",
    "x",
    "source_id",
    "target_id",
)


class AdapterError(ValueError):
    """Raised when adapter input, solver output, or dependency provenance is unsafe."""


@dataclass(frozen=True, order=True)
class Detection:
    dataset: str
    t: int
    detection_id: int
    z: int
    y: int
    x: int


@dataclass(frozen=True)
class Scale:
    z: float = 1.0
    y: float = 1.0
    x: float = 1.0

    def validate(self) -> "Scale":
        for name, value in (("z", self.z), ("y", self.y), ("x", self.x)):
            if not np.isfinite(value) or value <= 0:
                raise AdapterError(f"scale {name} must be finite and > 0")
        return self


class GraphLike(Protocol):
    @property
    def nodes(self) -> Iterable[tuple[int, int]]: ...

    @property
    def edges(self) -> Iterable[tuple[tuple[int, int], tuple[int, int]]]: ...


class SolverLike(Protocol):
    def predict(
        self,
        coords: Sequence[np.ndarray],
        connected_edges: Any = None,
        split_merge_validation: bool = True,
    ) -> GraphLike: ...


def _integer(value: object, field: str, row_number: int) -> int:
    if isinstance(value, bool):
        raise AdapterError(f"row {row_number}: {field} must be an integer")
    text = str(value)
    if text != text.strip():
        raise AdapterError(f"row {row_number}: {field} must not contain surrounding whitespace")
    try:
        result = int(text)
    except (TypeError, ValueError) as exc:
        raise AdapterError(f"row {row_number}: {field} must be an integer, got {value!r}") from exc
    if result < 0:
        raise AdapterError(f"row {row_number}: {field} must be non-negative")
    return result


def parse_detections(rows: Sequence[Mapping[str, object]]) -> list[Detection]:
    """Parse and canonicalize detections, requiring stable integer detection IDs."""
    result: list[Detection] = []
    seen_ids: set[tuple[str, int]] = set()
    for index, row in enumerate(rows, start=2):
        dataset_raw = row.get("dataset", "")
        dataset = str(dataset_raw)
        if dataset != dataset.strip() or not dataset:
            raise AdapterError(f"row {index}: dataset must be non-empty with no surrounding whitespace")
        if dataset.endswith(".zarr"):
            raise AdapterError(f"row {index}: dataset must omit the .zarr suffix")
        detection_id = _integer(row.get("detection_id", ""), "detection_id", index)
        key = (dataset, detection_id)
        if key in seen_ids:
            raise AdapterError(f"row {index}: duplicate detection_id {detection_id} in {dataset!r}")
        seen_ids.add(key)
        result.append(
            Detection(
                dataset=dataset,
                detection_id=detection_id,
                t=_integer(row.get("t", ""), "t", index),
                z=_integer(row.get("z", ""), "z", index),
                y=_integer(row.get("y", ""), "y", index),
                x=_integer(row.get("x", ""), "x", index),
            )
        )
    if not result:
        raise AdapterError("at least one detection is required")
    return sorted(result)


def read_detections(path: Path) -> list[Detection]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != INPUT_COLUMNS:
                raise AdapterError(f"input header must exactly equal {','.join(INPUT_COLUMNS)}")
            return parse_detections(list(reader))
    except OSError as exc:
        raise AdapterError(f"cannot read {path}: {exc}") from exc


def group_detections(detections: Sequence[Detection]) -> dict[str, list[Detection]]:
    groups: defaultdict[str, list[Detection]] = defaultdict(list)
    for detection in detections:
        groups[detection.dataset].append(detection)
    return {name: sorted(groups[name]) for name in sorted(groups)}


def build_coords(
    detections: Sequence[Detection], scale: Scale
) -> tuple[list[np.ndarray], dict[tuple[int, int], Detection]]:
    """Build LapTrack frame arrays and exact `(frame, local-index)` provenance."""
    scale.validate()
    if not detections:
        raise AdapterError("cannot build coordinates for an empty dataset")
    datasets = {item.dataset for item in detections}
    if len(datasets) != 1:
        raise AdapterError("build_coords accepts exactly one dataset")
    by_frame: defaultdict[int, list[Detection]] = defaultdict(list)
    for item in sorted(detections):
        by_frame[item.t].append(item)
    max_frame = max(by_frame)
    coords: list[np.ndarray] = []
    provenance: dict[tuple[int, int], Detection] = {}
    for frame in range(max_frame + 1):
        items = sorted(by_frame.get(frame, []), key=lambda item: item.detection_id)
        if not items:
            coords.append(np.empty((0, 3), dtype=np.float64))
            continue
        physical = np.asarray(
            [[item.z * scale.z, item.y * scale.y, item.x * scale.x] for item in items],
            dtype=np.float64,
        )
        coords.append(physical)
        for local_index, item in enumerate(items):
            provenance[(frame, local_index)] = item
    return coords, provenance


def _normalize_node(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise AdapterError(f"solver {label} must be a (frame,index) tuple, got {value!r}")
    frame, local_index = value
    if isinstance(frame, bool) or isinstance(local_index, bool):
        raise AdapterError(f"solver {label} indices must be integers")
    try:
        frame_i, index_i = operator.index(frame), operator.index(local_index)
    except TypeError as exc:
        raise AdapterError(f"solver {label} indices must be integers") from exc
    if min(frame_i, index_i) < 0:
        raise AdapterError(f"solver {label} indices must be non-negative integers")
    return frame_i, index_i


def graph_to_rows(
    dataset: str,
    provenance: Mapping[tuple[int, int], Detection],
    graph: GraphLike,
) -> list[dict[str, object]]:
    """Convert a LapTrack-style directed graph to strict Commons submission rows."""
    expected_nodes = set(provenance)
    graph_nodes = {_normalize_node(node, "node") for node in graph.nodes}
    missing = sorted(expected_nodes - graph_nodes)
    unexpected = sorted(graph_nodes - expected_nodes)
    if missing or unexpected:
        raise AdapterError(f"solver graph node mismatch: missing={missing}, unexpected={unexpected}")

    ordered_nodes = sorted(expected_nodes, key=lambda key: (key[0], provenance[key].detection_id))
    node_ids = {key: index for index, key in enumerate(ordered_nodes)}
    rows: list[dict[str, object]] = []
    for key in ordered_nodes:
        detection = provenance[key]
        rows.append(
            {
                "dataset": dataset,
                "row_type": "node",
                "node_id": node_ids[key],
                "t": detection.t,
                "z": detection.z,
                "y": detection.y,
                "x": detection.x,
                "source_id": -1,
                "target_id": -1,
            }
        )

    normalized_edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    seen_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    incoming: Counter[tuple[int, int]] = Counter()
    outgoing: Counter[tuple[int, int]] = Counter()
    for raw_source, raw_target in graph.edges:
        source = _normalize_node(raw_source, "edge source")
        target = _normalize_node(raw_target, "edge target")
        if source not in expected_nodes or target not in expected_nodes:
            raise AdapterError(f"solver edge references unknown node {source}->{target}")
        if target[0] != source[0] + 1:
            raise AdapterError(
                f"solver edge {source}->{target} is not consecutive t->t+1; "
                "gap closing is not submission-safe in this adapter"
            )
        edge = (source, target)
        if edge in seen_edges:
            raise AdapterError(f"solver returned duplicate edge {source}->{target}")
        seen_edges.add(edge)
        incoming[target] += 1
        outgoing[source] += 1
        if incoming[target] > 1:
            raise AdapterError(f"solver produced merge at {target}; strict Commons lineage forbids >1 parent")
        if outgoing[source] > 2:
            raise AdapterError(f"solver produced >2 children at {source}")
        normalized_edges.append(edge)

    for source, target in sorted(normalized_edges, key=lambda edge: (node_ids[edge[0]], node_ids[edge[1]])):
        rows.append(
            {
                "dataset": dataset,
                "row_type": "edge",
                "node_id": -1,
                "t": -1,
                "z": -1,
                "y": -1,
                "x": -1,
                "source_id": node_ids[source],
                "target_id": node_ids[target],
            }
        )
    return rows


def load_pinned_laptrack() -> type:
    """Import only the audited LapTrack version; fail closed on drift or absence."""
    try:
        module = importlib.import_module("laptrack")
    except ImportError as exc:
        raise AdapterError(
            f"laptrack {PINNED_LAPTRACK_VERSION} is required at runtime; no solver run was performed"
        ) from exc
    version = getattr(module, "__version__", None)
    if version != PINNED_LAPTRACK_VERSION:
        raise AdapterError(
            f"laptrack version drift: expected {PINNED_LAPTRACK_VERSION}, got {version!r}"
        )
    solver_type = getattr(module, "LapTrack", None)
    if solver_type is None:
        raise AdapterError("pinned laptrack module does not expose LapTrack")
    return solver_type


def solve_dataset(
    detections: Sequence[Detection],
    *,
    scale: Scale,
    cutoff: float,
    splitting_cutoff: float | bool = False,
    solver_factory: Callable[..., SolverLike] | None = None,
) -> list[dict[str, object]]:
    """Run one dataset with consecutive-edge settings and convert its graph."""
    if not np.isfinite(cutoff) or cutoff <= 0:
        raise AdapterError("cutoff must be finite and > 0")
    if splitting_cutoff is not False and (
        not np.isfinite(float(splitting_cutoff)) or float(splitting_cutoff) <= 0
    ):
        raise AdapterError("splitting_cutoff must be False or a finite value > 0")
    coords, provenance = build_coords(detections, scale)
    factory = solver_factory or load_pinned_laptrack()
    solver = factory(
        metric="sqeuclidean",
        cutoff=float(cutoff),
        gap_closing_cutoff=False,
        splitting_metric="sqeuclidean",
        splitting_cutoff=splitting_cutoff,
        merging_cutoff=False,
        parallel_backend="serial",
    )
    graph = solver.predict(coords, connected_edges=None, split_merge_validation=True)
    return graph_to_rows(detections[0].dataset, provenance, graph)


def solve_all(
    detections: Sequence[Detection],
    *,
    scale: Scale,
    cutoff: float,
    splitting_cutoff: float | bool = False,
    solver_factory: Callable[..., SolverLike] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for dataset, items in group_detections(detections).items():
        rows.extend(
            solve_dataset(
                items,
                scale=scale,
                cutoff=cutoff,
                splitting_cutoff=splitting_cutoff,
                solver_factory=solver_factory,
            )
        )
    for index, row in enumerate(rows):
        row["id"] = index
    return [{key: row[key] for key in SUBMISSION_COLUMNS} for row in rows]


def write_submission(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUBMISSION_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row[key] for key in SUBMISSION_COLUMNS})
    except (KeyError, OSError) as exc:
        raise AdapterError(f"cannot write {path}: {exc}") from exc


def _parse_splitting(value: str) -> float | bool:
    if value.lower() in {"false", "off", "none"}:
        return False
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be 'false' or a positive float") from exc
    if not np.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be 'false' or a positive finite float")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detections", type=Path, required=True, help="CSV with exact adapter input header")
    parser.add_argument("--output", type=Path, required=True, help="submission.csv destination")
    parser.add_argument("--scale-z", type=float, default=1.0)
    parser.add_argument("--scale-y", type=float, default=1.0)
    parser.add_argument("--scale-x", type=float, default=1.0)
    parser.add_argument("--cutoff", type=float, default=225.0, help="squared physical-distance cutoff")
    parser.add_argument(
        "--splitting-cutoff",
        type=_parse_splitting,
        default=False,
        help="false (default) or squared physical-distance cutoff for explicit split inference",
    )
    parser.add_argument("--provenance-json", type=Path, help="optional write-only run provenance receipt")
    args = parser.parse_args(argv)
    try:
        input_path = args.detections.resolve()
        output_path = args.output.resolve()
        provenance_path = args.provenance_json.resolve() if args.provenance_json else None
        if output_path == input_path:
            raise AdapterError("output must not overwrite the detections input")
        if provenance_path == input_path:
            raise AdapterError("provenance receipt must not overwrite the detections input")
        if provenance_path is not None and provenance_path == output_path:
            raise AdapterError("provenance receipt must not overwrite submission output")
        detections = read_detections(args.detections)
        rows = solve_all(
            detections,
            scale=Scale(args.scale_z, args.scale_y, args.scale_x),
            cutoff=args.cutoff,
            splitting_cutoff=args.splitting_cutoff,
        )
        write_submission(args.output, rows)
        if args.provenance_json:
            receipt = {
                "adapter": "BIOHUB-LAPTRACK-ADAPTER",
                "laptrack_version": PINNED_LAPTRACK_VERSION,
                "laptrack_commit": PINNED_LAPTRACK_COMMIT,
                "laptrack_tree": PINNED_LAPTRACK_TREE,
                "datasets": sorted(group_detections(detections)),
                "detections": len(detections),
                "rows": len(rows),
                "scale_zyx": [args.scale_z, args.scale_y, args.scale_x],
                "cutoff": args.cutoff,
                "splitting_cutoff": args.splitting_cutoff,
                "gap_closing": False,
                "merging": False,
            }
            args.provenance_json.parent.mkdir(parents=True, exist_ok=True)
            args.provenance_json.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (AdapterError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
