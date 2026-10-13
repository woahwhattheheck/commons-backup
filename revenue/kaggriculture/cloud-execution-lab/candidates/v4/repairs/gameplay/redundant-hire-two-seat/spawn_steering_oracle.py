#!/usr/bin/env python3
"""Source-bound HIRE spawn steering oracle for TITAN V4.

Research/default-OFF only. This module never changes HIRE count, wages, runtime
configuration, or returned actions. It certifies how same-callback unit movement
changes the deterministic location of a successful HIRE in the official engine.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
MOVES = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "WEST": (-1, 0),
    "EAST": (1, 0),
}
PASS = "PASS"


class Refusal(ValueError):
    """Fail-closed source/certificate refusal."""


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def authenticate_engine(data: bytes) -> str:
    blob = git_blob_id(data)
    if blob != ENGINE_GIT_BLOB:
        raise Refusal(f"engine Git blob drift: {blob}")
    return blob


def shed_access_tiles(board_size: int) -> tuple[tuple[int, int], ...]:
    if isinstance(board_size, bool) or not isinstance(board_size, int) or board_size < 2:
        raise Refusal("board_size must be an integer >= 2")
    h = board_size // 2
    return ((h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h))


def _point(value: Sequence[Any], board_size: int, name: str) -> tuple[int, int]:
    if isinstance(value, (str, bytes)) or len(value) != 2:
        raise Refusal(f"{name} must be [x,y]")
    x, y = value
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
        raise Refusal(f"{name} coordinates must be plain integers")
    if not (0 <= x < board_size and 0 <= y < board_size):
        raise Refusal(f"{name} out of bounds")
    return x, y


def occupancy_vector(positions: Sequence[Sequence[Any]], board_size: int = 10) -> tuple[int, int, int, int]:
    corners = shed_access_tiles(board_size)
    counts = Counter(_point(p, board_size, f"positions[{i}]") for i, p in enumerate(positions))
    return tuple(counts[c] for c in corners)


def spawn_index_from_occupancy(occupancy: Sequence[Any]) -> int:
    if len(occupancy) != 4:
        raise Refusal("occupancy must have four NW,NE,SW,SE counts")
    vals = []
    for i, n in enumerate(occupancy):
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise Refusal(f"occupancy[{i}] must be a nonnegative plain integer")
        vals.append(n)
    return min(range(4), key=lambda i: (vals[i], i))


def spawn_tile(positions: Sequence[Sequence[Any]], board_size: int = 10) -> tuple[int, int]:
    corners = shed_access_tiles(board_size)
    return corners[spawn_index_from_occupancy(occupancy_vector(positions, board_size))]


def minimal_occupancy_certificate(target: int) -> tuple[int, int, int, int]:
    """Canonical minimum-cardinality occupancy vector forcing a target corner.

    With target occupancy 0, every lexicographically earlier corner must be >0.
    Later corners may remain 0 because target wins the tie by earlier index.
    """
    if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < 4:
        raise Refusal("target must be an integer in [0,3]")
    return tuple(1 if i < target else 0 for i in range(4))


def certificate_forces_target(occupancy: Sequence[Any], target: int) -> bool:
    if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < 4:
        raise Refusal("target must be an integer in [0,3]")
    return spawn_index_from_occupancy(occupancy) == target


def apply_unit_moves(
    positions: Sequence[Sequence[Any]],
    actions: Sequence[Sequence[Any]],
    board_size: int = 10,
) -> tuple[tuple[int, int], ...]:
    """Apply only engine-equivalent movement/PASS effects for one unit phase.

    The caller must supply exactly one action per represented actor. This is an
    oracle, not an action generator: any farm operation is refused because it
    does not alter position and silently accepting arbitrary rows would hide
    malformed current-native evidence.
    """
    if len(positions) != len(actions):
        raise Refusal("positions/actions length mismatch")
    out: list[tuple[int, int]] = []
    for i, (pos, action) in enumerate(zip(positions, actions)):
        x, y = _point(pos, board_size, f"positions[{i}]")
        if isinstance(action, (str, bytes)) or not action:
            raise Refusal(f"actions[{i}] must be a nonempty sequence")
        op = action[0]
        if op == PASS:
            out.append((x, y))
            continue
        if op not in MOVES or len(action) != 1:
            raise Refusal(f"actions[{i}] must be PASS or one cardinal move")
        dx, dy = MOVES[op]
        nx, ny = x + dx, y + dy
        if 0 <= nx < board_size and 0 <= ny < board_size:
            x, y = nx, ny
        out.append((x, y))
    return tuple(out)


def certify_same_callback_steer(
    positions: Sequence[Sequence[Any]],
    actions: Sequence[Sequence[Any]],
    target: int,
    board_size: int = 10,
) -> dict[str, Any]:
    """Certify a supplied same-callback unit-move witness.

    It proves deterministic spawn location only. It does not prove the HIRE is
    funded, that a move is obligation-free, or that the new spawn improves EV.
    """
    corners = shed_access_tiles(board_size)
    before_occ = occupancy_vector(positions, board_size)
    after_positions = apply_unit_moves(positions, actions, board_size)
    after_occ = occupancy_vector(after_positions, board_size)
    baseline = spawn_index_from_occupancy(before_occ)
    steered = spawn_index_from_occupancy(after_occ)
    if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < 4:
        raise Refusal("target must be an integer in [0,3]")
    moved = sum(tuple(_point(p, board_size, f"positions[{i}]")) != after_positions[i]
                for i, p in enumerate(positions))
    return {
        "schema": "titan-v4-spawnsteer/v1",
        "decision_authority": False,
        "target_index": target,
        "target_tile": list(corners[target]),
        "baseline_index": baseline,
        "baseline_tile": list(corners[baseline]),
        "steered_index": steered,
        "steered_tile": list(corners[steered]),
        "changed_spawn": steered != baseline,
        "target_reached": steered == target,
        "moved_actors": moved,
        "before_occupancy": list(before_occ),
        "after_occupancy": list(after_occ),
        "after_positions": [list(p) for p in after_positions],
        "limits": [
            "successful HIRE funding/execution is not certified",
            "unit move opportunity cost and authored obligations are not certified",
            "new hand cannot act until the next callback because HIRE is market phase",
            "competitive/economic benefit is not certified",
        ],
    }


def source_report(engine: bytes) -> dict[str, Any]:
    blob = authenticate_engine(engine)
    certs = []
    for target in range(4):
        occ = minimal_occupancy_certificate(target)
        certs.append({
            "target_index": target,
            "occupancy": list(occ),
            "spawn_index": spawn_index_from_occupancy(occ),
            "existing_actors_required": sum(occ),
        })
    return {
        "schema": "titan-v4-spawnsteer/source-v1",
        "decision_authority": False,
        "engine_git_blob": blob,
        "shed_order": ["NW", "NE", "SW", "SE"],
        "minimal_zero_target_occupancy_certificates": certs,
        "phase_contract": "unit actions mutate actor positions before market HIRE calls _spawn_hand; a hired hand first appears for later callbacks",
    }


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--engine", required=True)
    p.add_argument("--pretty", action="store_true")
    args = p.parse_args()
    print(json.dumps(source_report(Path(args.engine).read_bytes()), sort_keys=True,
                     indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
