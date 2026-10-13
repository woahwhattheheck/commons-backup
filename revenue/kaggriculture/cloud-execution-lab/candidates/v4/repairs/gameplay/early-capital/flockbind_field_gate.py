# SPDX-License-Identifier: Apache-2.0
"""Fail-closed field-evidence gate for the canonical TITAN V4 FLOCKBIND helper.

This module does not execute an agent, rewrite actions, or authorize activation.
It validates a complete paired field receipt and classifies only the evidence:
INVALID, HOLD, or ALL_CELLS_NONNEGATIVE.  Runtime/default/config/archive/Kaggle
bytes are outside its authority.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "titan-v4-flockbind-field-panel/v1"
REQUIRED_SEEDS = (17, 101, 6607, 9922999)
REQUIRED_SEATS = (0, 1)
EXPECTED_B567 = {
    "artifact_id": 10175943272,
    "inner_tar_sha256": "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9",
    "engine_git_blob": "3c202c7ee921da239356789e266b694635103fc4",
    "parent_arlene_git_blob": "bdb9cf58148a3c7961c085f4902759537decabf6",
    "native_main_git_blob": "4a8cf7bcda1f0fea231a144692cb84a779a9e73e",
    "native_runtime_git_blob": "b952c9c228ecbde592bf3d2df01638677abb0d24",
    "helper_git_blob": "2118a89dc612ac5ae04e2f63ceec0282cb24b957",
}


def _finite_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)))


def _score_pair(value):
    return (isinstance(value, list) and len(value) == 2
            and all(_finite_number(v) for v in value))


def _canonical_json_sha256(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_panel(panel, *, expected_source=EXPECTED_B567, required_seeds=REQUIRED_SEEDS):
    """Validate one exact paired receipt and return a machine-readable verdict.

    ALL_CELLS_NONNEGATIVE is only an evidence predicate; it is deliberately not
    named PASS or PROMOTE because separate live-runtime and opponent gates remain.
    """
    reasons = []
    if not isinstance(panel, dict):
        return {"valid": False, "disposition": "INVALID", "reasons": ["panel_not_object"]}
    if panel.get("schema") != SCHEMA:
        reasons.append("schema_mismatch")
    source = panel.get("source")
    if not isinstance(source, dict):
        reasons.append("source_missing")
    else:
        for key, expected in expected_source.items():
            if source.get(key) != expected:
                reasons.append(f"source_mismatch:{key}")

    cells = panel.get("cells")
    if not isinstance(cells, list):
        reasons.append("cells_not_list")
        cells = []

    expected_coords = {(int(seed), seat) for seed in required_seeds for seat in REQUIRED_SEATS}
    seen = set()
    by_seed = defaultdict(dict)
    computed = []
    for index, cell in enumerate(cells):
        prefix = f"cell[{index}]"
        if not isinstance(cell, dict):
            reasons.append(f"{prefix}:not_object")
            continue
        seed, seat = cell.get("seed"), cell.get("seat")
        if (isinstance(seed, bool) or not isinstance(seed, int)
                or type(seat) is not int or seat not in REQUIRED_SEATS):
            reasons.append(f"{prefix}:bad_coordinate")
            continue
        coord = (seed, seat)
        if coord in seen:
            reasons.append(f"{prefix}:duplicate_coordinate")
        seen.add(coord)
        by_seed[seed][seat] = cell
        if coord not in expected_coords:
            reasons.append(f"{prefix}:unexpected_coordinate")

        base = cell.get("baseline_scores")
        candidate = cell.get("candidate_scores")
        if not _score_pair(base) or not _score_pair(candidate):
            reasons.append(f"{prefix}:bad_scores")
            continue
        own_delta = candidate[seat] - base[seat]
        rival_delta = candidate[1-seat] - base[1-seat]
        margin_delta = own_delta - rival_delta
        stated = (cell.get("own_delta"), cell.get("rival_delta"), cell.get("margin_delta"))
        actual = (own_delta, rival_delta, margin_delta)
        if any(not _finite_number(v) for v in stated) or tuple(float(v) for v in stated) != tuple(float(v) for v in actual):
            reasons.append(f"{prefix}:delta_mismatch")

        if cell.get("complete_steps") != 719:
            reasons.append(f"{prefix}:incomplete_episode")
        if cell.get("failure") not in (None, ""):
            reasons.append(f"{prefix}:failure_present")
        engagement = cell.get("engagement")
        if not isinstance(engagement, dict):
            reasons.append(f"{prefix}:engagement_missing")
        else:
            if engagement.get("rebind_count") != 1 or engagement.get("rebind_step") != 216:
                reasons.append(f"{prefix}:rebind_contract")
            if engagement.get("backfill_count") != 1 or engagement.get("backfill_step") != 227:
                reasons.append(f"{prefix}:backfill_contract")
            if engagement.get("obligation_status") != "fulfilled":
                reasons.append(f"{prefix}:obligation_unfulfilled")
            if engagement.get("obligation_item") != "WHEAT" or engagement.get("obligation_quantity") != 4:
                reasons.append(f"{prefix}:obligation_mismatch")
        computed.append({"seed": seed, "seat": seat,
                         "own_delta": own_delta, "rival_delta": rival_delta,
                         "margin_delta": margin_delta})

    missing = sorted(expected_coords - seen)
    extra = sorted(seen - expected_coords)
    if missing:
        reasons.append("missing_coordinates:" + ",".join(f"{s}/{seat}" for s, seat in missing))
    if extra:
        reasons.append("extra_coordinates:" + ",".join(f"{s}/{seat}" for s, seat in extra))

    # Both seats are expected to be mirror-exact for this starter panel.  This
    # catches seat-orientation errors without imposing the invariant on future
    # nonstarter opponent panels (callers can choose another validator then).
    for seed in required_seeds:
        pair = by_seed.get(seed, {})
        if 0 in pair and 1 in pair:
            a, b = pair[0], pair[1]
            if (a.get("baseline_scores") != list(reversed(b.get("baseline_scores", [])))
                    or a.get("candidate_scores") != list(reversed(b.get("candidate_scores", [])))):
                reasons.append(f"seed[{seed}]:seat_mirror_mismatch")

    valid = not reasons
    negative = [row for row in computed
                if _finite_number(row["own_delta"]) and _finite_number(row["margin_delta"])
                and (row["own_delta"] < 0 or row["margin_delta"] < 0)]
    if not valid:
        disposition = "INVALID"
    elif negative:
        disposition = "HOLD_NEGATIVE_CELLS"
    else:
        disposition = "ALL_CELLS_NONNEGATIVE"

    own = [float(row["own_delta"]) for row in computed] if valid else []
    margin = [float(row["margin_delta"]) for row in computed] if valid else []
    result = {
        "valid": valid,
        "disposition": disposition,
        "reasons": reasons,
        "cells": len(computed),
        "negative_cells": negative if valid else [],
        "mean_own_delta": sum(own) / len(own) if own else None,
        "mean_margin_delta": sum(margin) / len(margin) if margin else None,
        "activation_authority": False,
        "panel_sha256": _canonical_json_sha256(panel),
    }
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("panel", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    panel = json.loads(args.panel.read_text(encoding="utf-8"))
    result = validate_panel(panel)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
