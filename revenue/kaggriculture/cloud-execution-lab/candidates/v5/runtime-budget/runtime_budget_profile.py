# SPDX-License-Identifier: Apache-2.0
"""Deterministic runtime-budget profiles for TITAN V5 callback receipts.

This module is deliberately outside the gameplay path. It consumes diagnostics
already emitted by ``titan_runtime`` and turns them into a fail-closed admission
receipt for stronger policies.

Each JSONL row must identify one returned callback::

    {"candidate":"v5c:...", "seed":7, "seat":0, "step":12,
     "diagnostics":{"status":"completed", "elapsed_seconds":0.013,
                    "act_cpu_seconds":0.011}}

Diagnostics may also be flat at the row top level. Duplicate callback identities,
malformed/non-finite timing values, and unknown statuses fail closed. Promotion
requires an explicit expected-key JSONL design; merely observing a fast subset
can never produce ``promotion_ready=true``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_ALLOWED_STATUS = frozenset(("completed", "deadline_fallback"))


class BudgetProfileError(ValueError):
    """Raised when callback timing evidence is malformed or ambiguous."""


def _plain_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise BudgetProfileError(f"{name} must be a plain int >= {minimum}")
    return value


def _finite_nonnegative_number(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise BudgetProfileError(f"{name} must be a finite nonnegative int or float")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise BudgetProfileError(f"{name} must be a finite nonnegative int or float")
    return result


def _positive_number(value: Any, name: str) -> float:
    result = _finite_nonnegative_number(value, name)
    if result <= 0:
        raise BudgetProfileError(f"{name} must be > 0")
    return result


def _identity(
    row: Mapping[str, Any],
    *,
    row_number: int | None = None,
    total_steps: int | None = None,
) -> tuple[str, int, int, int]:
    where = f"row {row_number}: " if row_number is not None else ""
    candidate = row.get("candidate")
    if type(candidate) is not str or not candidate:
        raise BudgetProfileError(f"{where}candidate must be a nonempty string")
    try:
        seed = _plain_int(row.get("seed"), "seed")
        seat = _plain_int(row.get("seat"), "seat")
        if seat not in (0, 1):
            raise BudgetProfileError("seat must be 0 or 1")
        step = _plain_int(row.get("step"), "step")
        if total_steps is not None and step >= total_steps:
            raise BudgetProfileError(f"step must be < total_steps ({total_steps})")
    except BudgetProfileError as exc:
        raise BudgetProfileError(where + str(exc)) from exc
    return candidate, seed, seat, step


def _receipt(
    row: Mapping[str, Any], *, row_number: int, total_steps: int
) -> dict[str, Any]:
    key = _identity(row, row_number=row_number, total_steps=total_steps)
    diagnostics = row.get("diagnostics", row)
    if not isinstance(diagnostics, Mapping):
        raise BudgetProfileError(f"row {row_number}: diagnostics must be an object")

    status = diagnostics.get("status")
    if status not in _ALLOWED_STATUS:
        raise BudgetProfileError(
            f"row {row_number}: status must be one of {sorted(_ALLOWED_STATUS)!r}"
        )
    try:
        elapsed = _finite_nonnegative_number(
            diagnostics.get("elapsed_seconds"), "elapsed_seconds"
        )
        cpu = _finite_nonnegative_number(
            diagnostics.get("act_cpu_seconds"), "act_cpu_seconds"
        )
    except BudgetProfileError as exc:
        raise BudgetProfileError(f"row {row_number}: {exc}") from exc

    fallback_stage = diagnostics.get("fallback_stage")
    if status == "deadline_fallback":
        if type(fallback_stage) is not str or not fallback_stage:
            raise BudgetProfileError(
                f"row {row_number}: deadline_fallback requires nonempty fallback_stage"
            )
    elif fallback_stage is not None and type(fallback_stage) is not str:
        raise BudgetProfileError(
            f"row {row_number}: fallback_stage must be a string or null"
        )

    return {
        "key": key,
        "candidate": key[0],
        "seed": key[1],
        "seat": key[2],
        "step": key[3],
        "status": status,
        "elapsed_seconds": elapsed,
        "act_cpu_seconds": cpu,
        "fallback_stage": fallback_stage,
    }


def _nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    """Return an exact nearest-rank percentile (ceil(p*n), 1-indexed)."""
    if not values:
        return None
    if not (0.0 < percentile <= 1.0):
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _timing_summary(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    wall = [float(row["elapsed_seconds"]) for row in receipts]
    cpu = [float(row["act_cpu_seconds"]) for row in receipts]

    def stats(values: Sequence[float]) -> dict[str, Any]:
        return {
            "p50": _nearest_rank(values, 0.50),
            "p95": _nearest_rank(values, 0.95),
            "p99": _nearest_rank(values, 0.99),
            "max": max(values) if values else None,
        }

    return {
        "count": len(receipts),
        "wall_seconds": stats(wall),
        "cpu_seconds": stats(cpu),
    }


def _phase(step: int, *, total_steps: int) -> str:
    first = total_steps // 3
    second = (2 * total_steps) // 3
    if step < first:
        return "early"
    if step < second:
        return "mid"
    return "late"


def _normalize_expected(
    rows: Iterable[Mapping[str, Any]] | None,
    *,
    total_steps: int,
) -> set[tuple[str, int, int, int]] | None:
    if rows is None:
        return None
    result: set[tuple[str, int, int, int]] = set()
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise BudgetProfileError(f"expected row {row_number} is not an object")
        key = _identity(row, row_number=row_number, total_steps=total_steps)
        if key in result:
            raise BudgetProfileError(f"duplicate expected callback identity: {key!r}")
        result.add(key)
    if not result:
        raise BudgetProfileError("expected callback design must not be empty")
    return result


def profile_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    budget_seconds: float,
    reserve_seconds: float = 0.0,
    max_fallback_rate: float = 0.0,
    expected_rows: Iterable[Mapping[str, Any]] | None = None,
    total_steps: int = 720,
) -> dict[str, Any]:
    """Profile callback receipts and return a deterministic admission report."""
    budget = _positive_number(budget_seconds, "budget_seconds")
    reserve = _finite_nonnegative_number(reserve_seconds, "reserve_seconds")
    if reserve >= budget:
        raise BudgetProfileError("reserve_seconds must be < budget_seconds")
    fallback_ceiling = _finite_nonnegative_number(
        max_fallback_rate, "max_fallback_rate"
    )
    if fallback_ceiling > 1.0:
        raise BudgetProfileError("max_fallback_rate must be <= 1")
    total = _plain_int(total_steps, "total_steps", minimum=1)

    expected = _normalize_expected(expected_rows, total_steps=total)
    receipts: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, int]] = set()
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise BudgetProfileError(f"row {row_number} is not an object")
        receipt = _receipt(row, row_number=row_number, total_steps=total)
        key = receipt["key"]
        if key in seen:
            raise BudgetProfileError(f"duplicate callback identity: {key!r}")
        seen.add(key)
        receipt["phase"] = _phase(receipt["step"], total_steps=total)
        receipts.append(receipt)

    if not receipts:
        raise BudgetProfileError("at least one callback receipt is required")

    usable = budget - reserve
    fallback_count = sum(row["status"] == "deadline_fallback" for row in receipts)
    fallback_rate = fallback_count / len(receipts)
    fallback_stages = Counter(
        row["fallback_stage"]
        for row in receipts
        if row["status"] == "deadline_fallback"
    )

    by_phase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in receipts:
        by_phase[row["phase"]].append(row)
        by_candidate[row["candidate"]].append(row)

    overall = _timing_summary(receipts)
    p99_wall = overall["wall_seconds"]["p99"]
    if p99_wall is None:
        raise BudgetProfileError("missing p99 timing after nonempty receipt set")

    missing: list[tuple[str, int, int, int]] = []
    extras: list[tuple[str, int, int, int]] = []
    if expected is not None:
        missing = sorted(expected - seen)
        extras = sorted(seen - expected)
    expected_complete = expected is not None and not missing and not extras
    promotion_ready = bool(
        expected_complete
        and fallback_rate <= fallback_ceiling
        and p99_wall <= usable
    )

    return {
        "classification": "PASS" if promotion_ready else "BLOCK",
        "promotion_ready": promotion_ready,
        "receipt_count": len(receipts),
        "candidate_count": len(by_candidate),
        "budget_seconds": budget,
        "reserve_seconds": reserve,
        "usable_budget_seconds": usable,
        "p99_headroom_seconds": usable - p99_wall,
        "max_fallback_rate": fallback_ceiling,
        "deadline_fallback_count": fallback_count,
        "deadline_fallback_rate": fallback_rate,
        "fallback_stage_counts": {
            str(key): fallback_stages[key] for key in sorted(fallback_stages)
        },
        "expected_design_declared": expected is not None,
        "expected_callback_count": len(expected) if expected is not None else None,
        "expected_complete": expected_complete,
        "missing_expected": [
            {"candidate": key[0], "seed": key[1], "seat": key[2], "step": key[3]}
            for key in missing
        ],
        "unexpected_extra": [
            {"candidate": key[0], "seed": key[1], "seat": key[2], "step": key[3]}
            for key in extras
        ],
        "overall": overall,
        "by_phase": {
            phase: _timing_summary(by_phase.get(phase, []))
            for phase in ("early", "mid", "late")
        },
        "by_candidate": {
            candidate: {
                **_timing_summary(candidate_rows),
                "deadline_fallback_count": sum(
                    row["status"] == "deadline_fallback" for row in candidate_rows
                ),
            }
            for candidate, candidate_rows in sorted(by_candidate.items())
        },
        "phase_contract": {
            "total_steps": total,
            "early": [0, total // 3],
            "mid": [total // 3, (2 * total) // 3],
            "late": [(2 * total) // 3, total],
        },
    }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BudgetProfileError(f"duplicate JSON object member: {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> Any:
    raise BudgetProfileError(f"non-standard JSON constant is not allowed: {value}")


def _read_jsonl(path: Path) -> Iterable[Mapping[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(
                    line,
                    object_pairs_hook=_strict_object,
                    parse_constant=_reject_nonstandard_constant,
                )
            except json.JSONDecodeError as exc:
                raise BudgetProfileError(
                    f"{path}:{line_number}: invalid JSON: {exc.msg}"
                ) from exc
            except BudgetProfileError as exc:
                raise BudgetProfileError(
                    f"{path}:{line_number}: invalid JSON: {exc}"
                ) from exc
            if not isinstance(row, Mapping):
                raise BudgetProfileError(f"{path}:{line_number}: row is not an object")
            yield row


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a fail-closed TITAN V5 callback runtime-budget profile."
    )
    parser.add_argument("jsonl", type=Path, help="callback receipt JSONL")
    parser.add_argument("--budget-seconds", type=float, required=True)
    parser.add_argument("--reserve-seconds", type=float, default=0.0)
    parser.add_argument("--max-fallback-rate", type=float, default=0.0)
    parser.add_argument(
        "--expected-jsonl",
        type=Path,
        help="declared callback identities; required for promotion_ready=true",
    )
    parser.add_argument("--total-steps", type=int, default=720)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        expected = (
            list(_read_jsonl(args.expected_jsonl)) if args.expected_jsonl else None
        )
        report = profile_rows(
            _read_jsonl(args.jsonl),
            budget_seconds=args.budget_seconds,
            reserve_seconds=args.reserve_seconds,
            max_fallback_rate=args.max_fallback_rate,
            expected_rows=expected,
            total_steps=args.total_steps,
        )
        payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if args.output:
            args.output.write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
    except (BudgetProfileError, OSError, ValueError) as exc:
        print(f"runtime_budget_profile: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
