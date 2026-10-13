#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure target-agent seat/index predictability from matched game records.

The primary estimand is the within-(seed, opponent) margin change when the
target agent moves from seat 0 to seat 1.  This blocks opponent-mix and seed
difficulty from masquerading as a seat effect.  The report also includes an
equal-opponent average, an exact paired sign test, standardized effect size,
assignment total-variation distance, and matched-cell coverage.

This is an analysis tool only.  It does not alter gameplay or recommend
seat-dependent policy.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


class DataError(ValueError):
    """Input does not support a trustworthy matched-seat analysis."""


def _first(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in record:
            return record[name]
    raise DataError(f"missing any of fields {names!r}")


def _finite_number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError(f"{label} must be a finite number")
    if isinstance(value, int):
        # Preserve exact integer identity for redundant-outcome checks.  The
        # float conversion is validation only: integers too large for the
        # analyzer's downstream floating statistics still fail closed.
        try:
            finite_probe = float(value)
        except (OverflowError, ValueError):
            raise DataError(f"{label} must be finite")
        if not math.isfinite(finite_probe):
            raise DataError(f"{label} must be finite")
        return value
    if not math.isfinite(value):
        raise DataError(f"{label} must be finite")
    return value


def _authenticated_margin_bound(value: Any) -> int | float | None:
    """Validate an optional caller-authenticated absolute margin bound.

    There is deliberately no built-in game-score ceiling.  A bound is useful
    only when the caller can authenticate it from the producing engine or
    dataset contract.  Values outside the bound are rejected, never clipped,
    so the guard cannot manufacture a plausible-looking in-range outcome.
    """
    if value is None:
        return None
    result = _finite_number(value, "authenticated_max_abs_margin")
    if result <= 0:
        raise DataError("authenticated_max_abs_margin must be positive")
    return result


def _outcome_margin(record: dict[str, Any], index: int, seat: int) -> int | float:
    """Return one target-relative margin, rejecting contradictory encodings.

    Inputs sometimes carry more than one outcome representation.  A direct
    ``margin`` must never silently override contradictory engine-style
    ``rewards`` or ``score`` fields.  When redundant representations agree,
    prefer the more structured representation without imposing a guessed
    magnitude ceiling on legitimate engine rewards.
    """
    outcomes: dict[str, int | float] = {}

    if "margin" in record:
        outcomes["margin"] = _finite_number(record["margin"], f"record {index} margin")

    if "rewards" in record:
        rewards = record["rewards"]
        if not isinstance(rewards, list) or len(rewards) != 2:
            raise DataError(f"record {index}: rewards must be a two-item list")
        left = _finite_number(rewards[seat], f"record {index} target reward")
        right = _finite_number(rewards[1 - seat], f"record {index} opponent reward")
        outcomes["rewards"] = _finite_number(
            left - right, f"record {index} rewards-derived margin"
        )

    if "score" in record and "opponent_score" in record:
        outcomes["score+opponent_score"] = _finite_number(
            _finite_number(record["score"], f"record {index} score")
            - _finite_number(record["opponent_score"], f"record {index} opponent_score"),
            f"record {index} score-derived margin",
        )

    if not outcomes:
        raise DataError(
            f"record {index}: need margin, rewards[2], or score+opponent_score"
        )

    first_name, first_value = next(iter(outcomes.items()))
    for name, value in list(outcomes.items())[1:]:
        # This is a consistency/authentication check, not a numerical model.
        # A relative tolerance is unsafe without a magnitude bound: at 1e20,
        # rel_tol=1e-12 would silently accept tens of millions of disagreement.
        if first_value != value:
            raise DataError(
                f"record {index}: conflicting outcome representations "
                f"({first_name}={first_value!r}, {name}={value!r})"
            )

    for preferred in ("rewards", "score+opponent_score", "margin"):
        if preferred in outcomes:
            return outcomes[preferred]
    raise AssertionError("unreachable outcome representation state")


def normalize_record(
    record: Any,
    index: int,
    *,
    require_structured_outcome: bool = False,
    authenticated_max_abs_margin: int | float | None = None,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise DataError(f"record {index}: expected object")

    seed = _first(record, ("seed", "episode_seed", "game_seed"))
    if isinstance(seed, bool) or not isinstance(seed, (str, int)):
        raise DataError(f"record {index}: seed must be string/int")

    opponent = _first(record, ("opponent", "opponent_id", "opponent_name"))
    if isinstance(opponent, bool) or not isinstance(opponent, (str, int)):
        raise DataError(f"record {index}: opponent must be string/int")

    seat = _first(record, ("target_seat", "seat", "player_index", "agent_index", "player"))
    if isinstance(seat, bool) or type(seat) is not int or seat not in (0, 1):
        raise DataError(f"record {index}: target seat must be literal 0 or 1")

    if require_structured_outcome:
        has_rewards = "rewards" in record
        has_score_pair = "score" in record and "opponent_score" in record
        if not (has_rewards or has_score_pair):
            raise DataError(
                f"record {index}: structured outcome required; margin-only input is not accepted"
            )

    margin = _outcome_margin(record, index, seat)
    bound = _authenticated_margin_bound(authenticated_max_abs_margin)
    if bound is not None and abs(margin) > bound:
        raise DataError(
            f"record {index}: absolute margin {margin!r} exceeds authenticated bound {bound!r}"
        )

    # Keep the historical string report/key representation, but retain the
    # primitive provenance type until the dataset-level admission check below.
    # Without this custody, int 1 and str "1" silently collapse into one cell.
    return {
        "seed": str(seed),
        "seed_type": "int" if type(seed) is int else "str",
        "opponent": str(opponent),
        "opponent_type": "int" if type(opponent) is int else "str",
        "seat": seat,
        "margin": margin,
    }


def _sign_test_two_sided(diffs: list[int | float]) -> tuple[int, int, int, float]:
    positives = sum(x > 0 for x in diffs)
    negatives = sum(x < 0 for x in diffs)
    ties = len(diffs) - positives - negatives
    n = positives + negatives
    if n == 0:
        return positives, negatives, ties, 1.0
    k = min(positives, negatives)
    lower_tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return positives, negatives, ties, min(1.0, 2.0 * lower_tail)


def _cohen_dz(diffs: list[int | float]) -> float | None:
    if len(diffs) < 2:
        return None
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    if sd == 0.0:
        # Constant nonzero paired deltas imply an unbounded standardized effect.
        # Preserve strict JSON output by reporting that degenerate effect as null;
        # the paired mean and sign test still carry the directional evidence.
        return 0.0 if mean == 0.0 else None
    result = mean / sd
    return result if math.isfinite(result) else None


def _assignment_tv(records: list[dict[str, Any]]) -> float | None:
    by_seat: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    for row in records:
        by_seat[row["seat"]][row["opponent"]] += 1
    n0 = sum(by_seat[0].values())
    n1 = sum(by_seat[1].values())
    if n0 == 0 or n1 == 0:
        return None
    opponents = set(by_seat[0]) | set(by_seat[1])
    return 0.5 * sum(abs(by_seat[0][o] / n0 - by_seat[1][o] / n1) for o in opponents)


def analyze(
    records: Iterable[Any],
    *,
    require_complete: bool = False,
    require_structured_outcome: bool = False,
    authenticated_max_abs_margin: int | float | None = None,
) -> dict[str, Any]:
    bound = _authenticated_margin_bound(authenticated_max_abs_margin)
    rows = [
        normalize_record(
            record,
            index,
            require_structured_outcome=require_structured_outcome,
            authenticated_max_abs_margin=bound,
        )
        for index, record in enumerate(records)
    ]
    if not rows:
        raise DataError("no records")

    # Stringification is a report convenience, not an identity function.  A
    # dataset must use one primitive identifier type per provenance domain so
    # int 1 can never be paired with str "1" after normalization.
    seed_types = {row["seed_type"] for row in rows}
    opponent_types = {row["opponent_type"] for row in rows}
    if len(seed_types) != 1:
        raise DataError("mixed seed identifier primitive types are ambiguous")
    if len(opponent_types) != 1:
        raise DataError("mixed opponent identifier primitive types are ambiguous")

    cells: dict[tuple[str, str, int], int | float] = {}
    for row in rows:
        key = (row["seed"], row["opponent"], row["seat"])
        if key in cells:
            raise DataError(f"duplicate exact cell {key!r}")
        cells[key] = row["margin"]

    pair_keys = sorted({(seed, opponent) for seed, opponent, _seat in cells})
    complete: list[tuple[str, str, int | float, int | float]] = []
    missing: list[dict[str, Any]] = []
    for seed, opponent in pair_keys:
        present = [seat for seat in (0, 1) if (seed, opponent, seat) in cells]
        if present == [0, 1]:
            complete.append(
                (seed, opponent, cells[(seed, opponent, 0)], cells[(seed, opponent, 1)])
            )
        else:
            missing.append({"seed": seed, "opponent": opponent, "present_seats": present})

    if require_complete and missing:
        raise DataError(f"{len(missing)} seed/opponent pairs are missing a seat")
    if not complete:
        raise DataError("no exact seed+opponent pairs contain both seats")

    # Individual margins were finite at ingestion, but subtraction can still
    # overflow (e.g. -1e308 -> +1e308).  Authenticate the derived estimand too.
    diffs: list[int | float] = []
    by_opponent: dict[str, list[int | float]] = defaultdict(list)
    for seed, opponent, seat0, seat1 in complete:
        delta = _finite_number(
            seat1 - seat0,
            f"paired margin delta seed={seed!r} opponent={opponent!r}",
        )
        diffs.append(delta)
        by_opponent[opponent].append(delta)

    opponent_means = {opponent: statistics.mean(values)
                      for opponent, values in sorted(by_opponent.items())}
    balanced_mean = statistics.mean(opponent_means.values())
    positives, negatives, ties, p_value = _sign_test_two_sided(diffs)
    nonzero = positives + negatives
    sign_consistency = (max(positives, negatives) / nonzero) if nonzero else 0.5

    total_pair_slots = len(complete) + len(missing)
    report = {
        "schema": "titan-v4-agent-index-predictability/v1",
        "records": len(rows),
        "pair_groups": total_pair_slots,
        "matched_pairs": len(complete),
        "missing_pair_groups": len(missing),
        "matched_pair_coverage": len(complete) / total_pair_slots,
        "input_guard": {
            "require_structured_outcome": require_structured_outcome,
            "authenticated_max_abs_margin": bound,
            "margin_bound_policy": "reject_not_clip" if bound is not None else "none",
        },
        "seat0_mean_margin_matched": statistics.mean(x[2] for x in complete),
        "seat1_mean_margin_matched": statistics.mean(x[3] for x in complete),
        "paired_seat1_minus_seat0_mean": statistics.mean(diffs),
        "paired_seat1_minus_seat0_median": statistics.median(diffs),
        "equal_opponent_weighted_mean_delta": balanced_mean,
        "cohen_dz": _cohen_dz(diffs),
        "sign_test": {
            "positive": positives,
            "negative": negatives,
            "ties": ties,
            "two_sided_p": p_value,
            "directional_consistency": sign_consistency,
        },
        "opponent_pair_counts": {opponent: len(values)
                                 for opponent, values in sorted(by_opponent.items())},
        "opponent_mean_deltas": opponent_means,
        "raw_opponent_assignment_tv": _assignment_tv(rows),
        "missing_examples": missing[:20],
        "interpretation": (
            "Use the paired and equal-opponent metrics as the seat/index signal. "
            "A large raw assignment TV means pooled unpaired seat averages are confounded by "
            "opponent mix. This report is evidence only and does not authorize gameplay changes."
        ),
    }
    return report


def load_records(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        raise DataError("input file is empty")
    if stripped[0] == "[":
        value = json.loads(text)
        if not isinstance(value, list):
            raise DataError("JSON input must be an array")
        return value
    records = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise DataError(f"line {line_no}: invalid JSON: {exc}") from exc
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="JSON array or JSONL game records")
    parser.add_argument("--require-complete", action="store_true",
                        help="reject any seed/opponent pair missing one target seat")
    parser.add_argument(
        "--require-structured-outcome",
        action="store_true",
        help="reject margin-only records; require rewards or score+opponent_score",
    )
    parser.add_argument(
        "--authenticated-max-abs-margin",
        type=json.loads,
        default=None,
        help=(
            "caller-authenticated positive finite absolute margin bound; out-of-bound "
            "records are rejected, never clipped; there is no built-in game-score ceiling"
        ),
    )
    parser.add_argument("--output", type=Path,
                        help="write report JSON here instead of stdout")
    args = parser.parse_args()
    try:
        report = analyze(
            load_records(args.input),
            require_complete=args.require_complete,
            require_structured_outcome=args.require_structured_outcome,
            authenticated_max_abs_margin=args.authenticated_max_abs_margin,
        )
    except (DataError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
