#!/usr/bin/env python3
"""Fail-closed validator for the Sasria RFP2026/22 TJLabs self-attested workshare snapshot."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "tjlabs-sasria-rfp2026-22-workshare/v1"
COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"
COUNTERPARTY_STATE = "INBOUND_ONLY_AWAITING_PRIME_CONFIRMATION"
RELEASE_STATUS = "HOLD_PRIME_AND_TENDER_INPUTS"
EXPECTED_RFP = "2026/22"
EXPECTED_TITLE = "Appointment of Service Provider for Artificial Intelligence Training"
EXPECTED_DETAIL_URL = "https://procurement.sasria.co.za/tender-details/246"
EXPECTED_OBSERVED_AT = "2026-09-17T00:56:02-04:00"
EXPECTED_RECEIPT_NOTE = (
    "Portal metadata and filenames were visible; document bodies were not available through the current "
    "read interface. Tender-specific criteria remain HOLD until supplied by the prime or retrieved from "
    "the controlling files."
)
EXPECTED_DOCUMENTS = (
    "2026_22-RFP2026.22 Appointment of Service Provider for Artificial Intelligence Training.pdf",
    "2026_22-SBD 6.1 .docx",
    "2026_22-SCM-Bid documents SBD 1.doc",
    "2026_22-Standard Bidding Document (SDB) 4_Annexure A.doc",
)
REQUIRED_PRIME_GATES = (
    "live_bid_intent_confirmed",
    "procurement_documents_owned",
    "compliance_documents_owned",
    "accreditation_and_certification_evidence_owned",
    "facilitators_and_references_owned",
    "platform_access_owned",
    "bid_pricing_owned",
    "signatory_authority_owned",
    "submission_authority_owned",
    "controlling_tender_criteria_supplied",
)
EXPECTED_DELIVERABLES = (
    "responsible_ai_control_evidence_map",
    "six_role_pathway_acceptance_criteria",
    "hands_on_lab_qa_matrix",
    "deterministic_pre_post_assessment_pack",
    "versioned_evidence_exception_pack",
    "governance_evidence_handoff",
)

TOP_KEYS = {
    "schema", "commercial_state", "fee", "counterparty_state", "tender", "source_receipt",
    "prime_gates", "tjlabs_boundary", "role_pathways", "release",
}
TENDER_KEYS = {
    "issuer", "rfp_number", "title", "portal_status", "detail_url", "published_at_portal",
    "closes_at_portal", "queries_deadline_at_portal", "documents",
}
RECEIPT_KEYS = {"observed_at", "source_kind", "controlling_documents_read", "note"}
BOUNDARY_KEYS = {
    "prime_role", "submission_authority", "legal_or_compliance_certification",
    "production_mutation_authority", "learner_pii", "deliverables",
}
PATHWAY_KEYS = {"id", "acceptance_criteria"}
RELEASE_KEYS = {"buyer_send_allowed", "bid_submission_allowed", "status"}

SELF_ATTESTED_RELEASE_HOLD = (
    "release: self-attested v1 can never authorize a prime-backed transition; "
    "use a separate evidence-bound successor generation"
)


class StrictJSONError(ValueError):
    """Stable input error for duplicate keys and non-finite JSON constants."""


def _reject_constant(value: str) -> None:
    raise StrictJSONError(f"non-finite JSON value is forbidden: {value}")


def _unique_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise StrictJSONError(f"duplicate JSON key is forbidden: {key}")
        out[key] = value
    return out


def load_payload_text(text: str) -> Any:
    """Parse JSON with duplicate-key and non-finite-number rejection."""
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _need(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _exact_keys(value: Any, expected: set[str], field: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{field}: object required")
        return False
    actual = set(value)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "-"
        extra = ",".join(sorted(actual - expected)) or "-"
        errors.append(f"{field}: exact keys required (missing={missing}; extra={extra})")
        return False
    return True


def _exact_string_list(
    value: Any,
    expected: tuple[str, ...],
    field: str,
    errors: list[str],
    *,
    ordered: bool = False,
) -> bool:
    if not isinstance(value, list) or not all(type(item) is str for item in value):
        errors.append(f"{field}: list of strings required")
        return False
    if len(value) != len(set(value)):
        errors.append(f"{field}: duplicate values forbidden")
        return False
    match = tuple(value) == expected if ordered else set(value) == set(expected)
    if not match:
        errors.append(f"{field}: exact value set required")
        return False
    return True


def _parse_dt(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{field}: expected ISO-8601 string")
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        errors.append(f"{field}: invalid ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field}: timezone offset required")
        return None
    return parsed


def validate(payload: Any, *, release: bool = False) -> list[str]:
    """Validate only the frozen self-attested v1 snapshot.

    This generation deliberately cannot ingest prime assertions or tender-body text.
    A real prime-backed transition requires a separate evidence-bound successor schema.
    """
    errors: list[str] = []
    if not _exact_keys(payload, TOP_KEYS, "root", errors):
        if not isinstance(payload, dict):
            return errors

    _need(payload.get("schema") == SCHEMA, "schema: unsupported or missing", errors)
    _need(
        payload.get("commercial_state") == COMMERCIAL_STATE,
        "commercial_state: must remain PROPOSED_NOT_ACCEPTED",
        errors,
    )
    _need(payload.get("fee") == "TO_BE_AGREED", "fee: must remain TO_BE_AGREED before agreement", errors)
    _need(
        payload.get("counterparty_state") == COUNTERPARTY_STATE,
        "counterparty_state: must remain INBOUND_ONLY_AWAITING_PRIME_CONFIRMATION",
        errors,
    )

    tender = payload.get("tender")
    if _exact_keys(tender, TENDER_KEYS, "tender", errors):
        _need(tender.get("issuer") == "Sasria SOC Ltd", "tender.issuer: mismatch", errors)
        _need(tender.get("rfp_number") == EXPECTED_RFP, "tender.rfp_number: mismatch", errors)
        _need(tender.get("title") == EXPECTED_TITLE, "tender.title: mismatch", errors)
        _need(tender.get("portal_status") == "Published", "tender.portal_status: expected Published", errors)
        _need(tender.get("detail_url") == EXPECTED_DETAIL_URL, "tender.detail_url: provider receipt drift", errors)
        _exact_string_list(tender.get("documents"), EXPECTED_DOCUMENTS, "tender.documents", errors)
        published = _parse_dt(tender.get("published_at_portal"), "tender.published_at_portal", errors)
        close = _parse_dt(tender.get("closes_at_portal"), "tender.closes_at_portal", errors)
        queries = _parse_dt(tender.get("queries_deadline_at_portal"), "tender.queries_deadline_at_portal", errors)
        if published and close:
            _need(published < close, "tender dates: published must precede close", errors)
        if queries and close:
            _need(queries < close, "tender dates: query deadline must precede close", errors)
        _need(
            tender.get("published_at_portal") == "2026-08-24T22:00:00+02:00",
            "tender.published_at_portal: provider receipt drift",
            errors,
        )
        _need(
            tender.get("closes_at_portal") == "2026-09-17T10:00:00+02:00",
            "tender.closes_at_portal: provider receipt drift",
            errors,
        )
        _need(
            tender.get("queries_deadline_at_portal") == "2026-09-13T22:00:00+02:00",
            "tender.queries_deadline_at_portal: provider receipt drift",
            errors,
        )

    receipt = payload.get("source_receipt")
    if _exact_keys(receipt, RECEIPT_KEYS, "source_receipt", errors):
        _parse_dt(receipt.get("observed_at"), "source_receipt.observed_at", errors)
        _need(
            receipt.get("observed_at") == EXPECTED_OBSERVED_AT,
            "source_receipt.observed_at: provider receipt drift",
            errors,
        )
        _need(
            receipt.get("source_kind") == "SASRIA_PUBLIC_ETENDER_DETAIL",
            "source_receipt.source_kind: mismatch",
            errors,
        )
        _need(
            receipt.get("controlling_documents_read") is False,
            "source_receipt.controlling_documents_read: self-attested v1 must remain false",
            errors,
        )
        _need(
            receipt.get("note") == EXPECTED_RECEIPT_NOTE,
            "source_receipt.note: self-attested public-source note drift",
            errors,
        )

    gates = payload.get("prime_gates")
    if _exact_keys(gates, set(REQUIRED_PRIME_GATES), "prime_gates", errors):
        for key in REQUIRED_PRIME_GATES:
            _need(
                gates.get(key) is False,
                f"prime_gates.{key}: self-attested v1 cannot assert prime evidence",
                errors,
            )

    boundary = payload.get("tjlabs_boundary")
    if _exact_keys(boundary, BOUNDARY_KEYS, "tjlabs_boundary", errors):
        for false_field in (
            "prime_role",
            "submission_authority",
            "legal_or_compliance_certification",
            "production_mutation_authority",
        ):
            _need(boundary.get(false_field) is False, f"tjlabs_boundary.{false_field}: must be false", errors)
        _need(
            boundary.get("learner_pii") == "OPAQUE_IDENTIFIERS_ONLY",
            "tjlabs_boundary.learner_pii: boundary widened",
            errors,
        )
        _exact_string_list(
            boundary.get("deliverables"),
            EXPECTED_DELIVERABLES,
            "tjlabs_boundary.deliverables",
            errors,
            ordered=True,
        )

    pathways = payload.get("role_pathways")
    if not isinstance(pathways, list) or len(pathways) != 6:
        errors.append("role_pathways: exactly six slots required")
    else:
        seen_ids: set[str] = set()
        for index, item in enumerate(pathways, 1):
            label = f"role_pathways[{index - 1}]"
            if not _exact_keys(item, PATHWAY_KEYS, label, errors):
                continue
            expected_id = f"role-{index:02d}"
            _need(item.get("id") == expected_id, f"{label}.id: expected {expected_id}", errors)
            if type(item.get("id")) is str:
                _need(item["id"] not in seen_ids, f"{label}.id: duplicate identifier", errors)
                seen_ids.add(item["id"])
            _need(
                item.get("acceptance_criteria") == [],
                f"{label}.acceptance_criteria: self-attested v1 cannot persist prime-supplied text",
                errors,
            )

    release_block = payload.get("release")
    if _exact_keys(release_block, RELEASE_KEYS, "release", errors):
        _need(
            release_block.get("buyer_send_allowed") is False,
            "release.buyer_send_allowed: this artifact never grants outbound authority",
            errors,
        )
        _need(
            release_block.get("bid_submission_allowed") is False,
            "release.bid_submission_allowed: this artifact never grants submission authority",
            errors,
        )
        _need(
            release_block.get("status") == RELEASE_STATUS,
            "release.status: must remain HOLD_PRIME_AND_TENDER_INPUTS",
            errors,
        )

    if release:
        errors.append(SELF_ATTESTED_RELEASE_HOLD)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scope", type=Path)
    parser.add_argument(
        "--release",
        action="store_true",
        help="prove that this self-attested generation cannot authorize prime-backed release",
    )
    args = parser.parse_args()
    try:
        payload = load_payload_text(args.scope.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, StrictJSONError, ValueError) as exc:
        print(f"HOLD: input JSON rejected: {exc}")
        return 2
    errors = validate(payload, release=args.release)
    if errors:
        for error in errors:
            print(f"HOLD: {error}")
        return 2
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
