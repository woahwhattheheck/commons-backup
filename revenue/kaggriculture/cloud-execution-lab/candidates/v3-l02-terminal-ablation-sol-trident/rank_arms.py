# SPDX-License-Identifier: Apache-2.0
"""Rank complete L02 screen arms without ever emitting a promotion verdict."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from ablation import ARMS


def _pairs_no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs_no_duplicates)
    if not isinstance(report, dict) or report.get("status") != "complete":
        raise ValueError(f"incomplete report: {path}")
    summary = report.get("summary")
    identity = report.get("identity")
    if not isinstance(summary, dict) or not isinstance(identity, dict):
        raise ValueError(f"missing summary/identity: {path}")
    arm = identity.get("ablation_arm")
    if arm not in ARMS:
        raise ValueError(f"unknown or missing arm identity: {path}")
    for name in ("mean_own_delta", "mean_margin_delta", "min_own_delta"):
        value = summary.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"invalid {name}: {path}")
    return report


def rank(paths: list[Path]) -> dict[str, Any]:
    reports = [load_report(path) for path in paths]
    seen = set()
    rows = []
    common = None
    for report in reports:
        arm = report["identity"]["ablation_arm"]
        if arm in seen:
            raise ValueError(f"duplicate arm: {arm}")
        seen.add(arm)
        signature = (
            report["identity"].get("git_head"),
            tuple(report.get("seeds", ())),
            tuple(report.get("opponents", ())),
            report.get("expected_cells_per_variant"),
        )
        if common is None:
            common = signature
        elif signature != common:
            raise ValueError("arm reports do not share one immutable screen grid")
        per_opponent = report.get("per_opponent") or {}
        own = float(report["summary"]["mean_own_delta"])
        margin = float(report["summary"]["mean_margin_delta"])
        worst = min(float(item.get("mean_own_delta", -math.inf)) for item in per_opponent.values())
        nonnegative = sum(float(item.get("mean_own_delta", -math.inf)) >= 0 for item in per_opponent.values())
        rows.append({
            "arm": arm,
            "mean_own_delta": own,
            "mean_margin_delta": margin,
            "min_cell_own_delta": float(report["summary"]["min_own_delta"]),
            "worst_opponent_mean_own_delta": worst,
            "nonnegative_opponents": nonnegative,
            "cells": int(report["summary"]["cells"]),
            "trace_changed_cells": int(report["summary"].get("trace_changed_cells", 0)),
        })
    rows.sort(key=lambda row: (row["mean_own_delta"], row["mean_margin_delta"]), reverse=True)
    survivor = next((row for row in rows if row["mean_own_delta"] > 0
                     and row["worst_opponent_mean_own_delta"] >= -300
                     and row["trace_changed_cells"] > 0), None)
    return {
        "schema_version": 1,
        "decision": "FULL_PANEL_REQUIRED" if survivor else "NO_ARM_SURVIVES_SCREEN",
        "scope": "development screen only; never a promotion or leaderboard claim",
        "screen_identity": {
            "git_head": common[0] if common else None,
            "seeds": list(common[1]) if common else [],
            "opponents": list(common[2]) if common else [],
            "expected_cells_per_variant": common[3] if common else 0,
        },
        "recommended_arm": survivor["arm"] if survivor else None,
        "ranking": rows,
    }


def markdown(result: dict[str, Any]) -> str:
    lines = ["# TITAN L02 terminal-window ablation screen", "",
             f"Decision: **{result['decision']}**", "",
             "| Rank | Arm | Mean own Δ | Mean margin Δ | Worst opponent own Δ | Nonnegative opponents | Cells |",
             "|---:|---|---:|---:|---:|---:|---:|"]
    for index, row in enumerate(result["ranking"], 1):
        lines.append(f"| {index} | `{row['arm']}` | {row['mean_own_delta']:.3f} | "
                     f"{row['mean_margin_delta']:.3f} | {row['worst_opponent_mean_own_delta']:.3f} | "
                     f"{row['nonnegative_opponents']} | {row['cells']} |")
    lines += ["", result["scope"], ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    args = parser.parse_args(argv)
    result = rank(args.inputs)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(result), encoding="utf-8")
    print(json.dumps({"decision": result["decision"], "recommended_arm": result["recommended_arm"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
