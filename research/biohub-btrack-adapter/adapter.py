#!/usr/bin/env python3
"""Data-free BTrack v0.7.0 adapter for the Biohub Commons submission contract.

The adapter keeps competition data out of the repository. It accepts explicit point
detections, runs one fresh BTrack engine per dataset, and converts tracklets into
strict adjacent-frame Commons node/edge rows while preserving original integer voxel
coordinates. Real BTrack execution is optional and fails closed unless the pinned
0.7.0 runtime is installed.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import importlib
import math
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

PINNED_BTRACK_VERSION = "0.7.0"
PINNED_BTRACK_COMMIT = "a3bd947915efe6837936f9db6db88417f0b51b45"
BTRACK_UINT32_MAX = (1 << 32) - 1
RESERVED_ADAPTER_PROPERTIES = frozenset({"commons_detection_id"})
INPUT_COLUMNS = ("dataset", "detection_id", "t", "z", "y", "x")
BOUNDS_COLUMNS = ("dataset", "zlo", "zhi", "ylo", "yhi", "xlo", "xhi")
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
    """Raised when input, tracker output, or runtime provenance is unsafe."""


def _positive_btrack_float(value: object, label: str) -> float:
    """Narrow one positive physical distance through BTrack's c_float ABI."""
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AdapterError(f"{label} must be a finite physical distance > 0") from exc
    if not math.isfinite(numeric) or numeric <= 0:
        raise AdapterError(f"{label} must be a finite physical distance > 0")
    try:
        narrowed = ctypes.c_float(numeric).value
    except (TypeError, ValueError, OverflowError) as exc:
        raise AdapterError(f"{label} must fit the pinned BTrack float32 ABI") from exc
    if not math.isfinite(narrowed) or narrowed <= 0:
        raise AdapterError(
            f"{label} must remain finite and > 0 after pinned BTrack float32 conversion"
        )
    return float(narrowed)


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
    """Voxel spacing in physical units, in Commons z/y/x order."""

    z: float = 1.625
    y: float = 0.40625
    x: float = 0.40625

    def validate(self) -> "Scale":
        for name, value in (("z", self.z), ("y", self.y), ("x", self.x)):
            if not math.isfinite(value) or value <= 0:
                raise AdapterError(f"scale {name} must be finite and > 0")
        return self


def _physical_value(value: int | float, spacing: float, label: str) -> float:
    """Scale one BTrack coordinate and fail closed if the native double is non-finite."""
    try:
        result = float(value * spacing)
    except (OverflowError, ValueError) as exc:
        raise AdapterError(f"{label} exceeds finite BTrack coordinate range") from exc
    if not math.isfinite(result):
        raise AdapterError(f"{label} exceeds finite BTrack coordinate range")
    return result


@dataclass(frozen=True)
class VoxelBounds:
    """Inclusive voxel-coordinate bounds, kept explicit instead of inferred."""

    zlo: float
    zhi: float
    ylo: float
    yhi: float
    xlo: float
    xhi: float

    def validate(self) -> "VoxelBounds":
        for name, lo, hi in (
            ("z", self.zlo, self.zhi),
            ("y", self.ylo, self.yhi),
            ("x", self.xlo, self.xhi),
        ):
            if not math.isfinite(lo) or not math.isfinite(hi) or hi < lo:
                raise AdapterError(f"volume {name} bounds must be finite with high >= low")
        return self

    def physical_btrack(self, scale: Scale) -> tuple[tuple[float, float], ...]:
        """Return BTrack volume in physical (x,y,z) order."""
        self.validate()
        scale.validate()
        return (
            (
                _physical_value(self.xlo, scale.x, "volume xlo"),
                _physical_value(self.xhi, scale.x, "volume xhi"),
            ),
            (
                _physical_value(self.ylo, scale.y, "volume ylo"),
                _physical_value(self.yhi, scale.y, "volume yhi"),
            ),
            (
                _physical_value(self.zlo, scale.z, "volume zlo"),
                _physical_value(self.zhi, scale.z, "volume zhi"),
            ),
        )

    def contains(self, item: Detection) -> bool:
        return (
            self.zlo <= item.z <= self.zhi
            and self.ylo <= item.y <= self.yhi
            and self.xlo <= item.x <= self.xhi
        )


