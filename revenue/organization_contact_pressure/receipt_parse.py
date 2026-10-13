"""Strictly parse canonical organization-pressure receipts."""

from __future__ import annotations

from typing import Any, Mapping

from .core import (
    DECISIONS, HOLD_AUTHORITY, MAX_EVENTS, MAX_SAFE_INTEGER, READY, RECEIPT_SCHEMA,
    InputError, _expect_exact_fields, _expect_hex64, _expect_int, _expect_key_id,
    _expect_slug, _expect_string, _format_time, _parse_time,
)


def _normalize_receipt(document: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    fields = {
        "schema",
        "organization_scope_sha256",
        "proposed_route_scope_sha256",
        "proposed_event_id",
        "operation_id",
        "request_sha256",
        "decision",
        "reasons",
        "authority_policy_generation",
        "authority_sha256",
        "ledger_generation",
        "ledger_sha256",
        "evaluated_at",
        "valid_until",
        "key_id",
        "verifier_id",
        "external_send_authorized",
        "next_required_controls",
        "receipt_hmac",
        "receipt_sha256",
    }
    _expect_exact_fields(document, fields, "receipt")
    if document["schema"] != RECEIPT_SCHEMA:
        raise InputError("unsupported receipt schema")
    decision = _expect_string(document["decision"], "receipt.decision", maximum=64)
    if decision not in DECISIONS:
        raise InputError("unsupported receipt decision")
    reasons_raw = document["reasons"]
    if type(reasons_raw) is not list or len(reasons_raw) > MAX_EVENTS:
        raise InputError("receipt.reasons must be a bounded list")
    reasons = sorted(_expect_string(item, "receipt.reasons[]", maximum=256) for item in reasons_raw)
    if reasons != reasons_raw or len(set(reasons)) != len(reasons):
        raise InputError("receipt.reasons must be sorted and unique")
    policy_generation = document["authority_policy_generation"]
    authority_sha = document["authority_sha256"]
    ledger_generation = document["ledger_generation"]
    ledger_sha = document["ledger_sha256"]
    if decision == HOLD_AUTHORITY and policy_generation is None:
        if authority_sha is not None or ledger_generation is not None or ledger_sha is not None:
            raise InputError("partial authority fields are invalid")
    else:
        policy_generation = _expect_int(
            policy_generation, "receipt.authority_policy_generation", minimum=1, maximum=MAX_SAFE_INTEGER
        )
        authority_sha = _expect_hex64(authority_sha, "receipt.authority_sha256")
        ledger_generation = _expect_int(
            ledger_generation, "receipt.ledger_generation", minimum=0, maximum=MAX_SAFE_INTEGER
        )
        ledger_sha = _expect_hex64(ledger_sha, "receipt.ledger_sha256")
    valid_until = document["valid_until"]
    if decision == READY:
        valid_until = _format_time(_parse_time(valid_until, "receipt.valid_until"))
    elif valid_until is not None:
        raise InputError("HOLD receipt cannot have valid_until")
    if document["external_send_authorized"] is not False:
        raise InputError("receipt must never authorize external send")
    expected_controls = [
        "ATOMIC_ORGANIZATION_OUTBOUND_LEASE",
        "PER_PROSPECT_ATOMIC_LOCK",
        "COMMERCIAL_OPPORTUNITY_CUSTODY",
        "INITIAL_OUTREACH_ONE_SHOT",
        "PROVIDER_BOUND_SEND_CONSUMER",
    ]
    if document["next_required_controls"] != expected_controls:
        raise InputError("receipt next controls are invalid")
    body = {
        "schema": RECEIPT_SCHEMA,
        "organization_scope_sha256": _expect_hex64(
            document["organization_scope_sha256"], "receipt.organization_scope_sha256"
        ),
        "proposed_route_scope_sha256": _expect_hex64(
            document["proposed_route_scope_sha256"], "receipt.proposed_route_scope_sha256"
        ),
        "proposed_event_id": _expect_hex64(document["proposed_event_id"], "receipt.proposed_event_id"),
        "operation_id": _expect_slug(document["operation_id"], "receipt.operation_id"),
        "request_sha256": _expect_hex64(document["request_sha256"], "receipt.request_sha256"),
        "decision": decision,
        "reasons": reasons,
        "authority_policy_generation": policy_generation,
        "authority_sha256": authority_sha,
        "ledger_generation": ledger_generation,
        "ledger_sha256": ledger_sha,
        "evaluated_at": _format_time(_parse_time(document["evaluated_at"], "receipt.evaluated_at")),
        "valid_until": valid_until,
        "key_id": _expect_key_id(document["key_id"], "receipt.key_id"),
        "verifier_id": _expect_slug(document["verifier_id"], "receipt.verifier_id"),
        "external_send_authorized": False,
        "next_required_controls": expected_controls,
    }
    receipt_hmac = _expect_hex64(document["receipt_hmac"], "receipt.receipt_hmac")
    receipt_sha = _expect_hex64(document["receipt_sha256"], "receipt.receipt_sha256")
    return body, receipt_hmac, receipt_sha
