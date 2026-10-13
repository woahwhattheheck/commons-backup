# SPDX-License-Identifier: Apache-2.0
"""Fail-closed candidate-action and opponent-by-seat admission for the bound panel."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any


OPPONENTS = ("arlene", "v1")
SEEDS = (
    539131249,
    1834999074,
    2609097301,
    2609097302,
    2609097303,
    2609097304,
    2611092201,
    2611092207,
)
EXPECTED_ACTION_COUNT = 719


class EvidenceError(ValueError):
    """The retained panel is malformed, detached, or incompletely bound."""


def strict_load(path: Path, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in items:
            if key in output:
                raise EvidenceError(f"{label} has duplicate key {key!r}")
            output[key] = value
        return output

    def constant(value: str) -> Any:
        raise EvidenceError(f"{label} has non-finite JSON constant {value}")

    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot load {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} root must be an object")
    return value


def digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise EvidenceError(f"{label} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise EvidenceError(f"{label} must be a SHA-256 digest") from exc
    return value.lower()


def true_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EvidenceError(f"{label} must be an integer >= {minimum}")
    return value


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise EvidenceError(f"{label} must be finite")
    return value


def expected_keys() -> set[tuple[str, int, int]]:
    return {
        (opponent, seed, seat)
        for opponent in OPPONENTS
        for seed in SEEDS
        for seat in (0, 1)
    }


def evaluator_binding(
    receipt: dict[str, Any],
    control: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    if receipt.get("schema_version") != 1:
        raise EvidenceError("unsupported evaluator receipt schema")
    if receipt.get("operation") != (
        "titan-v3-own-value-bound-gameplay-screen-20260910-01"
    ):
        raise EvidenceError("evaluator receipt operation mismatch")
    source = receipt.get("source")
    patched = receipt.get("patched")
    if not isinstance(source, dict) or not isinstance(patched, dict):
        raise EvidenceError("evaluator receipt lacks source/patched objects")
    if source.get("git_blob_sha1") != "077feb2208b6e0c1727835eb4f8089709bf67f3b":
        raise EvidenceError("source evaluator blob mismatch")
    if patched.get("capture_phase") != (
        "after both returned actions, before interpreter"
    ):
        raise EvidenceError("candidate action capture phase mismatch")
    if patched.get("candidate_action_field") != "candidate_action_sha256":
        raise EvidenceError("candidate action field mismatch")
    if patched.get("candidate_action_count_field") != "candidate_action_count":
        raise EvidenceError("candidate action count field mismatch")
    evaluator_sha = digest(patched.get("sha256"), "patched evaluator SHA-256")
    source_sha = digest(source.get("sha256"), "source evaluator SHA-256")
    for label, report in (("control", control), ("candidate", candidate)):
        if digest(report.get("evaluator_sha256"), f"{label} evaluator SHA-256") != evaluator_sha:
            raise EvidenceError(f"{label} report is not bound to patched evaluator")
    return {
        "source_evaluator_sha256": source_sha,
        "patched_evaluator_sha256": evaluator_sha,
        "capture_phase": patched["capture_phase"],
    }


def index_report(
    report: dict[str, Any],
    label: str,
) -> dict[tuple[str, int, int], dict[str, Any]]:
    progress = report.get("progress")
    games = report.get("games")
    if not isinstance(progress, dict) or progress.get("state") != "complete":
        raise EvidenceError(f"{label} is not a complete final report")
    if not isinstance(games, list):
        raise EvidenceError(f"{label} games must be a list")
    planned = true_int(progress.get("planned_games"), f"{label} planned games", minimum=1)
    recorded = true_int(progress.get("recorded_games"), f"{label} recorded games", minimum=1)
    if planned != recorded or recorded != len(games):
        raise EvidenceError(f"{label} progress/game cardinality mismatch")
    seeds = report.get("seeds")
    opponents = report.get("opponents")
    if not isinstance(seeds, list) or tuple(seeds) != SEEDS:
        raise EvidenceError(f"{label} seed ledger mismatch")
    if not isinstance(opponents, dict) or tuple(sorted(opponents)) != tuple(sorted(OPPONENTS)):
        raise EvidenceError(f"{label} opponent ledger mismatch")

    output: dict[tuple[str, int, int], dict[str, Any]] = {}
    for offset, game in enumerate(games):
        if not isinstance(game, dict):
            raise EvidenceError(f"{label} game {offset} is not an object")
        try:
            key = (
                str(game["opponent"]),
                int(game["seed"]),
                int(game["candidate_seat"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceError(f"{label} game {offset} has malformed identity") from exc
        if key in output:
            raise EvidenceError(f"{label} has duplicate paired cell {key}")
        if game.get("status") != "complete" or game.get("failure") is not None:
            raise EvidenceError(f"{label} cell {key} is not complete")
        episode_steps = true_int(
            game.get("episode_steps"), f"{label} episode_steps {key}", minimum=2
        )
        steps = true_int(game.get("steps"), f"{label} steps {key}", minimum=1)
        action_count = true_int(
            game.get("candidate_action_count"),
            f"{label} candidate action count {key}",
            minimum=1,
        )
        if episode_steps != 720 or steps != EXPECTED_ACTION_COUNT:
            raise EvidenceError(f"{label} cell {key} has incomplete 720/719 lifecycle")
        if action_count != steps:
            raise EvidenceError(f"{label} cell {key} action count differs from steps")
        digest(
            game.get("candidate_action_sha256"),
            f"{label} candidate action SHA-256 {key}",
        )
        digest(game.get("trace_sha256"), f"{label} trace SHA-256 {key}")
        scores = game.get("scores")
        bank = game.get("bank_snapshot")
        if not isinstance(scores, list) or len(scores) != 2:
            raise EvidenceError(f"{label} cell {key} has malformed scores")
        if not isinstance(bank, list) or len(bank) != 2:
            raise EvidenceError(f"{label} cell {key} has malformed bank snapshot")
        score_values = [finite(value, f"{label} score {key}") for value in scores]
        bank_values = [finite(value, f"{label} bank {key}") for value in bank]
        if score_values != bank_values:
            raise EvidenceError(f"{label} cell {key} scores differ from terminal bank")
        output[key] = game

    if set(output) != expected_keys():
        raise EvidenceError(
            f"{label} paired grid mismatch: expected {len(expected_keys())}, got {len(output)}"
        )
    return output


def index_paired(
    report: dict[str, Any],
) -> dict[tuple[str, int, int], dict[str, Any]]:
    if report.get("schema_version") != 1:
        raise EvidenceError("unsupported paired report schema")
    if report.get("experiment") != "titan-v3-own-value-objective":
        raise EvidenceError("paired report experiment mismatch")
    cells = report.get("cells")
    if not isinstance(cells, list):
        raise EvidenceError("paired report cells must be a list")
    output: dict[tuple[str, int, int], dict[str, Any]] = {}
    for offset, row in enumerate(cells):
        if not isinstance(row, dict):
            raise EvidenceError(f"paired row {offset} is not an object")
        try:
            key = (
                str(row["opponent"]),
                int(row["seed"]),
                int(row["candidate_seat"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceError(f"paired row {offset} has malformed identity") from exc
        if key in output:
            raise EvidenceError(f"paired report has duplicate cell {key}")
        output[key] = row
    if set(output) != expected_keys():
        raise EvidenceError(
            f"paired report grid mismatch: expected {len(expected_keys())}, got {len(output)}"
        )
    return output


def outcome(own: float, rival: float) -> str:
    if own > rival:
        return "win"
    if own < rival:
        return "loss"
    return "tie"


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    own = [float(row["own_cash_delta"]) for row in rows]
    margins = [float(row["margin_delta"]) for row in rows]
    return {
        "cells": len(rows),
        "action_changed_cells": sum(bool(row["candidate_action_changed"]) for row in rows),
        "mean_own_cash_delta": statistics.mean(own),
        "median_own_cash_delta": statistics.median(own),
        "min_own_cash_delta": min(own),
        "max_own_cash_delta": max(own),
        "total_own_cash_delta": sum(own),
        "positive_cells": sum(value > 0 for value in own),
        "zero_cells": sum(value == 0 for value in own),
        "negative_cells": sum(value < 0 for value in own),
        "mean_margin_delta": statistics.mean(margins),
        "new_losses": sum(bool(row["new_loss"]) for row in rows),
        "lost_wins": sum(bool(row["lost_win"]) for row in rows),
    }


def assess(
    control_report: dict[str, Any],
    candidate_report: dict[str, Any],
    paired_report: dict[str, Any],
    evaluator_receipt: dict[str, Any],
) -> dict[str, Any]:
    binding = evaluator_binding(evaluator_receipt, control_report, candidate_report)
    control = index_report(control_report, "control")
    candidate = index_report(candidate_report, "candidate")
    paired = index_paired(paired_report)

    rows: list[dict[str, Any]] = []
    for key in sorted(expected_keys()):
        opponent, seed, seat = key
        left = control[key]
        right = candidate[key]
        pair = paired[key]
        left_scores = [finite(v, f"control score {key}") for v in left["scores"]]
        right_scores = [finite(v, f"candidate score {key}") for v in right["scores"]]
        control_own = left_scores[seat]
        candidate_own = right_scores[seat]
        control_rival = left_scores[1 - seat]
        candidate_rival = right_scores[1 - seat]
        own_delta = candidate_own - control_own
        rival_delta = candidate_rival - control_rival
        margin_delta = own_delta - rival_delta

        fields = {
            "control_own_cash": control_own,
            "candidate_own_cash": candidate_own,
            "own_cash_delta": own_delta,
            "control_margin": control_own - control_rival,
            "candidate_margin": candidate_own - candidate_rival,
            "margin_delta": margin_delta,
        }
        for name, expected in fields.items():
            actual = finite(pair.get(name), f"paired {name} {key}")
            if actual != expected:
                raise EvidenceError(
                    f"paired {name} for {key} is detached: expected {expected}, got {actual}"
                )

        control_trace = digest(
            left.get("trace_sha256"), f"control trace SHA-256 {key}"
        )
        candidate_trace = digest(
            right.get("trace_sha256"), f"candidate trace SHA-256 {key}"
        )
        if pair.get("control_trace_sha256") != control_trace:
            raise EvidenceError(f"paired control trace for {key} is detached")
        if pair.get("candidate_trace_sha256") != candidate_trace:
            raise EvidenceError(f"paired candidate trace for {key} is detached")
        trace_changed = control_trace != candidate_trace
        if pair.get("trace_changed") is not trace_changed:
            raise EvidenceError(f"paired trace-change flag for {key} is detached")

        control_action = digest(
            left.get("candidate_action_sha256"),
            f"control candidate action SHA-256 {key}",
        )
        candidate_action = digest(
            right.get("candidate_action_sha256"),
            f"candidate candidate action SHA-256 {key}",
        )
        action_changed = control_action != candidate_action
        if trace_changed and not action_changed:
            raise EvidenceError(
                f"complete trace changed without candidate action activation for {key}"
            )
        if (own_delta != 0 or rival_delta != 0) and not action_changed:
            raise EvidenceError(f"score changed without candidate action activation for {key}")

        before = outcome(control_own, control_rival)
        after = outcome(candidate_own, candidate_rival)
        rows.append(
            {
                "opponent": opponent,
                "seed": seed,
                "candidate_seat": seat,
                **fields,
                "control_rival_cash": control_rival,
                "candidate_rival_cash": candidate_rival,
                "rival_cash_delta": rival_delta,
                "control_candidate_action_sha256": control_action,
                "candidate_candidate_action_sha256": candidate_action,
                "candidate_action_changed": action_changed,
                "control_trace_sha256": control_trace,
                "candidate_trace_sha256": candidate_trace,
                "trace_changed": trace_changed,
                "control_outcome": before,
                "candidate_outcome": after,
                "new_loss": before != "loss" and after == "loss",
                "lost_win": before == "win" and after != "win",
            }
        )

    overall = aggregate(rows)
    strata = {
        f"{opponent}|seat{seat}": aggregate(
            [
                row
                for row in rows
                if row["opponent"] == opponent
                and row["candidate_seat"] == seat
            ]
        )
        for opponent in OPPONENTS
        for seat in (0, 1)
    }
    strata_safe = all(
        row["mean_own_cash_delta"] >= 0
        and row["median_own_cash_delta"] >= 0
        and row["positive_cells"] >= row["negative_cells"]
        and row["mean_margin_delta"] >= 0
        and row["new_losses"] == 0
        and row["lost_wins"] == 0
        for row in strata.values()
    )
    gates = {
        "candidate_action_activation": overall["action_changed_cells"] > 0,
        "positive_mean_own_cash": overall["mean_own_cash_delta"] > 0,
        "nonnegative_median_own_cash": overall["median_own_cash_delta"] >= 0,
        "nonnegative_cell_balance": (
            overall["positive_cells"] >= overall["negative_cells"]
        ),
        "positive_mean_margin": overall["mean_margin_delta"] > 0,
        "zero_new_losses": overall["new_losses"] == 0,
        "zero_lost_wins": overall["lost_wins"] == 0,
        "all_opponent_seat_strata_nonnegative": strata_safe,
    }
    if not gates["candidate_action_activation"]:
        verdict = "INACTIVE"
    elif all(gates.values()):
        verdict = "ADMIT"
    else:
        verdict = "REJECT"

    return {
        "schema_version": 1,
        "operation": "titan-v3-own-value-bound-gameplay-screen-20260910-01",
        "evaluator_binding": binding,
        "paired_verdict": paired_report.get("verdict"),
        "verdict": verdict,
        "gates": gates,
        "overall": overall,
        "by_opponent_seat": strata,
        "promotion_authorized": False,
        "hosted_leaderboard_claim": False,
        "rows": rows,
    }


def markdown(report: dict[str, Any]) -> str:
    overall = report["overall"]
    lines = [
        "# TITAN V3 own-value action-bound admission",
        "",
        f"- Verdict: **{report['verdict']}**",
        f"- Paired cells: **{overall['cells']}**",
        f"- Candidate-action changes: **{overall['action_changed_cells']}**",
        f"- Mean / median own-cash delta: **{overall['mean_own_cash_delta']:.3f} / "
        f"{overall['median_own_cash_delta']:.3f}**",
        f"- Positive / zero / negative cells: **{overall['positive_cells']} / "
        f"{overall['zero_cells']} / {overall['negative_cells']}**",
        f"- Mean margin delta: **{overall['mean_margin_delta']:.3f}**",
        f"- New losses / lost wins: **{overall['new_losses']} / {overall['lost_wins']}**",
        "",
        "Candidate actions are hashed after both actors return and before the official "
        "interpreter. This is an offline causal screen, not promotion authority.",
        "",
        "## Gates",
        "",
    ]
    lines.extend(
        f"- {'PASS' if value else 'FAIL'} — `{name}`"
        for name, value in report["gates"].items()
    )
    lines.extend(
        [
            "",
            "## Opponent × seat",
            "",
            "| Stratum | Cells | Mean own Δ | Median own Δ | + / 0 / - | "
            "Mean margin Δ | New losses | Lost wins |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, row in report["by_opponent_seat"].items():
        lines.append(
            f"| {name} | {row['cells']} | {row['mean_own_cash_delta']:.3f} | "
            f"{row['median_own_cash_delta']:.3f} | {row['positive_cells']} / "
            f"{row['zero_cells']} / {row['negative_cells']} | "
            f"{row['mean_margin_delta']:.3f} | {row['new_losses']} | "
            f"{row['lost_wins']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--paired", type=Path, required=True)
    parser.add_argument("--evaluator-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = assess(
            strict_load(args.control, "control report"),
            strict_load(args.candidate, "candidate report"),
            strict_load(args.paired, "paired report"),
            strict_load(args.evaluator_receipt, "evaluator receipt"),
        )
    except EvidenceError as exc:
        print(f"action-bound evidence error: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.markdown.write_text(markdown(result), encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": result["verdict"],
                "gates": result["gates"],
                **result["overall"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
