#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strict paired-game comparison for TITAN candidate panels."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

Key = tuple[str, int, int]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _label(value: int) -> str:
    return {-1: "L", 0: "T", 1: "W"}[value]


def load_games(path: Path) -> dict[Key, dict[str, Any]]:
    games: dict[Key, dict[str, Any]] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
            opponent = str(row["opponent"])
            seed = int(row["seed"])
            seat = int(row["candidate_seat"])
            scores = row["scores"]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{path}:{line_no}: malformed row: {error}") from error
        if seat not in (0, 1):
            raise ValueError(f"{path}:{line_no}: candidate_seat must be 0 or 1")
        if row.get("status") != "complete":
            raise ValueError(f"{path}:{line_no}: incomplete game {(opponent, seed, seat)!r}")
        if not isinstance(scores, list) or len(scores) != 2:
            raise ValueError(f"{path}:{line_no}: scores must contain two values")
        values = [float(value) for value in scores]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{path}:{line_no}: non-finite score")
        key = (opponent, seed, seat)
        if key in games:
            raise ValueError(f"{path}:{line_no}: duplicate key {key!r}")
        row = dict(row)
        row.update(opponent=opponent, seed=seed, candidate_seat=seat, scores=values)
        games[key] = row
    if not games:
        raise ValueError(f"{path}: no game rows")
    return games


def ensure_grid(
    games: dict[Key, dict[str, Any]],
    *,
    opponents: Iterable[str] | None,
    seeds: Iterable[int] | None,
) -> None:
    if opponents is None or seeds is None:
        return
    expected = {
        (str(opponent), int(seed), seat)
        for opponent in opponents for seed in seeds for seat in (0, 1)
    }
    observed = set(games)
    if observed != expected:
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        raise ValueError(
            f"grid mismatch: missing={missing[:20]!r} ({len(missing)}), "
            f"unexpected={unexpected[:20]!r} ({len(unexpected)})"
        )


def _view(row: dict[str, Any]) -> tuple[float, float, float, int]:
    seat = int(row["candidate_seat"])
    own = float(row["scores"][seat])
    rival = float(row["scores"][1 - seat])
    margin = own - rival
    return own, rival, margin, _sign(margin)


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "cells": 0, "changed": 0, "mean_margin_delta": None,
            "sum_margin_delta": 0.0, "mean_own_delta": None,
            "mean_rival_delta": None, "new_losses": 0,
            "recovered_losses": 0, "transitions": {},
        }
    transitions = Counter(row["transition"] for row in rows)
    n = len(rows)
    return {
        "cells": n,
        "changed": sum(row["changed"] for row in rows),
        "mean_margin_delta": round(sum(row["margin_delta"] for row in rows) / n, 6),
        "sum_margin_delta": round(sum(row["margin_delta"] for row in rows), 6),
        "mean_own_delta": round(sum(row["own_delta"] for row in rows) / n, 6),
        "mean_rival_delta": round(sum(row["rival_delta"] for row in rows) / n, 6),
        "new_losses": sum(row["candidate_result"] < 0 <= row["baseline_result"] for row in rows),
        "recovered_losses": sum(row["baseline_result"] < 0 <= row["candidate_result"] for row in rows),
        "transitions": dict(sorted(transitions.items())),
    }


def compare(
    baseline: dict[Key, dict[str, Any]],
    candidate: dict[Key, dict[str, Any]],
) -> dict[str, Any]:
    if set(baseline) != set(candidate):
        missing = sorted(set(baseline) - set(candidate))
        extra = sorted(set(candidate) - set(baseline))
        raise ValueError(f"paired keys differ: missing={missing[:20]!r}, candidate_only={extra[:20]!r}")

    rows: list[dict[str, Any]] = []
    baseline_results = Counter()
    candidate_results = Counter()
    for opponent, seed, seat in sorted(baseline):
        bo, br, bm, bresult = _view(baseline[(opponent, seed, seat)])
        co, cr, cm, cresult = _view(candidate[(opponent, seed, seat)])
        baseline_results[bresult] += 1
        candidate_results[cresult] += 1
        rows.append({
            "opponent": opponent, "seed": seed, "candidate_seat": seat,
            "baseline_own": bo, "baseline_rival": br, "baseline_margin": bm,
            "candidate_own": co, "candidate_rival": cr, "candidate_margin": cm,
            "own_delta": co - bo, "rival_delta": cr - br, "margin_delta": cm - bm,
            "baseline_result": bresult, "candidate_result": cresult,
            "transition": f"{_label(bresult)}->{_label(cresult)}",
            "changed": bool(co != bo or cr != br),
        })

    changed = [row for row in rows if row["changed"]]
    opponents = sorted({row["opponent"] for row in rows})
    by_opponent = {
        opponent: _aggregate([row for row in rows if row["opponent"] == opponent])
        for opponent in opponents
    }
    by_seat = {
        str(seat): _aggregate([row for row in rows if row["candidate_seat"] == seat])
        for seat in (0, 1)
    }

    normalization_sites = []
    for row in changed:
        counterpart = baseline.get((row["opponent"], row["seed"], 1 - row["candidate_seat"]))
        if counterpart is None:
            continue
        own, rival, _, _ = _view(counterpart)
        if own == row["candidate_own"] and rival == row["candidate_rival"]:
            normalization_sites.append({
                "opponent": row["opponent"], "seed": row["seed"],
                "candidate_seat": row["candidate_seat"],
            })

    overall = _aggregate(rows)
    changed_only = _aggregate(changed)
    if overall["new_losses"]:
        verdict = "reject"
    elif not changed:
        verdict = "null"
    elif overall["mean_margin_delta"] > 0:
        verdict = "advance"
    else:
        verdict = "hold"

    labels = {-1: "L", 0: "T", 1: "W"}
    return {
        "schema": "titan-v3-paired-panel-delta-v1",
        "cells": len(rows),
        "baseline_record": {labels[k]: baseline_results[k] for k in (-1, 0, 1)},
        "candidate_record": {labels[k]: candidate_results[k] for k in (-1, 0, 1)},
        "overall": overall,
        "changed_only": changed_only,
        "changed_cells": changed,
        "unchanged_cells": len(rows) - len(changed),
        "by_opponent": by_opponent,
        "by_seat": by_seat,
        "seat_normalization": {
            "matches": len(normalization_sites),
            "changed_cells": len(changed),
            "fraction": round(len(normalization_sites) / len(changed), 6) if changed else 0.0,
            "sites": normalization_sites,
        },
        "verdict": verdict,
    }


