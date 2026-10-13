# SPDX-License-Identifier: Apache-2.0
"""Fail-closed completeness for the TITAN S05 hosted exact-agent screen.

A green S05 job must prove the full requested panel: every variant/seat/seed
cell is present, `status == "complete"`, and carries usable scores. Incomplete
panels exit nonzero. Artifact upload remains `if: always()`.
"""
from __future__ import annotations

from typing import Any

VARIANTS = ("control", "shadow", "prior")
SEATS = (0, 1)


def expected_total(nseeds: int) -> int:
    return int(nseeds) * len(VARIANTS) * len(SEATS)


def expected_per_variant(nseeds: int) -> int:
    return int(nseeds) * len(SEATS)


def nseeds_from(report: dict, environ: dict | None = None) -> int:
    env = environ if environ is not None else {}
    raw = env.get("S05_SEEDS")
    if raw not in (None, ""):
        return int(raw)
    seeds = report.get("seeds") if isinstance(report, dict) else None
    if isinstance(seeds, list) and seeds:
        return len(seeds)
    return 0


def usable_scores(scores: Any) -> bool:
    if not isinstance(scores, (list, tuple)) or len(scores) < 2:
        return False
    try:
        float(scores[0])
        float(scores[1])
    except (TypeError, ValueError):
        return False
    return True


def completeness_errors(report: dict, nseeds: int) -> list[str]:
    errors: list[str] = []
    try:
        nseeds = int(nseeds)
    except (TypeError, ValueError):
        return ["nseeds_invalid"]
    if nseeds <= 0:
        return ["nseeds_invalid"]
    if not isinstance(report, dict):
        return ["report_missing"]
    games = report.get("games")
    if not isinstance(games, list):
        return ["games_missing"]
    want_total = expected_total(nseeds)
    if len(games) != want_total:
        errors.append(f"row_count:{len(games)}!={want_total}")
    by = {
        v: [g for g in games if isinstance(g, dict) and g.get("variant") == v]
        for v in VARIANTS
    }
    want_v = expected_per_variant(nseeds)
    for v in VARIANTS:
        if len(by[v]) != want_v:
            errors.append(f"variant_{v}:{len(by[v])}!={want_v}")
    for g in games:
        if not isinstance(g, dict):
            errors.append("row_not_object")
            continue
        label = f"{g.get('variant')}:{g.get('index')}:{g.get('candidate_seat')}"
        status = g.get("status")
        if status == "launcher_error":
            errors.append(f"launcher_error:{label}")
        elif status != "complete":
            errors.append(f"non_complete:{label}:{status}")
        if not usable_scores(g.get("scores")):
            errors.append(f"missing_score:{label}")
    return errors


def require_complete_panel(report: dict, nseeds: int) -> None:
    errors = completeness_errors(report, nseeds)
    if errors:
        raise SystemExit("S05_INCOMPLETE " + ";".join(errors[:24]))
