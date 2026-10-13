#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed candidate-custody gate for exact TITAN paired ledgers.

The existing ``titan_regression_gate.compare_ledgers`` compares exact
engine/seed/opponent/seat cells.  This front gate closes two provenance gaps
before delegating to that comparator:

* every completed row must name the candidate archive that produced it, and
  that digest must equal the ledger-level candidate archive digest;
* every engine/seed/opponent matchup must contain both candidate seats 0 and 1.

It also binds the declared game count and schedule digest, validates SHA-256
syntax, and refuses contradictory score/margin evidence.  It never runs games,
changes a controller, estimates leaderboard score, or promotes an archive.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping, Sequence

from titan_regression_gate import GateError, compare_ledgers as _base_compare_ledgers


SCHEMA = "titan-paired-regression-ledger/v2"
COMPLETE_STATUSES = frozenset({"DONE", "COMPLETE", "COMPLETED", "PASS"})
EXPECTED_SEATS = frozenset({0, 1})


class PairedLedgerError(ValueError):
    """Raised when ledger custody or paired-panel topology is not exact."""


@dataclass(frozen=True, order=True)
class ScheduleKey:
    engine_sha256: str
    environment_seed: int
    opponent_sha256: str
    seat: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine_sha256": self.engine_sha256,
            "environment_seed": self.environment_seed,
            "opponent_sha256": self.opponent_sha256,
            "seat": self.seat,
        }


@dataclass(frozen=True)
class ParsedLedger:
    archive_sha256: str
    cells: Mapping[ScheduleKey, float]
    schedule_sha256: str
    matchup_pairs: int


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PairedLedgerError(f"{where} must be an object")
    return value


