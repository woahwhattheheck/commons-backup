from __future__ import annotations

import copy
import hashlib
import json

from . import build_scope_bridge, build_scope_terms, create_operator_verification, terms_digest

OWNER_KEY = b"O" * 32
VERIFY_KEY = b"V" * 32
NOW = "2026-09-13T10:10:00Z"
ZERO, ONE, TWO, THREE, FOUR = (str(i) * 64 for i in range(5))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def offer():
    return {
        "schema_version": 1,
        "offer_id": "offer-production-001",
        "opportunity_id": "production-survival-sprint",
        "buyer_ref": "buyeropaque_001",
        "created_at": "2026-09-13T10:00:00Z",
        "valid_until": "2026-09-20T10:00:00Z",
        "currency": "USD",
        "total_amount_minor": 1_500_000,
        "deliverables": [
            {"id": "failure-cycle", "title": "Measured failure cycle", "acceptance_criteria": "The named workflow survives the agreed failure cycle.", "evidence_sha256": ONE},
            {"id": "rollback-receipt", "title": "Rollback and receipt", "acceptance_criteria": "Rollback restores the agreed state and emits a durable receipt.", "evidence_sha256": TWO},
        ],
        "milestones": [
            {"id": "m1", "deliverable_ids": ["failure-cycle"], "amount_minor": 750_000, "acceptance_window_hours": 48, "payment_due_days": 7},
            {"id": "m2", "deliverable_ids": ["rollback-receipt"], "amount_minor": 750_000, "acceptance_window_hours": 48, "payment_due_days": 7},
        ],
        "assumptions": ["Buyer provides one sandbox workflow."],
        "exclusions": ["No production deployment.", "No credential custody."],
    }


def contract():
    item = offer(); offer_sha = digest(item)
    return {
        "kind": "commercial_offer_contract", "schema_version": 1, "state": "BUYER_ACCEPTANCE_EVIDENCE_CAPTURED",
        "offer": item, "offer_sha256": offer_sha,
        "owner_approval": {"key_id": "sales-owner-v1", "approved_at": "2026-09-13T10:01:00Z", "offer_sha256": offer_sha, "hmac_sha256": THREE},
        "send_authority": {"offer_sha256": offer_sha, "owner_approval_hmac": THREE, "destination_sha256": FOUR, "channel": "email", "authorized_at": "2026-09-13T10:02:00Z", "hmac_sha256": ZERO},
        "buyer_acceptance": {"offer_sha256": offer_sha, "buyer_ref": item["buyer_ref"], "accepted_at": "2026-09-13T10:03:00Z", "evidence_sha256": TWO, "identity_verification_sha256": THREE},
        "authority": {"external_send_authorized": True, "buyer_acceptance_verified": False, "fulfillment_authorized": False, "payment_collected": False, "revenue_recognized": False},
    }


def service_window():
    return {
        "start": "2026-09-14T13:00:00Z",
        "end": "2026-09-18T21:00:00Z",
        "timezone": "America/Kentucky/Louisville",
    }


def catalog(amount="15000.00", currency="USD", sku="production-survival-sprint"):
    return {"listings": [{"id": sku, "name": "Production Survival Sprint", "pricing": {"currency": currency, "components": [{"amount": amount}]}}]}


def contract_verifier(value, owner_key):
    if owner_key != OWNER_KEY:
        raise ValueError("wrong owner key")
    return copy.deepcopy(value)


def scope_acceptance(c=None, cat=None, window=None, *, accepted_at="2026-09-13T10:05:00Z"):
    c, cat, window = c or contract(), cat or catalog(), window or service_window()
    terms = build_scope_terms(c, cat, window)
    return {
        "terms_digest": terms_digest(terms),
        "accepted_at": accepted_at,
        "evidence_sha256": FOUR,
        "identity_verification_sha256": ONE,
    }


def agreement_validator(value, _catalog):
    expected = {"schema_version", "kind", "agreement_id", "sku_id", "quote", "window", "written_acceptance", "buyer_ref", "intake_sentence", "acceptance_rows", "exclusions", "refund_choice"}
    if set(value) != expected or value["schema_version"] != "commons-scope-agreement/v1" or value["kind"] != "SCOPE_AGREEMENT":
        raise ValueError("agreement schema")
    if value["written_acceptance"]["status"] != "PRESENT" or value["written_acceptance"]["attestation"] != "AUTHORIZED_OPERATOR_VERIFIED_EXACT_TERMS_ACCEPTANCE":
        raise ValueError("acceptance")
    if value["refund_choice"] != "UNKNOWN" or value["sku_id"] != "production-survival-sprint":
        raise ValueError("authority")
    if value["quote"] != {"currency": "USD", "amount": "15000.00"}:
        raise ValueError("quote")
    if not value["buyer_ref"].startswith("buyer_") or len(value["buyer_ref"]) != 70:
        raise ValueError("buyer opacity")
    if not value["acceptance_rows"] or value["exclusions"] != offer()["exclusions"]:
        raise ValueError("scope")
    return copy.deepcopy(value)


def verification(c=None, acceptance=None, window=None, cat=None, **kwargs):
    c, cat, window = c or contract(), cat or catalog(), window or service_window()
    acceptance = acceptance or scope_acceptance(c, cat, window)
    return create_operator_verification(
        c, OWNER_KEY, VERIFY_KEY, verifier_id="operator-001", key_id="acceptance-key-v2",
        verified_at=kwargs.pop("verified_at", "2026-09-13T10:06:00Z"),
        public_ref=kwargs.pop("public_ref", "p/accepted-scope-terms.md"),
        catalog=cat, service_window=window, scope_terms_acceptance=acceptance,
        trusted_now=kwargs.pop("trusted_now", NOW), contract_verifier=contract_verifier, **kwargs,
    )


def bundle(c=None, receipt=None, cat=None):
    c, cat = c or contract(), cat or catalog(); receipt = receipt or verification(c, cat=cat)
    return build_scope_bridge(
        c, receipt, OWNER_KEY, VERIFY_KEY, catalog=cat, trusted_now=NOW,
        contract_verifier=contract_verifier, agreement_validator=agreement_validator,
    )
