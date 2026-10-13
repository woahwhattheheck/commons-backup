# SPDX-License-Identifier: Apache-2.0
"""Compare frozen V2 with the one-factor target-domain ablation."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from typing import Any, Mapping

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
V2_ENTRY_SHA256 = "2e4897fb3aa8b0bee3e97709808c3aa25fa5055bcf5ce7d433b493eb334870f2"
V2_SCHEDULER_BLOB = "7c068b7078c3d7c09bb3836590ad42b0af934cdf"


class CompareError(ValueError):
    """The paired reports are incomplete, incomparable, or unbound."""


def strict_object(path: Path) -> dict[str, Any]:
    def reject_pairs(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise CompareError(f"duplicate JSON key {key!r} in {path}")
            output[key] = value
        return output

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CompareError(f"non-finite JSON token {token} in {path}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompareError(f"cannot read {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise CompareError(f"{path} must contain one JSON object")
    return value


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CompareError(f"{label} is not numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise CompareError(f"{label} is not finite")
    return parsed


def sha256_text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise CompareError(f"{label} is not a lowercase SHA-256 digest")
    return value


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if receipt.get("schema_version") != 1:
        raise CompareError("materialization receipt schema mismatch")
    source = receipt.get("source")
    ablation = receipt.get("ablation")
    if not isinstance(source, Mapping) or not isinstance(ablation, Mapping):
        raise CompareError("materialization receipt is incomplete")
    if source.get("scheduler_git_blob_sha1") != V2_SCHEDULER_BLOB:
        raise CompareError("materialization receipt is not bound to frozen V2")
    if ablation.get("changed_files") != ["scheduler.py"]:
        raise CompareError("ablation is not one-factor scheduler-only")
    if (
        ablation.get("old_occurrences_before") != 1
        or ablation.get("old_occurrences_after") != 0
        or ablation.get("new_occurrences_before") != 0
        or ablation.get("new_occurrences_after") != 1
    ):
        raise CompareError("target-domain replacement cardinality is invalid")
    source_closure = sha256_text(source.get("closure_sha256"), "source closure")
    ablation_closure = sha256_text(ablation.get("closure_sha256"), "ablation closure")
    if source_closure == ablation_closure:
        raise CompareError("source and ablation closure identities are equal")
    return {
        "source_closure_sha256": source_closure,
        "ablation_closure_sha256": ablation_closure,
        "source_scheduler_git_blob_sha1": source["scheduler_git_blob_sha1"],
        "ablation_scheduler_git_blob_sha1": ablation.get(
            "scheduler_git_blob_sha1"
        ),
    }


def report_fingerprint(report: Mapping[str, Any], label: str) -> dict[str, Any]:
    if report.get("schema_version") != 1:
        raise CompareError(f"{label} schema mismatch")
    if report.get("engine_ref") != ENGINE_REF:
        raise CompareError(f"{label} engine ref mismatch")
    candidate = report.get("candidate")
    if not isinstance(candidate, Mapping):
        raise CompareError(f"{label} candidate identity missing")
    if candidate.get("sha256") != V2_ENTRY_SHA256:
        raise CompareError(
            f"{label} entrypoint bytes drifted; closure receipt cannot repair that"
        )
    opponents = report.get("opponents")
    if not isinstance(opponents, Mapping) or set(opponents) != {"arlene", "v1"}:
        raise CompareError(f"{label} opponent bank mismatch")
    seeds = report.get("seeds")
    if (
        not isinstance(seeds, list)
        or not seeds
        or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise CompareError(f"{label} seed grid is invalid")
    return {
        "engine_ref": report.get("engine_ref"),
        "engine_sha256": report.get("engine_sha256"),
        "loader_sha256": report.get("loader_sha256"),
        "evaluator_sha256": report.get("evaluator_sha256"),
        "opponents": dict(opponents),
        "seeds": list(seeds),
        "agent_rng_seed": report.get("agent_rng_seed"),
        "limits": report.get("limits"),
        "method": report.get("method"),
        "python": report.get("python"),
    }


def daily_map(game: Mapping[str, Any], label: str) -> dict[int, tuple[float, float]]:
    rows = game.get("daily_bank")
    if not isinstance(rows, list):
        raise CompareError(f"{label} daily_bank is not a list")
    output: dict[int, tuple[float, float]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise CompareError(f"{label} daily_bank row {index} is invalid")
        step = row.get("step")
        bank = row.get("bank")
        if (
            isinstance(step, bool)
            or not isinstance(step, int)
            or step in output
            or not isinstance(bank, list)
            or len(bank) != 2
        ):
            raise CompareError(f"{label} daily_bank row {index} identity is invalid")
        output[step] = (
            number(bank[0], f"{label} step {step} bank 0"),
            number(bank[1], f"{label} step {step} bank 1"),
        )
    if not output:
        raise CompareError(f"{label} daily_bank is empty")
    return output


def game_grid(
    report: Mapping[str, Any], label: str
) -> dict[tuple[str, int, int], dict[str, Any]]:
    seeds = set(report["seeds"])
    rows = report.get("games")
    if not isinstance(rows, list):
        raise CompareError(f"{label} games is not a list")
    grid: dict[tuple[str, int, int], dict[str, Any]] = {}
    for index, game in enumerate(rows):
        if not isinstance(game, dict):
            raise CompareError(f"{label} game {index} is not an object")
        opponent = game.get("opponent")
        seed = game.get("seed")
        seat = game.get("candidate_seat")
        key = (opponent, seed, seat)
        if (
            opponent not in ("arlene", "v1")
            or seed not in seeds
            or seat not in (0, 1)
            or key in grid
        ):
            raise CompareError(f"{label} invalid or duplicate game identity {key!r}")
        if game.get("status") != "complete" or game.get("failure") is not None:
            raise CompareError(f"{label} incomplete cell {key}: {game.get('failure')}")
        steps = game.get("steps")
        episode_steps = game.get("episode_steps")
        if (
            isinstance(steps, bool)
            or not isinstance(steps, int)
            or isinstance(episode_steps, bool)
            or not isinstance(episode_steps, int)
            or steps != episode_steps - 1
        ):
            raise CompareError(f"{label} incomplete step coverage for {key}")
        scores = game.get("scores")
        if not isinstance(scores, list) or len(scores) != 2:
            raise CompareError(f"{label} score vector is invalid for {key}")
        copied = dict(game)
        copied["scores"] = [
            number(scores[0], f"{label} {key} score 0"),
            number(scores[1], f"{label} {key} score 1"),
        ]
        copied["trace_sha256"] = sha256_text(
            game.get("trace_sha256"), f"{label} {key} trace"
        )
        copied["_daily"] = daily_map(game, f"{label} {key}")
        grid[key] = copied
    expected = {
        (opponent, seed, seat)
        for opponent in ("arlene", "v1")
        for seed in seeds
        for seat in (0, 1)
    }
    if set(grid) != expected:
        missing = sorted(expected - set(grid))
        extra = sorted(set(grid) - expected)
        raise CompareError(f"{label} grid mismatch; missing={missing}, extra={extra}")
    return grid


def first_bank_divergence(
    control: Mapping[str, Any], candidate: Mapping[str, Any]
) -> int | None:
    left = control["_daily"]
    right = candidate["_daily"]
    if set(left) != set(right):
        raise CompareError("control/candidate daily checkpoint grids differ")
    for step in sorted(left):
        if left[step] != right[step]:
            return step
    return None


def compare(
    control: Mapping[str, Any],
    candidate: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    git_head: str,
) -> dict[str, Any]:
    control_fp = report_fingerprint(control, "control")
    candidate_fp = report_fingerprint(candidate, "candidate")
    if control_fp != candidate_fp:
        raise CompareError("control/candidate provenance or grid drift")
    closure = validate_receipt(receipt)
    left = game_grid(control, "control")
    right = game_grid(candidate, "candidate")
    if set(left) != set(right):
        raise CompareError("paired game grids differ")

    rows: list[dict[str, Any]] = []
    for key in sorted(left):
        opponent, seed, seat = key
        baseline = left[key]
        ablation = right[key]
        baseline_own = baseline["scores"][seat]
        baseline_rival = baseline["scores"][1 - seat]
        ablation_own = ablation["scores"][seat]
        ablation_rival = ablation["scores"][1 - seat]
        rows.append(
            {
                "opponent": opponent,
                "seed": seed,
                "seat": seat,
                "control_own": baseline_own,
                "control_rival": baseline_rival,
                "ablation_own": ablation_own,
                "ablation_rival": ablation_rival,
                "own_delta": ablation_own - baseline_own,
                "rival_delta": ablation_rival - baseline_rival,
                "margin_delta": (
                    ablation_own
                    - ablation_rival
                    - (baseline_own - baseline_rival)
                ),
                "trace_changed": (
                    baseline["trace_sha256"] != ablation["trace_sha256"]
                ),
                "first_daily_bank_divergence_step": first_bank_divergence(
                    baseline, ablation
                ),
            }
        )

    changed = [row for row in rows if row["trace_changed"]]
    own_deltas = [row["own_delta"] for row in rows]
    rival_deltas = [row["rival_delta"] for row in rows]
    margin_deltas = [row["margin_delta"] for row in rows]
    by_opponent: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["opponent"]].append(row)
    for opponent, values in sorted(grouped.items()):
        deltas = [row["own_delta"] for row in values]
        by_opponent[opponent] = {
            "cells": len(values),
            "changed_cells": sum(row["trace_changed"] for row in values),
            "positive_cells": sum(delta > 0 for delta in deltas),
            "zero_cells": sum(delta == 0 for delta in deltas),
            "negative_cells": sum(delta < 0 for delta in deltas),
            "mean_own_delta": statistics.mean(deltas),
            "median_own_delta": statistics.median(deltas),
            "minimum_own_delta": min(deltas),
            "maximum_own_delta": max(deltas),
            "mean_margin_delta": statistics.mean(
                row["margin_delta"] for row in values
            ),
        }

    overall = {
        "cells": len(rows),
        "changed_cells": len(changed),
        "positive_cells": sum(delta > 0 for delta in own_deltas),
        "zero_cells": sum(delta == 0 for delta in own_deltas),
        "negative_cells": sum(delta < 0 for delta in own_deltas),
        "mean_own_delta": statistics.mean(own_deltas),
        "median_own_delta": statistics.median(own_deltas),
        "minimum_own_delta": min(own_deltas),
        "maximum_own_delta": max(own_deltas),
        "mean_rival_delta": statistics.mean(rival_deltas),
        "mean_margin_delta": statistics.mean(margin_deltas),
    }

    if not changed:
        verdict = "NO_ACTION_SIGNAL"
        reason = "the target-domain ablation never changed a returned action trace"
        exit_code = 4
    elif all(delta == 0 for delta in own_deltas + rival_deltas):
        verdict = "ACTION_NO_SCORE_SIGNAL"
        reason = "actions changed, but every terminal score remained identical"
        exit_code = 4
    elif (
        overall["mean_own_delta"] > 0
        and overall["median_own_delta"] >= 0
        and overall["positive_cells"] >= overall["negative_cells"]
        and all(value["mean_own_delta"] >= 0 for value in by_opponent.values())
    ):
        verdict = "UPSIDE_SCREEN"
        reason = (
            "the one-factor reversion improved mean own cash, did not lower median "
            "own cash, and did not regress either opponent stratum on average"
        )
        exit_code = 0
    elif overall["mean_own_delta"] < 0:
        verdict = "REGRESSION"
        reason = "the one-factor reversion lowered mean own cash"
        exit_code = 1
    else:
        verdict = "MIXED"
        reason = "the one-factor reversion changed play without broad own-cash upside"
        exit_code = 1

    return {
        "schema_version": 1,
        "operation": "titan-v2-target-domain-ablation-20260909-sol-bulwark-01",
        "git_head": git_head,
        "verdict": verdict,
        "reason": reason,
        "exit_code": exit_code,
        "provenance": control_fp,
        "closure_binding": closure,
        "overall": overall,
        "by_opponent": by_opponent,
        "changed_rows": changed,
        "rows": rows,
    }


def markdown(report: Mapping[str, Any]) -> str:
    overall = report.get("overall", {})
    lines = [
        "# TITAN V2 target-domain ablation",
        "",
        f"**Verdict:** `{report['verdict']}` — {report['reason']}",
        "",
    ]
    if overall:
        lines.extend(
            [
                f"- Complete paired cells: {overall['cells']}",
                f"- Trace-changed cells: {overall['changed_cells']}",
                f"- Mean / median own-cash delta: "
                f"{overall['mean_own_delta']:+.3f} / "
                f"{overall['median_own_delta']:+.3f}",
                f"- Minimum / maximum own-cash delta: "
                f"{overall['minimum_own_delta']:+.3f} / "
                f"{overall['maximum_own_delta']:+.3f}",
                f"- Mean rival-cash delta: {overall['mean_rival_delta']:+.3f}",
                f"- Mean margin delta: {overall['mean_margin_delta']:+.3f}",
                "",
                "## Opponent strata",
                "",
                "| Opponent | Cells | Changed | + / 0 / - | Mean own Δ | Median own Δ | Mean margin Δ |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for opponent, value in report["by_opponent"].items():
            lines.append(
                f"| {opponent} | {value['cells']} | {value['changed_cells']} | "
                f"{value['positive_cells']} / {value['zero_cells']} / "
                f"{value['negative_cells']} | {value['mean_own_delta']:+.3f} | "
                f"{value['median_own_delta']:+.3f} | "
                f"{value['mean_margin_delta']:+.3f} |"
            )
        lines.extend(["", "## Changed cells", ""])
        if report["changed_rows"]:
            lines.extend(
                [
                    "| Opponent | Seed | Seat | Own Δ | Rival Δ | Margin Δ | First daily bank Δ |",
                    "|---|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for row in report["changed_rows"]:
                first = row["first_daily_bank_divergence_step"]
                lines.append(
                    f"| {row['opponent']} | {row['seed']} | {row['seat']} | "
                    f"{row['own_delta']:+.1f} | {row['rival_delta']:+.1f} | "
                    f"{row['margin_delta']:+.1f} | "
                    f"{first if first is not None else 'terminal-only'} |"
                )
        else:
            lines.append("No returned action trace changed.")
    lines.extend(
        [
            "",
            "This is a one-factor offline causal screen, not a hosted leaderboard "
            "result or promotion authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = compare(
            strict_object(args.control),
            strict_object(args.candidate),
            strict_object(args.receipt),
            git_head=args.head,
        )
    except CompareError as exc:
        report = {
            "schema_version": 1,
            "operation": "titan-v2-target-domain-ablation-20260909-sol-bulwark-01",
            "git_head": args.head,
            "verdict": "INVALID",
            "reason": str(exc),
            "exit_code": 2,
        }
    atomic_write(
        args.output,
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    atomic_write(args.markdown, markdown(report))
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "reason": report["reason"],
                "exit_code": report["exit_code"],
                "overall": report.get("overall"),
                "by_opponent": report.get("by_opponent"),
            },
            sort_keys=True,
        )
    )
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
