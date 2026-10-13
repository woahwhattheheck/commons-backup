from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

from lean_feed_core import (
    ARM_CURRENT,
    ARM_MIN,
    ARMS,
    CURRENT_POLICY,
    D2_ARCHIVE_SHA256,
    D2_HOSTED_PYTHON,
    D2_MEMBER_COUNT,
    D2_RUNTIME_MEMBER,
    REPORT_SCHEMA,
    SCHEMA,
    SEATS,
    SPLITS,
    _require,
    compute_reserve_oracle,
    sha256_json,
)
from lean_feed_run import RunMetrics, _identity, analyze_run


def _validate_authority(document: Mapping[str, Any]) -> dict[str, Any]:
    authority = document.get("authority")
    _require(isinstance(authority, Mapping), "authority required")
    _require(
        authority.get("archive_sha256") == D2_ARCHIVE_SHA256,
        "wrong D2 archive SHA-256",
    )
    _require(
        authority.get("archive_member_count") == D2_MEMBER_COUNT,
        "wrong archive member count",
    )
    _require(
        authority.get("runtime_member") == D2_RUNTIME_MEMBER,
        "wrong runtime member",
    )
    _require(
        authority.get("hosted_python") == D2_HOSTED_PYTHON,
        "wrong hosted Python",
    )
    _require(
        authority.get("current_policy") == CURRENT_POLICY,
        "wrong current policy vector",
    )
    _require(
        authority.get("evidence_source") == "instrumented_runtime",
        "wrong evidence source",
    )
    _require(
        authority.get("holdout_sealed_before_dev") is True,
        "holdout was not sealed before dev",
    )
    for key in ("dev_manifest_sha256", "holdout_manifest_sha256"):
        digest = authority.get(key)
        _require(
            isinstance(digest, str)
            and len(digest) == 64
            and all(char in "0123456789abcdef" for char in digest),
            f"{key} invalid",
        )
    _require(
        authority["dev_manifest_sha256"] != authority["holdout_manifest_sha256"],
        "dev and holdout manifests must differ",
    )
    selection = document.get("candidate_selection")
    _require(isinstance(selection, Mapping), "candidate_selection required")
    _require(
        selection.get("arm") == ARM_MIN
        and selection.get("selected_before_holdout") is True,
        "MIN_PROVABLE must be selected before holdout",
    )
    digest = selection.get("selection_manifest_sha256")
    _require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest),
        "selection manifest digest invalid",
    )
    return dict(authority)


def _validate_design(metrics: Sequence[RunMetrics]) -> dict[str, Any]:
    _require(metrics, "runs required")
    _require(
        len({metric.identity.run_id for metric in metrics}) == len(metrics),
        "duplicate run_id",
    )
    cell_arms: dict[tuple[str, str, int, int, str], set[str]] = defaultdict(set)
    seat_cells: dict[tuple[str, str, int, str, str], set[int]] = defaultdict(set)
    dev_opponents: set[str] = set()
    holdout_opponents: set[str] = set()
    dev_cases: set[tuple[str, int]] = set()
    holdout_cases: set[tuple[str, int]] = set()
    for metric in metrics:
        identity = metric.identity
        cell_arms[
            (
                identity.split,
                identity.opponent,
                identity.seed,
                identity.seat,
                identity.pair_id,
            )
        ].add(identity.arm)
        seat_cells[
            (
                identity.split,
                identity.opponent,
                identity.seed,
                identity.pair_id,
                identity.arm,
            )
        ].add(identity.seat)
        if identity.split == "dev":
            dev_opponents.add(identity.opponent)
            dev_cases.add((identity.opponent, identity.seed))
        else:
            holdout_opponents.add(identity.opponent)
            holdout_cases.add((identity.opponent, identity.seed))
    for cell, arms in cell_arms.items():
        _require(arms == set(ARMS), f"cell {cell} missing arm")
    for cell, seats in seat_cells.items():
        _require(seats == set(SEATS), f"cell {cell} missing seat")
    _require(len(dev_opponents) >= 2, "dev requires two opponent regimes")
    _require(bool(holdout_opponents), "holdout opponent required")
    _require(dev_cases.isdisjoint(holdout_cases), "holdout cases overlap dev")
    return {
        "cells": len(cell_arms),
        "dev_opponents": sorted(dev_opponents),
        "holdout_opponents": sorted(holdout_opponents),
    }


