from __future__ import annotations

from typing import Any

from .core import COMMERCIAL_STATE, canonical_json, pack_catalog

SCHEMA = "partner-workshare-public-catalog/v1"
PUBLIC_PACK_IDS = (
    "DATA_MIGRATION_ACCEPTANCE",
    "RESPONSIBLE_AI_EVALUATION",
    "FINANCIAL_EVIDENCE_RECONCILIATION",
)

_POSITIONING = {
    "DATA_MIGRATION_ACCEPTANCE": (
        "Independent second-source migration/integration acceptance evidence beside the prime or delivery team; "
        "not staffing and not a platform replacement."
    ),
    "RESPONSIBLE_AI_EVALUATION": (
        "Independent bounded evaluation and governance-evidence support beside the buyer or prime; "
        "not certification, legal advice, or model-vendor replacement."
    ),
    "FINANCIAL_EVIDENCE_RECONCILIATION": (
        "Independent read-only closed-period evidence reconciliation beside the owner or operator; "
        "not bookkeeping, payment execution, fraud adjudication, or an accounting opinion."
    ),
}


def build_public_catalog() -> dict[str, Any]:
    """Return the public catalog directly from the code-owned workshare pack definitions."""
    source = pack_catalog()
    if set(source) != set(PUBLIC_PACK_IDS):
        raise ValueError("public workshare catalog pack set drift")

    rows: list[dict[str, Any]] = []
    for pack_id in PUBLIC_PACK_IDS:
        pack = source[pack_id]
        rows.append(
            {
                "pack_id": pack_id,
                "name": pack["name"],
                "commercial_state": COMMERCIAL_STATE,
                "positioning": _POSITIONING[pack_id],
                "summary": pack["summary"],
                "fixed_fee": {
                    "currency": "USD",
                    "decimals": 2,
                    "min_minor": pack["fee_min_minor"],
                    "reference_minor": pack["fee_reference_minor"],
                    "max_minor": pack["fee_max_minor"],
                },
                "delivery_business_days": {
                    "min": pack["duration_min"],
                    "reference": pack["duration_reference"],
                    "max": pack["duration_max"],
                },
                "deliverables": list(pack["deliverables"]),
                "acceptance": list(pack["acceptance"]),
                "intake_gates": list(pack["intake_gates"]),
                "exclusions": list(pack["exclusions"]),
                "retained_authority": list(pack["retained_authority"]),
            }
        )

    return {
        "schema": SCHEMA,
        "canonical_source": "revenue/human_reply_workshare_kit/core.py",
        "source_package": "revenue/human_reply_workshare_kit",
        "source_release": {
            "pull_request": 15334,
            "merge_sha": "5b49ee7ee5ff731d1f94ef6d296f944cfd5e529a",
        },
        "commercial_state": COMMERCIAL_STATE,
        "checkout_available": False,
        "buyer_acceptance_claimed": False,
        "contract_claimed": False,
        "invoice_claimed": False,
        "payment_claimed": False,
        "revenue_claimed": False,
        "contact": {
            "method": "email",
            "address": "tokenjunkielabs@gmail.com",
            "first_contact_rule": (
                "Name the workshare, bounded system/period, delivery window, and acceptance owner. "
                "Do not send credentials, production secrets, regulated records, or confidential datasets in first contact."
            ),
        },
        "truth_boundary": (
            "This is a public proposal menu, not evidence of a buyer, acceptance, award, contract, invoice, payment, "
            "receivable, booked revenue, recognized revenue, or delivery outcome. Each engagement is separately scoped."
        ),
        "packs": rows,
    }


def render_public_catalog_json() -> str:
    return canonical_json(build_public_catalog())
