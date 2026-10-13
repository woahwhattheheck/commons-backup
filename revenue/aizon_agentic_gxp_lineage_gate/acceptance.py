"""Deterministic synthetic acceptance fixture for the Aizon lineage gate."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from typing import Any

from .gate import compute_lineage_digest, evaluate, verify_receipt

BASE = datetime(2026, 9, 13, 9, 0, tzinfo=timezone.utc)


def _t(minutes: int) -> str:
    return (BASE + timedelta(minutes=minutes)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def policy() -> dict[str, Any]:
    return {
        "schema": "aizon-agentic-gxp-lineage-gate/v1",
        "policy_id": "synthetic-policy",
        "version": "2026.09",
        "valid_from": _t(-60),
        "valid_until": _t(24 * 60),
        "allowed_execution_roles": ["manufacturing-analyst"],
        "allowed_approver_roles": ["human-quality-reviewer"],
        "allowed_risks": ["LOW", "MEDIUM"],
        "max_source_age_s": 6 * 3600,
        "max_execution_age_s": 4 * 3600,
        "max_approval_age_s": 2 * 3600,
        "max_future_skew_s": 30,
    }


def fixture(index: int = 0) -> list[dict[str, Any]]:
    artifact = f"artifact-{index:03d}"
    source = {
        "event_id": f"src-{index:03d}", "kind": "SOURCE", "artifact_id": artifact, "occurred_at": _t(0),
        "body": {"source_snapshot_hash": _h(f"src:{index}"), "batch_context_hash": _h(f"batch:{index}"), "dataset_version": "synthetic-v1"},
    }
    change = {
        "event_id": f"chg-{index:03d}", "kind": "CHANGE_CONTROL", "artifact_id": artifact, "occurred_at": _t(1),
        "body": {
            "status": "APPROVED", "model_version": "model-7.3", "tools": {"oee-query": "2.1"},
            "prompt_policy_version": "prompt-policy-4", "allowed_risks": ["LOW", "MEDIUM"],
            "approved_at": _t(1), "expires_at": _t(180),
        },
    }
    execution = {
        "event_id": f"exe-{index:03d}", "kind": "EXECUTION", "artifact_id": artifact, "occurred_at": _t(5),
        "body": {
            "source_event_id": source["event_id"], "change_event_id": change["event_id"],
            "model_version": "model-7.3", "tools": {"oee-query": "2.1"}, "prompt_policy_version": "prompt-policy-4",
            "query_hash": _h(f"query:{index}"), "result_hash": _h(f"result:{index}"),
            "actor_id": f"operator-{index:03d}", "actor_role": "manufacturing-analyst", "intended_use_risk": "MEDIUM",
        },
    }
    lineage = compute_lineage_digest(source, change, execution)
    approval = {
        "event_id": f"app-{index:03d}", "kind": "HUMAN_APPROVAL", "artifact_id": artifact, "occurred_at": _t(10),
        "body": {
            "execution_event_id": execution["event_id"], "approver_id": f"reviewer-{index:03d}",
            "approver_role": "human-quality-reviewer", "decision": "APPROVE", "lineage_digest": lineage,
            "approved_at": _t(10), "expires_at": _t(120),
        },
    }
    return [approval, execution, source, change]  # deliberately out of arrival order


def run_acceptance() -> dict[str, Any]:
    counts = {"READY": 0, "HOLD": 0}
    reason_counts: dict[str, int] = {}
    receipts = []
    for index in range(100):
        events = fixture(index)
        if 80 <= index < 85:
            events[1]["body"]["model_version"] = "undeclared-model"
        elif 85 <= index < 90:
            events[0]["body"]["lineage_digest"] = "0" * 64
        elif 90 <= index < 95:
            events.append(deepcopy(events[2]))
            events[-1]["body"]["dataset_version"] = "conflicting-version"
        elif 95 <= index < 100:
            events[1]["body"]["intended_use_risk"] = "HIGH"
        receipt = evaluate(events, policy(), evaluated_at=_t(30))
        counts[receipt["status"]] += 1
        for reason in receipt["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        receipts.append(receipt)
    clean = evaluate(fixture(777), policy(), evaluated_at=_t(30))
    replay = list(reversed(fixture(777))) + [deepcopy(fixture(777)[0])]
    replay_receipt = evaluate(replay, policy(), evaluated_at=_t(30))
    return {
        "schema": "aizon-agentic-gxp-lineage-acceptance/v1",
        "counts": counts,
        "reason_counts": dict(sorted(reason_counts.items())),
        "clean_order_invariant": clean == replay_receipt,
        "clean_verifies": verify_receipt(clean, fixture(777), policy(), evaluated_at=_t(31)),
        "receipt_set_digest": hashlib.sha256(json.dumps(receipts, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), sort_keys=True, indent=2))