def _paired_deltas(metrics: Sequence[RunMetrics]) -> list[dict[str, Any]]:
    by_cell: dict[tuple[str, str, int, int, str], dict[str, RunMetrics]] = defaultdict(dict)
    for metric in metrics:
        identity = metric.identity
        by_cell[
            (
                identity.split,
                identity.opponent,
                identity.seed,
                identity.seat,
                identity.pair_id,
            )
        ][identity.arm] = metric
    rows: list[dict[str, Any]] = []
    for (split, opponent, seed, seat, pair_id), arms in sorted(by_cell.items()):
        current = arms[ARM_CURRENT]
        candidate = arms[ARM_MIN]
        rows.append(
            {
                "split": split,
                "opponent": opponent,
                "seed": seed,
                "seat": seat,
                "pair_id": pair_id,
                "delta_own": candidate.own - current.own,
                "delta_rival": candidate.rival - current.rival,
                "delta_m": candidate.margin - current.margin,
                "activations": candidate.activations,
                "units_removed": candidate.units_removed,
                "cash_liberated": candidate.cash_liberated,
                "downstream_cash_used": candidate.downstream_cash_used,
                "obligation_failures": candidate.obligation_failures,
                "productivity_loss": candidate.productivity_loss,
                "survival_loss": candidate.survival_loss,
            }
        )
    return rows


def _mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return fmean(materialized) if materialized else 0.0


