# SPDX-License-Identifier: Apache-2.0
"""Exact Kaggriculture game-grid loading."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from gate_common import (
    CellKey, Game, GateError, MAX_JSONL_BYTES, finite_number, is_int,
    regular_file, strict_loads,
)


def expected_keys(contract: Mapping[str, Any]) -> set[CellKey]:
    return {
        CellKey(opponent, seed, seat)
        for opponent in contract["opponents"]
        for seed in contract["seeds"]
        for seat in contract["seats"]
    }


def load_games(path: Path, *, label: str, expected: set[CellKey]) -> dict[CellKey, Game]:
    path = regular_file(path, max_bytes=MAX_JSONL_BYTES, label=label)
    rows: dict[CellKey, Game] = {}
    seen: set[CellKey] = set()
    failures: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            obj = strict_loads(raw, label=f"{label} line {line_number}")
            if not isinstance(obj, dict):
                raise GateError(f"{label} line {line_number}: row must be an object")
            opponent, seed, seat = obj.get("opponent"), obj.get("seed"), obj.get("candidate_seat")
            if not isinstance(opponent, str) or not opponent:
                raise GateError(f"{label} line {line_number}: invalid opponent")
            if not is_int(seed):
                raise GateError(f"{label} line {line_number}: invalid seed")
            if not is_int(seat) or seat not in (0, 1):
                raise GateError(f"{label} line {line_number}: candidate_seat must be 0 or 1")
            key = CellKey(opponent, seed, seat)
            if key in seen:
                raise GateError(f"{label}: duplicate cell {key.as_list()} at line {line_number}")
            seen.add(key)
            if key not in expected:
                raise GateError(f"{label}: extra cell {key.as_list()} at line {line_number}")
            if obj.get("status") != "complete":
                failures.append({
                    "key": key.as_list(), "line": line_number,
                    "status": obj.get("status"), "error": obj.get("error"),
                })
                continue
            scores = obj.get("scores")
            if not isinstance(scores, list) or len(scores) != 2:
                raise GateError(f"{label} line {line_number}: scores must have exactly two entries")
            rows[key] = Game(
                key,
                (
                    finite_number(scores[0], label=f"{label} line {line_number} scores[0]"),
                    finite_number(scores[1], label=f"{label} line {line_number} scores[1]"),
                ),
                line_number,
            )
    if not seen:
        raise GateError(f"{label}: no JSONL rows")
    if failures:
        raise GateError(f"{label}: non-complete cells: {json.dumps(failures, sort_keys=True)}")
    missing = sorted(expected - set(rows))
    if missing:
        raise GateError(f"{label}: missing {len(missing)} cells: {[key.as_list() for key in missing]}")
    return rows
