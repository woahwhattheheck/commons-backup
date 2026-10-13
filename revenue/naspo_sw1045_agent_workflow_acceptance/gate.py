from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

if __package__:
    from .validation import (
        GateError,
        RECEIPT_SCHEMA,
        SCHEMA,
        _instant,
        _normalize_packet,
        _strict_dict,
        load_json_strict,
        sha256_json,
    )
else:
    from validation import (
        GateError,
        RECEIPT_SCHEMA,
        SCHEMA,
        _instant,
        _normalize_packet,
        _strict_dict,
        load_json_strict,
        sha256_json,
    )

def expected_action_digest(packet: Mapping[str, Any]) -> str:
    normalized = _normalize_packet(packet)
    bound = {
        "workflow_id": normalized["workflow_id"],
        "request_id": normalized["request_id"],
        "principal_id": normalized["principal_id"],
        "resource_scope": normalized["resource_scope"],
        "action": normalized["action"],
        "policy": normalized["policy"],
        "snapshot": normalized["snapshot"],
    }
    return sha256_json(bound)


def expected_idempotency_key(packet: Mapping[str, Any]) -> str:
    normalized = _normalize_packet(packet)
    return sha256_json({
        "schema": "naspo-sw1045-idempotency/v1",
        "workflow_id": normalized["workflow_id"],
        "request_id": normalized["request_id"],
        "action_digest": expected_action_digest(normalized),
    })


def _semantic_holds(packet: dict[str, Any], trusted_now: datetime) -> tuple[list[str], dict[str, Any]]:
    holds: list[str] = []
    captured = _instant(packet["snapshot"]["captured_at"], "snapshot.captured_at")
    approved = _instant(packet["approval"]["approved_at"], "approval.approved_at")
    expires = _instant(packet["approval"]["expires_at"], "approval.expires_at")
    max_age = packet["snapshot"]["max_age_seconds"]

    if captured > trusted_now:
        holds.append("SNAPSHOT_FROM_FUTURE")
    elif (trusted_now - captured).total_seconds() > max_age:
        holds.append("SNAPSHOT_STALE")

    expected_action = expected_action_digest(packet)
    if packet["approval"]["action_digest"] != expected_action:
        holds.append("APPROVAL_ACTION_BINDING_MISMATCH")
    if approved < captured:
        holds.append("APPROVAL_PREDATES_SNAPSHOT")
    if approved > trusted_now:
        holds.append("APPROVAL_FROM_FUTURE")
    if expires <= approved:
        holds.append("APPROVAL_EXPIRY_INVALID")
    elif trusted_now >= expires:
        holds.append("APPROVAL_EXPIRED")

    expected_idem = expected_idempotency_key(packet)
    seen_attempt_ids: set[str] = set()
    successful_effects: set[str] = set()
    success_seen = False
    unresolved_unknown_seen = False
    previous_dispatch: datetime | None = None

    for idx, attempt in enumerate(packet["attempts"]):
        label = f"ATTEMPT_{idx}"
        if attempt["attempt_id"] in seen_attempt_ids:
            holds.append(f"{label}_DUPLICATE_ATTEMPT_ID")
        seen_attempt_ids.add(attempt["attempt_id"])
        if attempt["idempotency_key"] != expected_idem:
            holds.append(f"{label}_IDEMPOTENCY_KEY_MISMATCH")

        dispatched = _instant(attempt["dispatched_at"], f"attempts[{idx}].dispatched_at")
        if dispatched < approved:
            holds.append(f"{label}_DISPATCH_BEFORE_APPROVAL")
        if dispatched > trusted_now:
            holds.append(f"{label}_DISPATCH_FROM_FUTURE")
        if previous_dispatch is not None and dispatched < previous_dispatch:
            holds.append(f"{label}_DISPATCH_ORDER_INVALID")
        previous_dispatch = dispatched

        if success_seen:
            holds.append(f"{label}_DISPATCH_AFTER_EFFECT_CONFIRMED")
        if unresolved_unknown_seen:
            holds.append(f"{label}_DISPATCH_AFTER_UNRESOLVED_UNKNOWN")

        transport = attempt["transport_result"]
        recon = attempt["reconciliation"]
        effect = attempt["provider_effect_id"]
        state_digest = attempt["provider_state_digest"]
        reconciled_at = attempt["reconciled_at"]

        if transport == "SUCCESS":
            if recon != "NONE" or reconciled_at is not None:
                holds.append(f"{label}_SUCCESS_RECONCILIATION_SHOULD_BE_NONE")
            if effect is None or state_digest is None:
                holds.append(f"{label}_SUCCESS_MISSING_PROVIDER_EVIDENCE")
            else:
                success_seen = True
                successful_effects.add(effect)
        elif transport == "FAILURE":
            if effect is not None or state_digest is not None:
                holds.append(f"{label}_FAILURE_HAS_EFFECT_EVIDENCE")
            if recon != "NONE" or reconciled_at is not None:
                holds.append(f"{label}_FAILURE_RECONCILIATION_SHOULD_BE_NONE")
        else:  # UNKNOWN
            if recon == "NONE" or reconciled_at is None:
                holds.append(f"{label}_UNKNOWN_NOT_RECONCILED")
                unresolved_unknown_seen = True
            else:
                reconciled = _instant(reconciled_at, f"attempts[{idx}].reconciled_at")
                if reconciled < dispatched:
                    holds.append(f"{label}_RECONCILIATION_BEFORE_DISPATCH")
                if reconciled > trusted_now:
                    holds.append(f"{label}_RECONCILIATION_FROM_FUTURE")
                if recon == "SUCCEEDED":
                    if effect is None or state_digest is None:
                        holds.append(f"{label}_RECONCILED_SUCCESS_MISSING_EVIDENCE")
                    else:
                        success_seen = True
                        successful_effects.add(effect)
                elif recon in {"FAILED", "NOT_FOUND"}:
                    if effect is not None or state_digest is not None:
                        holds.append(f"{label}_RECONCILED_NO_EFFECT_HAS_EFFECT_EVIDENCE")
                elif recon == "AMBIGUOUS":
                    holds.append(f"{label}_RECONCILIATION_AMBIGUOUS")
                    unresolved_unknown_seen = True

    if len(successful_effects) > 1:
        holds.append("MULTIPLE_PROVIDER_EFFECTS")

    facts = {
        "expected_action_digest": expected_action,
        "expected_idempotency_key": expected_idem,
        "attempt_count": len(packet["attempts"]),
        "provider_effect_count": len(successful_effects),
        "provider_effect_confirmed": bool(successful_effects),
    }
    return sorted(set(holds)), facts


