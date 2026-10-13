#!/usr/bin/env python3
"""Deterministic family-stratified planner for an existing TITAN V4 gauntlet.

The planner emits coordinates only. It does not execute games, score candidates,
choose promotion thresholds, or infer policy identity. Family/source authority is
provided by panel_diversity's strict manifest contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import panel_diversity as pd

SCHEDULE_SCHEMA = "titan.gauntlet.family-schedule.v1"


class IncompletePanelError(pd.DataError):
    pass


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        raise pd.DataError(f"{where} must be a positive exact integer")
    return value


def _seed_list(values: Any) -> list[int]:
    if type(values) is not list or not values:
        raise pd.DataError("seeds must be a non-empty list")
    seeds: list[int] = []
    seen: set[int] = set()
    for index, value in enumerate(values):
        if type(value) is not int or value < 0:
            raise pd.DataError(f"seeds[{index}] must be a non-negative exact integer")
        if value in seen:
            raise pd.DataError(f"duplicate seed: {value}")
        seen.add(value)
        seeds.append(value)
    return sorted(seeds)


def _member_sort_key(opp: dict[str, Any]) -> tuple[int, int, str]:
    rank = opp.get("rank")
    return (1 if rank is None else 0, 0 if rank is None else rank, opp["id"])


def _panel_identity_payload(panel: dict[str, Any]) -> dict[str, Any]:
    """Order-invariant identity used to bind a schedule to the exact panel authority."""
    opponents = []
    for opp in sorted(panel["opponents"], key=lambda row: row["id"]):
        opponents.append(
            {
                "id": opp["id"],
                "kind": opp["kind"],
                "family": opp["family"],
                "source_id": opp["source_id"],
                "status": opp["status"],
                "rank": opp.get("rank"),
            }
        )
    return {
        "schema": panel["schema"],
        "expected_labels": panel["expected_labels"],
        "opponents": opponents,
    }


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def panel_identity_sha256(panel: dict[str, Any]) -> str:
    return _canonical_sha256(_panel_identity_payload(panel))


def _cell_id(panel_digest: str, family: str, opponent_id: str, cycle: int, seed: int, seat: int) -> str:
    return _canonical_sha256(
        {
            "panel": panel_digest,
            "family": family,
            "opponent_id": opponent_id,
            "cycle": cycle,
            "seed": seed,
            "seat": seat,
        }
    )


def plan(
    panel_raw: Any,
    seeds: list[int],
    cycles: int,
    *,
    rotation_offset: int = 0,
    preview_incomplete: bool = False,
) -> dict[str, Any]:
    panel = pd.validate_panel(panel_raw)
    seeds = _seed_list(seeds)
    cycles = _positive_int(cycles, "cycles")
    if type(rotation_offset) is not int or rotation_offset < 0:
        raise pd.DataError("rotation_offset must be a non-negative exact integer")

    opponents = panel["opponents"]
    unresolved = [opp["id"] for opp in opponents if opp["status"] == "unresolved"]
    missing_label_count = panel["expected_labels"] - len(opponents)
    identity_complete = not unresolved and missing_label_count == 0
    if not identity_complete and not preview_incomplete:
        raise IncompletePanelError(
            "panel identity is incomplete; use --preview-incomplete only for a non-authoritative plan"
        )

    resolved = [opp for opp in opponents if opp["status"] == "resolved"]
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for opp in resolved:
        families[opp["family"]].append(opp)
    if not families:
        raise pd.DataError("panel has no resolved families to schedule")
    for members in families.values():
        members.sort(key=_member_sort_key)

    digest = panel_identity_sha256(panel)
    cells: list[dict[str, Any]] = []
    usage: dict[str, int] = defaultdict(int)
    family_rows: list[dict[str, Any]] = []

    for family in sorted(families):
        members = families[family]
        selected_ids: list[str] = []
        selected_sources: list[str] = []
        for cycle in range(cycles):
            member = members[(rotation_offset + cycle) % len(members)]
            selected_ids.append(member["id"])
            selected_sources.append(member["source_id"])
            for seed in seeds:
                for seat in (0, 1):
                    row = {
                        "cell_id": _cell_id(digest, family, member["id"], cycle, seed, seat),
                        "family": family,
                        "source_id": member["source_id"],
                        "opponent_id": member["id"],
                        "kind": member["kind"],
                        "cycle": cycle,
                        "seed": seed,
                        "seat": seat,
                    }
                    cells.append(row)
                    usage[member["id"]] += 1
        family_rows.append(
            {
                "family": family,
                "labels": [row["id"] for row in members],
                "sources": sorted({row["source_id"] for row in members}),
                "multiplicity": len(members),
                "scheduled_labels": sorted(set(selected_ids)),
                "scheduled_sources": sorted(set(selected_sources)),
                "cells": cycles * len(seeds) * 2,
            }
        )

    expected_family_cells = cycles * len(seeds) * 2
    family_cell_counts: dict[str, int] = defaultdict(int)
    for cell in cells:
        family_cell_counts[cell["family"]] += 1
    if set(family_cell_counts.values()) != {expected_family_cells}:
        raise pd.DataError("internal invariant violated: family budgets are unequal")

    resolved_ids = {opp["id"] for opp in resolved}
    seen_ids = set(usage)
    max_multiplicity = max(len(rows) for rows in families.values())
    schedule_core = {
        "schema": SCHEDULE_SCHEMA,
        "panel_identity_sha256": digest,
        "authoritative": identity_complete,
        "parameters": {
            "seeds": seeds,
            "cycles": cycles,
            "rotation_offset": rotation_offset,
            "seats": [0, 1],
        },
        "panel_status": {
            "expected_labels": panel["expected_labels"],
            "observed_labels": len(opponents),
            "resolved_labels": len(resolved),
            "unresolved_labels": sorted(unresolved),
            "missing_label_count": missing_label_count,
        },
        "coverage": {
            "families": len(families),
            "cells": len(cells),
            "cells_per_family": expected_family_cells,
            "max_family_multiplicity": max_multiplicity,
            "cycles_for_full_label_coverage": max_multiplicity,
            "resolved_labels_scheduled": len(seen_ids),
            "resolved_labels_total": len(resolved_ids),
            "all_resolved_labels_seen": seen_ids == resolved_ids,
            "next_rotation_offset": rotation_offset + cycles,
        },
        "families": family_rows,
        "cells": cells,
    }
    report = dict(schedule_core)
    report["schedule_sha256"] = _canonical_sha256(schedule_core)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel")
    parser.add_argument("--seed", type=int, action="append", required=True)
    parser.add_argument("--cycles", type=int, required=True)
    parser.add_argument("--rotation-offset", type=int, default=0)
    parser.add_argument("--preview-incomplete", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        panel = pd.load_strict(args.panel)
        report = plan(
            panel,
            args.seed,
            args.cycles,
            rotation_offset=args.rotation_offset,
            preview_incomplete=args.preview_incomplete,
        )
    except IncompletePanelError as exc:
        print(f"INCOMPLETE: {exc}", file=sys.stderr)
        return 3
    except (OSError, pd.DataError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
