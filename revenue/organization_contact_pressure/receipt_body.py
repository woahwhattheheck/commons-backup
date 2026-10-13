"""Build and authenticate canonical organization-pressure receipts."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Optional

from .core import (
    READY, RECEIPT_SCHEMA, ActiveKey, AuthorityView, LedgerView,
    _canonical_bytes, _format_time, _hmac_hex, _parse_time, _sha256,
)


def _receipt_body(
    request: Mapping[str, Any],
    active: ActiveKey,
    authority: Optional[AuthorityView],
    ledger: Optional[LedgerView],
    decision: str,
    reasons: Iterable[str],
    now: datetime,
) -> dict[str, Any]:
    valid_until = None
    if decision == READY:
        if authority is None:
            raise ValueError("READY receipt requires authenticated authority")
        policy_valid_until = now + timedelta(seconds=authority.ready_validity_seconds)
        request_valid_until = _parse_time(
            request["requested_at"], "requested_at"
        ) + timedelta(seconds=authority.request_max_age_seconds)
        valid_until = _format_time(min(policy_valid_until, request_valid_until))
    return {
        "schema": RECEIPT_SCHEMA,
        "organization_scope_sha256": request["organization_scope_sha256"],
        "proposed_route_scope_sha256": request["proposed_route_scope_sha256"],
        "proposed_event_id": request["proposed_event_id"],
        "operation_id": request["operation_id"],
        "request_sha256": _sha256(_canonical_bytes(request)),
        "decision": decision,
        "reasons": sorted(set(reasons)),
        "authority_policy_generation": authority.policy_generation if authority else None,
        "authority_sha256": authority.digest if authority else None,
        "ledger_generation": ledger.generation if ledger else None,
        "ledger_sha256": ledger.digest if ledger else None,
        "evaluated_at": _format_time(now),
        "valid_until": valid_until,
        "key_id": active.key_id,
        "verifier_id": active.verifier_id,
        "external_send_authorized": False,
        "next_required_controls": [
            "ATOMIC_ORGANIZATION_OUTBOUND_LEASE",
            "PER_PROSPECT_ATOMIC_LOCK",
            "COMMERCIAL_OPPORTUNITY_CUSTODY",
            "INITIAL_OUTREACH_ONE_SHOT",
            "PROVIDER_BOUND_SEND_CONSUMER",
        ],
    }


def _seal_receipt(body: Mapping[str, Any], key: bytes) -> dict[str, Any]:
    signed = dict(body)
    signed["receipt_hmac"] = _hmac_hex(key, body)
    signed["receipt_sha256"] = _sha256(_canonical_bytes(signed))
    return signed
