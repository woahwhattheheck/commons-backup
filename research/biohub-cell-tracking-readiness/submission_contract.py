"""Validation and deterministic CSV helpers for the Biohub cell-tracking competition.

This module is intentionally data-free and standard-library-only.  It validates the
public submission contract without importing or redistributing competition data.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

COLUMNS = (
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

NODE_SENTINEL_COLUMNS = ("source_id", "target_id")
EDGE_SENTINEL_COLUMNS = ("node_id", "t", "z", "y", "x")


class SubmissionError(ValueError):
    """Raised when a submission violates the public CSV/lineage contract."""


@dataclass(frozen=True)
class Node:
    dataset: str
    node_id: int
    t: int
    z: int
    y: int
    x: int


@dataclass(frozen=True)
class Edge:
    dataset: str
    source_id: int
    target_id: int


def _as_int(row: Mapping[str, str], key: str, row_number: int) -> int:
    raw = row.get(key, "")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise SubmissionError(f"row {row_number}: {key} must be an integer, got {raw!r}") from exc


def _parse_rows(rows: Sequence[Mapping[str, str]]) -> tuple[list[Node], list[Edge]]:
    nodes: list[Node] = []
    edges: list[Edge] = []
    seen_nodes: set[tuple[str, int]] = set()

    for position, row in enumerate(rows):
        row_number = position + 2  # header is line 1
        expected_id = position
        actual_id = _as_int(row, "id", row_number)
        if actual_id != expected_id:
            raise SubmissionError(
                f"row {row_number}: id must be consecutive from 0; expected {expected_id}, got {actual_id}"
            )

        dataset = row.get("dataset") or ""
        if dataset != dataset.strip():
            raise SubmissionError(f"row {row_number}: dataset must not contain leading or trailing whitespace")
        if not dataset:
            raise SubmissionError(f"row {row_number}: dataset must be non-empty")
        if dataset.endswith(".zarr"):
            raise SubmissionError(f"row {row_number}: dataset must omit the .zarr suffix")

        row_type = row.get("row_type") or ""
        if row_type != row_type.strip():
            raise SubmissionError(f"row {row_number}: row_type must not contain leading or trailing whitespace")
        if row_type == "node":
            node_id = _as_int(row, "node_id", row_number)
            t = _as_int(row, "t", row_number)
            z = _as_int(row, "z", row_number)
            y = _as_int(row, "y", row_number)
            x = _as_int(row, "x", row_number)
            if node_id < 0 or min(t, z, y, x) < 0:
                raise SubmissionError(f"row {row_number}: node values node_id,t,z,y,x must be non-negative")
            for key in NODE_SENTINEL_COLUMNS:
                if _as_int(row, key, row_number) != -1:
                    raise SubmissionError(f"row {row_number}: node {key} must be -1")
            node_key = (dataset, node_id)
            if node_key in seen_nodes:
                raise SubmissionError(f"row {row_number}: duplicate node_id {node_id} in dataset {dataset!r}")
            seen_nodes.add(node_key)
            nodes.append(Node(dataset, node_id, t, z, y, x))
        elif row_type == "edge":
            for key in EDGE_SENTINEL_COLUMNS:
                if _as_int(row, key, row_number) != -1:
                    raise SubmissionError(f"row {row_number}: edge {key} must be -1")
            source_id = _as_int(row, "source_id", row_number)
            target_id = _as_int(row, "target_id", row_number)
            if source_id < 0 or target_id < 0:
                raise SubmissionError(f"row {row_number}: edge source_id and target_id must be non-negative")
            if source_id == target_id:
                raise SubmissionError(f"row {row_number}: self-edge {source_id}->{target_id} is invalid")
            edges.append(Edge(dataset, source_id, target_id))
        else:
            raise SubmissionError(f"row {row_number}: row_type must be 'node' or 'edge', got {row_type!r}")

    return nodes, edges


def validate_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    expected_datasets: Iterable[str] | None = None,
    require_consecutive_edges: bool = True,
    strict_lineage: bool = True,
) -> dict[str, int]:
    """Validate rows and return compact counts.

    Consecutive t->t+1 edges are enforced by default because the organizer scorer
    filters non-consecutive links. ``strict_lineage=True`` additionally applies the
    Commons readiness policy: reject exact duplicate edges, multiple parents, and
    sources with more than two children. Set ``strict_lineage=False`` only when
    checking organizer-compatible graph ingestion/scoring behavior; structural,
    reference, sentinel, ID, and temporal checks remain active.
    """
    nodes, edges = _parse_rows(rows)
    node_map = {(node.dataset, node.node_id): node for node in nodes}
    incoming: defaultdict[tuple[str, int], int] = defaultdict(int)
    outgoing: defaultdict[tuple[str, int], int] = defaultdict(int)
    seen_edges: set[tuple[str, int, int]] = set()

    for edge in edges:
        edge_key = (edge.dataset, edge.source_id, edge.target_id)
        is_duplicate = edge_key in seen_edges
        if is_duplicate and strict_lineage:
            raise SubmissionError(
                f"duplicate edge {edge.source_id}->{edge.target_id} in {edge.dataset!r}"
            )
        seen_edges.add(edge_key)

        src_key = (edge.dataset, edge.source_id)
        dst_key = (edge.dataset, edge.target_id)
        if src_key not in node_map:
            raise SubmissionError(f"edge references missing source node {edge.source_id} in {edge.dataset!r}")
        if dst_key not in node_map:
            raise SubmissionError(f"edge references missing target node {edge.target_id} in {edge.dataset!r}")
        src = node_map[src_key]
        dst = node_map[dst_key]
        if dst.t <= src.t:
            raise SubmissionError(
                f"edge {edge.source_id}->{edge.target_id} in {edge.dataset!r} must move forward in time"
            )
        if require_consecutive_edges and dst.t != src.t + 1:
            raise SubmissionError(
                f"edge {edge.source_id}->{edge.target_id} in {edge.dataset!r} must connect consecutive frames"
            )

        # Edge-Jaccard scoring deduplicates exact source->target pairs. Non-strict
        # mode also deduplicates them for Commons compact lineage counts, but
        # duplicate rows can still affect organizer division/fork topology.
        if is_duplicate:
            continue

        incoming[dst_key] += 1
        outgoing[src_key] += 1
        if strict_lineage and incoming[dst_key] > 1:
            raise SubmissionError(f"node {edge.target_id} in {edge.dataset!r} has more than one parent")
        if strict_lineage and outgoing[src_key] > 2:
            raise SubmissionError(f"node {edge.source_id} in {edge.dataset!r} has more than two children")

    present = {node.dataset for node in nodes} | {edge.dataset for edge in edges}
    if expected_datasets is not None:
        expected = {name.strip().removesuffix(".zarr") for name in expected_datasets if name.strip()}
        missing = sorted(expected - present)
        unexpected = sorted(present - expected)
        if missing:
            raise SubmissionError(f"submission is missing datasets: {', '.join(missing)}")
        if unexpected:
            raise SubmissionError(f"submission contains unexpected datasets: {', '.join(unexpected)}")

    return {
        "rows": len(rows),
        "nodes": len(nodes),
        "edges": len(edges),
        "datasets": len(present),
        "divisions": sum(1 for degree in outgoing.values() if degree == 2),
    }


def read_submission(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise SubmissionError(f"CSV header must exactly equal {','.join(COLUMNS)}")
        return list(reader)


def validate_submission(
    path: Path,
    *,
    expected_datasets: Iterable[str] | None = None,
    require_consecutive_edges: bool = True,
    strict_lineage: bool = True,
) -> dict[str, int]:
    return validate_rows(
        read_submission(path),
        expected_datasets=expected_datasets,
        require_consecutive_edges=require_consecutive_edges,
        strict_lineage=strict_lineage,
    )


def write_submission(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        item = {key: row[key] for key in COLUMNS if key != "id"}
        item["id"] = index
        normalized.append({key: item[key] for key in COLUMNS})

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(normalized)


def _load_expected(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Biohub submission.csv without loading competition data")
    parser.add_argument("submission", type=Path)
    parser.add_argument("--expected-datasets", type=Path, help="newline-delimited dataset names")
    parser.add_argument(
        "--strict-consecutive",
        action="store_true",
        default=True,
        help="require every edge to connect t to t+1 (default; flag retained for compatibility)",
    )
    policy = parser.add_mutually_exclusive_group()
    policy.add_argument(
        "--strict-lineage",
        dest="strict_lineage",
        action="store_true",
        default=True,
        help="apply conservative duplicate/parent/child lineage guards (default)",
    )
    policy.add_argument(
        "--organizer-compatible",
        dest="strict_lineage",
        action="store_false",
        help="allow organizer-ingestible duplicate/merge/high-outdegree graph shapes; structural and t->t+1 checks remain",
    )
    args = parser.parse_args()
    counts = validate_submission(
        args.submission,
        expected_datasets=_load_expected(args.expected_datasets),
        require_consecutive_edges=args.strict_consecutive,
        strict_lineage=args.strict_lineage,
    )
    print("PASS " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
