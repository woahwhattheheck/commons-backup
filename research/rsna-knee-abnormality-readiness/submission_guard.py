#!/usr/bin/env python3
"""Data-free submission validation and local scoring for RSNA Knee Abnormality Detection.

This module intentionally uses only the Python standard library and contains no
competition data. It validates the public submission contract and can score
local/synthetic labels with macro-averaged ROC AUC.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ID_COLUMN = "StudyInstanceUID"
TARGET_COLUMNS = (
    "ACL",
    "MCL",
    "Medial Meniscus",
    "Lateral Meniscus",
    "Medial OA",
    "Lateral OA",
    "PF OA",
    "Effusion",
    "Synovitis",
    "Baker's",
    "Contusion",
    "Fracture",
)
SUBMISSION_COLUMNS = (ID_COLUMN, *TARGET_COLUMNS)
NOTEBOOK_RUNTIME_LIMIT_SECONDS = 9 * 60 * 60


class ContractError(ValueError):
    """Raised when local files violate the public competition contract."""


@dataclass(frozen=True)
class SubmissionSummary:
    rows: int
    ids: tuple[str, ...]


def _as_probability(raw: str, *, row_number: int, column: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ContractError(
            f"row {row_number}: {column!r} must be a numeric probability"
        ) from exc
    if not math.isfinite(value):
        raise ContractError(f"row {row_number}: {column!r} must be finite")
    if not 0.0 <= value <= 1.0:
        raise ContractError(
            f"row {row_number}: {column!r}={value!r} is outside [0, 1]"
        )
    return value


def _read_csv(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError(f"{path}: missing CSV header")
        fieldnames = list(reader.fieldnames)
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def validate_submission(
    submission_path: str | Path,
    *,
    expected_ids: Iterable[str] | None = None,
) -> SubmissionSummary:
    """Validate exact header, unique IDs, finite probabilities, and optional ID set."""

    fieldnames, rows = _read_csv(submission_path)
    if tuple(fieldnames) != SUBMISSION_COLUMNS:
        raise ContractError(
            "submission header mismatch; expected exactly: "
            + ",".join(SUBMISSION_COLUMNS)
        )
    if not rows:
        raise ContractError("submission must contain at least one prediction row")

    seen: set[str] = set()
    ids: list[str] = []
    for row_number, row in enumerate(rows, start=2):
        uid = (row.get(ID_COLUMN) or "").strip()
        if not uid:
            raise ContractError(f"row {row_number}: {ID_COLUMN} must be non-empty")
        if uid in seen:
            raise ContractError(f"row {row_number}: duplicate {ID_COLUMN} {uid!r}")
        seen.add(uid)
        ids.append(uid)
        for column in TARGET_COLUMNS:
            _as_probability(
                row.get(column, ""),
                row_number=row_number,
                column=column,
            )

    if expected_ids is not None:
        expected = list(expected_ids)
        expected_set = set(expected)
        if len(expected_set) != len(expected):
            raise ContractError("expected ID source contains duplicate StudyInstanceUIDs")
        actual_set = set(ids)
        missing = sorted(expected_set - actual_set)
        unexpected = sorted(actual_set - expected_set)
        if missing or unexpected:
            pieces = []
            if missing:
                pieces.append(f"missing IDs={missing[:5]!r}")
            if unexpected:
                pieces.append(f"unexpected IDs={unexpected[:5]!r}")
            raise ContractError("submission ID set mismatch: " + "; ".join(pieces))

    return SubmissionSummary(rows=len(rows), ids=tuple(ids))


def load_expected_ids(test_csv_path: str | Path) -> tuple[str, ...]:
    """Read the public test.csv contract without requiring any private fields."""

    fieldnames, rows = _read_csv(test_csv_path)
    if ID_COLUMN not in fieldnames:
        raise ContractError(f"{test_csv_path}: missing {ID_COLUMN} column")
    ids: list[str] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        uid = (row.get(ID_COLUMN) or "").strip()
        if not uid:
            raise ContractError(f"row {row_number}: {ID_COLUMN} must be non-empty")
        if uid in seen:
            raise ContractError(
                f"row {row_number}: duplicate {ID_COLUMN} {uid!r} in test CSV"
            )
        seen.add(uid)
        ids.append(uid)
    if not ids:
        raise ContractError("test CSV must contain at least one StudyInstanceUID")
    return tuple(ids)


def _rank_average_ties(values: Sequence[float]) -> list[float]:
    """Return 1-based ranks with tied values receiving their average rank."""

    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        current_value = values[order[cursor]]
        while end < len(order) and values[order[end]] == current_value:
            end += 1
        average_rank = ((cursor + 1) + end) / 2.0
        for offset in range(cursor, end):
            ranks[order[offset]] = average_rank
        cursor = end
    return ranks


def binary_roc_auc(labels: Sequence[int], scores: Sequence[float]) -> float:
    """Compute ROC AUC via rank statistics, including deterministic tie handling."""

    if len(labels) != len(scores):
        raise ContractError("labels and scores must have the same number of rows")
    if not labels:
        raise ContractError("cannot score an empty target")
    if any(label not in (0, 1) for label in labels):
        raise ContractError("labels must contain only 0 or 1")
    if any(not math.isfinite(score) for score in scores):
        raise ContractError("scores must be finite")
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise ContractError("ROC AUC requires at least one positive and one negative")

    ranks = _rank_average_ties(scores)
    positive_rank_sum = sum(rank for rank, label in zip(ranks, labels) if label == 1)
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def macro_auc(
    labels: Mapping[str, Sequence[int]],
    predictions: Mapping[str, Sequence[float]],
) -> float:
    """Average AUC equally across the twelve public target labels."""

    aucs: list[float] = []
    for column in TARGET_COLUMNS:
        if column not in labels or column not in predictions:
            raise ContractError(f"missing target for scoring: {column!r}")
        aucs.append(binary_roc_auc(labels[column], predictions[column]))
    return sum(aucs) / len(aucs)


def validate_runtime(seconds: float) -> None:
    """Fail if a measured notebook runtime exceeds the public 9-hour ceiling."""

    if not math.isfinite(seconds) or seconds < 0:
        raise ContractError("runtime seconds must be finite and non-negative")
    if seconds > NOTEBOOK_RUNTIME_LIMIT_SECONDS:
        raise ContractError(
            f"runtime {seconds:.3f}s exceeds {NOTEBOOK_RUNTIME_LIMIT_SECONDS}s "
            "competition notebook ceiling"
        )


def _command_validate(args: argparse.Namespace) -> int:
    expected_ids = load_expected_ids(args.test_csv) if args.test_csv else None
    summary = validate_submission(args.submission, expected_ids=expected_ids)
    print(f"VALID rows={summary.rows} targets={len(TARGET_COLUMNS)}")
    return 0


def _command_runtime(args: argparse.Namespace) -> int:
    validate_runtime(args.seconds)
    remaining = NOTEBOOK_RUNTIME_LIMIT_SECONDS - args.seconds
    print(
        f"VALID runtime_seconds={args.seconds:.3f} "
        f"remaining_seconds={remaining:.3f}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate submission.csv")
    validate.add_argument("submission")
    validate.add_argument(
        "--test-csv",
        help="optional test.csv used only to verify exact StudyInstanceUID coverage",
    )
    validate.set_defaults(func=_command_validate)

    runtime = subparsers.add_parser("runtime", help="check measured notebook runtime")
    runtime.add_argument("seconds", type=float)
    runtime.set_defaults(func=_command_runtime)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ContractError as exc:
        print(f"INVALID: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
