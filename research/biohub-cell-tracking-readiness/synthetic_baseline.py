"""Tiny deterministic CPU baseline hook using synthetic sparse 3D+time frames.

The real competition loader is intentionally absent.  This script exercises the
geometry, linking, lineage and CSV path without any competition bytes.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

from submission_contract import validate_submission, write_submission

SCALE_UM = (1.625, 0.40625, 0.40625)  # z, y, x microns per voxel


@dataclass(frozen=True)
class Detection:
    t: int
    z: int
    y: int
    x: int
    intensity: int


def synthetic_frames() -> list[list[Detection]]:
    """Return two moving cells across four frames."""
    return [
        [Detection(0, 10, 30, 40, 1000), Detection(0, 20, 70, 80, 900)],
        [Detection(1, 10, 32, 42, 1005), Detection(1, 20, 69, 79, 905)],
        [Detection(2, 11, 34, 44, 1010), Detection(2, 20, 68, 78, 910)],
        [Detection(3, 11, 36, 46, 1015), Detection(3, 20, 67, 77, 915)],
    ]


def distance_um(a: Detection, b: Detection) -> float:
    dz = (a.z - b.z) * SCALE_UM[0]
    dy = (a.y - b.y) * SCALE_UM[1]
    dx = (a.x - b.x) * SCALE_UM[2]
    return math.sqrt(dz * dz + dy * dy + dx * dx)


def link_nearest(frames: list[list[Detection]], *, radius_um: float = 8.5) -> tuple[list[Detection], list[tuple[int, int]]]:
    """Deterministic one-to-one nearest-neighbour linker in physical units."""
    nodes: list[Detection] = []
    ids_by_frame: list[list[int]] = []
    for frame in frames:
        ids: list[int] = []
        for detection in sorted(frame, key=lambda d: (d.z, d.y, d.x, d.intensity)):
            ids.append(len(nodes))
            nodes.append(detection)
        ids_by_frame.append(ids)

    edges: list[tuple[int, int]] = []
    for frame_index in range(len(frames) - 1):
        available_targets = set(ids_by_frame[frame_index + 1])
        for source_id in ids_by_frame[frame_index]:
            source = nodes[source_id]
            ranked = sorted(
                (
                    (distance_um(source, nodes[target_id]), target_id)
                    for target_id in available_targets
                ),
                key=lambda item: (item[0], item[1]),
            )
            if ranked and ranked[0][0] <= radius_um:
                _, target_id = ranked[0]
                available_targets.remove(target_id)
                edges.append((source_id, target_id))
    return nodes, edges


def build_rows(dataset: str = "synthetic_embryo_0001") -> list[dict[str, object]]:
    nodes, edges = link_nearest(synthetic_frames())
    rows: list[dict[str, object]] = []
    for node_id, node in enumerate(nodes):
        rows.append(
            {
                "dataset": dataset,
                "row_type": "node",
                "node_id": node_id,
                "t": node.t,
                "z": node.z,
                "y": node.y,
                "x": node.x,
                "source_id": -1,
                "target_id": -1,
            }
        )
    for source_id, target_id in edges:
        rows.append(
            {
                "dataset": dataset,
                "row_type": "edge",
                "node_id": -1,
                "t": -1,
                "z": -1,
                "y": -1,
                "x": -1,
                "source_id": source_id,
                "target_id": target_id,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and validate a data-free synthetic Biohub submission")
    parser.add_argument("--output", type=Path, default=Path("submission.synthetic.csv"))
    args = parser.parse_args()
    write_submission(args.output, build_rows())
    counts = validate_submission(args.output, expected_datasets=["synthetic_embryo_0001"])
    print("PASS " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
