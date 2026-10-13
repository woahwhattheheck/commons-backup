#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Single fail-closed gate for every authenticated Gemini convergence layer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import check_full_coverage as D
import check_labeled_history as L
import check_ledger as C

TOTAL_DISTINCT = 37


def validate_all(base: Path, repo_root: Path | None = None) -> dict:
    base = base.resolve()
    root = repo_root if repo_root is not None else C.find_repo_root(base)

    master = C.load_strict_json(base / "GEMINI-ANTIGRAVITY.json")
    direct = C.load_strict_json(base / "HISTORICAL-DIRECT.json")
    labeled = C.load_strict_json(base / "HISTORICAL-LABELED.json")

    master_result = C.validate_document(master, root)
    direct_result = D.validate_history(direct, root)
    labeled_result = L.validate_document(labeled, root)

    master_ids = set(C.REQUIRED_IDS)
    direct_ids = set(D.HISTORICAL_IDS)
    labeled_ids = set(L.REQUIRED_IDS)
    overlaps = {
        "master_direct": sorted(master_ids & direct_ids),
        "master_labeled": sorted(master_ids & labeled_ids),
        "direct_labeled": sorted(direct_ids & labeled_ids),
    }
    if any(overlaps.values()):
        raise C.ConvergenceError(f"Gemini convergence ID overlap: {overlaps}")

    union = master_ids | direct_ids | labeled_ids
    if len(union) != TOTAL_DISTINCT:
        raise C.ConvergenceError(
            f"Gemini convergence union must contain {TOTAL_DISTINCT} distinct IDs, got {len(union)}"
        )

    return {
        "status": "PASS",
        "direct_author_messages": direct_result["direct_author_messages"],
        "recent_master": master_result["entry_count"],
        "direct_historical": direct_result["historical_propositions"],
        "cross_identity_historical": labeled_result["entry_count"],
        "combined_distinct_propositions": len(union),
        "runtime_activation_implied": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    try:
        result = validate_all(args.base, args.repo_root)
    except C.ConvergenceError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
