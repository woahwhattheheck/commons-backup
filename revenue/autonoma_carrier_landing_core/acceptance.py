# SPDX-License-Identifier: MIT
"""Deterministic six-carrier acceptance run for the Autonoma delivery core."""

from __future__ import annotations

import hashlib
import json

from revenue.autonoma_carrier_landing_core.core import (
    apply_plan,
    build_plan,
    empty_state,
    make_branch,
)


BASE = hashlib.sha256(b"autonoma-acceptance-base").hexdigest()
STALE = hashlib.sha256(b"autonoma-stale-base").hexdigest()
BAD_MANIFEST = "f" * 64


def _tree(label: str) -> str:
    return hashlib.sha256(f"candidate-tree:{label}".encode()).hexdigest()


def fixture() -> dict:
    """Return six branches: two admissible and four distinct fail-closed holds."""
    return {
        "schema_version": 1,
        "batch_id": "autonoma-six-branch-acceptance-v1",
        "base_sha": BASE,
        "carrier_prefix": "carrier/",
        "branches": [
            make_branch(
                branch_id="carrier-alpha",
                order=10,
                base_sha=BASE,
                paths=["carrier/alpha/adapter.py", "carrier/alpha/test_adapter.py"],
                purpose="carrier-only alpha change",
                candidate_tree_sha=_tree("alpha"),
            ),
            make_branch(
                branch_id="forbidden-path",
                order=20,
                base_sha=BASE,
                paths=["production/payment_router.py"],
                purpose="attempted protected-surface edit",
                candidate_tree_sha=_tree("forbidden"),
            ),
            make_branch(
                branch_id="stale-base",
                order=30,
                base_sha=STALE,
                paths=["carrier/stale/adapter.py"],
                purpose="carrier based on stale main",
                candidate_tree_sha=_tree("stale"),
            ),
            make_branch(
                branch_id="manifest-mismatch",
                order=40,
                base_sha=BASE,
                paths=["carrier/manifest/adapter.py"],
                purpose="carrier with forged manifest digest",
                candidate_tree_sha=_tree("manifest"),
                manifest_digest_override=BAD_MANIFEST,
            ),
            make_branch(
                branch_id="test-failure",
                order=50,
                base_sha=BASE,
                paths=["carrier/red/adapter.py"],
                purpose="carrier with failing premerge suite",
                candidate_tree_sha=_tree("red"),
                premerge_status="FAIL",
            ),
            make_branch(
                branch_id="carrier-omega",
                order=60,
                base_sha=BASE,
                paths=["carrier/omega/adapter.py", "carrier/omega/test_adapter.py"],
                purpose="carrier-only omega change",
                candidate_tree_sha=_tree("omega"),
            ),
        ],
    }


def run_acceptance() -> dict:
    plan = build_plan(fixture())
    first = apply_plan(plan, empty_state())
    second = apply_plan(plan, first.state)
    expected_holds = {
        "forbidden-path": ["FORBIDDEN_PATH"],
        "stale-base": ["STALE_BASE"],
        "manifest-mismatch": ["MANIFEST_MISMATCH"],
        "test-failure": ["TEST_FAILURE"],
    }
    actual = {row["branch_id"]: row for row in plan["branches"]}

    checks = {
        "exact_landing_order": plan["landing_order"]
        == ["carrier-alpha", "carrier-omega"],
        "exact_hold_reasons": all(
            actual[branch]["disposition"] == "HOLD"
            and actual[branch]["reason_codes"] == reasons
            for branch, reasons in expected_holds.items()
        ),
        "first_run_two_merges": first.new_merges == 2,
        "green_after_each": all(
            event["main_green_after"] is True for event in first.merge_events
        ),
        "no_force": all(event["force"] is False for event in first.merge_events),
        "no_branch_delete": all(
            event["delete_branch"] is False for event in first.merge_events
        ),
        "replay_zero_merges": second.new_merges == 0,
        "replay_identical_receipt": second.receipt == first.receipt,
        "replay_state_stable": second.state == first.state,
    }
    if not all(checks.values()):
        failed = [name for name, value in checks.items() if not value]
        raise SystemExit("acceptance failed: " + ", ".join(failed))

    return {
        "status": "PASS",
        "checks": checks,
        "landing_order": plan["landing_order"],
        "holds": expected_holds,
        "receipt_sha256": plan["receipt_sha256"],
        "first_run_new_merges": first.new_merges,
        "replay_new_merges": second.new_merges,
    }


def main() -> int:
    print(json.dumps(run_acceptance(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
