#!/usr/bin/env python3
"""Accepted-scope-to-delivery composer for Commons.

Turns a written buyer agreement plus public observations into an exact SOW,
bounded work packet, execution status, evidence bundle, delivery receipt,
invoice/payment state, and buyer handoff.

This module never invents acceptance, work, delivery, invoice, payment,
testimonial, or receipt. It never calls Stripe, Airtable, email, or a bank.
It never writes party names, emails, addresses, or secrets onto public artifacts.

QUOTED != CHARGEABLE != INVOICED != AUTHORIZATION != SETTLEMENT != PAYOUT != BANK_AVAILABLE
Payment never proves delivery. Catalog cash stays $0 until BANK_AVAILABLE evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_CATALOG = ROOT / "revenue" / "outcome_commerce" / "catalog.json"
DEFAULT_BINDINGS = ROOT / "revenue" / "scope_to_delivery" / "catalog_bindings.json"

SCHEMA_AGREEMENT = "commons-scope-agreement/v1"
SCHEMA_OBSERVATIONS = "commons-scope-observations/v1"
SCHEMA_PAYMENT = "commons-scope-payment/v1"
SCHEMA_PROJECT = "commons-scope-project/v1"

AGREEMENT_KEYS = {
    "schema_version", "kind", "agreement_id", "sku_id", "quote",
    "window", "written_acceptance", "buyer_ref", "intake_sentence",
    "acceptance_rows", "exclusions", "refund_choice",
}
QUOTE_KEYS = {"currency", "amount"}
WINDOW_KEYS = {"start", "end", "timezone"}
WRITTEN_KEYS = {"status", "attestation", "terms_digest", "public_ref", "accepted_at"}
ROW_KEYS = {"id", "given", "when", "then", "evidence_required"}
TERMS_KEYS = (
    "sku_id", "quote", "window", "intake_sentence",
    "acceptance_rows", "exclusions", "refund_choice",
)
OBSERVATIONS_KEYS = {"schema_version", "kind", "agreement_id", "observations"}
OBSERVATION_KEYS = {
    "observation_id", "kind", "row_id", "result",
    "public_ref", "sha256", "observed_at", "note",
}
PAYMENT_KEYS = {
    "schema_version", "kind", "agreement_id", "processor_ref",
    "invoice_issued", "authorization", "settlement", "payout",
    "bank_available", "amount", "currency",
}

WRITTEN_STATUSES = {"PRESENT", "ABSENT", "REJECTED", "EXPIRED"}
ACCEPTANCE_ATTESTATION = "AUTHORIZED_OPERATOR_VERIFIED_EXACT_TERMS_ACCEPTANCE"
TERMS_ATTESTATION = "AUTHORIZED_OPERATOR_VERIFIED_TERMS_SENT"
REFUND_CHOICES = {
    "REFUND_IF_MISS",
    "FREE_NEXT_BUSINESS_DAY_REPAIR_IF_MISS",
    "UNKNOWN",
}
OBSERVATION_KINDS = {"WORK_STARTED", "ACCEPTANCE_ROW", "BLOCKED", "CLAIMED_COMPLETE"}
ROW_RESULTS = {"PASS", "MISS", "UNMEASURED"}
MONEY_STATES = {"CONFIRMED", "UNMEASURED", "ABSENT", "FAILED"}
PARTY_FORBIDDEN = {
    "legal_name", "billing_address", "shipping_address", "contact_name",
    "customer_phone", "company_name", "buyer_name", "buyer_email",
}

ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,120}$")
BUYER_RE = re.compile(r"^buyer_[0-9a-f]{32,64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_RE = re.compile(r"^opaque:[A-Za-z0-9._-]{8,200}$")
PUBLIC_REF_RE = re.compile(r"^(https://[^\s]+|p/[A-Za-z0-9._-]+\.md|revenue/[A-Za-z0-9._/-]+)$")
SENSITIVE_KEYS = {
    "password", "secret", "token", "api_key", "apikey", "card", "card_number",
    "credential", "routing_number", "bank_account", "tax_id", "ssn", "pii", "phi",
    "cvv", "iban", "testimonial", "customer_email", "customer_name",
    "street_address", "private_key",
}


class PipelineError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(value: Any) -> str:
    text = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_float=lambda value: (_ for _ in ()).throw(
            PipelineError("JSON numbers must not use floating point: %s" % value)
        ))


def timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not (value.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", value)):
        raise PipelineError("%s must be an offset-aware ISO-8601 timestamp" % field)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise PipelineError("%s must be a real timestamp" % field) from exc
    if parsed.utcoffset() is None:
        raise PipelineError("%s must include an offset" % field)
    return parsed.astimezone(timezone.utc)


def require_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError("%s must be an object" % field)
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PipelineError("%s fields mismatch; missing=%s extra=%s" % (field, missing, extra))
    return value


def reject_sensitive_keys(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            if lowered in SENSITIVE_KEYS or lowered in PARTY_FORBIDDEN:
                raise PipelineError("%s.%s is a forbidden private-data or party field" % (path, key))
            reject_sensitive_keys(child, "%s.%s" % (path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_sensitive_keys(child, "%s[%d]" % (path, index))


def decimal_amount(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", value):
        raise PipelineError("%s must be a non-negative two-decimal string" % field)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise PipelineError("%s is not a decimal" % field) from exc


def nonempty_string(value: Any, field: str, *, max_length: int = 800) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError("%s must be a nonempty string" % field)
    if value != value.strip():
        raise PipelineError("%s must not have leading or trailing whitespace" % field)
    if len(value) > max_length:
        raise PipelineError("%s exceeds %d characters" % (field, max_length))
    return value


def catalog_listing(catalog: dict[str, Any], sku_id: str) -> dict[str, Any]:
    for listing in catalog.get("listings", []):
        if listing.get("id") == sku_id:
            return listing
    raise PipelineError("unknown canonical sku_id: %s" % sku_id)


def listing_quoted_amount(listing: dict[str, Any]) -> tuple[str, Decimal]:
    pricing = listing.get("pricing") or {}
    currency = pricing.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise PipelineError("canonical currency must be a three-letter code")
    components = pricing.get("components")
    if not isinstance(components, list) or not components:
        raise PipelineError("listing requires pricing components")
    total = Decimal("0.00")
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise PipelineError("pricing component %d is invalid" % index)
        if "amount" in component:
            total += decimal_amount(component["amount"], "component.amount")
        elif "unit_amount" in component:
            total += decimal_amount(component["unit_amount"], "component.unit_amount")
        else:
            raise PipelineError("pricing component %d has no amount" % index)
    return currency, total


def load_bindings(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_BINDINGS
    if not target.exists():
        return {"skus": {}}
    data = load_json(target)
    if not isinstance(data, dict) or not isinstance(data.get("skus"), dict):
        raise PipelineError("catalog_bindings.json must be an object with a skus map")
    return data


def terms_object(agreement: dict[str, Any]) -> dict[str, Any]:
    return {key: agreement[key] for key in TERMS_KEYS}


def terms_digest(agreement: dict[str, Any]) -> str:
    return sha256(terms_object(agreement))


def validate_row(row: Any, field: str) -> dict[str, Any]:
    row = require_keys(row, ROW_KEYS, field)
    nonempty_string(row["id"], field + ".id", max_length=80)
    if not ID_RE.fullmatch(row["id"]):
        raise PipelineError("%s.id is invalid" % field)
    for key in ("given", "when", "then"):
        nonempty_string(row[key], "%s.%s" % (field, key))
    required = row["evidence_required"]
    if not isinstance(required, list) or not required or any(not isinstance(item, str) for item in required):
        raise PipelineError("%s.evidence_required must be a nonempty string list" % field)
    if "public_ref" not in required or "sha256" not in required:
        raise PipelineError("%s.evidence_required must include public_ref and sha256" % field)
    return row


def validate_agreement(agreement: Any, catalog: dict[str, Any]) -> dict[str, Any]:
    reject_sensitive_keys(agreement, "agreement")
    agreement = require_keys(agreement, AGREEMENT_KEYS, "agreement")
    if agreement["schema_version"] != SCHEMA_AGREEMENT:
        raise PipelineError("schema_version must be %s" % SCHEMA_AGREEMENT)
    if agreement["kind"] != "SCOPE_AGREEMENT":
        raise PipelineError("kind must be SCOPE_AGREEMENT")
    if not isinstance(agreement["agreement_id"], str) or not ID_RE.fullmatch(agreement["agreement_id"]):
        raise PipelineError("agreement_id is invalid")
    if not isinstance(agreement["sku_id"], str) or not ID_RE.fullmatch(agreement["sku_id"]):
        raise PipelineError("sku_id is invalid")
    listing = catalog_listing(catalog, agreement["sku_id"])
    quote = require_keys(agreement["quote"], QUOTE_KEYS, "quote")
    amount = decimal_amount(quote["amount"], "quote.amount")
    currency, catalog_amount = listing_quoted_amount(listing)
    if quote["currency"] != currency:
        raise PipelineError("quote.currency must equal the catalog currency")
    if amount != catalog_amount:
        raise PipelineError("quote.amount must equal the catalog total %s" % catalog_amount)
    window = require_keys(agreement["window"], WINDOW_KEYS, "window")
    nonempty_string(window["timezone"], "window.timezone", max_length=64)
    start = timestamp(window["start"], "window.start")
    end = timestamp(window["end"], "window.end")
    if end <= start:
        raise PipelineError("window.end must be after window.start")
    written = require_keys(agreement["written_acceptance"], WRITTEN_KEYS, "written_acceptance")
    if written["status"] not in WRITTEN_STATUSES:
        raise PipelineError("written_acceptance.status is invalid")
    digest = terms_digest(agreement)
    if written["terms_digest"] != digest:
        raise PipelineError("written_acceptance.terms_digest does not match the canonical terms")
    if written["status"] == "PRESENT":
        if written["attestation"] != ACCEPTANCE_ATTESTATION:
            raise PipelineError("PRESENT acceptance requires the exact terms attestation")
        if not isinstance(written["public_ref"], str) or not PUBLIC_REF_RE.fullmatch(written["public_ref"]):
            raise PipelineError("PRESENT acceptance requires a public_ref")
        timestamp(written["accepted_at"], "written_acceptance.accepted_at")
    else:
        if written["attestation"] not in {None, TERMS_ATTESTATION}:
            raise PipelineError("non-PRESENT attestation must be null or TERMS_SENT")
        if written["public_ref"] is not None:
            raise PipelineError("non-PRESENT acceptance must not carry a public_ref")
        if written["accepted_at"] is not None:
            raise PipelineError("non-PRESENT acceptance must not carry accepted_at")
    if not isinstance(agreement["buyer_ref"], str) or not BUYER_RE.fullmatch(agreement["buyer_ref"]):
        raise PipelineError("buyer_ref must be an opaque buyer_<32-64 lowercase hex> token")
    nonempty_string(agreement["intake_sentence"], "intake_sentence", max_length=400)
    rows = agreement["acceptance_rows"]
    if not isinstance(rows, list) or not rows:
        raise PipelineError("acceptance_rows must be a nonempty list")
    seen = set()
    for index, row in enumerate(rows):
        validated = validate_row(row, "acceptance_rows[%d]" % index)
        if validated["id"] in seen:
            raise PipelineError("duplicate acceptance row id: %s" % validated["id"])
        seen.add(validated["id"])
    exclusions = agreement["exclusions"]
    if not isinstance(exclusions, list) or not exclusions or any(not isinstance(item, str) or not item.strip() for item in exclusions):
        raise PipelineError("exclusions must be a nonempty string list")
    if agreement["refund_choice"] not in REFUND_CHOICES:
        raise PipelineError("refund_choice is invalid")
    return agreement


def agreement_state(agreement: dict[str, Any]) -> str:
    status = agreement["written_acceptance"]["status"]
    if status == "REJECTED":
        return "REJECTED"
    if status == "EXPIRED":
        return "EXPIRED"
    if status == "PRESENT":
        return "ACCEPTED"
    if agreement["written_acceptance"]["attestation"] == TERMS_ATTESTATION:
        return "TERMS_SENT"
    return "WRITTEN_INTAKE"


def validate_observations(blob: Any, agreement: dict[str, Any]) -> dict[str, Any]:
    reject_sensitive_keys(blob, "observations")
    blob = require_keys(blob, OBSERVATIONS_KEYS, "observations")
    if blob["schema_version"] != SCHEMA_OBSERVATIONS:
        raise PipelineError("observations schema_version must be %s" % SCHEMA_OBSERVATIONS)
    if blob["kind"] != "EXECUTION_OBSERVATIONS":
        raise PipelineError("observations kind must be EXECUTION_OBSERVATIONS")
    if blob["agreement_id"] != agreement["agreement_id"]:
        raise PipelineError("observations.agreement_id does not match the agreement")
    items = blob["observations"]
    if not isinstance(items, list):
        raise PipelineError("observations must be a list")
    seen = set()
    row_ids = {row["id"] for row in agreement["acceptance_rows"]}
    for index, item in enumerate(items):
        item = require_keys(item, OBSERVATION_KEYS, "observations[%d]" % index)
        if not isinstance(item["observation_id"], str) or not ID_RE.fullmatch(item["observation_id"]):
            raise PipelineError("observations[%d].observation_id is invalid" % index)
        if item["observation_id"] in seen:
            raise PipelineError("duplicate observation_id: %s" % item["observation_id"])
        seen.add(item["observation_id"])
        if item["kind"] not in OBSERVATION_KINDS:
            raise PipelineError("observations[%d].kind is invalid" % index)
        if item["result"] not in ROW_RESULTS:
            raise PipelineError("observations[%d].result is invalid" % index)
        timestamp(item["observed_at"], "observations[%d].observed_at" % index)
        if not isinstance(item["note"], str):
            raise PipelineError("observations[%d].note must be a string" % index)
        if item["kind"] == "ACCEPTANCE_ROW":
            if item["row_id"] not in row_ids:
                raise PipelineError("observations[%d].row_id is not an acceptance row" % index)
            if item["result"] in {"PASS", "MISS"}:
                if not isinstance(item["public_ref"], str) or not PUBLIC_REF_RE.fullmatch(item["public_ref"]):
                    raise PipelineError("PASS/MISS rows require a public_ref")
                if not isinstance(item["sha256"], str) or not SHA256_RE.fullmatch(item["sha256"]):
                    raise PipelineError("PASS/MISS rows require a sha256 digest")
            else:
                if item["public_ref"] is not None or item["sha256"] is not None:
                    raise PipelineError("UNMEASURED rows must not claim evidence")
        else:
            if item["row_id"] is not None:
                raise PipelineError("%s observations must not carry a row_id" % item["kind"])
            if item["kind"] == "WORK_STARTED" and item["result"] != "UNMEASURED":
                raise PipelineError("WORK_STARTED result must be UNMEASURED")
            if item["kind"] == "BLOCKED" and item["result"] != "UNMEASURED":
                raise PipelineError("BLOCKED result must be UNMEASURED")
            if item["kind"] == "CLAIMED_COMPLETE" and item["result"] != "UNMEASURED":
                raise PipelineError("CLAIMED_COMPLETE result must be UNMEASURED")
            if item["public_ref"] is not None:
                if not isinstance(item["public_ref"], str) or not PUBLIC_REF_RE.fullmatch(item["public_ref"]):
                    raise PipelineError("optional public_ref is invalid")
            if item["sha256"] is not None and not SHA256_RE.fullmatch(item["sha256"]):
                raise PipelineError("optional sha256 is invalid")
    return blob


def validate_payment(blob: Any, agreement: dict[str, Any]) -> dict[str, Any]:
    reject_sensitive_keys(blob, "payment")
    blob = require_keys(blob, PAYMENT_KEYS, "payment")
    if blob["schema_version"] != SCHEMA_PAYMENT:
        raise PipelineError("payment schema_version must be %s" % SCHEMA_PAYMENT)
    if blob["kind"] != "PAYMENT_OBSERVATION":
        raise PipelineError("payment kind must be PAYMENT_OBSERVATION")
    if blob["agreement_id"] != agreement["agreement_id"]:
        raise PipelineError("payment.agreement_id does not match the agreement")
    if not isinstance(blob["invoice_issued"], bool):
        raise PipelineError("invoice_issued must be a boolean")
    for field in ("authorization", "settlement", "payout", "bank_available"):
        if blob[field] not in MONEY_STATES:
            raise PipelineError("payment.%s is invalid" % field)
    if blob["currency"] != agreement["quote"]["currency"]:
        raise PipelineError("payment.currency must match the quote")
    if decimal_amount(blob["amount"], "payment.amount") != decimal_amount(agreement["quote"]["amount"], "quote.amount"):
        raise PipelineError("payment.amount must match the quote")
    if blob["invoice_issued"]:
        if not isinstance(blob["processor_ref"], str) or not OPAQUE_RE.fullmatch(blob["processor_ref"]):
            raise PipelineError("issued invoices require an opaque processor_ref")
    else:
        if blob["processor_ref"] is not None:
            raise PipelineError("unissued invoices must not carry a processor_ref")
        for field in ("authorization", "settlement", "payout", "bank_available"):
            if blob[field] not in {"UNMEASURED", "ABSENT"}:
                raise PipelineError("unissued invoices cannot confirm money states")
    if blob["bank_available"] == "CONFIRMED" and blob["payout"] != "CONFIRMED":
        raise PipelineError("BANK_AVAILABLE requires CONFIRMED payout")
    if blob["payout"] == "CONFIRMED" and blob["settlement"] != "CONFIRMED":
        raise PipelineError("PAYOUT requires CONFIRMED settlement")
    if blob["settlement"] == "CONFIRMED" and blob["authorization"] != "CONFIRMED":
        raise PipelineError("SETTLEMENT requires CONFIRMED authorization")
    return blob


def compose_sow(agreement: dict[str, Any], catalog: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    listing = catalog_listing(catalog, agreement["sku_id"])
    binding = (bindings.get("skus") or {}).get(agreement["sku_id"]) or {}
    state = agreement_state(agreement)
    lock = "LOCKED_SOW" if state == "ACCEPTED" else "DRAFT_SOW"
    return {
        "schema_version": "commons-scope-sow/v1",
        "kind": "STATEMENT_OF_WORK",
        "agreement_id": agreement["agreement_id"],
        "sku_id": agreement["sku_id"],
        "sku_name": listing.get("name"),
        "lock": lock,
        "agreement_state": state,
        "quote": agreement["quote"],
        "window": agreement["window"],
        "intake_sentence": agreement["intake_sentence"],
        "in_scope": list(binding.get("in_scope") or []),
        "out_of_scope": list(agreement["exclusions"]),
        "acceptance_rows": agreement["acceptance_rows"],
        "refund_choice": agreement["refund_choice"],
        "refund_text": binding.get("refund_text") or "UNKNOWN",
        "parties": {
            "buyer": "REDACTED_PUBLIC",
            "seller": "Commons founder (public terms only)",
            "emails": "NOT_ON_PUBLIC_MAIN",
            "addresses": "NOT_ON_PUBLIC_MAIN",
            "buyer_ref": agreement["buyer_ref"],
        },
        "source": listing.get("source") or listing.get("source_artifact"),
        "honesty": [
            "DRAFT_SOW is not a locked contract.",
            "LOCKED_SOW requires written PRESENT acceptance of the exact terms digest.",
            "Party names, emails, and addresses are never filled on public main.",
        ],
    }


def compose_packet(sow: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    if sow["lock"] != "LOCKED_SOW":
        return {
            "schema_version": "commons-scope-packet/v1",
            "kind": "WORK_PACKET",
            "agreement_id": sow["agreement_id"],
            "state": "NOT_ISSUED",
            "reason": "SOW is not LOCKED_SOW; no work packet is issued without written acceptance.",
        }
    binding = (bindings.get("skus") or {}).get(sow["sku_id"]) or {}
    return {
        "schema_version": "commons-scope-packet/v1",
        "kind": "WORK_PACKET",
        "agreement_id": sow["agreement_id"],
        "state": "ISSUED",
        "sku_id": sow["sku_id"],
        "window": sow["window"],
        "in_scope": sow["in_scope"] or list(binding.get("in_scope") or []),
        "out_of_scope": sow["out_of_scope"],
        "acceptance_rows": [
            {
                "id": row["id"],
                "given": row["given"],
                "when": row["when"],
                "then": row["then"],
                "binary": True,
                "evidence_required": row["evidence_required"],
            }
            for row in sow["acceptance_rows"]
        ],
        "required_evidence": ["public_ref", "sha256"],
        "deliverables": list(binding.get("deliverables") or []),
        "honesty": [
            "A work packet is a bound, not a claim that work ran.",
            "Every acceptance row is binary PASS or MISS. There is no mostly-complete.",
        ],
    }


def _row_measurements(agreement: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    measured: dict[str, dict[str, Any]] = {}
    for item in observations:
        if item["kind"] != "ACCEPTANCE_ROW":
            continue
        prior = measured.get(item["row_id"])
        if prior and prior["result"] != item["result"]:
            raise PipelineError("conflicting results for row %s" % item["row_id"])
        if prior and prior.get("sha256") and item["sha256"] and prior["sha256"] != item["sha256"]:
            raise PipelineError("conflicting evidence for row %s" % item["row_id"])
        measured[item["row_id"]] = item
    return measured


def compose_status(agreement: dict[str, Any], observations_blob: dict[str, Any] | None) -> dict[str, Any]:
    state = agreement_state(agreement)
    items = list((observations_blob or {}).get("observations") or [])
    kinds = {item["kind"] for item in items}
    measured = _row_measurements(agreement, items)
    rows = []
    for row in agreement["acceptance_rows"]:
        hit = measured.get(row["id"])
        rows.append({
            "id": row["id"],
            "result": hit["result"] if hit else "UNMEASURED",
            "public_ref": hit["public_ref"] if hit else None,
            "sha256": hit["sha256"] if hit else None,
        })
    results = {row["result"] for row in rows}
    if state != "ACCEPTED":
        status = "NOT_STARTED"
        reason = "Work does not start without ACCEPTED written terms."
    elif "BLOCKED" in kinds:
        status = "BLOCKED"
        reason = "A BLOCKED observation is present."
    elif results == {"PASS"}:
        status = "PASS"
        reason = "Every acceptance row is PASS with public_ref and sha256."
    elif "MISS" in results:
        status = "MISS"
        reason = "At least one acceptance row is MISS."
    elif "CLAIMED_COMPLETE" in kinds:
        status = "SUBMITTED"
        reason = "Completion was claimed but acceptance rows are incomplete."
    elif "WORK_STARTED" in kinds or "UNMEASURED" not in results:
        status = "RUNNING"
        reason = "Work started; not every acceptance row is PASS."
    else:
        status = "NOT_STARTED"
        reason = "No WORK_STARTED observation is present."
    if status == "PASS" and "WORK_STARTED" not in kinds:
        status = "SUBMITTED"
        reason = "PASS rows exist but WORK_STARTED was never observed."
    return {
        "schema_version": "commons-scope-status/v1",
        "kind": "EXECUTION_STATUS",
        "agreement_id": agreement["agreement_id"],
        "agreement_state": state,
        "status": status,
        "reason": reason,
        "rows": rows,
        "work_started": "WORK_STARTED" in kinds,
        "claimed_complete": "CLAIMED_COMPLETE" in kinds,
        "blocked": "BLOCKED" in kinds,
        "honesty": [
            "Status is projected from observations only.",
            "PASS requires every acceptance row PASS with hashes.",
            "A claimed complete without hashes is SUBMITTED, never PASS.",
        ],
    }


def compose_evidence(agreement: dict[str, Any], observations_blob: dict[str, Any] | None) -> dict[str, Any]:
    items = list((observations_blob or {}).get("observations") or [])
    bundle = []
    for item in items:
        if item["kind"] != "ACCEPTANCE_ROW":
            continue
        if item["result"] in {"PASS", "MISS"}:
            bundle.append({
                "row_id": item["row_id"],
                "result": item["result"],
                "public_ref": item["public_ref"],
                "sha256": item["sha256"],
                "observed_at": item["observed_at"],
                "note": item["note"],
            })
    measured_ids = {item["row_id"] for item in bundle}
    unmeasured = [row["id"] for row in agreement["acceptance_rows"] if row["id"] not in measured_ids]
    return {
        "schema_version": "commons-scope-evidence/v1",
        "kind": "EVIDENCE_BUNDLE",
        "agreement_id": agreement["agreement_id"],
        "items": bundle,
        "unmeasured_rows": unmeasured,
        "complete": not unmeasured and all(item["result"] == "PASS" for item in bundle) and len(bundle) == len(agreement["acceptance_rows"]),
        "honesty": [
            "Only observations with public_ref and sha256 enter the bundle.",
            "Missing rows stay UNMEASURED. The composer never invents evidence.",
        ],
    }


def compose_receipt(status: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    delivered = status["status"] == "PASS" and evidence["complete"]
    missing = [row["id"] for row in status["rows"] if row["result"] != "PASS"]
    return {
        "schema_version": "commons-scope-receipt/v1",
        "kind": "DELIVERY_RECEIPT",
        "agreement_id": status["agreement_id"],
        "delivered": delivered,
        "delivery_state": "DELIVERED" if delivered else "NOT_DELIVERED",
        "execution_status": status["status"],
        "missing_rows": missing,
        "evidence_item_count": len(evidence["items"]),
        "payment_does_not_prove_delivery": True,
        "honesty": [
            "delivered is true only when every acceptance row is PASS.",
            "Authorization, settlement, payout, or a bank credit never flips delivered.",
            "This receipt is not a testimonial.",
        ],
    }


def compose_invoice(agreement: dict[str, Any], payment: dict[str, Any] | None) -> dict[str, Any]:
    if not payment or not payment.get("invoice_issued"):
        return {
            "schema_version": "commons-scope-invoice/v1",
            "kind": "INVOICE_STATE",
            "agreement_id": agreement["agreement_id"],
            "state": "NOT_ISSUED",
            "amount": agreement["quote"]["amount"],
            "currency": agreement["quote"]["currency"],
            "processor_ref": None,
            "honesty": [
                "An invoice is not issued from a quote, SOW, or delivery claim.",
                "Customer-specific invoices stay off public main except for an opaque processor_ref.",
            ],
        }
    return {
        "schema_version": "commons-scope-invoice/v1",
        "kind": "INVOICE_STATE",
        "agreement_id": agreement["agreement_id"],
        "state": "ISSUED",
        "amount": payment["amount"],
        "currency": payment["currency"],
        "processor_ref": payment["processor_ref"],
        "honesty": [
            "ISSUED is not SETTLED and not BANK_AVAILABLE.",
            "The public artifact carries only an opaque processor_ref.",
        ],
    }


def compose_payment_state(agreement: dict[str, Any], payment: dict[str, Any] | None) -> dict[str, Any]:
    if not payment:
        truth = {
            "authorization": "UNMEASURED",
            "settlement": "UNMEASURED",
            "payout": "UNMEASURED",
            "bank_available": "UNMEASURED",
        }
        processor_ref = None
        invoice_issued = False
    else:
        truth = {
            "authorization": payment["authorization"],
            "settlement": payment["settlement"],
            "payout": payment["payout"],
            "bank_available": payment["bank_available"],
        }
        processor_ref = payment["processor_ref"]
        invoice_issued = payment["invoice_issued"]
    cash_claimed = truth["bank_available"] == "CONFIRMED"
    return {
        "schema_version": "commons-scope-payment-state/v1",
        "kind": "PAYMENT_STATE",
        "agreement_id": agreement["agreement_id"],
        "invoice_issued": invoice_issued,
        "processor_ref": processor_ref,
        "payment_truth": truth,
        "cash_claimed": cash_claimed,
        "amount": agreement["quote"]["amount"],
        "currency": agreement["quote"]["currency"],
        "honesty": [
            "QUOTED != CHARGEABLE != INVOICED != AUTHORIZATION != SETTLEMENT != PAYOUT != BANK_AVAILABLE.",
            "cash_claimed is true only at BANK_AVAILABLE.",
            "Payment never proves delivery.",
        ],
    }


def compose_handoff(
    agreement: dict[str, Any],
    sow: dict[str, Any],
    packet: dict[str, Any],
    status: dict[str, Any],
    evidence: dict[str, Any],
    receipt: dict[str, Any],
    invoice: dict[str, Any],
    payment_state: dict[str, Any],
    listing: dict[str, Any],
) -> dict[str, Any]:
    gaps = []
    if sow["lock"] != "LOCKED_SOW":
        gaps.append("No written PRESENT acceptance; SOW remains DRAFT.")
    if packet.get("state") != "ISSUED":
        gaps.append("No work packet issued.")
    if not receipt["delivered"]:
        if receipt["missing_rows"]:
            gaps.append("Delivery incomplete; missing rows: %s." % ", ".join(receipt["missing_rows"]))
        else:
            gaps.append("Delivery is NOT_DELIVERED.")
    if invoice["state"] != "ISSUED":
        gaps.append("Invoice is NOT_ISSUED.")
    if not payment_state["cash_claimed"]:
        gaps.append("Cash is not BANK_AVAILABLE; cash_claimed is false.")
    markdown = "\n".join([
        "# Scope-to-delivery handoff",
        "",
        "- SKU: %s (%s)" % (listing.get("name"), agreement["sku_id"]),
        "- Agreement: `%s` state **%s**" % (agreement["agreement_id"], sow["agreement_state"]),
        "- SOW: **%s**" % sow["lock"],
        "- Work packet: **%s**" % packet.get("state"),
        "- Execution: **%s**" % status["status"],
        "- Delivery: **%s**" % receipt["delivery_state"],
        "- Invoice: **%s**" % invoice["state"],
        "- Authorization: **%s**" % payment_state["payment_truth"]["authorization"],
        "- Settlement: **%s**" % payment_state["payment_truth"]["settlement"],
        "- Payout: **%s**" % payment_state["payment_truth"]["payout"],
        "- Bank available: **%s**" % payment_state["payment_truth"]["bank_available"],
        "- Cash claimed: **%s**" % payment_state["cash_claimed"],
        "",
        "## Honest gaps",
        *(["- %s" % gap for gap in gaps] or ["- None recorded."]),
        "",
        "This handoff is not a testimonial. Payment does not prove delivery.",
        "Buyer names, emails, and addresses are not on public main.",
    ])
    return {
        "schema_version": "commons-scope-handoff/v1",
        "kind": "BUYER_HANDOFF",
        "agreement_id": agreement["agreement_id"],
        "sku_id": agreement["sku_id"],
        "sku_name": listing.get("name"),
        "artifacts": {
            "sow_lock": sow["lock"],
            "packet_state": packet.get("state"),
            "execution_status": status["status"],
            "delivery_state": receipt["delivery_state"],
            "invoice_state": invoice["state"],
            "cash_claimed": payment_state["cash_claimed"],
        },
        "gaps": gaps,
        "markdown": markdown,
        "honesty": [
            "No testimonial field exists.",
            "Gaps stay listed until evidence closes them.",
        ],
    }


def compose_project(
    agreement: dict[str, Any],
    catalog: dict[str, Any],
    bindings: dict[str, Any],
    observations: dict[str, Any] | None = None,
    payment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agreement = validate_agreement(agreement, catalog)
    if observations is not None:
        observations = validate_observations(observations, agreement)
    if payment is not None:
        payment = validate_payment(payment, agreement)
    sow = compose_sow(agreement, catalog, bindings)
    packet = compose_packet(sow, bindings)
    status = compose_status(agreement, observations)
    evidence = compose_evidence(agreement, observations)
    receipt = compose_receipt(status, evidence)
    invoice = compose_invoice(agreement, payment)
    payment_state = compose_payment_state(agreement, payment)
    listing = catalog_listing(catalog, agreement["sku_id"])
    handoff = compose_handoff(agreement, sow, packet, status, evidence, receipt, invoice, payment_state, listing)
    funnel = (catalog.get("funnels") or {}).get(agreement["sku_id"]) or {}
    return {
        "schema_version": SCHEMA_PROJECT,
        "kind": "SCOPE_TO_DELIVERY_PROJECT",
        "sku_id": agreement["sku_id"],
        "sku_name": listing.get("name"),
        "agreement_id": agreement["agreement_id"],
        "agreement_state": sow["agreement_state"],
        "catalog_funnel_truth": catalog.get("funnel_truth"),
        "routes": listing.get("routes"),
        "funnel_readiness": funnel.get("readiness"),
        "sow": sow,
        "work_packet": packet,
        "execution_status": status,
        "evidence_bundle": evidence,
        "delivery_receipt": receipt,
        "invoice": invoice,
        "payment_state": payment_state,
        "handoff": handoff,
        "markdown": handoff["markdown"],
    }


def compose_catalog(catalog: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    reject_sensitive_keys(catalog, "catalog")
    listings = []
    for listing in catalog.get("listings") or []:
        sku_id = listing.get("id")
        currency, amount = listing_quoted_amount(listing)
        binding = (bindings.get("skus") or {}).get(sku_id) or {}
        funnel = (catalog.get("funnels") or {}).get(sku_id) or {}
        listings.append({
            "id": sku_id,
            "name": listing.get("name"),
            "state": listing.get("state"),
            "currency": currency,
            "amount": format(amount, ".2f"),
            "family": binding.get("family") or "UNKNOWN",
            "in_scope": list(binding.get("in_scope") or []),
            "out_of_scope": list(binding.get("out_of_scope") or []),
            "acceptance_row_count": len(binding.get("default_acceptance_rows") or []),
            "refund_text": binding.get("refund_text") or funnel.get("fulfillment", {}).get("refund") or "UNKNOWN",
            "routes": listing.get("routes"),
            "readiness": funnel.get("readiness"),
        })
    truth = catalog.get("funnel_truth") or {}
    return {
        "schema_version": "commons-scope-catalog/v1",
        "kind": "SCOPE_TO_DELIVERY_CATALOG",
        "listing_count": len(listings),
        "listings": listings,
        "funnel_truth": truth,
        "honesty": [
            "accepted_scopes on current catalog truth: %s" % truth.get("accepted_scopes"),
            "paid_deliveries on current catalog truth: %s" % truth.get("paid_deliveries"),
            "collected_cash_usd on current catalog truth: %s" % truth.get("collected_cash_usd"),
            "This composer does not mint buyers, acceptances, or cash.",
        ],
    }


def _read_optional(path: str | None) -> Any | None:
    if not path:
        return None
    return load_json(path)


def _emit(value: Any) -> None:
    json.dump(value, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose accepted-scope-to-delivery artifacts without inventing success.")
    parser.add_argument("command", choices=[
        "catalog", "sow", "packet", "status", "evidence", "receipt",
        "invoice", "handoff", "project",
    ])
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--bindings", default=str(DEFAULT_BINDINGS))
    parser.add_argument("--agreement")
    parser.add_argument("--observations")
    parser.add_argument("--payment")
    args = parser.parse_args(argv)

    catalog = load_json(args.catalog)
    bindings = load_bindings(args.bindings)

    if args.command == "catalog":
        _emit(compose_catalog(catalog, bindings))
        return 0

    if not args.agreement:
        raise PipelineError("%s requires --agreement" % args.command)
    agreement = load_json(args.agreement)
    observations = _read_optional(args.observations)
    payment = _read_optional(args.payment)
    project = compose_project(agreement, catalog, bindings, observations, payment)
    mapping = {
        "sow": project["sow"],
        "packet": project["work_packet"],
        "status": project["execution_status"],
        "evidence": project["evidence_bundle"],
        "receipt": project["delivery_receipt"],
        "invoice": project["invoice"],
        "handoff": project["handoff"],
        "project": project,
    }
    _emit(mapping[args.command])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
