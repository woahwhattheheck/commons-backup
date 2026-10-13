#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed validator for cross-identity historical Gemini lineages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import check_ledger as C

SCHEMA = "titan-v4-gemini-labeled-history/v1"
REQUIRED_IDS = frozenset({
    "gemini.endgame-calendar-skip",
    "gemini.endgame-glut-bleed",
    "gemini.flash-market-goop",
    "gemini.idle-service",
    "gemini.legacy-g01-e11",
    "gemini.legacy-g01-e20",
    "gemini.legacy-g01-o01",
    "gemini.legacy-g01-shop",
    "gemini.meridian-adaptive-recourse",
    "gemini.meridian-hidden-inventory",
    "gemini.pro-capital",
    "gemini.s33-stratum",
})
MUST_STAY_BLOCKED = frozenset({
    "gemini.endgame-calendar-skip",
    "gemini.endgame-glut-bleed",
    "gemini.idle-service",
    "gemini.meridian-adaptive-recourse",
    "gemini.pro-capital",
    "gemini.s33-stratum",
})
STALE_DONOR_BASENAMES = frozenset({"gemini_market_certificate.py"})

# Historical attribution is part of the theorem, not editable commentary.  The
# earlier donor deliberately quarantined cross-identity labels until exact
# source custody was recovered.  Lock each admitted row to the recovered source
# statement and the exact PR ancestry set that supports that statement.  Any
# future provenance improvement must deliberately update this contract + tests;
# arbitrary non-empty prose can never mint or relabel a Gemini family.
SOURCE_LINEAGE_LOCKS = {
    "gemini.endgame-calendar-skip": (
        "Historical Gemini endgame family recorded by current V4 GEMINI-CONVERGENCE; "
        "the literal calendar-only rule was intentionally not transplanted."
    ),
    "gemini.endgame-glut-bleed": (
        "Historical Gemini endgame family recorded by current V4 GEMINI-CONVERGENCE; "
        "blanket glut selling was intentionally not transplanted."
    ),
    "gemini.flash-market-goop": (
        "Gemini Flash market lane launched under operation titan-gemini-flash-market-20260909 "
        "with catalog model gemini-3.8-flash-high; historical donor converges its useful market "
        "ideas into current V4 market authorities."
    ),
    "gemini.idle-service": (
        "Historical Gemini idle-hands handoff preserved in the current V4 idle-hands donor "
        "package; exact independently tested donor bytes are retained but not activated."
    ),
    "gemini.legacy-g01-e11": (
        "Gemini G01 commit 3379fd799766609691b4bb777e13f7b3cae0da00 / PR #11371 ancestry. "
        "Current V4 convergence records the broad historical rule as too coarse and competitively negative."
    ),
    "gemini.legacy-g01-e20": (
        "Gemini G01 commit 3379fd799766609691b4bb777e13f7b3cae0da00 / PR #11371 ancestry; "
        "current V4 executable-prefix HIRE authority supersedes the crude guard."
    ),
    "gemini.legacy-g01-o01": (
        "Gemini G01 commit 3379fd799766609691b4bb777e13f7b3cae0da00 / PR #11371 ancestry; "
        "static archetypes are retired in current V4."
    ),
    "gemini.legacy-g01-shop": (
        "Gemini G01 commit 3379fd799766609691b4bb777e13f7b3cae0da00 / PR #11371 ancestry; "
        "fixed absorption weights are superseded by current source-bound demand models."
    ),
    "gemini.meridian-adaptive-recourse": (
        "Custom Gemini MERIDIAN Slack result (message p1788822548344359) proposed identical-prefix "
        "public-observation recourse; PR #10008 implemented the T15 adaptive authority and PR #10225 "
        "tightened exact continuation-prefix custody."
    ),
    "gemini.meridian-hidden-inventory": (
        "Custom Gemini MERIDIAN Slack result (message p1788816451643229) proposed public cash/mass-balance "
        "hidden-state feasibility; later T15 joint-capacity and interval-family work in PRs #10377/#10395 "
        "implemented stronger bounded descendants."
    ),
    "gemini.pro-capital": (
        "Gemini Pro capital lane launched under operation titan-gemini-pro-capital-20260909 with catalog "
        "model gemini-3.1-pro-high; current V4 early-capital authority owns the source-safe descendants."
    ),
    "gemini.s33-stratum": (
        "Historical Gemini STRATUM row-shed lane; current row-shed-sell-order package owns the single "
        "V4 implementation seam."
    ),
}
PROVENANCE_PULL_LOCKS = {
    "gemini.endgame-calendar-skip": (12796,),
    "gemini.endgame-glut-bleed": (12551, 12998),
    "gemini.flash-market-goop": (12846, 12883, 12962, 12965),
    "gemini.idle-service": (12618, 12812, 12884, 12920, 13015),
    "gemini.legacy-g01-e11": (11371, 11460, 12368, 12403, 12466, 12597, 12962, 13024),
    "gemini.legacy-g01-e20": (11371, 11460, 12643),
    "gemini.legacy-g01-o01": (11371, 11460, 12466, 12597, 12965, 13024),
    "gemini.legacy-g01-shop": (11371, 11460, 12803, 12846, 12892, 12910, 13018),
    "gemini.meridian-adaptive-recourse": (10008, 10225),
    "gemini.meridian-hidden-inventory": (10377, 10395),
    "gemini.pro-capital": (12967,),
    "gemini.s33-stratum": (12551, 12801, 12998),
}


