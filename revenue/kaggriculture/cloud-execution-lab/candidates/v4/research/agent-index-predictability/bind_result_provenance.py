#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind TITAN result rows to exact candidate/engine/opponent artifact bytes.

This is a producer-side adapter for the provenance theorem already carried by
``titan_regression_gate.py`` (#11727).  It computes artifact digests from disk,
derives target-relative scores from engine-style ``rewards`` arrays, requires a
complete both-seat schedule, and emits a compatible ledger plus analyzer JSONL.

It deliberately does not impose a magnitude ceiling: large finite engine rewards
are valid.  Malformed/non-finite/contradictory inputs fail closed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any, Iterable, Mapping


class ProvenanceError(ValueError):
    """Raised when bytes or result rows cannot support a provenance claim."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _loads_strict(text: str, label: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ProvenanceError(f"{label}: invalid numeric constant {value}")
            ),
        )
    except ProvenanceError:
        raise
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"{label}: invalid JSON: {exc}") from exc


def _finite_number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProvenanceError(f"{label} must be a finite number")
    if isinstance(value, int):
        # Keep exact integer identity for provenance comparisons.  Conversion is
        # only a range probe so integers outside downstream floating capacity
        # continue to fail closed instead of becoming +/-inf later.
        try:
            finite_probe = float(value)
        except (OverflowError, ValueError) as exc:
            raise ProvenanceError(f"{label} must be finite") from exc
        if not math.isfinite(finite_probe):
            raise ProvenanceError(f"{label} must be finite")
        return value
    if not math.isfinite(value):
        raise ProvenanceError(f"{label} must be finite")
    return value


def _strict_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or type(value) is not int:
        raise ProvenanceError(f"{label} must be a literal integer")
    if minimum is not None and value < minimum:
        raise ProvenanceError(f"{label} must be >= {minimum}")
    return value


def _seed(value: Any, label: str) -> str:
    if isinstance(value, bool):
        raise ProvenanceError(f"{label} must be a non-bool integer or nonempty string")
    if type(value) is int:
        if value < 0:
            raise ProvenanceError(f"{label} must be nonnegative")
        return str(value)
    if isinstance(value, str) and value and value.strip() == value:
        return value
    raise ProvenanceError(f"{label} must be a non-bool integer or nonempty trimmed string")


@dataclass(frozen=True)
class Artifact:
    kind: str
    sha256: str
    bytes: int
    files: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "files": self.files,
        }


def _read_regular_stable(path: Path) -> bytes:
    """Read one regular file without following symlinks and reject mutation."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ProvenanceError(f"cannot safely open regular file: {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ProvenanceError(f"artifact member is not a regular file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise ProvenanceError(f"artifact member changed while being read: {path}")
    try:
        final = os.lstat(path)
    except OSError as exc:
        raise ProvenanceError(f"artifact member disappeared after read: {path}") from exc
    if stat.S_ISLNK(final.st_mode) or not stat.S_ISREG(final.st_mode):
        raise ProvenanceError(f"artifact member changed type after read: {path}")
    if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns) != identity_after:
        raise ProvenanceError(f"artifact member identity changed after read: {path}")
    return b"".join(chunks)


def digest_artifact(path: str | Path) -> Artifact:
    """Digest one regular file or a symlink-free directory tree deterministically."""
    root = Path(path)
    if root.is_symlink():
        raise ProvenanceError(f"artifact root must not be a symlink: {root}")
    if root.is_file():
        data = _read_regular_stable(root)
        return Artifact("file", _sha256(data), len(data), 1)
    if not root.is_dir():
        raise ProvenanceError(f"artifact path must be a regular file or directory: {root}")

    members: list[dict[str, Any]] = []
    total = 0
    for child in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if child.is_symlink():
            raise ProvenanceError(f"artifact tree contains symlink: {child}")
        if child.is_dir():
            continue
        if not child.is_file():
            raise ProvenanceError(f"artifact tree contains non-regular entry: {child}")
        rel = child.relative_to(root).as_posix()
        data = _read_regular_stable(child)
        size = len(data)
        total += size
        members.append({"path": rel, "bytes": size, "sha256": _sha256(data)})
    if not members:
        raise ProvenanceError(f"artifact directory is empty: {root}")
    payload = {"schema": "titan-artifact-tree/v1", "files": members}
    return Artifact("tree", _sha256(_canonical_json(payload)), total, len(members))


def _opponent_path(root: Path, relative: Any, index: int) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ProvenanceError(f"row {index} opponent_artifact must be a nonempty relative path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise ProvenanceError(f"row {index} opponent_artifact must be a canonical relative path")
    candidate = root.joinpath(*pure.parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ProvenanceError(f"row {index} opponent_artifact escapes opponent root") from exc
    return candidate


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = _loads_strict(line, f"line {lineno}")
        if not isinstance(value, dict):
            raise ProvenanceError(f"line {lineno}: expected JSON object")
        rows.append(value)
    if not rows:
        raise ProvenanceError("results JSONL contains no rows")
    return rows


def _derived_outcome(
    row: Mapping[str, Any], index: int
) -> tuple[int, int | float, int | float, int | float]:
    seat = _strict_int(row.get("seat"), f"row {index} seat")
    if seat not in (0, 1):
        raise ProvenanceError(f"row {index} seat must be literal 0 or 1")
    if row.get("status") != "DONE":
        raise ProvenanceError(f"row {index} status must be exactly DONE")
    if row.get("error") not in (None, "", False):
        raise ProvenanceError(f"row {index} carries an error")
    if row.get("timeout") not in (None, False):
        raise ProvenanceError(f"row {index} carries a timeout")

    rewards = row.get("rewards")
    if not isinstance(rewards, list) or len(rewards) != 2:
        raise ProvenanceError(f"row {index} rewards must be a two-item list")
    left = _finite_number(rewards[0], f"row {index} rewards[0]")
    right = _finite_number(rewards[1], f"row {index} rewards[1]")
    candidate = left if seat == 0 else right
    opponent = right if seat == 0 else left
    margin = _finite_number(candidate - opponent, f"row {index} derived margin")

    # These optional fields are assertions about the exact engine-derived
    # outcome, not alternative numerical estimates.  Relative tolerances are
    # unsafe without a trusted magnitude bound: at 1e20, rel_tol=1e-12 admits
    # tens of millions of absolute contradiction.
    if "candidate_score" in row and (
        _finite_number(row["candidate_score"], f"row {index} candidate_score") != candidate
    ):
        raise ProvenanceError(f"row {index} candidate_score contradicts rewards")
    if "opponent_score" in row and (
        _finite_number(row["opponent_score"], f"row {index} opponent_score") != opponent
    ):
        raise ProvenanceError(f"row {index} opponent_score contradicts rewards")
    if "margin" in row and _finite_number(row["margin"], f"row {index} margin") != margin:
        raise ProvenanceError(f"row {index} margin contradicts rewards")
    return seat, candidate, opponent, margin


def bind_results(
    *,
    candidate_path: str | Path,
    engine_path: str | Path,
    opponent_root: str | Path,
    rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Return (#11727-compatible ledger, analyzer rows, provenance receipt)."""
    candidate = digest_artifact(candidate_path)
    engine = digest_artifact(engine_path)
    opp_root = Path(opponent_root)
    if opp_root.is_symlink() or not opp_root.is_dir():
        raise ProvenanceError(f"opponent root must be a symlink-free directory: {opp_root}")

    opponent_cache: dict[str, Artifact] = {}
    ledger_rows: list[dict[str, Any]] = []
    analyzer_rows: list[dict[str, Any]] = []
    cells: set[tuple[str, str, int, int]] = set()
    pair_members: dict[tuple[str, str, int], set[int]] = {}

    for index, original in enumerate(rows):
        if not isinstance(original, Mapping):
            raise ProvenanceError(f"row {index} must be an object")
        row = dict(original)
        seed = _seed(row.get("environment_seed"), f"row {index} environment_seed")
        replicate_present = "replicate" in row
        replicate = _strict_int(row.get("replicate", 0), f"row {index} replicate", minimum=0)
        seat, candidate_score, opponent_score, margin = _derived_outcome(row, index)

        rel = row.get("opponent_artifact")
        opp_path = _opponent_path(opp_root, rel, index)
        rel_key = str(rel)
        if rel_key not in opponent_cache:
            opponent_cache[rel_key] = digest_artifact(opp_path)
        opponent = opponent_cache[rel_key]

        key = (seed, opponent.sha256, seat, replicate)
        if key in cells:
            raise ProvenanceError(
                f"duplicate result cell for seed={seed} opponent={opponent.sha256} "
                f"seat={seat} replicate={replicate}"
            )
        cells.add(key)
        pair_members.setdefault((seed, opponent.sha256, replicate), set()).add(seat)

        source_result_sha = _sha256(_canonical_json(row))
        ledger_seed = f"{seed}::replicate={replicate}" if replicate_present else seed
        ledger_row = {
            "environment_seed": ledger_seed,
            "opponent_sha256": opponent.sha256,
            "seat": seat,
            "candidate_score": candidate_score,
            "opponent_score": opponent_score,
            "status": "DONE",
            "source_result_sha256": source_result_sha,
        }
        if replicate_present:
            ledger_row["environment_seed_original"] = seed
            ledger_row["replicate"] = replicate
        ledger_rows.append(ledger_row)
        analyzer_rows.append(
            {
                "seed": ledger_seed,
                "opponent": opponent.sha256,
                "seat": seat,
                "margin": margin,
                "provenance": {
                    "candidate_sha256": candidate.sha256,
                    "engine_sha256": engine.sha256,
                    "opponent_sha256": opponent.sha256,
                    "source_result_sha256": source_result_sha,
                },
            }
        )

    incomplete = [
        {"seed": seed, "opponent_sha256": opp, "replicate": rep, "seats": sorted(seats)}
        for (seed, opp, rep), seats in sorted(pair_members.items())
        if seats != {0, 1}
    ]
    if incomplete:
        raise ProvenanceError(f"incomplete both-seat schedule: {incomplete}")

    ledger_rows.sort(
        key=lambda row: (str(row["environment_seed"]), row["opponent_sha256"], row["seat"])
    )
    analyzer_rows.sort(key=lambda row: (str(row["seed"]), row["opponent"], row["seat"]))

    ledger = {
        "schema_version": 1,
        "archive_sha256": candidate.sha256,
        "candidate_sha256": candidate.sha256,
        "engine_sha256": engine.sha256,
        "candidate_artifact": candidate.as_dict(),
        "engine_artifact": engine.as_dict(),
        "rows": ledger_rows,
    }
    identity_rows = [
        {
            "environment_seed": row["environment_seed"],
            "opponent_sha256": row["opponent_sha256"],
            "seat": row["seat"],
            "candidate_score": row["candidate_score"],
            "opponent_score": row["opponent_score"],
            "source_result_sha256": row["source_result_sha256"],
        }
        for row in ledger_rows
    ]
    panel_sha = _sha256(
        _canonical_json(
            {
                "candidate_sha256": candidate.sha256,
                "engine_sha256": engine.sha256,
                "rows": identity_rows,
            }
        )
    )
    margins = [abs(float(row["margin"])) for row in analyzer_rows]
    receipt = {
        "schema_version": 1,
        "verdict": "PASS",
        "candidate": candidate.as_dict(),
        "engine": engine.as_dict(),
        "opponents": [
            {"artifact": name, **artifact.as_dict()}
            for name, artifact in sorted(opponent_cache.items())
        ],
        "rows": len(ledger_rows),
        "paired_cells": len(pair_members),
        "panel_sha256": panel_sha,
        "max_abs_margin": max(margins, default=0.0),
        "score_ceiling_applied": False,
        "legacy_pair_key": ["engine_sha256", "environment_seed", "opponent_sha256", "seat"],
    }
    return ledger, analyzer_rows, receipt


def _write_json(path: str | Path, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    Path(path).write_text(
        "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, help="candidate file or directory to hash")
    parser.add_argument("--engine", required=True, help="engine file or directory to hash")
    parser.add_argument(
        "--opponent-root", required=True, help="root containing row opponent_artifact paths"
    )
    parser.add_argument("--results", required=True, help="JSONL engine result rows")
    parser.add_argument("--ledger-out", required=True, help="#11727-compatible ledger JSON")
    parser.add_argument("--analyzer-jsonl", required=True, help="analyze_agent_index.py input JSONL")
    parser.add_argument("--receipt-out", required=True, help="provenance receipt JSON")
    args = parser.parse_args(argv)
    try:
        rows = _read_jsonl(args.results)
        ledger, analyzer_rows, receipt = bind_results(
            candidate_path=args.candidate,
            engine_path=args.engine,
            opponent_root=args.opponent_root,
            rows=rows,
        )
        _write_json(args.ledger_out, ledger)
        _write_jsonl(args.analyzer_jsonl, analyzer_rows)
        _write_json(args.receipt_out, receipt)
    except (OSError, ProvenanceError) as exc:
        print(f"PROVENANCE BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(
        f"PROVENANCE PASS rows={receipt['rows']} pairs={receipt['paired_cells']} "
        f"panel={receipt['panel_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
