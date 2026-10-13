"""Fail-closed promotion authority for TITAN V5 lean-feed research.

The economics evaluator in ``lean_feed_gate`` answers a narrower question:
whether a normalized evidence document would support the MIN_PROVABLE arm on
its own terms. This module decides whether that candidate conclusion is allowed
to cross the promotion boundary.

Synthetic or caller-authored manifests are never promotion authority. A root
must be committed in ``TRUSTED_AUTHORITY_ROOT_SHA256`` after independent source
custody review. The set is intentionally empty while the D2 source contract is
blocked.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from lean_feed_core import (
    ARM_MIN,
    ARMS,
    D2_ARCHIVE_SHA256,
    D2_MEMBER_COUNT,
    _require,
    compute_reserve_oracle,
    sha256_json,
)
from lean_feed_gate import analyze_document as analyze_candidate_document

AUTHORITY_ROOT_SCHEMA = "titan-v5-lean-feed-authority-root-v1"
PROMOTE = "PROMOTE_RESEARCH_CANDIDATE"
NO_PROMOTION = "NO_PROMOTION"
SOURCE_MODEL_BLOCKED = "SOURCE_MODEL_BLOCKED"
SOURCE_AUTHORITY_RECEIPT_SHA256 = (
    "297f7cf6e38f8e4be7fd00387e228194e366648570b781cd7abe05be41f2d4d8"
)
SOURCE_BLOCK_REASON = (
    "retained official source is WHEAT-only and exact D2 archive member bytes "
    "are not retained; synthetic legacy economics cannot authorize promotion"
)

# Promotion authority is a code-retained trust decision, not a field that an
# evidence producer can mint. Add a reviewed root digest only in a dedicated
# source-custody change. The D2 source-contract fix-forward currently blocks
# that step, so the correct set is empty.
TRUSTED_AUTHORITY_ROOT_SHA256: frozenset[str] = frozenset()


def _hex_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _cell_key(run: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        run.get("split"),
        run.get("opponent"),
        run.get("seed"),
        run.get("seat"),
        run.get("pair_id"),
    )


def _validate_exact_cells(runs: Sequence[Mapping[str, Any]]) -> None:
    """Reject duplicate arm rows that set-based coverage used to hide."""
    counts: Counter[tuple[Any, ...]] = Counter()
    for run in runs:
        _require(isinstance(run, Mapping), "run must be an object")
        counts[(*_cell_key(run), run.get("arm"))] += 1

    cells = {_cell_key(run) for run in runs}
    for cell in cells:
        for arm in ARMS:
            _require(
                counts[(*cell, arm)] == 1,
                f"cell {cell} must contain exactly one {arm} row",
            )


def _validate_initial_snapshots(runs: Sequence[Mapping[str, Any]]) -> None:
    """All counterfactual arms in one paired cell must start identically."""
    snapshots: dict[tuple[Any, ...], dict[str, str]] = defaultdict(dict)
    for run in runs:
        windows = run.get("decision_windows")
        _require(isinstance(windows, list) and windows, "decision_windows required")
        first = windows[0]
        _require(isinstance(first, Mapping), "decision window invalid")
        snapshot = first.get("snapshot")
        _require(isinstance(snapshot, Mapping), "initial snapshot required")
        snapshots[_cell_key(run)][str(run.get("arm"))] = sha256_json(snapshot)

    for cell, by_arm in snapshots.items():
        _require(set(by_arm) == set(ARMS), f"cell {cell} missing arm snapshot")
        _require(
            len(set(by_arm.values())) == 1,
            f"cell {cell} has cross-arm initial snapshot mismatch",
        )


def _validate_obligation_census_and_cash(runs: Sequence[Mapping[str, Any]]) -> None:
    """Require source-bound lean activations and single-use cash liberation IDs."""
    for run in runs:
        run_id = run.get("run_id")
        seen_liberation_ids: set[str] = set()
        windows = run.get("decision_windows")
        _require(isinstance(windows, list) and windows, "decision_windows required")
        for window in windows:
            _require(isinstance(window, Mapping), "decision window invalid")
            oracle = compute_reserve_oracle(window.get("snapshot"))
            decision = window.get("decision")
            _require(isinstance(decision, Mapping), "decision required")
            active_lean = (
                run.get("arm") == ARM_MIN
                and oracle["reachable_excess"]
                and decision.get("candidate_active") is True
            )
            if active_lean:
                _require(
                    oracle["next_boundary_step"] is not None,
                    f"{run_id}: null source-proven obligation boundary",
                )
                _require(
                    bool(oracle["obligation_sources"]),
                    f"{run_id}: empty source-proven obligation census",
                )

                liberation_id = decision.get("liberation_id")
                _require(
                    isinstance(liberation_id, str) and liberation_id,
                    f"{run_id}: liberation_id required",
                )
                _require(
                    liberation_id not in seen_liberation_ids,
                    f"{run_id}: reused liberation_id {liberation_id}",
                )
                seen_liberation_ids.add(liberation_id)

                liberated = decision.get("cash_liberated")
                _require(
                    isinstance(liberated, (int, float))
                    and not isinstance(liberated, bool)
                    and math.isfinite(float(liberated))
                    and float(liberated) >= 0.0,
                    f"{run_id}: invalid cash_liberated",
                )
                claimed = 0.0
                uses = window.get("cash_uses", [])
                _require(isinstance(uses, list), "cash_uses must be a list")
                for use in uses:
                    _require(isinstance(use, Mapping), "cash use invalid")
                    amount = use.get("amount")
                    _require(
                        isinstance(amount, (int, float))
                        and not isinstance(amount, bool)
                        and math.isfinite(float(amount))
                        and float(amount) >= 0.0,
                        f"{run_id}: invalid cash use amount",
                    )
                    claimed += float(amount)
                _require(
                    claimed <= float(liberated) + 1e-9,
                    f"{run_id}: cash use exceeds liberated cash",
                )


def _validate_authority_root(document: Mapping[str, Any]) -> tuple[bool, str | None]:
    root = document.get("authority_root")
    if root is None:
        return False, None
    _require(isinstance(root, Mapping), "authority_root must be an object")
    _require(
        root.get("schema") == AUTHORITY_ROOT_SCHEMA,
        f"authority_root.schema must be {AUTHORITY_ROOT_SCHEMA}",
    )

    authority = document.get("authority")
    selection = document.get("candidate_selection")
    _require(isinstance(authority, Mapping), "authority required")
    _require(isinstance(selection, Mapping), "candidate_selection required")

    bindings = {
        "archive_sha256": authority.get("archive_sha256"),
        "dev_manifest_sha256": authority.get("dev_manifest_sha256"),
        "holdout_manifest_sha256": authority.get("holdout_manifest_sha256"),
        "selection_manifest_sha256": selection.get("selection_manifest_sha256"),
        "evidence_sha256": sha256_json(
            {
                "schema": document.get("schema"),
                "authority": authority,
                "candidate_selection": selection,
                "runs": document.get("runs"),
            }
        ),
    }
    for key, expected in bindings.items():
        actual = root.get(key)
        _require(_hex_digest(actual), f"authority_root.{key} invalid")
        _require(actual == expected, f"authority_root.{key} binding mismatch")

    root_sha256 = sha256_json(root)
    return root_sha256 in TRUSTED_AUTHORITY_ROOT_SHA256, root_sha256


def _result_bound_digest(run: Mapping[str, Any]) -> str:
    """Bind terminal results to the evidence identity, not windows alone."""
    return sha256_json(
        {
            "run_id": run.get("run_id"),
            "decision_windows": run.get("decision_windows"),
            "result": run.get("result"),
        }
    )


def _suppress_blocked_source_economics(report: dict[str, Any]) -> None:
    """Expose source custody state without publishing fictional-domain economics."""
    promotion = report["promotion"]
    promotion.update(
        {
            "conclusion": SOURCE_MODEL_BLOCKED,
            "selected_arm": None,
            "dev_mean_delta_m": 0.0,
            "holdout_mean_delta_m": 0.0,
            "active_dev_windows": 0,
            "active_holdout_windows": 0,
            "dev_downstream_cash_used": 0.0,
            "holdout_downstream_cash_used": 0.0,
            "obligation_failures": 0,
            "productivity_loss": 0.0,
            "survival_loss": 0.0,
            "strata": [],
            "falsifiers": [SOURCE_BLOCK_REASON],
            "source_model_state": SOURCE_MODEL_BLOCKED,
        }
    )
    report["authority"] = {
        "archive_sha256": D2_ARCHIVE_SHA256,
        "archive_member_count": D2_MEMBER_COUNT,
        "source_model_state": SOURCE_MODEL_BLOCKED,
        "promotion_authorized": False,
        "source_authority_receipt_sha256": SOURCE_AUTHORITY_RECEIPT_SHA256,
    }
    report["design"] = {
        "cells": 0,
        "dev_opponents": [],
        "holdout_opponents": [],
    }
    report["census"] = []
    report["paired_deltas"] = []
    report["runs"] = []


def analyze_authoritative_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return candidate economics plus an independently rooted final verdict."""
    runs = document.get("runs")
    _require(isinstance(runs, list) and runs, "runs must be a non-empty list")
    _validate_exact_cells(runs)
    _validate_initial_snapshots(runs)
    _validate_obligation_census_and_cash(runs)
    authority_verified, root_sha256 = _validate_authority_root(document)

    report = analyze_candidate_document(document)
    promotion = report["promotion"]
    candidate_conclusion = promotion["conclusion"]
    candidate_selected_arm = promotion["selected_arm"]

    run_by_id = {run["run_id"]: run for run in runs}
    for row in report["runs"]:
        row["evidence_sha256"] = _result_bound_digest(run_by_id[row["run_id"]])

    promotion["candidate_conclusion"] = candidate_conclusion
    promotion["candidate_selected_arm"] = candidate_selected_arm
    promotion["authority_verified"] = authority_verified
    promotion["authority_root_sha256"] = root_sha256

    if candidate_conclusion == PROMOTE and not authority_verified:
        _suppress_blocked_source_economics(report)

    report["hardening"] = {
        "exact_one_row_per_cell_arm": True,
        "cross_arm_initial_snapshot_bound": True,
        "source_proven_obligation_boundary_required_for_activation": True,
        "liberation_id_single_use_per_run": True,
        "terminal_result_bound_in_run_digest": True,
        "authority_root_schema": AUTHORITY_ROOT_SCHEMA,
        "authority_verified": authority_verified,
        "trusted_root_count": len(TRUSTED_AUTHORITY_ROOT_SHA256),
        "source_model_state": (
            "SOURCE_AUTHORITY_VERIFIED" if authority_verified else SOURCE_MODEL_BLOCKED
        ),
    }

    report.pop("report_sha256", None)
    report["report_sha256"] = sha256_json(report)
    return report


__all__ = [
    "AUTHORITY_ROOT_SCHEMA",
    "SOURCE_MODEL_BLOCKED",
    "TRUSTED_AUTHORITY_ROOT_SHA256",
    "analyze_authoritative_document",
]