class LabeledHistoryError(C.ConvergenceError):
    pass


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LabeledHistoryError(f"{field} must be a non-empty string")
    return value


def _check_validator_contract() -> None:
    if frozenset(SOURCE_LINEAGE_LOCKS) != REQUIRED_IDS:
        raise LabeledHistoryError("validator source-lineage lock set does not match required ids")
    if frozenset(PROVENANCE_PULL_LOCKS) != REQUIRED_IDS:
        raise LabeledHistoryError("validator PR-provenance lock set does not match required ids")


def validate_document(doc: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    _check_validator_contract()
    if doc.get("schema") != SCHEMA:
        raise LabeledHistoryError(f"schema must be {SCHEMA}")
    if doc.get("runtime_activation_implied") is not False:
        raise LabeledHistoryError("runtime_activation_implied must remain false")

    entries = doc.get("entries")
    if not isinstance(entries, list):
        raise LabeledHistoryError("entries must be a list")
    if doc.get("entry_count") != len(entries):
        raise LabeledHistoryError("entry_count mismatch")

    ids: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise LabeledHistoryError(f"entries[{index}] must be an object")
        entry_id = _nonempty(entry.get("id"), f"entries[{index}].id")
        ids.append(entry_id)
        for field in ("gemini_label", "source_lineage", "literal_claim", "best_form", "next_gate"):
            _nonempty(entry.get(field), f"{entry_id}.{field}")

        expected_lineage = SOURCE_LINEAGE_LOCKS.get(entry_id)
        if expected_lineage is None:
            raise LabeledHistoryError(f"{entry_id} has no authenticated source-lineage contract")
        if entry.get("source_lineage") != expected_lineage:
            raise LabeledHistoryError(f"{entry_id} source-lineage provenance drift")

        disposition = entry.get("disposition")
        activation = entry.get("activation")
        if disposition not in C.ALLOWED_DISPOSITIONS:
            raise LabeledHistoryError(f"{entry_id} invalid disposition {disposition!r}")
        if activation not in C.ALLOWED_ACTIVATIONS:
            raise LabeledHistoryError(f"{entry_id} invalid activation {activation!r}")
        if entry_id in MUST_STAY_BLOCKED:
            if disposition != "FIELD_BLOCKED" or activation != "BLOCKED":
                raise LabeledHistoryError(f"{entry_id} must remain FIELD_BLOCKED/BLOCKED")
            if entry.get("do_not_repeat_without_new_evidence") is not True:
                raise LabeledHistoryError(f"{entry_id} must remain durably fenced")

        evidence = entry.get("canonical_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise LabeledHistoryError(f"{entry_id} must have canonical_evidence")
        if len(evidence) != len(set(evidence)):
            raise LabeledHistoryError(f"{entry_id} has duplicate canonical evidence")
        for rel in evidence:
            if Path(str(rel)).name in STALE_DONOR_BASENAMES:
                raise LabeledHistoryError(f"{entry_id} points at stale donor-only evidence: {rel}")
            C._regular_file_under_v4(repo_root, rel, entry_id)

        pulls = entry.get("provenance_pull_numbers")
        if not isinstance(pulls, list) or not pulls:
            raise LabeledHistoryError(f"{entry_id} must retain provenance_pull_numbers")
        if any(type(value) is not int or value <= 0 for value in pulls):
            raise LabeledHistoryError(f"{entry_id} has invalid PR provenance")
        if pulls != sorted(set(pulls)):
            raise LabeledHistoryError(f"{entry_id} PR provenance must be sorted and unique")
        expected_pulls = PROVENANCE_PULL_LOCKS.get(entry_id)
        if expected_pulls is None or tuple(pulls) != expected_pulls:
            raise LabeledHistoryError(f"{entry_id} PR provenance drift")

    if len(ids) != len(set(ids)):
        raise LabeledHistoryError("duplicate entry id")
    actual = set(ids)
    if actual != REQUIRED_IDS:
        raise LabeledHistoryError(
            f"coverage mismatch missing={sorted(REQUIRED_IDS - actual)} extra={sorted(actual - REQUIRED_IDS)}"
        )
    if ids != sorted(ids):
        raise LabeledHistoryError("entries must be sorted by id")

    return {
        "status": "PASS",
        "schema": SCHEMA,
        "entry_count": len(ids),
        "blocked_count": sum(1 for e in entries if e["disposition"] == "FIELD_BLOCKED"),
        "corrected_count": sum(1 for e in entries if e["disposition"] == "CORRECTED_DESCENDANT"),
        "provenance_locked_count": len(ids),
    }


def validate_path(path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    path = path.resolve()
    root = repo_root if repo_root is not None else C.find_repo_root(path.parent)
    return validate_document(C.load_strict_json(path), root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "history",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("HISTORICAL-LABELED.json"),
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = validate_path(args.history, args.repo_root)
    except C.ConvergenceError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