def _sequence(value: Any, where: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise PairedLedgerError(f"{where} must be an array")
    return value


def _sha256(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise PairedLedgerError(f"{where} must be a lowercase 64-hex SHA-256")
    value = value.strip()
    if len(value) != 64 or value != value.lower() or any(c not in "0123456789abcdef" for c in value):
        raise PairedLedgerError(f"{where} must be a lowercase 64-hex SHA-256")
    return value


def _nonnegative_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PairedLedgerError(f"{where} must be a nonnegative integer")
    return value


def _finite_number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PairedLedgerError(f"{where} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise PairedLedgerError(f"{where} must be finite")
    return value


def _ledger_archive_sha(ledger: Mapping[str, Any], label: str) -> str:
    if "archive_sha256" in ledger:
        return _sha256(ledger["archive_sha256"], f"{label}.archive_sha256")
    archive = ledger.get("archive")
    if isinstance(archive, Mapping):
        return _sha256(archive.get("sha256"), f"{label}.archive.sha256")
    raise PairedLedgerError(f"{label} must include archive_sha256 or archive.sha256")


def _row_archive_sha(row: Mapping[str, Any], where: str) -> str:
    if "candidate_archive_sha256" in row:
        return _sha256(row["candidate_archive_sha256"], f"{where}.candidate_archive_sha256")
    candidate = row.get("candidate_archive")
    if isinstance(candidate, Mapping):
        return _sha256(candidate.get("sha256"), f"{where}.candidate_archive.sha256")
    raise PairedLedgerError(
        f"{where} must include candidate_archive_sha256 or candidate_archive.sha256"
    )


def _margin(row: Mapping[str, Any], where: str) -> float:
    has_candidate = "candidate_score" in row
    has_opponent = "opponent_score" in row
    if has_candidate != has_opponent:
        raise PairedLedgerError(
            f"{where} must provide candidate_score and opponent_score together"
        )

    derived: float | None = None
    if has_candidate:
        derived = _finite_number(row["candidate_score"], f"{where}.candidate_score") - _finite_number(
            row["opponent_score"], f"{where}.opponent_score"
        )

    if "margin" not in row:
        if derived is None:
            raise PairedLedgerError(
                f"{where} must include margin or candidate_score + opponent_score"
            )
        return derived

    explicit = _finite_number(row["margin"], f"{where}.margin")
    if derived is not None and not math.isclose(explicit, derived, rel_tol=0.0, abs_tol=1e-9):
        raise PairedLedgerError(
            f"{where}.margin contradicts candidate_score - opponent_score"
        )
    return explicit


def canonical_schedule(keys: Iterable[ScheduleKey]) -> list[dict[str, Any]]:
    """Return the comparison schedule in deterministic wire order."""
    return [key.as_dict() for key in sorted(keys)]


def schedule_sha256(keys: Iterable[ScheduleKey]) -> str:
    encoded = json.dumps(
        canonical_schedule(keys),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_matchup_pairs(cells: Mapping[ScheduleKey, float], label: str) -> int:
    seats: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for key in cells:
        seats[(key.engine_sha256, key.environment_seed, key.opponent_sha256)].add(key.seat)

    broken = [
        {
            "engine_sha256": engine,
            "environment_seed": seed,
            "opponent_sha256": opponent,
            "seats": sorted(actual),
        }
        for (engine, seed, opponent), actual in sorted(seats.items())
        if actual != EXPECTED_SEATS
    ]
    if broken:
        raise PairedLedgerError(
            f"{label} has incomplete two-seat matchup pairs: "
            + json.dumps(broken, sort_keys=True, separators=(",", ":"))
        )
    return len(seats)


def validate_ledger(ledger: Mapping[str, Any], label: str) -> ParsedLedger:
    """Validate candidate custody, schedule identity, and exact two-seat closure."""
    ledger = _mapping(ledger, label)
    if ledger.get("schema") != SCHEMA:
        raise PairedLedgerError(f"{label}.schema must equal {SCHEMA!r}")

    archive_sha = _ledger_archive_sha(ledger, label)
    rows = _sequence(ledger.get("rows"), f"{label}.rows")
    if not rows:
        raise PairedLedgerError(f"{label}.rows must be nonempty")

    games = _nonnegative_int(ledger.get("games"), f"{label}.games")
    if games != len(rows):
        raise PairedLedgerError(
            f"{label}.games={games} does not equal rows={len(rows)}"
        )

    top_engine = ledger.get("engine_sha256")
    if top_engine is not None:
        top_engine = _sha256(top_engine, f"{label}.engine_sha256")

    cells: dict[ScheduleKey, float] = {}
    for index, raw in enumerate(rows):
        where = f"{label}.rows[{index}]"
        row = _mapping(raw, where)
        status = str(row.get("status", "")).upper()
        if status not in COMPLETE_STATUSES:
            raise PairedLedgerError(f"{where}.status is not complete: {status or '<missing>'}")
        for failure_field in ("error", "timeout", "timed_out"):
            if row.get(failure_field):
                raise PairedLedgerError(f"{where} reports {failure_field}")

        row_archive = _row_archive_sha(row, where)
        if row_archive != archive_sha:
            raise PairedLedgerError(
                f"{where} candidate archive {row_archive} does not match "
                f"{label} archive {archive_sha}"
            )

        engine_value = row.get("engine_sha256", top_engine)
        engine = _sha256(engine_value, f"{where}.engine_sha256")
        if top_engine is not None and engine != top_engine:
            raise PairedLedgerError(
                f"{where}.engine_sha256 does not match {label}.engine_sha256"
            )
        seed = _nonnegative_int(
            row.get("environment_seed", row.get("seed")),
            f"{where}.environment_seed",
        )
        opponent = _sha256(
            row.get("opponent_sha256", row.get("opponent_archive_sha256")),
            f"{where}.opponent_sha256",
        )
        seat = row.get("seat", row.get("candidate_seat"))
        if isinstance(seat, bool) or not isinstance(seat, int) or seat not in EXPECTED_SEATS:
            raise PairedLedgerError(f"{where}.seat must be exactly 0 or 1")

        key = ScheduleKey(engine, seed, opponent, seat)
        if key in cells:
            raise PairedLedgerError(
                f"{label} has duplicate comparison cell "
                + json.dumps(key.as_dict(), sort_keys=True, separators=(",", ":"))
            )
        cells[key] = _margin(row, where)

    actual_schedule_sha = schedule_sha256(cells)
    declared_schedule_sha = _sha256(
        ledger.get("schedule_sha256"), f"{label}.schedule_sha256"
    )
    if declared_schedule_sha != actual_schedule_sha:
        raise PairedLedgerError(
            f"{label}.schedule_sha256 mismatch: declared={declared_schedule_sha} "
            f"actual={actual_schedule_sha}"
        )

    matchup_pairs = _validate_matchup_pairs(cells, label)
    return ParsedLedger(
        archive_sha256=archive_sha,
        cells=cells,
        schedule_sha256=actual_schedule_sha,
        matchup_pairs=matchup_pairs,
    )


def _strata(
    left: ParsedLedger,
    right: ParsedLedger,
) -> dict[str, Any]:
    deltas = {
        key: right.cells[key] - left.cells[key]
        for key in sorted(left.cells)
    }
    by_seat: dict[int, list[float]] = defaultdict(list)
    by_opponent_seat: dict[tuple[str, int], list[float]] = defaultdict(list)
    for key, delta in deltas.items():
        by_seat[key.seat].append(delta)
        by_opponent_seat[(key.opponent_sha256, key.seat)].append(delta)

    def summary(values: Sequence[float]) -> dict[str, Any]:
        return {
            "cells": len(values),
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "minimum": min(values),
            "maximum": max(values),
            "sum": math.fsum(values),
            "right_better": sum(value > 0 for value in values),
            "tie": sum(value == 0 for value in values),
            "right_worse": sum(value < 0 for value in values),
        }

    return {
        "by_seat": {
            str(seat): summary(values)
            for seat, values in sorted(by_seat.items())
        },
        "by_opponent_seat": [
            {
                "opponent_sha256": opponent,
                "seat": seat,
                **summary(values),
            }
            for (opponent, seat), values in sorted(by_opponent_seat.items())
        ],
    }


def compare_paired_ledgers(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    """Run strict custody/pair checks, then delegate exact delta arithmetic."""
    left_parsed = validate_ledger(left, "left")
    right_parsed = validate_ledger(right, "right")

    blockers: list[dict[str, Any]] = []
    if left_parsed.archive_sha256 == right_parsed.archive_sha256:
        blockers.append({
            "code": "SAME_ARCHIVE",
            "message": "left and right name the same candidate archive",
            "archive_sha256": left_parsed.archive_sha256,
        })
    if left_parsed.schedule_sha256 != right_parsed.schedule_sha256:
        only_left = sorted(set(left_parsed.cells) - set(right_parsed.cells))
        only_right = sorted(set(right_parsed.cells) - set(left_parsed.cells))
        blockers.append({
            "code": "PANEL_MISMATCH",
            "message": "strict comparison requires the identical exact two-seat schedule",
            "left_schedule_sha256": left_parsed.schedule_sha256,
            "right_schedule_sha256": right_parsed.schedule_sha256,
            "only_left": [key.as_dict() for key in only_left],
            "only_right": [key.as_dict() for key in only_right],
        })

    if blockers:
        return {
            "schema": "titan-paired-regression-comparison/v2",
            "verdict": "REFUSED",
            "left_archive_sha256": left_parsed.archive_sha256,
            "right_archive_sha256": right_parsed.archive_sha256,
            "blockers": blockers,
        }

    try:
        base = _base_compare_ledgers(left, right, require_identical_panel=True)
    except GateError as exc:
        raise PairedLedgerError(f"base comparator refused validated ledgers: {exc}") from exc
    if base.get("verdict") != "COMPARABLE":
        raise PairedLedgerError(
            "base comparator refused a firewall-validated panel: "
            + json.dumps(base.get("blockers", []), sort_keys=True, separators=(",", ":"))
        )

    return {
        **base,
        "schema": "titan-paired-regression-comparison/v2",
        "custody": {
            "candidate_archive_bound_per_row": True,
            "left_archive_sha256": left_parsed.archive_sha256,
            "right_archive_sha256": right_parsed.archive_sha256,
        },
        "panel": {
            "schedule_sha256": left_parsed.schedule_sha256,
            "cells": len(left_parsed.cells),
            "matchup_pairs": left_parsed.matchup_pairs,
            "required_seats": [0, 1],
            "complete_two_seat_pairs": True,
        },
        "strata": _strata(left_parsed, right_parsed),
    }


def _load(path: str | Path) -> Mapping[str, Any]:
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PairedLedgerError(f"missing ledger: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PairedLedgerError(f"invalid JSON in {path}: {exc}") from exc
    return _mapping(value, str(path))


def _write(report: Mapping[str, Any], target: str | None) -> None:
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if target:
        Path(target).write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--report-json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = compare_paired_ledgers(_load(args.left), _load(args.right))
        _write(report, args.report_json)
        return 0 if report["verdict"] == "COMPARABLE" else 3
    except PairedLedgerError as exc:
        _write({
            "schema": "titan-paired-regression-comparison/v2",
            "verdict": "REFUSED",
            "error": str(exc),
        }, args.report_json)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