def _promotion_gate(delta_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    split_rows = {
        split: [row for row in delta_rows if row["split"] == split]
        for split in SPLITS
    }
    strata: list[dict[str, Any]] = []
    all_nonnegative = True
    repeated_negative = False
    for split in SPLITS:
        keys = sorted(
            {(row["opponent"], row["seat"]) for row in split_rows[split]}
        )
        for opponent, seat in keys:
            rows = [
                row
                for row in split_rows[split]
                if row["opponent"] == opponent and row["seat"] == seat
            ]
            mean_margin = _mean(row["delta_m"] for row in rows)
            negatives = sum(1 for row in rows if row["delta_m"] < 0)
            all_nonnegative &= mean_margin >= 0
            repeated_negative |= negatives >= 2
            strata.append(
                {
                    "split": split,
                    "opponent": opponent,
                    "seat": seat,
                    "cells": len(rows),
                    "mean_delta_m": mean_margin,
                    "negative_cells": negatives,
                }
            )

    dev = split_rows["dev"]
    holdout = split_rows["holdout"]
    dev_mean = _mean(row["delta_m"] for row in dev)
    holdout_mean = _mean(row["delta_m"] for row in holdout)
    active_dev = sum(row["activations"] for row in dev)
    active_holdout = sum(row["activations"] for row in holdout)
    used_dev = sum(row["downstream_cash_used"] for row in dev)
    used_holdout = sum(row["downstream_cash_used"] for row in holdout)
    failures = sum(row["obligation_failures"] for row in delta_rows)
    productivity = sum(row["productivity_loss"] for row in delta_rows)
    survival = sum(row["survival_loss"] for row in delta_rows)
    positive_dev_opponents = {
        opponent
        for opponent in {row["opponent"] for row in dev}
        if _mean(
            row["delta_m"] for row in dev if row["opponent"] == opponent
        )
        > 0
    }
    promote = (
        active_dev > 0
        and active_holdout > 0
        and used_dev > 0
        and used_holdout > 0
        and failures == 0
        and productivity == 0
        and survival == 0
        and all_nonnegative
        and not repeated_negative
        and len(positive_dev_opponents) >= 2
        and dev_mean > 0
        and holdout_mean > 0
    )
    falsifiers: list[str] = []
    if active_dev == 0 or active_holdout == 0:
        falsifiers.append(
            "no reachable discretionary excess on both dev and holdout"
        )
    if used_dev == 0 or used_holdout == 0:
        falsifiers.append(
            "liberated cash was not productively redeployed on both splits"
        )
    if failures or productivity or survival:
        falsifiers.append(
            "lean reserve caused obligation/productivity/survival loss"
        )
    if not all_nonnegative or repeated_negative:
        falsifiers.append("paired margin flips materially by seat/opponent")
    if len(positive_dev_opponents) < 2:
        falsifiers.append("gain does not span two dev opponent regimes")
    if holdout_mean <= 0:
        falsifiers.append("improvement disappeared on untouched holdout")
    return {
        "conclusion": "PROMOTE_RESEARCH_CANDIDATE" if promote else "NO_PROMOTION",
        "selected_arm": ARM_MIN if promote else None,
        "dev_mean_delta_m": dev_mean,
        "holdout_mean_delta_m": holdout_mean,
        "active_dev_windows": active_dev,
        "active_holdout_windows": active_holdout,
        "dev_downstream_cash_used": used_dev,
        "holdout_downstream_cash_used": used_holdout,
        "obligation_failures": failures,
        "productivity_loss": productivity,
        "survival_loss": survival,
        "strata": strata,
        "falsifiers": falsifiers,
    }


def _window_census(runs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        identity = _identity(run)
        for window in run["decision_windows"]:
            oracle = compute_reserve_oracle(window["snapshot"])
            rows.append(
                {
                    "run_id": identity.run_id,
                    "split": identity.split,
                    "arm": identity.arm,
                    "opponent": identity.opponent,
                    "seed": identity.seed,
                    "seat": identity.seat,
                    "pair_id": identity.pair_id,
                    "window_id": window["window_id"],
                    "next_boundary_step": oracle["next_boundary_step"],
                    "feed_on_hand": oracle["feed_on_hand"],
                    "source_bound_obligations": oracle[
                        "source_bound_obligations"
                    ],
                    "obligation_sources": oracle["obligation_sources"],
                    "owned_feed_applied": oracle["owned_feed_applied"],
                    "min_provable_fresh": oracle["min_provable_fresh"],
                    "current_authored": oracle["arms"][ARM_CURRENT]["authored"],
                    "current_executable": oracle["arms"][ARM_CURRENT][
                        "executable"
                    ],
                    "min_executable": oracle["arms"][ARM_MIN]["executable"],
                    "plus_one_executable": oracle["arms"]["PLUS_ONE"][
                        "executable"
                    ],
                    "current_authored_rows": oracle["arms"][ARM_CURRENT][
                        "authored_rows"
                    ],
                    "current_executable_rows": oracle["arms"][ARM_CURRENT][
                        "executable_rows"
                    ],
                    "units_removed": oracle["units_removed"],
                    "cash_tied_in_discretionary_feed": oracle[
                        "cash_tied_in_discretionary_feed"
                    ],
                    "safe_to_lean": oracle["safe_to_lean"],
                    "reachable_excess": oracle["reachable_excess"],
                    "oracle_sha256": oracle["oracle_sha256"],
                }
            )
    return rows


def analyze_document(document: Mapping[str, Any]) -> dict[str, Any]:
    _require(document.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    authority = _validate_authority(document)
    runs = document.get("runs")
    _require(isinstance(runs, list), "runs must be a list")
    metrics = [analyze_run(run) for run in runs]
    design = _validate_design(metrics)
    deltas = _paired_deltas(metrics)
    census = _window_census(runs)
    gate = _promotion_gate(deltas)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "authority": authority,
        "design": design,
        "promotion": gate,
        "census": census,
        "paired_deltas": deltas,
        "runs": [metric.row() for metric in metrics],
        "input_sha256": sha256_json(document),
    }
    report["report_sha256"] = sha256_json(report)
    return report