class TrackLike(Protocol):
    ID: int
    parent: int | None
    children: Sequence[int]
    refs: Sequence[int]
    dummy: Sequence[bool]
    t: Sequence[int]
    x: Sequence[float]
    y: Sequence[float]
    z: Sequence[float]
    properties: Mapping[str, Sequence[Any]]


class TrackerLike(Protocol):
    configuration: Any
    volume: tuple[tuple[float, float], ...]
    max_search_radius: float
    tracks: Sequence[TrackLike]

    def __enter__(self) -> "TrackerLike": ...
    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any: ...
    def configure(self, configuration: Any) -> None: ...
    def append(self, objects: Mapping[str, Sequence[Any]]) -> None: ...
    def track(self) -> Any: ...
    def optimise(self, options: dict | None = None) -> Any: ...


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


def _finite_float(value: object, field: str, row_number: int) -> float:
    if isinstance(value, bool):
        raise AdapterError(f"row {row_number}: {field} must be a finite number")
    text = str(value)
    if not text or text != text.strip():
        raise AdapterError(f"row {row_number}: {field} must be a finite number with no surrounding whitespace")
    try:
        result = float(text)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AdapterError(f"row {row_number}: {field} must be a finite number") from exc
    if not math.isfinite(result):
        raise AdapterError(f"row {row_number}: {field} must be a finite number")
    return result


