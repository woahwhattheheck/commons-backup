"""Deterministic 240-envelope acceptance panel for the evidence gate."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from . import engine

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def base_policy() -> dict[str, Any]:
    return {
        "schema": engine.POLICY_SCHEMA, "policy_id": "golden-policy", "generation": 1,
        "effective_at": "2026-09-01T00:00:00Z", "expires_at": "2026-10-01T00:00:00Z", "request_max_age_seconds": 300,
        "allowed_agents": [{"agent_id": "solstice", "version": "5.6", "roles": ["builder", "reviewer"]}],
        "rules": [
            {"rule_id": "read-public", "tool": "repo", "action": "read", "roles": ["builder", "reviewer"], "resource_prefixes": ["repo:public/"], "data_classes": ["PUBLIC"], "approval_kind": None, "max_cost_cents": 20, "window_seconds": 60, "max_calls_per_window": 1000, "max_cost_cents_per_window": 20000},
            {"rule_id": "write-private", "tool": "repo", "action": "write", "roles": ["builder"], "resource_prefixes": ["repo:workspace/"], "data_classes": ["INTERNAL"], "approval_kind": "HUMAN_CHANGE", "max_cost_cents": 100, "window_seconds": 60, "max_calls_per_window": 1000, "max_cost_cents_per_window": 100000},
        ],
    }


def request(i: int, *, action: str = "read", role: str = "builder", resource: str = "repo:public/project", data_class: str = "PUBLIC", cost: int = 5, approval_ids: list[str] | None = None) -> dict[str, Any]:
    return {"schema": engine.REQUEST_SCHEMA, "request_id": f"req-{i:03d}", "requested_at": "2026-09-17T08:59:30Z", "agent_id": "solstice", "agent_version": "5.6", "actor_role": role, "tool": "repo", "action": action, "resource": resource, "data_class": data_class, "estimated_cost_cents": cost, "operation_key": f"op-{i:03d}", "trace_id": f"trace-{i:03d}", "approval_ids": [] if approval_ids is None else approval_ids}


def authority_for(requests: list[dict[str, Any]]) -> dict[str, Any]:
    approvals = []
    for r in requests:
        if r["action"] == "write":
            aid = f"ap-{r['request_id']}"; r["approval_ids"] = [aid]
            approvals.append({"approval_id": aid, "kind": "HUMAN_CHANGE", "scope_sha256": engine.request_scope_sha(r), "issued_at": "2026-09-17T08:50:00Z", "expires_at": "2026-09-17T10:00:00Z", "issuer": "owner"})
    return {"schema": engine.AUTHORITY_SCHEMA, "authority_id": "golden-authority", "generation": 1, "approvals": approvals}


def empty_ledger() -> dict[str, Any]:
    return {"schema": engine.LEDGER_SCHEMA, "ledger_id": "golden-ledger", "generation": 1, "events": []}


def panel() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    # 192 known-good requests: 160 cheap public reads + 32 approved workspace writes.
    cases: list[tuple[str, dict[str, Any]]] = []
    for i in range(160): cases.append(("ALLOW", request(i)))
    for i in range(160, 192): cases.append(("ALLOW", request(i, action="write", resource="repo:workspace/project", data_class="INTERNAL", cost=25)))
    # Six independent defect families x eight = 48 HOLD.
    for i in range(192, 200): cases.append(("TOOL_ACTION_DISALLOWED", request(i, action="delete")))
    for i in range(200, 208): cases.append(("ROLE_RESOURCE_MISMATCH", request(i, role="reviewer", action="write", resource="repo:workspace/project", data_class="INTERNAL")))
    for i in range(208, 216): cases.append(("RESTRICTED_DATA_EXPOSURE", request(i, data_class="SECRET")))
    for i in range(216, 224): cases.append(("MISSING_APPROVAL", request(i, action="write", resource="repo:workspace/project", data_class="INTERNAL", approval_ids=[])))
    for i in range(224, 232): cases.append(("BUDGET_RATE_BREACH", request(i, cost=999)))
    for i in range(232, 240): cases.append(("REPLAY_COLLISION", request(i)))
    reqs = [r for _, r in cases]
    auth = authority_for(reqs)
    # Remove authority records for the intentional missing-approval family.
    missing_ids = {f"ap-req-{i:03d}" for i in range(216, 224)}
    auth["approvals"] = [a for a in auth["approvals"] if a["approval_id"] not in missing_ids]
    ledger = empty_ledger()
    # Seed eight replay collisions with matching operation keys, but fresh unrelated trace IDs.
    for j, i in enumerate(range(232, 240), start=1):
        body = {"schema": engine.EVENT_SCHEMA, "sequence": j, "prev_event_sha256": engine.GENESIS if j == 1 else ledger["events"][-1]["event_sha256"], "operation_key": f"op-{i:03d}", "trace_id": f"old-trace-{i:03d}", "request_sha256": "a" * 64, "occurred_at": "2026-09-17T08:58:00Z", "actor_role": "builder", "tool": "repo", "action": "read", "resource": "repo:public/project", "cost_cents": 1, "outcome": "SENT"}
        body["event_sha256"] = engine.canonical_sha(engine._event_body(body)); ledger["events"].append(body)
    return base_policy(), auth, ledger, cases


def run_panel() -> dict[str, Any]:
    policy, authority, ledger, cases = panel()
    psha = engine.canonical_sha(engine._normalize_policy(policy)); asha = engine.canonical_sha(engine._normalize_authority(authority)); lhead = engine.ledger_head(ledger)
    rows = []
    for expected, req in cases:
        receipt = engine.evaluate(policy, req, authority, ledger, expected_policy_sha256=psha, expected_authority_sha256=asha, expected_ledger_head=lhead, _now=NOW)
        rows.append({"request_id": req["request_id"], "expected": expected, "decision": receipt["decision"], "reasons": receipt["reasons"], "receipt_sha256": receipt["receipt_sha256"]})
    allowed = sum(row["decision"] == engine.EXECUTE_ALLOWED for row in rows)
    held = len(rows) - allowed
    result = {"schema": "tjlabs.agent-toolcall-golden/v1", "case_count": len(rows), "allowed": allowed, "held": held, "rows": rows}
    result["panel_sha256"] = engine.canonical_sha(result)
    return result


if __name__ == "__main__":
    print(engine.canonical_bytes(run_panel()).decode(), end="")
