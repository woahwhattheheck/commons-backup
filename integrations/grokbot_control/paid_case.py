#!/usr/bin/env python3
"""Build grokbot_control receipt rows from G2 submit results.

Does not touch Stripe, fulfillment, or checkout URLs. Callers pass the
normalized case into GrokBotControlClient.submit / grokbot_submit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .store import normalize_case

_RECEIPT_OPTIONAL = (
    "client_reference_id",
    "g2_run_id",
    "g2_session_id",
    "payment_observed_at",
)
_RECEIPT_MAX = 200
_FORBIDDEN_RECEIPT_KEYS = frozenset(
    {
        "email",
        "buyer_email",
        "customer",
        "name",
        "phone",
        "artifact",
        "artifacts",
        "pii",
        "secret",
        "token",
    }
)


def _receipt_text(value: str) -> str:
    text = value.strip()
    if len(text) > _RECEIPT_MAX:
        raise ValueError(f"receipt values must not exceed {_RECEIPT_MAX} characters")
    return text


def receipt_row_from_case(
    case: Mapping[str, Any],
    *,
    g2_run_id: str | None = None,
    g2_session_id: str | None = None,
    payment_observed_at: str | None = None,
    state: str = "UNVERIFIED",
) -> dict[str, str]:
    """Build an opaque public seats `case_row` from a G2 case + optional run ids.

    Required on the row: offer_id, case_ref, sku, state.
    Optional: client_reference_id, g2_run_id, g2_session_id, payment_observed_at.
    Callers supply opaque identifiers; this helper is not a PII sanitizer or
    payment verifier. State defaults to UNVERIFIED; callers pass an observed
    state only when supported by evidence. Values over 200 characters raise
    instead of silently changing identifiers. Does not append to seats.json;
    callers append after REAL_STRIPE_PAYMENT_OBSERVED + owner authorization.
    """
    if any(k in case for k in _FORBIDDEN_RECEIPT_KEYS):
        raise ValueError("case must not carry buyer PII / artifact keys")

    normalized = normalize_case(case)
    if normalized is None:
        raise ValueError("case must normalize to a nonempty object")
    for required in ("offer_id", "case_ref", "sku"):
        if required not in normalized:
            raise ValueError(f"case missing {required}")

    if not isinstance(state, str) or not state.strip():
        raise ValueError("state must be a nonempty string")

    row: dict[str, str] = {
        "offer_id": normalized["offer_id"],
        "case_ref": normalized["case_ref"],
        "sku": normalized["sku"],
        "state": _receipt_text(state),
    }
    if "client_reference_id" in normalized:
        row["client_reference_id"] = normalized["client_reference_id"]

    optionals = {
        "g2_run_id": g2_run_id,
        "g2_session_id": g2_session_id,
        "payment_observed_at": payment_observed_at,
    }
    for key, value in optionals.items():
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a nonempty string when provided")
        row[key] = _receipt_text(value)

    for key in row:
        if key in _FORBIDDEN_RECEIPT_KEYS:
            raise ValueError(f"forbidden receipt key: {key}")
    return row


def receipt_from_g2_submit(
    case: Mapping[str, Any],
    submit_response: Mapping[str, Any],
    *,
    payment_observed_at: str | None = None,
    state: str = "UNVERIFIED",
) -> dict[str, str]:
    """Bind a grokbot_submit/inspect response onto an opaque seats case_row.

    Requires nonempty submit_response.run_id. session_id is optional when present
    and nonempty. Does not invent payment evidence (default state UNVERIFIED).
    """
    if not isinstance(submit_response, Mapping):
        raise ValueError("submit_response must be a mapping")
    run_id = submit_response.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("submit_response.run_id must be a nonempty string")
    session_raw = submit_response.get("session_id")
    session_id = (
        session_raw
        if isinstance(session_raw, str) and session_raw.strip()
        else None
    )
    return receipt_row_from_case(
        case,
        g2_run_id=run_id,
        g2_session_id=session_id,
        payment_observed_at=payment_observed_at,
        state=state,
    )
