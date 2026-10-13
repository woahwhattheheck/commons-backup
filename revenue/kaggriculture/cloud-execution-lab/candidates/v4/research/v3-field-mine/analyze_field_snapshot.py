#!/usr/bin/env python3
"""Deterministic summary of a frozen TITAN hosted-field snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
from typing import Any


class DataError(ValueError):
    pass


def _plain_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise DataError(f"{label} must be an integer")
    return value


def _negative_margin(row: dict[str, Any], label: str) -> int:
    if not isinstance(row, dict):
        raise DataError(f"{label} row must be an object")
    margin = _plain_int(row.get("margin"), f"{label}.margin")
    if margin >= 0:
        raise DataError(f"{label}.margin must be negative")
    return margin


def deficit_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(rows, list) or not rows:
        raise DataError("loss rows must be a nonempty list")
    deficits = [-_negative_margin(row, "loss") for row in rows]
    ranks = []
    for row in rows:
        if "opponent_rank" in row:
            rank = _plain_int(row["opponent_rank"], "opponent_rank")
            if rank <= 0:
                raise DataError("opponent_rank must be positive")
            ranks.append(rank)
    return {
        "games": len(deficits),
        "median_deficit": statistics.median(deficits),
        "max_deficit": max(deficits),
        "within_100": sum(v <= 100 for v in deficits),
        "within_250": sum(v <= 250 for v in deficits),
        "within_500": sum(v <= 500 for v in deficits),
        "known_rank_games": len(ranks),
        "known_rank_median": statistics.median(ranks) if ranks else None,
        "known_rank_min": min(ranks) if ranks else None,
        "known_rank_max": max(ranks) if ranks else None,
    }


def _validate_exposure(document: dict[str, Any]) -> dict[str, Any]:
    exposure = document.get("opponent_exposure")
    if not isinstance(exposure, dict) or set(exposure) != {"v3", "v3.1"}:
        raise DataError("opponent_exposure must contain exactly v3 and v3.1")
    v31 = exposure["v3.1"]
    v3 = exposure["v3"]
    if not isinstance(v31, dict) or not isinstance(v3, dict):
        raise DataError("opponent exposure rows must be objects")

    top20_v31 = _plain_int(v31.get("top20_games"), "v3.1.top20_games")
    best_rank = _plain_int(v31.get("best_known_opponent_rank"), "v3.1.best_known_opponent_rank")
    median_rank = _plain_int(v31.get("median_known_opponent_rank"), "v3.1.median_known_opponent_rank")
    fresh_losses = _plain_int(
        v31.get("losses_against_same_day_fresh_submissions"),
        "v3.1.losses_against_same_day_fresh_submissions",
    )
    total_losses = _plain_int(v31.get("losses_total"), "v3.1.losses_total")
    if min(top20_v31, best_rank, median_rank, fresh_losses, total_losses) < 0:
        raise DataError("v3.1 exposure values must be nonnegative")
    if fresh_losses > total_losses:
        raise DataError("fresh-loss count exceeds total losses")

    groups = v3.get("top20_groups")
    if not isinstance(groups, list) or not groups:
        raise DataError("v3.top20_groups must be nonempty")
    group_games = 0
    all_negative = True
    seen = set()
    for index, row in enumerate(groups):
        if not isinstance(row, dict):
            raise DataError("top20 group must be an object")
        name = row.get("opponent")
        if not isinstance(name, str) or not name.strip() or name in seen:
            raise DataError("top20 opponent names must be unique nonempty strings")
        seen.add(name)
        rank = _plain_int(row.get("rank"), f"top20_groups[{index}].rank")
        games = _plain_int(row.get("games"), f"top20_groups[{index}].games")
        mean_margin = _plain_int(row.get("mean_margin"), f"top20_groups[{index}].mean_margin")
        if not (1 <= rank <= 20) or games <= 0:
            raise DataError("invalid top20 rank/game count")
        group_games += games
        all_negative &= mean_margin < 0

    advertised_games = _plain_int(v3.get("top20_games"), "v3.top20_games")
    advertised_wins = _plain_int(v3.get("top20_wins"), "v3.top20_wins")
    if group_games != advertised_games:
        raise DataError("top20 group games do not match advertised total")
    if advertised_wins < 0 or advertised_wins > advertised_games:
        raise DataError("invalid top20 win count")
    return {
        "v31_top20_games": top20_v31,
        "v31_best_known_opponent_rank": best_rank,
        "v31_median_known_opponent_rank": median_rank,
        "v31_losses_all_same_day_fresh": bool(total_losses and fresh_losses == total_losses),
        "v3_top20_games": advertised_games,
        "v3_top20_wins": advertised_wins,
        "v3_top20_group_means_all_negative": all_negative,
    }


def analyze(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise DataError("schema_version must be literal integer 1")
    captured = document.get("captured_at")
    if not isinstance(captured, str) or not captured:
        raise DataError("captured_at must be a nonempty string")

    versions = document.get("versions")
    if not isinstance(versions, dict):
        raise DataError("versions must be an object")
    for version in ("v3", "v3.1"):
        row = versions.get(version)
        if not isinstance(row, dict):
            raise DataError(f"missing {version} version summary")
        games = _plain_int(row.get("games"), f"{version}.games")
        if games <= 0:
            raise DataError(f"{version}.games must be positive")

    post = document.get("post_snapshot_events", [])
    if not isinstance(post, list):
        raise DataError("post_snapshot_events must be a list")
    for row in post:
        _negative_margin(row, "post_snapshot_event")

    return {
        "schema_version": 1,
        "captured_at": captured,
        "snapshot_games": {"v3": versions["v3"]["games"], "v3.1": versions["v3.1"]["games"]},
        "v3_close_losses": deficit_stats(document.get("v3_close_losses")),
        "v31_losses": deficit_stats(document.get("v31_losses")),
        "exposure": _validate_exposure(document),
        "post_snapshot_loss_events": len(post),
        "snapshot_is_current": len(post) == 0,
        "limits": [
            "This is a frozen coordination snapshot, not a live Kaggle API export.",
            "Opponent rank/exposure describes observed matchmaking, not causal strength.",
            "Close deficits are numerical flip targets only; no mechanism is credited without paired replay or field evidence.",
            "Replay-derived dairy labels may select opponents, but responsive paired S2-off/on runs are required for causal field gating.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.snapshot.read_text(encoding="utf-8"))
        encoded = json.dumps(analyze(document), indent=2, sort_keys=True) + "\n"
        if args.output:
            if args.output.resolve() == args.snapshot.resolve():
                raise DataError("output must not overwrite snapshot")
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
        return 0
    except (OSError, json.JSONDecodeError, DataError) as exc:
        import sys
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
