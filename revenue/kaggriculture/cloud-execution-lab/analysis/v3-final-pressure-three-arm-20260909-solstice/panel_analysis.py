"""Complete-cell validation and paired score/state attribution."""
from __future__ import annotations

import math
import statistics
from typing import Any, Iterable, Mapping, Sequence

import evidence
import variants as arm_defs


def finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def game_key(game: Mapping[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(game.get("variant")),
        str(game.get("opponent")),
        int(game.get("seed")),
        int(game.get("candidate_seat")),
    )


def validate_games(
    games: Sequence[Mapping[str, Any]],
    variants: Sequence[Mapping[str, Any]],
    opponents: Sequence[str],
    seeds: Sequence[int],
) -> None:
    names = [row["name"] for row in variants]
    if names != list(arm_defs.VARIANTS):
        raise evidence.EvidenceError(f"Variant order/identity mismatch: {names}")
    expected = {
        (variant, opponent, int(seed), seat)
        for variant in arm_defs.VARIANTS
        for opponent in opponents
        for seed in seeds
        for seat in (0, 1)
    }
    if len(games) != len(expected):
        raise evidence.EvidenceError(
            f"Expected {len(expected)} games, received {len(games)}"
        )
    observed: set[tuple[str, str, int, int]] = set()
    for game in games:
        try:
            key = game_key(game)
        except (TypeError, ValueError) as exc:
            raise evidence.EvidenceError(f"Malformed game identity: {game}") from exc
        if key in observed:
            raise evidence.EvidenceError(f"Duplicate game cell: {key}")
        observed.add(key)
        if key not in expected:
            raise evidence.EvidenceError(f"Unexpected game cell: {key}")
        if game.get("status") != "complete" or game.get("failure") is not None:
            raise evidence.EvidenceError(
                f"Incomplete game cell: {key}; {game.get('failure')}"
            )
        scores = game.get("scores")
        if (
            not isinstance(scores, list)
            or len(scores) != 2
            or not all(finite_number(value) for value in scores)
        ):
            raise evidence.EvidenceError(f"Invalid scores: {key}")
        steps = game.get("steps")
        episode_steps = game.get("episode_steps")
        if (
            isinstance(steps, bool)
            or not isinstance(steps, int)
            or isinstance(episode_steps, bool)
            or not isinstance(episode_steps, int)
            or steps != episode_steps - 1
        ):
            raise evidence.EvidenceError(f"Invalid completed step count: {key}")
        for field in (
            "candidate_action_trace_sha256",
            "post_state_trace_sha256",
        ):
            if not evidence.valid_sha256(game.get(field)):
                raise evidence.EvidenceError(f"Invalid {field}: {key}")
        traces = game.get("step_digests")
        if not isinstance(traces, list) or len(traces) != steps:
            raise evidence.EvidenceError(f"Invalid step_digests length: {key}")
        for index, row in enumerate(traces):
            if not isinstance(row, dict) or row.get("step") != index:
                raise evidence.EvidenceError(
                    f"Non-contiguous trace row at {key}/{index}"
                )
            for field in ("candidate_action_sha256", "post_state_sha256"):
                if not evidence.valid_sha256(row.get(field)):
                    raise evidence.EvidenceError(
                        f"Invalid {field} at {key}/{index}"
                    )
        actors = game.get("actors")
        if not isinstance(actors, list) or len(actors) != 2:
            raise evidence.EvidenceError(f"Missing actor receipts: {key}")
        for actor in actors:
            if (
                not isinstance(actor, dict)
                or not finite_number(actor.get("max_rpc_seconds"))
            ):
                raise evidence.EvidenceError(f"Invalid actor receipt: {key}")
    if observed != expected:
        raise evidence.EvidenceError(
            f"Missing cells: {sorted(expected - observed)[:5]}"
        )


def margin(game: Mapping[str, Any]) -> float:
    seat = int(game["candidate_seat"])
    return float(game["scores"][seat]) - float(game["scores"][1 - seat])


def own_score(game: Mapping[str, Any]) -> float:
    return float(game["scores"][int(game["candidate_seat"])])


def rival_score(game: Mapping[str, Any]) -> float:
    return float(game["scores"][1 - int(game["candidate_seat"])])


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return statistics.mean(values) if values else None


def first_divergence(
    left: Mapping[str, Any], right: Mapping[str, Any], field: str
) -> int | None:
    left_rows = left["step_digests"]
    right_rows = right["step_digests"]
    if len(left_rows) != len(right_rows):
        raise evidence.EvidenceError("Cannot compare traces with different lengths")
    for index, (a, b) in enumerate(zip(left_rows, right_rows)):
        if a[field] != b[field]:
            return index
    return None


def verdict(value: float) -> str:
    return "W" if value > 0 else "L" if value < 0 else "T"


def summarize(
    games: Sequence[Mapping[str, Any]],
    variants: Sequence[Mapping[str, Any]],
    opponents: Sequence[str],
    seeds: Sequence[int],
) -> dict[str, Any]:
    validate_games(games, variants, opponents, seeds)
    index = {
        (
            game["opponent"],
            int(game["seed"]),
            int(game["candidate_seat"]),
            game["variant"],
        ): game
        for game in games
    }
    cells = sorted(
        {
            (game["opponent"], int(game["seed"]), int(game["candidate_seat"]))
            for game in games
        }
    )
    by_variant: dict[str, Any] = {}
    for name in arm_defs.VARIANTS:
        rows = [index[cell + (name,)] for cell in cells]
        margins = [margin(row) for row in rows]
        by_variant[name] = {
            "games": len(rows),
            "wins": sum(value > 0 for value in margins),
            "ties": sum(value == 0 for value in margins),
            "losses": sum(value < 0 for value in margins),
            "mean_margin": mean(margins),
            "mean_candidate_score": mean(own_score(row) for row in rows),
            "mean_opponent_score": mean(rival_score(row) for row in rows),
            "max_candidate_rpc_seconds": max(
                float(row["actors"][int(row["candidate_seat"])]["max_rpc_seconds"])
                for row in rows
            ),
        }

    comparisons: dict[str, Any] = {}
    for left_name, right_name in arm_defs.PAIRINGS:
        paired: list[dict[str, Any]] = []
        for cell in cells:
            left = index[cell + (left_name,)]
            right = index[cell + (right_name,)]
            action_step = first_divergence(
                left, right, "candidate_action_sha256"
            )
            state_step = first_divergence(left, right, "post_state_sha256")
            left_margin, right_margin = margin(left), margin(right)
            paired.append(
                {
                    "opponent": cell[0],
                    "seed": cell[1],
                    "candidate_seat": cell[2],
                    "left_margin": left_margin,
                    "right_margin": right_margin,
                    "margin_delta": left_margin - right_margin,
                    "candidate_score_delta": own_score(left) - own_score(right),
                    "opponent_score_delta": rival_score(left) - rival_score(right),
                    "first_candidate_action_divergence": action_step,
                    "first_post_state_divergence": state_step,
                    "classification": (
                        "identical"
                        if action_step is None and state_step is None
                        else "syntactic_only"
                        if action_step is not None and state_step is None
                        else "state_only"
                        if action_step is None and state_step is not None
                        else "realized"
                    ),
                    "verdict_transition": (
                        f"{verdict(right_margin)}->{verdict(left_margin)}"
                    ),
                }
            )
        key = f"{left_name}_minus_{right_name}"
        comparisons[key] = {
            "cells": len(paired),
            "candidate_action_changed_cells": sum(
                row["first_candidate_action_divergence"] is not None
                for row in paired
            ),
            "post_state_changed_cells": sum(
                row["first_post_state_divergence"] is not None
                for row in paired
            ),
            "syntactic_only_cells": sum(
                row["classification"] == "syntactic_only" for row in paired
            ),
            "identical_cells": sum(
                row["classification"] == "identical" for row in paired
            ),
            "new_losses": sum(
                row["right_margin"] >= 0 and row["left_margin"] < 0
                for row in paired
            ),
            "resolved_losses": sum(
                row["right_margin"] < 0 and row["left_margin"] >= 0
                for row in paired
            ),
            "mean_margin_delta": mean(row["margin_delta"] for row in paired),
            "median_margin_delta": statistics.median(
                row["margin_delta"] for row in paired
            ),
            "min_margin_delta": min(row["margin_delta"] for row in paired),
            "max_margin_delta": max(row["margin_delta"] for row in paired),
            "mean_candidate_score_delta": mean(
                row["candidate_score_delta"] for row in paired
            ),
            "mean_opponent_score_delta": mean(
                row["opponent_score_delta"] for row in paired
            ),
            "earliest_candidate_action_divergence": min(
                (
                    row["first_candidate_action_divergence"]
                    for row in paired
                    if row["first_candidate_action_divergence"] is not None
                ),
                default=None,
            ),
            "earliest_post_state_divergence": min(
                (
                    row["first_post_state_divergence"]
                    for row in paired
                    if row["first_post_state_divergence"] is not None
                ),
                default=None,
            ),
            "verdict_transitions": {
                value: sum(
                    row["verdict_transition"] == value for row in paired
                )
                for value in sorted(
                    {row["verdict_transition"] for row in paired}
                )
            },
            "paired_cells": paired,
        }

    means = {
        name: by_variant[name]["mean_margin"] for name in arm_defs.VARIANTS
    }
    best = max(means.values())
    leaders = sorted(name for name, value in means.items() if value == best)
    final_off = comparisons["final_boundary_minus_pressure_off"]
    final_legacy = comparisons["final_boundary_minus_legacy_in_pipeline"]
    if (
        leaders == ["final_boundary"]
        and final_off["new_losses"] == 0
        and final_legacy["new_losses"] == 0
    ):
        signal = "FINAL_BOUNDARY_LEADS_DEVELOPMENT"
    elif leaders == ["legacy_in_pipeline"]:
        signal = "LEGACY_IN_PIPELINE_LEADS_DEVELOPMENT"
    elif leaders == ["pressure_off"]:
        signal = "PRESSURE_OFF_LEADS_DEVELOPMENT"
    elif len(leaders) > 1:
        signal = "DEVELOPMENT_TIE"
    else:
        signal = "MIXED_DEVELOPMENT"
    return {
        "by_variant": by_variant,
        "comparisons": comparisons,
        "development_signal": signal,
        "leaders_by_mean_margin": leaders,
        "scope": (
            "development attribution only; no automatic promotion or "
            "hosted-score claim"
        ),
    }


def markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TITAN V3 final-pressure three-arm panel",
        "",
        f"- Dispatch: `{report['dispatch_commit']}`",
        f"- Archive: `{report['archive']['sha256']}` "
        f"({report['archive']['bytes']} bytes)",
        f"- Source manifest: `{report['archive']['source_manifest_sha256']}`",
        f"- Games: **{report['scheduled_games']} complete**",
        f"- Development signal: **{summary['development_signal']}**",
        "",
        "## Arms",
        "",
        "| Arm | W-T-L | Mean margin | Mean own | Mean rival | Max candidate RPC |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant in arm_defs.VARIANTS:
        value = summary["by_variant"][variant]
        lines.append(
            f"| `{variant}` | {value['wins']}-{value['ties']}-{value['losses']} | "
            f"{value['mean_margin']:.3f} | "
            f"{value['mean_candidate_score']:.3f} | "
            f"{value['mean_opponent_score']:.3f} | "
            f"{value['max_candidate_rpc_seconds']:.6f}s |"
        )
    lines += ["", "## Paired attribution", ""]
    for key, value in summary["comparisons"].items():
        lines += [
            f"### `{key}`",
            "",
            f"- Mean margin delta: **{value['mean_margin_delta']:.3f}** "
            f"(min {value['min_margin_delta']:.3f}, "
            f"max {value['max_margin_delta']:.3f}).",
            f"- Candidate-action divergence: "
            f"**{value['candidate_action_changed_cells']}/{value['cells']}** "
            f"cells; post-state divergence: "
            f"**{value['post_state_changed_cells']}/{value['cells']}** cells.",
            f"- Syntactic-only cells: **{value['syntactic_only_cells']}**; "
            f"new losses: **{value['new_losses']}**; resolved losses: "
            f"**{value['resolved_losses']}**.",
            "",
        ]
    lines += [
        "This is a source-bound offline official-interpreter development panel. "
        "It does not authorize canonical mutation, provider submission, or a "
        "leaderboard claim.",
        "",
    ]
    return "\n".join(lines)
