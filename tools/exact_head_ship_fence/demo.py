"""Fresh synthetic READY example; no GitHub/provider call occurs."""
from __future__ import annotations

from datetime import datetime, timezone
import json

from .fence import compile_current, render_markdown


def snapshot() -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = "1" * 40
    base = "2" * 40
    return {
        "schema_version": 1,
        "repository": "example/repo",
        "base_branch": "main",
        "expected_pr_head": head,
        "current_pr_head": head,
        "construction_parent": base,
        "current_base_head": base,
        "observed_at": now,
        "max_age_seconds": 3600,
        "snapshot_complete": True,
        "refs": {"pr_ref_exists": True, "base_ref_exists": True},
        "topology": {
            "candidate_paths_known": True,
            "candidate_paths": [{"path": "src/example.py", "blob_sha": "3" * 40}],
            "base_delta_paths_known": True,
            "base_delta_paths": [],
            "evaluated_base_sha": base,
            "rejoin_proven": False,
            "rejoin_head_sha": None,
        },
        "check_policy": [{"name": "tests", "required": True, "allow_skipped": False}],
        "checks": [{
            "name": "tests",
            "run_id": "run-1",
            "head_sha": head,
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "observed_at": now,
        }],
        "review_policy": {"required": True, "min_passes": 1},
        "reviews": [{
            "review_id": "review-1",
            "reviewer": "independent-seat",
            "head_sha": head,
            "verdict": "PASS",
            "observed_at": now,
        }],
    }


def main() -> int:
    report = compile_current(snapshot())
    print(json.dumps(report, indent=2, sort_keys=True))
    print()
    print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
