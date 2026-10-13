from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .contracts import (RouteScoutError, _CONTROL, _RESULT_FIELDS, CHANNEL_TYPES, PERMISSION_STATES, TERMINAL, _exact_keys, inquiry_digest, validate_inquiry)

_CALL_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

def _clean_result_text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise RouteScoutError(f"{field}: must be string")
    if _CONTROL.search(value) or len(value) > limit:
        raise RouteScoutError(f"{field}: invalid text")
    return value.strip()

def validate_structured_result(result: Mapping[str, Any]) -> dict[str, Any]:
    _exact_keys(result, _RESULT_FIELDS, "structured_result")
    for field in ("organization_confirmed","consented_to_continue","routing_answered",
                  "channel_is_business","do_not_contact"):
        if type(result[field]) is not bool:
            raise RouteScoutError(f"{field}: must be boolean")
    channel_type = _clean_result_text(result["channel_type"], "channel_type", 24)
    permission_state = _clean_result_text(result["permission_state"], "permission_state", 24)
    if channel_type not in CHANNEL_TYPES:
        raise RouteScoutError("channel_type: invalid")
    if permission_state not in PERMISSION_STATES:
        raise RouteScoutError("permission_state: invalid")
    return {
        "organization_confirmed": result["organization_confirmed"],
        "consented_to_continue": result["consented_to_continue"],
        "routing_answered": result["routing_answered"],
        "department_or_role": _clean_result_text(result["department_or_role"], "department_or_role", 160),
        "channel_type": channel_type,
        "channel_value": _clean_result_text(result["channel_value"], "channel_value", 240),
        "channel_is_business": result["channel_is_business"],
        "permission_state": permission_state,
        "do_not_contact": result["do_not_contact"],
        "verbatim_route": _clean_result_text(result["verbatim_route"], "verbatim_route", 500),
        "notes": _clean_result_text(result["notes"], "notes", 500),
    }

def normalize_terminal_call(call: Mapping[str, Any]) -> dict[str, Any]:
    status = call.get("status")
    if status not in TERMINAL:
        raise RouteScoutError("CALL-E call is not terminal")
    recipients = call.get("recipients")
    structured: Any = None
    if isinstance(recipients, list) and len(recipients) == 1 and isinstance(recipients[0], Mapping):
        structured = recipients[0].get("structured_result")
    if not isinstance(structured, Mapping):
        structured = call.get("structured_result")
    if not isinstance(structured, Mapping):
        structured = {}
    call_id = call.get("id")
    if not isinstance(call_id, str) or not _CALL_ID.fullmatch(call_id):
        call_id = None
    metadata = call.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    digest = metadata.get("inquiry_digest_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        digest = None
    inquiry_id = metadata.get("inquiry_id")
    if not isinstance(inquiry_id, str) or not inquiry_id:
        inquiry_id = None
    return {
        "provider_status": status,
        "task_completed": call.get("task_completed") is True,
        "provider_call_id": call_id,
        "provider_workflow": metadata.get("workflow"),
        "provider_schema_version": metadata.get("schema_version"),
        "provider_inquiry_id": inquiry_id,
        "provider_inquiry_digest_sha256": digest,
        "structured_result": dict(structured),
        "provider_evidence": [x for x in (call.get("evidence") or []) if isinstance(x, str)][:20],
    }

def reconcile(
    inquiry: Mapping[str, Any],
    terminal: Mapping[str, Any],
    *,
    expected_call_id: str | None = None,
) -> dict[str, Any]:
    i = validate_inquiry(inquiry)
    expected_digest = inquiry_digest(i)
    normalized = normalize_terminal_call(terminal)
    reasons: list[str] = []

    if normalized["provider_call_id"] is None:
        reasons.append("provider terminal result lacks a valid call id")
    if expected_call_id is not None:
        if not isinstance(expected_call_id, str) or not _CALL_ID.fullmatch(expected_call_id):
            raise RouteScoutError("expected_call_id: invalid")
        if normalized["provider_call_id"] != expected_call_id:
            reasons.append("provider terminal call id does not match the requested call id")
    if normalized["provider_workflow"] != "routescout":
        reasons.append("provider terminal metadata does not identify the RouteScout workflow")
    if normalized["provider_schema_version"] != "1":
        reasons.append("provider terminal metadata schema version does not match RouteScout")
    if normalized["provider_inquiry_id"] != i["inquiry_id"]:
        reasons.append("provider terminal metadata inquiry id does not match the exact inquiry")
    if normalized["provider_inquiry_digest_sha256"] != expected_digest:
        reasons.append("provider terminal metadata digest does not match the exact inquiry")

    binding_verified = not reasons
    r: dict[str, Any] | None = None
    if binding_verified:
        try:
            r = validate_structured_result(normalized["structured_result"])
        except RouteScoutError as exc:
            reasons.append(f"unusable structured result: {exc}")

    if not binding_verified:
        outcome = "HUMAN_REQUIRED"
    elif normalized["provider_status"] != "completed" or not normalized["task_completed"] or r is None:
        outcome = "HUMAN_REQUIRED"
        if not reasons:
            reasons.append("provider call did not complete with usable structured result")
    elif r["do_not_contact"] or r["permission_state"] == "declined":
        outcome = "DO_NOT_CONTACT"
    elif not (r["organization_confirmed"] and r["consented_to_continue"] and r["routing_answered"]):
        outcome = "NO_ROUTE"
        reasons.append("organization/consent/routing answer not all confirmed")
    elif (
        r["channel_type"] != "none"
        and bool(r["channel_value"])
        and r["channel_is_business"]
        and r["permission_state"] in {"invited", "permitted"}
        and bool(r["verbatim_route"])
    ):
        outcome = "ROUTE_FOUND"
    else:
        outcome = "NO_ROUTE"
        reasons.append("no permitted business follow-up channel proven")

    route_is_authoritative = (
        binding_verified and normalized["provider_status"] == "completed"
        and normalized["task_completed"] and r is not None
    )
    core = {
        "schema_version": 1,
        "inquiry_digest_sha256": expected_digest,
        "inquiry_id": i["inquiry_id"],
        "provider_call_id": normalized["provider_call_id"],
        "provider_binding": {
            "workflow": normalized["provider_workflow"],
            "schema_version": normalized["provider_schema_version"],
            "inquiry_id": normalized["provider_inquiry_id"],
            "inquiry_digest_sha256": normalized["provider_inquiry_digest_sha256"],
            "verified": binding_verified,
        },
        "outcome": outcome,
        "route": None if not route_is_authoritative else {
            "department_or_role": r["department_or_role"],
            "channel_type": r["channel_type"],
            "channel_value": r["channel_value"],
            "permission_state": r["permission_state"],
            "verbatim_route": r["verbatim_route"],
        },
        "reasons": reasons,
        "provider_evidence": normalized["provider_evidence"],
        "authority": {
            "may_send_followup": False,
            "may_pitch": False,
            "may_negotiate": False,
            "may_bypass_procurement": False,
            "may_claim_acceptance": False,
            "may_claim_revenue": False,
        },
    }
    receipt = dict(core)
    receipt["receipt_sha256"] = hashlib.sha256(
        (json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
    ).hexdigest()
    return receipt
