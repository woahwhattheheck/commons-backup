from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any


EVALUATED_AT = "2026-09-17T12:00:00-04:00"
SOURCE_SHA = hashlib.sha256(b"travelers-agent-toolcall-evidence-fixture-v1").hexdigest()
ARG_SHA = hashlib.sha256(b"synthetic-redacted-arguments").hexdigest()


def _approval(call_id: str, index: int) -> dict[str, Any]:
    return {
        "approval_id": f"approval-{index:04d}",
        "call_id": call_id,
        "decision": "APPROVED",
        "approved_by_role": "human_approver",
        "approved_at": "2026-09-17T11:50:00-04:00",
        "expires_at": "2026-09-17T12:10:00-04:00",
    }


def _base(index: int, variant: int = 0) -> dict[str, Any]:
    call_id = f"call-{index:04d}"
    templates = (
        {
            "role": "service_agent",
            "tool": "policy_lookup",
            "action": "read",
            "resource": f"policy/P{index:04d}",
            "data_class": "PUBLIC_POLICY",
            "cost": 50,
            "effect": "READ_ONLY",
            "approval": None,
        },
        {
            "role": "adjuster",
            "tool": "claims_lookup",
            "action": "read",
            "resource": f"claim/C{index:04d}",
            "data_class": "MASKED_CLAIM",
            "cost": 100,
            "effect": "READ_ONLY",
            "approval": None,
        },
        {
            "role": "service_agent",
            "tool": "customer_notice",
            "action": "send",
            "resource": f"notice/N{index:04d}",
            "data_class": "CUSTOMER_CONTACT_TOKEN",
            "cost": 300,
            "effect": "MUTATING",
            "approval": "required",
        },
        {
            "role": "adjuster",
            "tool": "document_store",
            "action": "write",
            "resource": f"document/D{index:04d}",
            "data_class": "CLAIM_DOCUMENT_TOKEN",
            "cost": 500,
            "effect": "MUTATING",
            "approval": "required",
        },
    )
    template = templates[variant % len(templates)]
    approval = _approval(call_id, index) if template["approval"] else None
    return {
        "schema": "agent-toolcall-envelope/v1",
        "environment": "SYNTHETIC_NONPRODUCTION",
        "evaluated_at": EVALUATED_AT,
        "run_id": "travelers-acceptance-240",
        "call_id": call_id,
        "agent": {"id": "synthetic-agent", "version": "v1.0.0"},
        "actor": {"role": template["role"]},
        "request": {
            "tool": template["tool"],
            "action": template["action"],
            "target_resource": template["resource"],
            "data_class": template["data_class"],
            "arguments_sha256": ARG_SHA,
            "estimated_cost_minor": template["cost"],
            "effect": template["effect"],
        },
        "approval": approval,
        "idempotency_key": f"idem-{index:04d}",
        "trace": {
            "requested_at": "2026-09-17T11:55:00-04:00",
            "dispatched_at": None,
            "observed_at": None,
            "completed_at": None,
            "outcome": "NOT_DISPATCHED",
        },
        "source": {"fixture": True, "source_sha256": SOURCE_SHA},
    }


def acceptance_envelopes() -> list[dict[str, Any]]:
    envelopes = [_base(index, index % 4) for index in range(1, 193)]

    # Eight isolated DISALLOWED_TOOL_ACTION cases.
    for index in range(193, 201):
        item = _base(index, 0)
        item["request"]["action"] = "delete"
        envelopes.append(item)

    # Eight isolated ROLE_RESOURCE_MISMATCH cases.
    for index in range(201, 209):
        item = _base(index, 0)
        item["request"]["target_resource"] = f"payment/X{index:04d}"
        envelopes.append(item)

    # Eight isolated RESTRICTED_DATA_EXPOSURE cases.
    for index in range(209, 217):
        item = _base(index, 0)
        item["request"]["data_class"] = "FULL_SSN"
        envelopes.append(item)

    # Eight isolated MISSING_HUMAN_APPROVAL cases.
    for index in range(217, 225):
        item = _base(index, 2)
        item["approval"] = None
        envelopes.append(item)

    # Eight isolated BUDGET_RATE_BREACH cases.
    for index in range(225, 233):
        item = _base(index, 0)
        item["request"]["estimated_cost_minor"] = 251
        envelopes.append(item)

    # Eight isolated REPLAY_IDEMPOTENCY_COLLISION cases. Reuse eight keys from
    # the valid population while keeping call identity unique.
    for offset, index in enumerate(range(233, 241), start=1):
        item = _base(index, 0)
        item["idempotency_key"] = f"idem-{offset:04d}"
        item["trace"]["requested_at"] = "2026-09-17T11:59:00-04:00"
        envelopes.append(item)

    return envelopes


def expected_hold_distribution() -> dict[str, int]:
    return {
        "DISALLOWED_TOOL_ACTION": 8,
        "ROLE_RESOURCE_MISMATCH": 8,
        "RESTRICTED_DATA_EXPOSURE": 8,
        "MISSING_HUMAN_APPROVAL": 8,
        "BUDGET_RATE_BREACH": 8,
        "REPLAY_IDEMPOTENCY_COLLISION": 8,
    }


def cloned_acceptance_envelopes() -> list[dict[str, Any]]:
    return deepcopy(acceptance_envelopes())
