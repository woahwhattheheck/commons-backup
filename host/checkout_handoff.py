#!/usr/bin/env python3
"""Acceptance-locked hosted-checkout handoff for Commons.

This module is deliberately provider-credential-free.  It creates a request
envelope for a server-side Stripe Checkout Sessions call and folds normalized,
verified provider observations into a conservative payment-truth projection.
It never calls Stripe, Airtable, email, or a bank.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_CATALOG = ROOT / "revenue" / "outcome_commerce" / "catalog.json"

REQUEST_KEYS = {
    "schema_version", "kind", "request_id", "crm", "sku_id", "state",
    "acceptance", "acceptance_digest", "quote", "provider", "routes",
}
CRM_KEYS = {"base_id", "table_id", "record_id"}
ACCEPTANCE_KEYS = {
    "intake_sentence", "given", "when", "then", "input", "expected_output",
    "environment", "window_start", "window_end", "timezone", "refund_choice",
    "exclusions",
}
QUOTE_KEYS = {"currency", "amount"}
PROVIDER_KEYS = {"name", "livemode"}
ROUTE_KEYS = {"success_url", "cancel_url"}
EVENT_KEYS = {
    "schema_version", "kind", "event_id", "provider", "provider_event_id",
    "provider_event_type", "provider_object_ref", "request_id", "crm_record_ref",
    "sku_id", "acceptance_digest", "occurred_at", "observed_at", "verification",
    "payload_sha256", "amount_minor", "currency", "facts",
}
FACT_KEYS = {
    "payment_status", "funds_available", "payout_status", "bank_posted",
    "refund_status",
}
REQUIRED_EXCLUSIONS = {
    "credentials", "private-data", "pii-phi", "authentication", "billing",
    "production-migration", "ongoing-hosting-or-sla", "white-box-or-model-files",
}
EVENT_TYPES = {
    "checkout.session.created", "checkout.session.completed",
    "payment_intent.succeeded", "charge.succeeded", "balance.available",
    "payout.paid", "charge.refunded", "commons.bank_available.confirmed",
}
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,120}$")
AIRTABLE_RE = {
    "base_id": re.compile(r"^app[A-Za-z0-9]{14}$"),
    "table_id": re.compile(r"^tbl[A-Za-z0-9]{14}$"),
    "record_id": re.compile(r"^rec[A-Za-z0-9]{14}$"),
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
URL_RE = re.compile(r"^https://[^\s]+$")
SENSITIVE_KEYS = {
    "password", "secret", "token", "api_key", "apikey", "card", "card_number",
    "credential", "routing_number", "bank_account", "tax_id", "ssn", "pii", "phi",
}


class HandoffError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(value: Any) -> str:
    text = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_float=lambda value: (_ for _ in ()).throw(
            HandoffError("JSON numbers must not use floating point: %s" % value)
        ))


def timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not (value.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", value)):
        raise HandoffError("%s must be an offset-aware ISO-8601 timestamp" % field)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise HandoffError("%s must be a real timestamp" % field) from exc
    if parsed.utcoffset() is None:
        raise HandoffError("%s must include an offset" % field)
    return parsed.astimezone(timezone.utc)


def require_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffError("%s must be an object" % field)
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise HandoffError("%s fields mismatch; missing=%s extra=%s" % (field, missing, extra))
    return value


def reject_sensitive_keys(value: Any, path: str = "request") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in SENSITIVE_KEYS:
                raise HandoffError("%s.%s is a forbidden private-data field" % (path, key))
            reject_sensitive_keys(child, "%s.%s" % (path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_sensitive_keys(child, "%s[%d]" % (path, index))


def decimal_amount(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", value):
        raise HandoffError("%s must be a non-negative two-decimal string" % field)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise HandoffError("%s is not a decimal" % field) from exc


def catalog_listing(catalog: dict[str, Any], sku_id: str) -> dict[str, Any]:
    for listing in catalog.get("listings", []):
        if listing.get("id") == sku_id:
            return listing
    raise HandoffError("unknown canonical sku_id: %s" % sku_id)


def listing_fixed_amount(listing: dict[str, Any]) -> tuple[str, Decimal]:
    pricing = listing.get("pricing", {})
    components = pricing.get("components")
    if not isinstance(components, list) or len(components) != 1:
        raise HandoffError("checkout handoff requires exactly one canonical price component")
    component = components[0]
    if component.get("kind") != "fixed":
        raise HandoffError("checkout handoff currently requires a fixed canonical price")
    currency = pricing.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise HandoffError("canonical currency must be a three-letter code")
    return currency, decimal_amount(component.get("amount"), "catalog amount")


def acceptance_digest(acceptance: dict[str, Any]) -> str:
    return sha256(acceptance)


def validate_request(request: Any, catalog: dict[str, Any]) -> dict[str, Any]:
    request = require_keys(request, REQUEST_KEYS, "request")
    reject_sensitive_keys(request)
    if request["schema_version"] != "commons-checkout-request/v1":
        raise HandoffError("schema_version must be commons-checkout-request/v1")
    if request["kind"] != "ACCEPTANCE_LOCKED_CHECKOUT_REQUEST":
        raise HandoffError("kind must be ACCEPTANCE_LOCKED_CHECKOUT_REQUEST")
    if request["state"] != "ACCEPTANCE_LOCKED":
        raise HandoffError("state must be ACCEPTANCE_LOCKED")
    if not isinstance(request["request_id"], str) or not ID_RE.fullmatch(request["request_id"]):
        raise HandoffError("request_id is invalid")

    crm = require_keys(request["crm"], CRM_KEYS, "crm")
    for field, pattern in AIRTABLE_RE.items():
        if not isinstance(crm[field], str) or not pattern.fullmatch(crm[field]):
            raise HandoffError("crm.%s is not an Airtable ID" % field)
    if crm["base_id"] != "appo8mlEVFcph1SP0" or crm["table_id"] != "tblYNSKoenAE3Tcl1":
        raise HandoffError("checkout handoff must reuse the existing JOJO Revenue Pipeline table")

    acceptance = require_keys(request["acceptance"], ACCEPTANCE_KEYS, "acceptance")
    for field in ACCEPTANCE_KEYS - {"exclusions"}:
        if not isinstance(acceptance[field], str) or not acceptance[field].strip():
            raise HandoffError("acceptance.%s must be a nonempty string" % field)
    if acceptance["timezone"] != "America/New_York":
        raise HandoffError("acceptance.timezone must be America/New_York")
    if acceptance["refund_choice"] not in {
        "REFUND_IF_MISS", "FREE_NEXT_BUSINESS_DAY_REPAIR_IF_MISS",
    }:
        raise HandoffError("acceptance.refund_choice is invalid")
    exclusions = acceptance["exclusions"]
    if not isinstance(exclusions, list) or set(exclusions) != REQUIRED_EXCLUSIONS or len(exclusions) != len(set(exclusions)):
        raise HandoffError("acceptance.exclusions must contain the exact bounded offer exclusions")
    if timestamp(acceptance["window_end"], "acceptance.window_end") <= timestamp(
        acceptance["window_start"], "acceptance.window_start"
    ):
        raise HandoffError("acceptance.window_end must be after window_start")
    digest = acceptance_digest(acceptance)
    if request["acceptance_digest"] != digest:
        raise HandoffError("acceptance_digest does not match the canonical acceptance object")

    if not isinstance(request["sku_id"], str) or not ID_RE.fullmatch(request["sku_id"]):
        raise HandoffError("sku_id is invalid")
    listing = catalog_listing(catalog, request["sku_id"])
    canonical_currency, canonical_amount = listing_fixed_amount(listing)
    quote = require_keys(request["quote"], QUOTE_KEYS, "quote")
    amount = decimal_amount(quote["amount"], "quote.amount")
    if quote["currency"] != canonical_currency or amount != canonical_amount:
        raise HandoffError("quote must equal the canonical catalog currency and amount")

    provider = require_keys(request["provider"], PROVIDER_KEYS, "provider")
    if provider["name"] != "stripe" or not isinstance(provider["livemode"], bool):
        raise HandoffError("provider must name Stripe and use an explicit livemode boolean")
    routes = require_keys(request["routes"], ROUTE_KEYS, "routes")
    for field in ROUTE_KEYS:
        if not isinstance(routes[field], str) or not URL_RE.fullmatch(routes[field]):
            raise HandoffError("routes.%s must be an https URL" % field)
    return request


def integration_identifier(request_id: str) -> str:
    digest = sha256(request_id)
    suffix = "".join(chr(ord("a") + int(char, 16)) for char in digest[:8])
    return "commons_checkout_" + suffix


def build_checkout_envelope(request: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    request = validate_request(request, catalog)
    listing = catalog_listing(catalog, request["sku_id"])
    currency, amount = listing_fixed_amount(listing)
    amount_minor = int(amount * 100)
    digest = sha256({
        "request_id": request["request_id"],
        "record_id": request["crm"]["record_id"],
        "sku_id": request["sku_id"],
        "acceptance_digest": request["acceptance_digest"],
    })
    idempotency_key = "commons-checkout-" + digest[:40]
    metadata = {
        "commons_request_id": request["request_id"],
        "commons_crm_record": request["crm"]["record_id"],
        "commons_sku_id": request["sku_id"],
        "commons_acceptance_sha256": request["acceptance_digest"],
        "commons_dedupe_key": idempotency_key,
    }
    parameters = {
        "mode": "payment",
        "ui_mode": "hosted",
        "success_url": request["routes"]["success_url"],
        "cancel_url": request["routes"]["cancel_url"],
        "client_reference_id": request["crm"]["record_id"],
        "integration_identifier": integration_identifier(request["request_id"]),
        "line_items": [{
            "quantity": 1,
            "price_data": {
                "currency": currency.lower(),
                "unit_amount": amount_minor,
                "product_data": {
                    "name": listing.get("name", request["sku_id"]),
                    "description": "Acceptance-locked Commons outcome; sha256:%s" % request["acceptance_digest"],
                },
            },
        }],
        "metadata": metadata,
        "payment_intent_data": {"metadata": metadata},
    }
    return {
        "schema_version": "commons-checkout-envelope/v1",
        "kind": "PROVIDER_REQUEST_ENVELOPE",
        "provider": "stripe",
        "livemode": request["provider"]["livemode"],
        "operation": "checkout.sessions.create",
        "api_version": "2026-07-29.dahlia",
        "idempotency_key": idempotency_key,
        "parameters": parameters,
        "claims": [
            "The canonical SKU amount and accepted binary scope are bound before checkout creation.",
            "The envelope is ready for a server-side Stripe Checkout Sessions call.",
        ],
        "non_claims": [
            "This envelope did not call Stripe or create a Checkout Session.",
            "It is not authorization, settlement, payout, bank availability, delivery, or cash.",
        ],
    }


def validate_event(event: Any, request: dict[str, Any]) -> dict[str, Any]:
    event = require_keys(event, EVENT_KEYS, "event")
    reject_sensitive_keys(event, "event")
    if event["schema_version"] != "commons-checkout-event/v1" or event["kind"] != "CHECKOUT_PROVIDER_OBSERVATION":
        raise HandoffError("event schema_version or kind is invalid")
    for field in ("event_id", "provider_event_id"):
        if not isinstance(event[field], str) or not ID_RE.fullmatch(event[field]):
            raise HandoffError("event.%s is invalid" % field)
    if event["provider_event_type"] not in EVENT_TYPES:
        raise HandoffError("unsupported provider_event_type")
    bank_event = event["provider_event_type"] == "commons.bank_available.confirmed"
    expected_provider = "bank-readback" if bank_event else "stripe"
    expected_verification = "PRIVATE_READBACK_VERIFIED" if bank_event else "SIGNATURE_VERIFIED"
    if event["provider"] != expected_provider or event["verification"] != expected_verification:
        raise HandoffError("provider event lacks the required integrity verification")
    if not isinstance(event["provider_object_ref"], str) or not event["provider_object_ref"].strip():
        raise HandoffError("provider_object_ref must be a public-safe opaque reference")
    if not isinstance(event["payload_sha256"], str) or not SHA256_RE.fullmatch(event["payload_sha256"]):
        raise HandoffError("payload_sha256 is invalid")
    occurred = timestamp(event["occurred_at"], "event.occurred_at")
    observed = timestamp(event["observed_at"], "event.observed_at")
    if observed < occurred:
        raise HandoffError("event.observed_at precedes occurred_at")
    bindings = {
        "request_id": request["request_id"],
        "crm_record_ref": request["crm"]["record_id"],
        "sku_id": request["sku_id"],
        "acceptance_digest": request["acceptance_digest"],
        "currency": request["quote"]["currency"],
        "amount_minor": int(decimal_amount(request["quote"]["amount"], "quote.amount") * 100),
    }
    for field, expected in bindings.items():
        if event[field] != expected:
            raise HandoffError("event.%s does not match the acceptance-locked request" % field)
    facts = event["facts"]
    if not isinstance(facts, dict) or not set(facts).issubset(FACT_KEYS):
        raise HandoffError("event.facts contains unsupported fields")
    if bank_event and facts != {"bank_posted": True}:
        raise HandoffError("bank availability requires an explicit positive private bank readback")
    if event["provider_event_type"] == "balance.available" and facts != {"funds_available": True}:
        raise HandoffError("balance.available requires funds_available=true")
    if event["provider_event_type"] == "payout.paid" and facts != {"payout_status": "paid"}:
        raise HandoffError("payout.paid requires payout_status=paid")
    if event["provider_event_type"] == "charge.refunded" and facts != {"refund_status": "succeeded"}:
        raise HandoffError("charge.refunded requires refund_status=succeeded")
    if event["provider_event_type"] == "checkout.session.completed":
        if facts.get("payment_status") not in {"paid", "unpaid", "no_payment_required"} or len(facts) != 1:
            raise HandoffError("checkout.session.completed requires one payment_status fact")
    return event


def payment_projection(request: dict[str, Any], events: list[dict[str, Any]], catalog: dict[str, Any]) -> dict[str, Any]:
    request = validate_request(request, catalog)
    unique: dict[str, dict[str, Any]] = {}
    duplicate_event_ids: list[str] = []
    for raw in events:
        event = validate_event(raw, request)
        provider_id = event["provider_event_id"]
        if provider_id in unique:
            if canonical(unique[provider_id]) != canonical(event):
                raise HandoffError("conflicting duplicate provider_event_id %s" % provider_id)
            duplicate_event_ids.append(provider_id)
        else:
            unique[provider_id] = event
    rows = sorted(unique.values(), key=lambda row: (row["occurred_at"], row["event_id"]))
    types = {row["provider_event_type"] for row in rows}
    paid_checkout = any(
        row["provider_event_type"] == "checkout.session.completed"
        and row["facts"].get("payment_status") == "paid"
        for row in rows
    )
    authorization = bool(types & {"payment_intent.succeeded", "charge.succeeded"}) or paid_checkout
    settlement = "balance.available" in types
    payout = "payout.paid" in types
    bank_available = "commons.bank_available.confirmed" in types
    refunded = "charge.refunded" in types
    delivery_start_allowed = authorization and not refunded
    if refunded:
        next_action = "STOP DELIVERY; retain the refund receipt and reconcile the accepted scope."
        result = "REFUNDED; authorization does not permit fulfillment."
    elif delivery_start_allowed:
        next_action = "START DELIVERY at %s; binary acceptance remains due by %s." % (
            request["acceptance"]["window_start"], request["acceptance"]["window_end"],
        )
        result = "PAYMENT AUTHORIZATION CONFIRMED; settlement, payout, and bank availability remain separately measured."
    elif rows:
        next_action = "WAIT FOR VERIFIED PAYMENT AUTHORIZATION; do not start the delivery clock."
        result = "CHECKOUT OBSERVED; PAYMENT AUTHORIZATION UNMEASURED."
    else:
        next_action = "CREATE THE CUSTOMER-SPECIFIC HOSTED CHECKOUT FROM THE ACCEPTANCE-LOCKED ENVELOPE."
        result = "NO PROVIDER EVENT OBSERVED; PAYMENT AUTHORIZATION UNMEASURED."
    truth = {
        "authorization": "CONFIRMED" if authorization else "UNMEASURED",
        "settlement": "CONFIRMED" if settlement else "UNMEASURED",
        "payout": "CONFIRMED" if payout else "UNMEASURED",
        "bank_available": "CONFIRMED" if bank_available else "UNMEASURED",
        "refunded": "CONFIRMED" if refunded else "UNMEASURED",
        "cash_claimed": bool(bank_available and not refunded),
    }
    return {
        "schema_version": "commons-checkout-projection/v1",
        "kind": "CHECKOUT_PAYMENT_TRUTH",
        "request_id": request["request_id"],
        "crm_record_ref": request["crm"]["record_id"],
        "sku_id": request["sku_id"],
        "acceptance_digest": request["acceptance_digest"],
        "source_event_count": len(events),
        "unique_event_count": len(rows),
        "deduped_provider_event_ids": sorted(set(duplicate_event_ids)),
        "provider_object_refs": sorted({row["provider_object_ref"] for row in rows}),
        "payment_truth": truth,
        "fulfillment": {
            "delivery_start_allowed": delivery_start_allowed,
            "window_start": request["acceptance"]["window_start"],
            "window_end": request["acceptance"]["window_end"],
            "next_action": next_action,
        },
        "crm_mutation_plan": {
            "policy": "UPDATE_EXISTING_RECORD_ONLY",
            "base_id": request["crm"]["base_id"],
            "table_id": request["crm"]["table_id"],
            "record_id": request["crm"]["record_id"],
            "fields_by_id": {
                "fldDf9lWyJLw7CzLM": result,
                "fld1D14nHtiJp4KP7": next_action,
            },
            "stage_change": None,
        },
        "claims": ["The projection is a deterministic fold of normalized verified observations."],
        "non_claims": [
            "The projector did not call Stripe, Airtable, email, a delivery runtime, or a bank.",
            "Checkout completion is not settlement, payout, bank availability, delivery, acceptance, or cash.",
            "A payout-paid event does not prove that funds posted at the bank.",
        ],
    }


def write_or_print(value: Any, path: str | None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        print(destination)
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="host/checkout_handoff.py")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    sub = parser.add_subparsers(dest="command", required=True)
    digest_parser = sub.add_parser("digest")
    digest_parser.add_argument("--request", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--request", required=True)
    build_parser.add_argument("--out")
    project_parser = sub.add_parser("project")
    project_parser.add_argument("--request", required=True)
    project_parser.add_argument("--events", required=True)
    project_parser.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        request = load_json(args.request)
        if args.command == "digest":
            acceptance = require_keys(request.get("acceptance"), ACCEPTANCE_KEYS, "acceptance")
            print(acceptance_digest(acceptance))
            return 0
        catalog = load_json(args.catalog)
        if args.command == "build":
            write_or_print(build_checkout_envelope(request, catalog), args.out)
            return 0
        events = load_json(args.events)
        if not isinstance(events, list):
            raise HandoffError("events input must be a JSON array")
        write_or_print(payment_projection(request, events, catalog), args.out)
        return 0
    except (HandoffError, OSError, json.JSONDecodeError) as exc:
        print("INVALID %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
