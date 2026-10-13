# SPDX-License-Identifier: Apache-2.0
"""Compare canonical TITAN V3 with the own-value objective candidate."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
from typing import Any


class ComparisonError(ValueError):
    """The paired evaluator evidence is incomplete or not comparable."""


PROVENANCE_KEYS = (
    "schema_version",
    "engine_ref",
    "engine_sha256",
    "loader_sha256",
    "evaluator_sha256",
    "seeds",
    "agent_rng_seed",
    "limits",
    "opponents",
)


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComparisonError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ComparisonError(f"{label} must be finite")
    return value


def _validate_provenance(control: dict[str, Any], candidate: dict[str, Any]) -> None:
    for key in PROVENANCE_KEYS:
        if control.get(key) != candidate.get(key):
            raise ComparisonError(f"paired provenance mismatch: {key}")
    for label, report in (("control", control), ("candidate", candidate)):
        progress = report.get("progress")
        if not isinstance(progress, dict) or progress.get("state") != "complete":
            raise ComparisonError(f"{label} report is not a completed final snapshot")
        if not isinstance(report.get("games"), list):
            raise ComparisonError(f"{label} report lacks games")
        fingerprint = report.get("candidate")
        if not isinstance(fingerprint, dict) or not fingerprint.get("sha256"):
            raise ComparisonError(f"{label} candidate fingerprint is missing")
    if control["candidate"] == candidate["candidate"]:
        raise ComparisonError("control and candidate entrypoint fingerprints are equal")


def _index(report: dict[str, Any], label: str) -> dict[tuple[str, int, int], dict[str, Any]]:
    rows: dict[tuple[str, int, int], dict[str, Any]] = {}
    for game in report["games"]:
        try:
            key = (
                str(game["opponent"]),
                int(game["seed"]),
                int(game["candidate_seat"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ComparisonError(f"{label} game has malformed identity") from exc
        if key[2] not in (0, 1):
            raise ComparisonError(f"{label} game has invalid candidate seat")
        if key in rows:
            raise ComparisonError(f"{label} report has duplicate cell {key}")
        if game.get("status") != "complete" or game.get("failure") is not None:
            raise ComparisonError(f"{label} cell {key} is not complete")
        scores = game.get("scores")
        if not isinstance(scores, list) or len(scores) != 2:
            raise ComparisonError(f"{label} cell {key} has malformed scores")
        _finite(scores[0], f"{label} score[0] for {key}")
        _finite(scores[1], f"{label} score[1] for {key}")
        trace = game.get("trace_sha256")
        if not isinstance(trace, str) or len(trace) != 64:
            raise ComparisonError(f"{label} cell {key} lacks a complete trace hash")
        rows[key] = game
    return rows


def _expected_keys(report: dict[str, Any]) -> set[tuple[str, int, int]]:
    opponents = report.get("opponents")
    seeds = report.get("seeds")
    if not isinstance(opponents, dict) or not opponents:
        raise ComparisonError("paired report has no opponents")
    if not isinstance(seeds, list) or not seeds:
        raise ComparisonError("paired report has no seeds")
    return {
        (str(opponent), int(seed), seat)
        for opponent in opponents
        for seed in seeds
        for seat in (0, 1)
    }


def _first_bank_divergence(
    control: dict[str, Any], candidate: dict[str, Any], seat: int
) -> dict[str, float] | None:
    def bank_index(game: dict[str, Any], label: str) -> dict[int, float]:
        output: dict[int, float] = {}
        for row in game.get("daily_bank", []):
            if not isinstance(row, dict) or "step" not in row or "bank" not in row:
                raise ComparisonError(f"{label} daily-bank row is malformed")
            bank = row["bank"]
            if not isinstance(bank, list) or len(bank) != 2:
                raise ComparisonError(f"{label} daily-bank row has malformed balances")
            step = int(row["step"])
            if step in output:
                raise ComparisonError(f"{label} daily-bank step is duplicated")
            output[step] = _finite(bank[seat], f"{label} daily bank")
        return output

    left = bank_index(control, "control")
    right = bank_index(candidate, "candidate")
    for step in sorted(set(left) & set(right)):
        if left[step] != right[step]:
            return {
                "step": step,
                "control_own_cash": left[step],
                "candidate_own_cash": right[step],
                "delta": right[step] - left[step],
            }
    return None


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["own_cash_delta"]) for row in rows]
    margins = [float(row["margin_delta"]) for row in rows]
    changed = sum(bool(row["trace_changed"]) for row in rows)
    return {
        "cells": len(rows),
        "mean_own_cash_delta": statistics.mean(deltas),
        "median_own_cash_delta": statistics.median(deltas),
        "min_own_cash_delta": min(deltas),
        "max_own_cash_delta": max(deltas),
        "total_own_cash_delta": sum(deltas),
        "positive_cells": sum(delta > 0 for delta in deltas),
        "zero_cells": sum(delta == 0 for delta in deltas),
        "negative_cells": sum(delta < 0 for delta in deltas),
        "mean_margin_delta": statistics.mean(margins),
        "trace_changed_cells": changed,
        "trace_change_rate": changed / len(rows),
    }


def compare(
    control: dict[str, Any],
    candidate: dict[str, Any],
    *,
    git_head: str | None = None,
) -> dict[str, Any]:
    _validate_provenance(control, candidate)
    left = _index(control, "control")
    right = _index(candidate, "candidate")
    expected = _expected_keys(control)
    if set(left) != expected:
        raise ComparisonError(
            f"control grid mismatch: expected {len(expected)} cells, got {len(left)}"
        )
    if set(right) != expected:
        raise ComparisonError(
            f"candidate grid mismatch: expected {len(expected)} cells, got {len(right)}"
        )

    cells = []
    for key in sorted(expected):
        opponent, seed, seat = key
        base = left[key]
        arm = right[key]
        base_own = _finite(base["scores"][seat], "control own cash")
        arm_own = _finite(arm["scores"][seat], "candidate own cash")
        base_other = _finite(base["scores"][1 - seat], "control rival cash")
        arm_other = _finite(arm["scores"][1 - seat], "candidate rival cash")
        cells.append(
            {
                "opponent": opponent,
                "seed": seed,
                "candidate_seat": seat,
                "control_own_cash": base_own,
                "candidate_own_cash": arm_own,
                "own_cash_delta": arm_own - base_own,
                "control_margin": base_own - base_other,
                "candidate_margin": arm_own - arm_other,
                "margin_delta": (arm_own - arm_other) - (base_own - base_other),
                "control_trace_sha256": base["trace_sha256"],
                "candidate_trace_sha256": arm["trace_sha256"],
                "trace_changed": base["trace_sha256"] != arm["trace_sha256"],
                "first_daily_bank_divergence": _first_bank_divergence(base, arm, seat),
            }
        )

    overall = _aggregate(cells)
    strata = {
        opponent: _aggregate([row for row in cells if row["opponent"] == opponent])
        for opponent in sorted(control["opponents"])
    }
    if overall["trace_changed_cells"] == 0:
        verdict = "NO_ACTION_CHANGE"
    elif (
        overall["mean_own_cash_delta"] > 0
        and overall["median_own_cash_delta"] >= 0
        and overall["positive_cells"] >= overall["negative_cells"]
        and all(row["mean_own_cash_delta"] >= 0 for row in strata.values())
    ):
        verdict = "UPSIDE_SCREEN"
    elif (
        overall["mean_own_cash_delta"] < 0
        and overall["median_own_cash_delta"] <= 0
        and overall["negative_cells"] > overall["positive_cells"]
    ):
        verdict = "REGRESSION_SCREEN"
    else:
        verdict = "MIXED_SCREEN"

    return {
        "schema_version": 1,
        "experiment": "titan-v3-own-value-objective",
        "git_head": git_head,
        "control_fingerprint": control["candidate"],
        "candidate_fingerprint": candidate["candidate"],
        "paired_provenance": {
            key: control[key] for key in PROVENANCE_KEYS
        },
        "overall": overall,
        "by_opponent": strata,
        "verdict": verdict,
        "promotion_authorized": False,
        "hosted_leaderboard_claim": False,
        "cells": cells,
    }


def markdown(report: dict[str, Any]) -> str:
    overall = report["overall"]
    lines = [
        "# TITAN V3 own-value objective paired screen",
        "",
        f"- Verdict: **{report['verdict']}**",
        f"- Paired cells: **{overall['cells']}**",
        f"- Mean own-cash delta: **{overall['mean_own_cash_delta']:.3f}**",
        f"- Median own-cash delta: **{overall['median_own_cash_delta']:.3f}**",
        f"- Positive / zero / negative: **{overall['positive_cells']} / "
        f"{overall['zero_cells']} / {overall['negative_cells']}**",
        f"- Action-trace changes: **{overall['trace_changed_cells']} "
        f"({overall['trace_change_rate']:.1%})**",
        "",
        "This is an offline causal screen, not a hosted leaderboard result or "
        "promotion authorization.",
        "",
        "## Opponent strata",
        "",
        "| Opponent | Cells | Mean own Δ | Median own Δ | + / 0 / - | Trace changes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for opponent, row in report["by_opponent"].items():
        lines.append(
            f"| {opponent} | {row['cells']} | {row['mean_own_cash_delta']:.3f} | "
            f"{row['median_own_cash_delta']:.3f} | {row['positive_cells']} / "
            f"{row['zero_cells']} / {row['negative_cells']} | "
            f"{row['trace_changed_cells']} |"
        )
    lines.extend(
        [
            "",
            "## Paired cells",
            "",
            "| Opponent | Seed | Seat | Control own | Candidate own | Own Δ | Margin Δ | Trace | First bank divergence |",
            "|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in report["cells"]:
        divergence = row["first_daily_bank_divergence"]
        first = (
            "none"
            if divergence is None
            else f"step {divergence['step']}: {divergence['delta']:+.1f}"
        )
        lines.append(
            f"| {row['opponent']} | {row['seed']} | {row['candidate_seat']} | "
            f"{row['control_own_cash']:.1f} | {row['candidate_own_cash']:.1f} | "
            f"{row['own_cash_delta']:+.1f} | {row['margin_delta']:+.1f} | "
            f"{'changed' if row['trace_changed'] else 'same'} | {first} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--head")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    control = json.loads(args.control.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    report = compare(control, candidate, git_head=args.head)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], **report["overall"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
