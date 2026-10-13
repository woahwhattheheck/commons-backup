"""Strict validation and normalization for verified paid proof records."""
from __future__ import annotations
from typing import Any
from .core import (
    CURRENCY_RE, DELIVERY_STATES, ENGAGEMENT_RE, PAYMENT_STATES, PERMISSION_SCOPES, ProofError,
    _bool, _canonical_json, _dict, _exact_keys, _int, _list, _nullable_str, _nullable_timestamp, _permission,
    _source_ref, _source_refs, _str,
)

def validate_and_normalize(raw: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "engagement_id",
        "customer",
        "payment",
        "delivery",
        "quote",
        "outcomes",
        "permissions",
        "revocation",
    }
    _exact_keys(raw, expected, "$")
    if _int(raw["schema_version"], "$.schema_version") != 1:
        raise ProofError("$.schema_version must equal 1")

    engagement_id = _str(raw["engagement_id"], "$.engagement_id", max_len=128)
    if not ENGAGEMENT_RE.fullmatch(engagement_id):
        raise ProofError("$.engagement_id has invalid characters")

    customer = _dict(raw["customer"], "$.customer")
    _exact_keys(customer, {"display_name", "logo_ref"}, "$.customer")
    display_name = _nullable_str(customer["display_name"], "$.customer.display_name", max_len=120)
    logo_ref = None if customer["logo_ref"] is None else _source_ref(customer["logo_ref"], "$.customer.logo_ref")

    payment = _dict(raw["payment"], "$.payment")
    _exact_keys(payment, {"status", "amount_minor", "currency", "currency_decimals", "settled_at", "evidence_refs"}, "$.payment")
    payment_status = _str(payment["status"], "$.payment.status", max_len=16).upper()
    if payment_status not in PAYMENT_STATES:
        raise ProofError(f"$.payment.status must be one of {sorted(PAYMENT_STATES)}")
    amount_minor = None if payment["amount_minor"] is None else _int(payment["amount_minor"], "$.payment.amount_minor", minimum=0)
    currency = None if payment["currency"] is None else _str(payment["currency"], "$.payment.currency", max_len=3).upper()
    currency_decimals = None if payment["currency_decimals"] is None else _int(payment["currency_decimals"], "$.payment.currency_decimals", minimum=0, maximum=3)
    settled_at = _nullable_timestamp(payment["settled_at"], "$.payment.settled_at")
    payment_refs = _source_refs(payment["evidence_refs"], "$.payment.evidence_refs")

    if payment_status == "SETTLED":
        if amount_minor is None or amount_minor <= 0:
            raise ProofError("SETTLED payment requires positive $.payment.amount_minor")
        if currency is None or not CURRENCY_RE.fullmatch(currency):
            raise ProofError("SETTLED payment requires three-letter uppercase currency")
        if currency_decimals is None:
            raise ProofError("SETTLED payment requires $.payment.currency_decimals")
        if settled_at is None:
            raise ProofError("SETTLED payment requires $.payment.settled_at")
        if not payment_refs:
            raise ProofError("SETTLED payment requires payment evidence_refs")
    elif any(value is not None for value in (amount_minor, currency, currency_decimals, settled_at)):
        raise ProofError("non-SETTLED payment must not carry settled amount/currency/time")

    delivery = _dict(raw["delivery"], "$.delivery")
    _exact_keys(delivery, {"status", "accepted_at", "evidence_refs"}, "$.delivery")
    delivery_status = _str(delivery["status"], "$.delivery.status", max_len=20).upper()
    if delivery_status not in DELIVERY_STATES:
        raise ProofError(f"$.delivery.status must be one of {sorted(DELIVERY_STATES)}")
    accepted_at = _nullable_timestamp(delivery["accepted_at"], "$.delivery.accepted_at")
    delivery_refs = _source_refs(delivery["evidence_refs"], "$.delivery.evidence_refs")
    if delivery_status == "ACCEPTED":
        if accepted_at is None or not delivery_refs:
            raise ProofError("ACCEPTED delivery requires accepted_at and evidence_refs")
    elif accepted_at is not None:
        raise ProofError("non-ACCEPTED delivery must not carry accepted_at")

    quote = _dict(raw["quote"], "$.quote")
    _exact_keys(quote, {"text", "evidence_ref"}, "$.quote")
    quote_text = _nullable_str(quote["text"], "$.quote.text", max_len=1000)
    quote_ref = None if quote["evidence_ref"] is None else _source_ref(quote["evidence_ref"], "$.quote.evidence_ref")
    if (quote_text is None) != (quote_ref is None):
        raise ProofError("quote text and evidence_ref must either both be present or both be null")

    outcomes_raw = _list(raw["outcomes"], "$.outcomes")
    outcomes: list[dict[str, Any]] = []
    seen_claims: set[str] = set()
    for index, item in enumerate(outcomes_raw):
        path = f"$.outcomes[{index}]"
        obj = _dict(item, path)
        _exact_keys(obj, {"claim", "evidence_refs", "publication_permission"}, path)
        claim = _str(obj["claim"], f"{path}.claim", max_len=500)
        folded = claim.casefold()
        if folded in seen_claims:
            raise ProofError(f"duplicate outcome claim: {claim}")
        seen_claims.add(folded)
        refs = _source_refs(obj["evidence_refs"], f"{path}.evidence_refs", required=True)
        permission = _permission(obj["publication_permission"], f"{path}.publication_permission")
        outcomes.append({"claim": claim, "evidence_refs": refs, "publication_permission": permission})
    outcomes.sort(key=lambda item: (item["claim"].casefold(), _canonical_json(item)))

    permissions_raw = _dict(raw["permissions"], "$.permissions")
    _exact_keys(permissions_raw, PERMISSION_SCOPES, "$.permissions")
    permissions = {scope: _permission(permissions_raw[scope], f"$.permissions.{scope}") for scope in sorted(PERMISSION_SCOPES)}

    revocation = _dict(raw["revocation"], "$.revocation")
    _exact_keys(revocation, {"revoked", "evidence_refs"}, "$.revocation")
    revoked = _bool(revocation["revoked"], "$.revocation.revoked")
    revocation_refs = _source_refs(revocation["evidence_refs"], "$.revocation.evidence_refs", required=revoked)

    if permissions["logo"]["granted"] and logo_ref is None:
        raise ProofError("logo permission granted but $.customer.logo_ref is null")
    if permissions["customer_identity"]["granted"] and display_name is None:
        raise ProofError("customer_identity permission granted but display_name is null")
    if permissions["quote"]["granted"] and quote_text is None:
        raise ProofError("quote permission granted but quote is null")

    return {
        "schema_version": 1,
        "engagement_id": engagement_id,
        "customer": {"display_name": display_name, "logo_ref": logo_ref},
        "payment": {
            "status": payment_status,
            "amount_minor": amount_minor,
            "currency": currency,
            "currency_decimals": currency_decimals,
            "settled_at": settled_at,
            "evidence_refs": payment_refs,
        },
        "delivery": {"status": delivery_status, "accepted_at": accepted_at, "evidence_refs": delivery_refs},
        "quote": {"text": quote_text, "evidence_ref": quote_ref},
        "outcomes": outcomes,
        "permissions": permissions,
        "revocation": {"revoked": revoked, "evidence_refs": revocation_refs},
    }