def assert_historical_l01(report: dict[str, Any]) -> None:
    expected = {("arlene", seed, 0) for seed in range(2611061001, 2611061009)}
    actual = {
        (row["opponent"], int(row["seed"]), int(row["candidate_seat"]))
        for row in report["changed_cells"]
    }
    checks = {
        "cells": report["cells"] == 192,
        "changed_keys": actual == expected,
        "loss_to_win": report["changed_only"]["transitions"] == {"L->W": 8},
        "new_losses": report["overall"]["new_losses"] == 0,
        "sum_margin_delta": report["overall"]["sum_margin_delta"] == 129576.0,
        "mean_margin_delta": report["overall"]["mean_margin_delta"] == 674.875,
        "arlene_mean_delta": report["by_opponent"]["arlene"]["mean_margin_delta"] == 4049.25,
        "changed_own_mean": report["changed_only"]["mean_own_delta"] == -8505.0,
        "changed_rival_mean": report["changed_only"]["mean_rival_delta"] == -24702.0,
        "seat_normalization_matches": report["seat_normalization"]["matches"] == 7,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    report["historical_l01_profile"] = {"passed": not failed, "checks": checks, "failed": failed}
    if failed:
        raise ValueError(f"historical L01 signature mismatch: {failed}")


def markdown(report: dict[str, Any]) -> str:
    overall = report["overall"]
    changed = report["changed_only"]
    lines = [
        "# TITAN paired-panel delta", "",
        f"- Verdict: **{report['verdict'].upper()}**",
        f"- Cells: {report['cells']} ({len(report['changed_cells'])} changed)",
        f"- Record: {report['baseline_record']} → {report['candidate_record']}",
        f"- Mean margin Δ: {overall['mean_margin_delta']:+.3f}",
        f"- Sum margin Δ: {overall['sum_margin_delta']:+.3f}",
        f"- New losses: {overall['new_losses']}",
        f"- Recovered losses: {overall['recovered_losses']}",
        (
            f"- Changed-cell economics: own {changed['mean_own_delta']:+.3f}, "
            f"rival {changed['mean_rival_delta']:+.3f}, "
            f"margin {changed['mean_margin_delta']:+.3f}"
            if changed["cells"] else "- Changed-cell economics: no changed cells"
        ),
        f"- Opposite-seat baseline matches: {report['seat_normalization']['matches']}/{len(report['changed_cells'])}",
        "", "## Opponents", "",
        "| opponent | cells | changed | mean margin Δ | new losses | recovered losses |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for opponent, metrics in report["by_opponent"].items():
        lines.append(
            f"| {opponent} | {metrics['cells']} | {metrics['changed']} | "
            f"{metrics['mean_margin_delta']:+.3f} | {metrics['new_losses']} | "
            f"{metrics['recovered_losses']} |"
        )
    lines.extend(["", "## Changed cells", ""])
    if not report["changed_cells"]:
        lines.append("None.")
    else:
        lines.extend([
            "| opponent | seed | seat | transition | own Δ | rival Δ | margin Δ |",
            "|---|---:|---:|---|---:|---:|---:|",
        ])
        for row in report["changed_cells"]:
            lines.append(
                f"| {row['opponent']} | {row['seed']} | {row['candidate_seat']} | "
                f"{row['transition']} | {row['own_delta']:+.0f} | "
                f"{row['rival_delta']:+.0f} | {row['margin_delta']:+.0f} |"
            )
    return "\n".join(lines) + "\n"


def _csv(raw: str | None) -> list[str] | None:
    return None if raw is None else [part.strip() for part in raw.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--opponents")
    parser.add_argument("--seed-start", type=int)
    parser.add_argument("--seed-count", type=int)
    parser.add_argument("--expect-historical-l01", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()
    if (args.seed_start is None) != (args.seed_count is None):
        parser.error("--seed-start and --seed-count must be supplied together")
    seeds = range(args.seed_start, args.seed_start + args.seed_count) if args.seed_start is not None else None
    opponents = _csv(args.opponents)
    baseline = load_games(args.baseline)
    candidate = load_games(args.candidate)
    ensure_grid(baseline, opponents=opponents, seeds=seeds)
    ensure_grid(candidate, opponents=opponents, seeds=seeds)
    report = compare(baseline, candidate)
    report["inputs"] = {
        "baseline": str(args.baseline), "baseline_sha256": sha256(args.baseline),
        "candidate": str(args.candidate), "candidate_sha256": sha256(args.candidate),
    }
    if args.expect_historical_l01:
        assert_historical_l01(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