def parse_detections(rows: Sequence[Mapping[str, object]]) -> list[Detection]:
    result: list[Detection] = []
    seen: set[tuple[str, int]] = set()
    for row_number, row in enumerate(rows, start=2):
        dataset = str(row.get("dataset", ""))
        if not dataset or dataset != dataset.strip() or dataset.endswith(".zarr"):
            raise AdapterError(
                f"row {row_number}: dataset must be non-empty, omit .zarr, and have no surrounding whitespace"
            )
        detection_id = _integer(row.get("detection_id", ""), "detection_id", row_number)
        key = (dataset, detection_id)
        if key in seen:
            raise AdapterError(f"row {row_number}: duplicate detection_id {detection_id} in {dataset!r}")
        seen.add(key)
        result.append(
            Detection(
                dataset=dataset,
                detection_id=detection_id,
                t=_integer(row.get("t", ""), "t", row_number),
                z=_integer(row.get("z", ""), "z", row_number),
                y=_integer(row.get("y", ""), "y", row_number),
                x=_integer(row.get("x", ""), "x", row_number),
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


def read_bounds_manifest(path: Path) -> dict[str, VoxelBounds]:
    """Read an exact dataset -> voxel-bounds manifest for multi-dataset CLI runs."""
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != BOUNDS_COLUMNS:
                raise AdapterError(f"bounds header must exactly equal {','.join(BOUNDS_COLUMNS)}")
            result: dict[str, VoxelBounds] = {}
            for row_number, row in enumerate(reader, start=2):
                dataset = str(row.get("dataset", ""))
                if not dataset or dataset != dataset.strip() or dataset.endswith(".zarr"):
                    raise AdapterError(
                        f"row {row_number}: bounds dataset must be non-empty, omit .zarr, and have no surrounding whitespace"
                    )
                if dataset in result:
                    raise AdapterError(f"row {row_number}: duplicate bounds dataset {dataset!r}")
                result[dataset] = VoxelBounds(
                    _finite_float(row.get("zlo", ""), "zlo", row_number),
                    _finite_float(row.get("zhi", ""), "zhi", row_number),
                    _finite_float(row.get("ylo", ""), "ylo", row_number),
                    _finite_float(row.get("yhi", ""), "yhi", row_number),
                    _finite_float(row.get("xlo", ""), "xlo", row_number),
                    _finite_float(row.get("xhi", ""), "xhi", row_number),
                ).validate()
            if not result:
                raise AdapterError("bounds manifest must contain at least one dataset row")
            return {dataset: result[dataset] for dataset in sorted(result)}
    except OSError as exc:
        raise AdapterError(f"cannot read bounds manifest {path}: {exc}") from exc


def group_detections(detections: Sequence[Detection]) -> dict[str, list[Detection]]:
    groups: defaultdict[str, list[Detection]] = defaultdict(list)
    for item in detections:
        groups[item.dataset].append(item)
    return {dataset: sorted(groups[dataset]) for dataset in sorted(groups)}


def build_btrack_payload(
    detections: Sequence[Detection], scale: Scale, bounds: VoxelBounds
) -> tuple[dict[str, list[Any]], dict[int, Detection]]:
    """Build deterministic BTrack localizations and immutable sequential-ref map."""
    scale.validate()
    bounds.validate()
    if not detections:
        raise AdapterError("cannot build BTrack payload for an empty dataset")
    datasets = {item.dataset for item in detections}
    if len(datasets) != 1:
        raise AdapterError("build_btrack_payload accepts exactly one dataset")
    ordered = sorted(detections)
    for item in ordered:
        if item.t > BTRACK_UINT32_MAX:
            raise AdapterError(
                f"detection {item.detection_id} time {item.t} exceeds pinned BTrack uint32 range"
            )
        if not bounds.contains(item):
            raise AdapterError(f"detection {item.detection_id} lies outside configured voxel volume")
    # btrack.io.localizations_to_objects replaces caller IDs with np.arange(n).
    # The map below is therefore the adapter's authoritative frozen ref identity.
    ref_map = {index: item for index, item in enumerate(ordered)}
    payload: dict[str, list[Any]] = {
        "t": [item.t for item in ordered],
        "x": [
            _physical_value(item.x, scale.x, f"detection {item.detection_id} x")
            for item in ordered
        ],
        "y": [
            _physical_value(item.y, scale.y, f"detection {item.detection_id} y")
            for item in ordered
        ],
        "z": [
            _physical_value(item.z, scale.z, f"detection {item.detection_id} z")
            for item in ordered
        ],
        # Extra properties survive PyTrackObject.from_dict and provide an independent
        # identity check if a later operation mutates object IDs/Tracklet.refs.
        "commons_detection_id": [item.detection_id for item in ordered],
    }
    return payload, ref_map


def _as_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise AdapterError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AdapterError(f"{label} must be an integer") from exc
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AdapterError(f"{label} must be an integer") from exc
    if not math.isfinite(numeric) or numeric != float(result):
        raise AdapterError(f"{label} must be an integer")
    return result


def _close(actual: Any, expected: float, label: str) -> None:
    try:
        value = float(actual)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AdapterError(f"{label} must be numeric") from exc
    if not math.isfinite(value) or not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-9):
        raise AdapterError(f"{label} disagrees with frozen Commons identity map")


def _real_observations(
    track: TrackLike, ref_map: Mapping[int, Detection], scale: Scale
) -> list[tuple[int, Detection]]:
    refs = list(track.refs)
    dummies = list(track.dummy)
    times = list(track.t)
    xs, ys, zs = list(track.x), list(track.y), list(track.z)
    try:
        tags = list(track.properties["commons_detection_id"])
    except (KeyError, TypeError) as exc:
        raise AdapterError(
            "track is missing commons_detection_id provenance; refuse ref-only conversion"
        ) from exc
    lengths = {len(refs), len(dummies), len(times), len(xs), len(ys), len(zs), len(tags)}
    if len(lengths) != 1:
        raise AdapterError(f"track {track.ID} has misaligned observation arrays")

    real: list[tuple[int, Detection]] = []
    for index, raw_ref in enumerate(refs):
        ref = _as_int(raw_ref, f"track {track.ID} ref")
        if bool(dummies[index]) or ref < 0:
            if not bool(dummies[index]) or ref >= 0:
                raise AdapterError(f"track {track.ID} has inconsistent dummy/ref sign")
            continue
        item = ref_map.get(ref)
        if item is None:
            raise AdapterError(f"track {track.ID} references unknown object ID {ref}")
        tag = _as_int(tags[index], f"track {track.ID} provenance tag")
        if tag != item.detection_id:
            raise AdapterError(
                f"track {track.ID} ref/provenance mismatch; object IDs may have been mutated before conversion"
            )
        if _as_int(times[index], f"track {track.ID} time") != item.t:
            raise AdapterError(f"track {track.ID} time disagrees with frozen Commons identity map")
        _close(xs[index], item.x * scale.x, f"track {track.ID} x")
        _close(ys[index], item.y * scale.y, f"track {track.ID} y")
        _close(zs[index], item.z * scale.z, f"track {track.ID} z")
        real.append((ref, item))
    return real


def tracks_to_rows(
    dataset: str,
    detections: Sequence[Detection],
    tracks: Sequence[TrackLike],
    ref_map: Mapping[int, Detection],
    scale: Scale,
    *,
    require_full_coverage: bool = True,
) -> list[dict[str, object]]:
    """Convert BTrack tracklets immediately, before any list-mode HDF export."""
    if any(item.dataset != dataset for item in detections):
        raise AdapterError("tracks_to_rows accepts exactly one dataset")
    ordered = sorted(detections)

    track_by_id: dict[int, TrackLike] = {}
    real_by_id: dict[int, list[tuple[int, Detection]]] = {}
    edges: set[tuple[int, int]] = set()
    seen_real_refs: dict[int, int] = {}

    for track in tracks:
        track_id = _as_int(track.ID, "track ID")
        if track_id <= 0:
            raise AdapterError("track ID must be positive; 0 is reserved as the no-parent lineage sentinel")
        if track_id in track_by_id:
            raise AdapterError(f"duplicate track ID {track_id}")
        track_by_id[track_id] = track
        real = _real_observations(track, ref_map, scale)
        if not real:
            raise AdapterError(f"track {track_id} has no real observations")
        for ref, _ in real:
            if ref in seen_real_refs:
                raise AdapterError(f"object ID {ref} appears in multiple track observations")
            seen_real_refs[ref] = track_id
        real_by_id[track_id] = real
        for (_, source), (_, target) in zip(real, real[1:]):
            if target.t != source.t + 1:
                raise AdapterError(
                    f"track {track_id} spans nonconsecutive real observations {source.t}->{target.t}; "
                    "max_lost/dummy gaps are not submission-safe"
                )
            edges.add((source.detection_id, target.detection_id))

    missing_real_refs = sorted(set(ref_map) - set(seen_real_refs))
    if missing_real_refs and require_full_coverage:
        raise AdapterError(f"tracker output omitted real object ID {missing_real_refs[0]}")

    if require_full_coverage:
        emitted = ordered
    else:
        retained_detection_ids = {ref_map[ref].detection_id for ref in seen_real_refs}
        emitted = [item for item in ordered if item.detection_id in retained_detection_ids]
    node_ids = {item.detection_id: index for index, item in enumerate(emitted)}
    detection_by_id = {item.detection_id: item for item in emitted}
    rows: list[dict[str, object]] = [
        {
            "dataset": dataset,
            "row_type": "node",
            "node_id": node_ids[item.detection_id],
            "t": item.t,
            "z": item.z,
            "y": item.y,
            "x": item.x,
            "source_id": -1,
            "target_id": -1,
        }
        for item in emitted
    ]

    # Validate declared lineage and add one parent-last -> child-first edge.
    for track_id, track in track_by_id.items():
        parent_raw = track.parent
        if parent_raw is None:
            continue
        parent_id = _as_int(parent_raw, f"track {track_id} parent")
        if parent_id in (0, track_id):
            continue
        parent_track = track_by_id.get(parent_id)
        if parent_track is None:
            raise AdapterError(f"track {track_id} references unknown parent track {parent_id}")
        declared_children = {
            _as_int(raw_child, f"track {parent_id} child")
            for raw_child in list(parent_track.children or [])
        }
        if track_id not in declared_children:
            raise AdapterError(
                f"lineage {parent_id}->{track_id} is missing reciprocal parent child declaration"
            )
        parent_real = real_by_id[parent_id]
        child_real = real_by_id[track_id]
        if not parent_real or not child_real:
            raise AdapterError(f"lineage {parent_id}->{track_id} lacks real observations")
        source, target = parent_real[-1][1], child_real[0][1]
        if target.t != source.t + 1:
            raise AdapterError(
                f"lineage {parent_id}->{track_id} is not adjacent-frame: {source.t}->{target.t}"
            )
        edges.add((source.detection_id, target.detection_id))

    for track_id, track in track_by_id.items():
        seen_children: set[int] = set()
        for raw_child in list(track.children or []):
            child_id = _as_int(raw_child, f"track {track_id} child")
            if child_id == track_id:
                raise AdapterError(f"track {track_id} cannot declare itself as a child")
            if child_id in seen_children:
                raise AdapterError(f"track {track_id} declares duplicate child {child_id}")
            seen_children.add(child_id)
            child = track_by_id.get(child_id)
            if child is None:
                raise AdapterError(f"track {track_id} declares unknown child {child_id}")
            child_parent = child.parent
            if child_parent is None or _as_int(child_parent, f"track {child_id} parent") != track_id:
                raise AdapterError(f"track {track_id} child declaration disagrees with child {child_id} parent")
        if len(seen_children) > 2:
            raise AdapterError(f"track {track_id} declares more than two children")
        if len(seen_children) not in (0, 2):
            raise AdapterError(
                f"track {track_id} must declare exactly 0 or 2 children for pinned BTrack output"
            )

    incoming: Counter[int] = Counter()
    outgoing: Counter[int] = Counter()
    ordered_edges = sorted(edges, key=lambda edge: (node_ids[edge[0]], node_ids[edge[1]]))
    for source_detection_id, target_detection_id in ordered_edges:
        if source_detection_id not in node_ids or target_detection_id not in node_ids:
            raise AdapterError("edge identity escaped the current dataset")
        source = detection_by_id[source_detection_id]
        target = detection_by_id[target_detection_id]
        if target.t != source.t + 1:
            raise AdapterError("only adjacent-frame edges may be emitted")
        incoming[target_detection_id] += 1
        outgoing[source_detection_id] += 1
        if incoming[target_detection_id] > 1:
            raise AdapterError(f"detection {target_detection_id} has more than one parent")
        if outgoing[source_detection_id] > 2:
            raise AdapterError(f"detection {source_detection_id} has more than two children")
        rows.append(
            {
                "dataset": dataset,
                "row_type": "edge",
                "node_id": -1,
                "t": -1,
                "z": -1,
                "y": -1,
                "x": -1,
                "source_id": node_ids[source_detection_id],
                "target_id": node_ids[target_detection_id],
            }
        )
    return rows


def load_pinned_tracker() -> type:
    try:
        module = importlib.import_module("btrack")
    except ImportError as exc:
        raise AdapterError(f"btrack {PINNED_BTRACK_VERSION} is required for a real solver run") from exc
    version = getattr(module, "__version__", None)
    if version != PINNED_BTRACK_VERSION:
        raise AdapterError(
            f"btrack version drift: expected {PINNED_BTRACK_VERSION}, got {version!r}"
        )
    tracker_type = getattr(module, "BayesianTracker", None)
    if tracker_type is None:
        raise AdapterError("pinned btrack module does not expose BayesianTracker")
    return tracker_type


def solve_dataset(
    detections: Sequence[Detection],
    *,
    scale: Scale,
    bounds: VoxelBounds,
    configuration: Any,
    max_search_radius: float,
    optimise: bool = False,
    optimizer_distance_units: str | None = None,
    tracker_factory: Callable[[], TrackerLike] | None = None,
) -> list[dict[str, object]]:
    """Run exactly one dataset in exactly one fresh tracker engine."""
    if not detections:
        raise AdapterError("cannot solve an empty dataset")
    if len({item.dataset for item in detections}) != 1:
        raise AdapterError("solve_dataset accepts exactly one dataset")
    btrack_search_radius = _positive_btrack_float(max_search_radius, "max_search_radius")
    if optimise and optimizer_distance_units != "physical":
        raise AdapterError(
            "optimise=True requires explicit optimizer_distance_units='physical'; "
            "BTrack optimiser thresholds must share the scaled coordinate units"
        )
    payload, ref_map = build_btrack_payload(detections, scale, bounds)
    factory = tracker_factory or load_pinned_tracker()
    tracker_obj = factory()
    # BTrack has a context manager that closes the native engine. Requiring the same
    # shape from injected fakes also prevents accidental engine reuse across datasets.
    with tracker_obj as tracker:
        tracker.configure(configuration)
        resolved_configuration = getattr(tracker, "configuration", None)
        features = getattr(resolved_configuration, "features", None)
        if isinstance(features, (str, bytes)) or not isinstance(features, Sequence):
            raise AdapterError("resolved BTrack configuration.features must be an inspectable sequence")
        reserved_features = sorted(RESERVED_ADAPTER_PROPERTIES.intersection(features))
        if reserved_features:
            raise AdapterError(
                "reserved adapter-only BTrack feature(s) are not allowed: "
                + ", ".join(reserved_features)
            )
        tracker.max_search_radius = btrack_search_radius
        tracker.volume = bounds.physical_btrack(scale)
        tracker.append(payload)
        tracker.track()
        if optimise:
            tracker.optimise()
        tracks = list(tracker.tracks)
        # Critical ordering: convert while refs/properties still reflect the live run.
        # Do not call HDF5FileHandler.write_tracks(list[Tracklet]) before this point.
        rows = tracks_to_rows(
            detections[0].dataset,
            detections,
            tracks,
            ref_map,
            scale,
            require_full_coverage=not optimise,
        )
        if optimise and not any(row["row_type"] == "node" for row in rows):
            raise AdapterError("optimisation retained no real observations for non-empty dataset")
        return rows


def solve_all(
    detections: Sequence[Detection],
    *,
    scale: Scale,
    bounds: VoxelBounds | Mapping[str, VoxelBounds],
    configuration: Any,
    max_search_radius: float,
    optimise: bool = False,
    optimizer_distance_units: str | None = None,
    tracker_factory: Callable[[], TrackerLike] | None = None,
) -> list[dict[str, object]]:
    if not detections:
        raise AdapterError("cannot solve an empty detection collection")
    rows: list[dict[str, object]] = []
    groups = group_detections(detections)
    if isinstance(bounds, Mapping):
        expected = set(groups)
        actual = set(bounds)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            details = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if extra:
                details.append("extra=" + ",".join(extra))
            raise AdapterError("bounds mapping must exactly match detection datasets (" + "; ".join(details) + ")")
    for dataset, items in groups.items():
        dataset_bounds = bounds[dataset] if isinstance(bounds, Mapping) else bounds
        rows.extend(
            solve_dataset(
                items,
                scale=scale,
                bounds=dataset_bounds,
                configuration=configuration,
                max_search_radius=max_search_radius,
                optimise=optimise,
                optimizer_distance_units=optimizer_distance_units,
                tracker_factory=tracker_factory,
            )
        )
    for row_id, row in enumerate(rows):
        row["id"] = row_id
    return [{key: row[key] for key in SUBMISSION_COLUMNS} for row in rows]


def write_submission(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    staging_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            staging_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=SUBMISSION_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row[key] for key in SUBMISSION_COLUMNS})
        staging_path.replace(path)
        staging_path = None
    except (csv.Error, KeyError, OSError) as exc:
        raise AdapterError(f"cannot write {path}: {exc}") from exc
    finally:
        if staging_path is not None:
            try:
                staging_path.unlink(missing_ok=True)
            except OSError:
                pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True, help="audited BTrack v0.7.0 configuration")
    parser.add_argument("--max-search-radius", type=float, required=True, help="physical distance")
    parser.add_argument("--scale-z", type=float, default=Scale.z)
    parser.add_argument("--scale-y", type=float, default=Scale.y)
    parser.add_argument("--scale-x", type=float, default=Scale.x)
    parser.add_argument("--bounds-csv", type=Path, help="exact per-dataset voxel-bounds manifest for multi-dataset runs")
    parser.add_argument("--zlo", type=float)
    parser.add_argument("--zhi", type=float)
    parser.add_argument("--ylo", type=float)
    parser.add_argument("--yhi", type=float)
    parser.add_argument("--xlo", type=float)
    parser.add_argument("--xhi", type=float)
    parser.add_argument("--optimise", action="store_true")
    parser.add_argument(
        "--optimizer-distance-units",
        choices=("physical",),
        help="required with --optimise; attests config distance thresholds use the same physical units",
    )
    args = parser.parse_args(argv)
    try:
        input_paths = [args.detections, args.config]
        if args.bounds_csv is not None:
            input_paths.append(args.bounds_csv)
        resolved_inputs = {input_path.resolve() for input_path in input_paths}
        output_path = args.output.resolve()
        if output_path in resolved_inputs:
            raise AdapterError("output must not overwrite any adapter input")
        for input_path in input_paths:
            try:
                aliases_input = args.output.samefile(input_path)
            except FileNotFoundError:
                aliases_input = False
            except OSError as exc:
                raise AdapterError(f"cannot verify output file identity: {exc}") from exc
            if aliases_input:
                raise AdapterError("output must not overwrite any adapter input")
        detections = read_detections(args.detections)
        datasets = sorted(group_detections(detections))
        scale = Scale(args.scale_z, args.scale_y, args.scale_x).validate()
        scalar_bounds = (args.zlo, args.zhi, args.ylo, args.yhi, args.xlo, args.xhi)
        if args.bounds_csv is not None:
            if any(value is not None for value in scalar_bounds):
                raise AdapterError("use either --bounds-csv or the six scalar bounds flags, not both")
            bounds: VoxelBounds | Mapping[str, VoxelBounds] = read_bounds_manifest(args.bounds_csv)
            if set(bounds) != set(datasets):
                missing = sorted(set(datasets) - set(bounds))
                extra = sorted(set(bounds) - set(datasets))
                details = []
                if missing:
                    details.append("missing=" + ",".join(missing))
                if extra:
                    details.append("extra=" + ",".join(extra))
                raise AdapterError("bounds manifest must exactly match detection datasets (" + "; ".join(details) + ")")
        else:
            if any(value is None for value in scalar_bounds):
                raise AdapterError("single-dataset CLI requires all six scalar bounds flags or --bounds-csv")
            if len(datasets) != 1:
                raise AdapterError("multi-dataset detections require --bounds-csv with one exact bounds row per dataset")
            zlo, zhi, ylo, yhi, xlo, xhi = scalar_bounds
            assert None not in scalar_bounds
            bounds = VoxelBounds(zlo, zhi, ylo, yhi, xlo, xhi).validate()
        rows = solve_all(
            detections,
            scale=scale,
            bounds=bounds,
            configuration=args.config,
            max_search_radius=args.max_search_radius,
            optimise=args.optimise,
            optimizer_distance_units=args.optimizer_distance_units,
        )
        write_submission(args.output, rows)
    except AdapterError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
