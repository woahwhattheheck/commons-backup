# SPDX-License-Identifier: Apache-2.0
"""Fail-closed custody checks for the immutable historical L01 panel."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ci_support import git_blob_id

_REQUIRED_FIELDS = {
    "opponent",
    "seed",
    "candidate_seat",
    "status",
    "scores",
    "failure",
}


def _inspect_jsonl(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if not payload:
        raise ValueError(f"historical panel is empty: {path}")
    if not payload.endswith(b"\n"):
        raise ValueError(f"historical panel lacks final newline: {path}")

    keys: set[tuple[str, int, int]] = set()
    row_count = 0
    for line_number, raw in enumerate(payload.splitlines(), 1):
        if not raw.strip():
            raise ValueError(f"blank historical row at {path}:{line_number}")
        try:
            row = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"invalid historical JSON at {path}:{line_number}"
            ) from error
        if not isinstance(row, dict) or set(row) != _REQUIRED_FIELDS:
            raise ValueError(
                f"historical row shape drift at {path}:{line_number}"
            )
        opponent = row["opponent"]
        seed = row["seed"]
        seat = row["candidate_seat"]
        scores = row["scores"]
        if not isinstance(opponent, str) or not opponent:
            raise ValueError(f"invalid opponent at {path}:{line_number}")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"invalid seed at {path}:{line_number}")
        if isinstance(seat, bool) or seat not in (0, 1):
            raise ValueError(f"invalid candidate seat at {path}:{line_number}")
        if row["status"] != "complete" or row["failure"] is not None:
            raise ValueError(f"incomplete historical row at {path}:{line_number}")
        if not isinstance(scores, list) or len(scores) != 2:
            raise ValueError(f"invalid scores at {path}:{line_number}")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in scores
        ):
            raise ValueError(f"non-finite score at {path}:{line_number}")
        key = (opponent, seed, seat)
        if key in keys:
            raise ValueError(f"duplicate historical cell at {path}:{line_number}: {key}")
        keys.add(key)
        row_count += 1

    return {
        "path": path.name,
        "bytes": len(payload),
        "rows": row_count,
        "git_blob": git_blob_id(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "keys": keys,
    }


def verify_historical_pair(
    directory: Path, historical_pin: dict[str, Any]
) -> dict[str, Any]:
    """Verify exact bytes, shape, cardinality, and paired grid; persist receipt."""
    expected_rows = int(historical_pin["expected_rows_per_arm"])
    if expected_rows <= 0:
        raise ValueError("expected_rows_per_arm must be positive")

    specs = {
        "baseline": (
            directory / "canonical.GAMES.jsonl",
            historical_pin["baseline_games_git_blob"],
            historical_pin["baseline_games_sha256"],
        ),
        "candidate": (
            directory / "land.GAMES.jsonl",
            historical_pin["land_games_git_blob"],
            historical_pin["land_games_sha256"],
        ),
    }
    inspected: dict[str, dict[str, Any]] = {}
    for role, (path, expected_blob, expected_sha256) in specs.items():
        actual = _inspect_jsonl(path)
        if actual["git_blob"] != expected_blob:
            raise ValueError(
                f"{role} historical Git blob drifted: "
                f"{actual['git_blob']} != {expected_blob}"
            )
        if actual["sha256"] != expected_sha256:
            raise ValueError(
                f"{role} historical SHA-256 drifted: "
                f"{actual['sha256']} != {expected_sha256}"
            )
        if actual["rows"] != expected_rows:
            raise ValueError(
                f"{role} historical row count drifted: "
                f"{actual['rows']} != {expected_rows}"
            )
        inspected[role] = actual

    if inspected["baseline"]["keys"] != inspected["candidate"]["keys"]:
        missing = sorted(
            inspected["baseline"]["keys"] - inspected["candidate"]["keys"]
        )
        extra = sorted(
            inspected["candidate"]["keys"] - inspected["baseline"]["keys"]
        )
        raise ValueError(
            f"historical paired grid drifted: missing={missing[:3]!r} "
            f"extra={extra[:3]!r}"
        )

    receipt = {
        "schema": "titan-v3-l01-historical-provenance-v1",
        "source_head": historical_pin["head_commit"],
        "source_pull_request": historical_pin["pull_request"],
        "rows_per_arm": expected_rows,
        "paired_cells": expected_rows,
        "baseline": {
            key: value
            for key, value in inspected["baseline"].items()
            if key != "keys"
        },
        "candidate": {
            key: value
            for key, value in inspected["candidate"].items()
            if key != "keys"
        },
    }
    (directory / "PROVENANCE.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