def compile_trace(packet: Any, *, trusted_now: str) -> dict[str, Any]:
    normalized = _normalize_packet(packet)
    now = _instant(trusted_now, "trusted_now")
    holds, facts = _semantic_holds(normalized, now)
    if holds:
        status = "HOLD"
    elif not normalized["attempts"]:
        status = "PREFLIGHT_EVIDENCE_READY"
    else:
        status = "EXECUTION_EVIDENCE_VALID"

    packet_digest = sha256_json(normalized)
    decision_core = {
        "schema": RECEIPT_SCHEMA,
        "packet_digest": packet_digest,
        "trusted_now": trusted_now,
        "status": status,
        "holds": holds,
        "facts": facts,
        "external_action_authorized": False,
        "payment_authorized": False,
        "submission_authorized": False,
        "revenue_recognized": False,
    }
    receipt_digest = sha256_json(decision_core)
    return {**decision_core, "receipt_digest": receipt_digest}


def verify_receipt(packet: Any, *, trusted_now: str, receipt: Any) -> bool:
    candidate = _strict_dict(receipt, "receipt")
    expected = compile_trace(packet, trusted_now=trusted_now)
    return candidate == expected


def make_packet(
    *,
    workflow_id: str,
    request_id: str,
    principal_id: str,
    resource_scope: str,
    operation: str,
    target: str,
    payload_digest: str,
    policy_version: str,
    policy_digest: str,
    snapshot_digest: str,
    captured_at: str,
    max_age_seconds: int,
    approver_id: str,
    role: str,
    approved_at: str,
    expires_at: str,
    attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "schema": SCHEMA,
        "workflow_id": workflow_id,
        "request_id": request_id,
        "principal_id": principal_id,
        "resource_scope": resource_scope,
        "action": {"operation": operation, "target": target, "payload_digest": payload_digest},
        "policy": {"version": policy_version, "digest": policy_digest},
        "snapshot": {"digest": snapshot_digest, "captured_at": captured_at, "max_age_seconds": max_age_seconds},
        "approval": {
            "approver_id": approver_id,
            "role": role,
            "action_digest": "0" * 64,
            "approved_at": approved_at,
            "expires_at": expires_at,
        },
        "attempts": attempts or [],
    }
    packet["approval"]["action_digest"] = expected_action_digest(packet)
    idem = expected_idempotency_key(packet)
    for attempt in packet["attempts"]:
        attempt["idempotency_key"] = idem
    return packet
