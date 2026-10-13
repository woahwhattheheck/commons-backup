from __future__ import annotations

import copy
import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .primitives import (
    MAX_SHORT, REFUND_CHOICE, decimal_amount, digest, exact, fail, identifier,
    scope_identifier, sha, text, timestamp,
)

TERMS_KEYS = {
    "sku_id", "quote", "window", "intake_sentence", "acceptance_rows",
    "exclusions", "refund_choice",
}


def catalog_quote(catalog: Mapping[str, Any], sku_id: str) -> tuple[str, Decimal]:
    if type(catalog) is not dict or type(catalog.get("listings")) is not list:
        fail("catalog.listings must be a list")
    matches = [item for item in catalog["listings"] if type(item) is dict and item.get("id") == sku_id]
    if len(matches) != 1:
        fail("sku_id must resolve to exactly one canonical catalog listing")
    pricing = matches[0].get("pricing")
    if type(pricing) is not dict or pricing.get("currency") != "USD":
        fail("v2 bridge supports only USD catalog listings")
    components = pricing.get("components")
    if type(components) is not list or not components:
        fail("catalog listing requires pricing components")
    total = Decimal("0.00")
    for i, component in enumerate(components):
        if type(component) is not dict:
            fail(f"catalog pricing component {i} is invalid")
        if "amount" in component:
            total += decimal_amount(component["amount"], f"catalog.components[{i}].amount")
        elif "unit_amount" in component:
            total += decimal_amount(component["unit_amount"], f"catalog.components[{i}].unit_amount")
        else:
            fail(f"catalog pricing component {i} has no amount")
    return "USD", total


def normalize_service_window(value: Mapping[str, Any], where: str = "service_window") -> tuple[dict[str, str], datetime]:
    value = exact(value, {"start", "end", "timezone"}, where)
    start, start_dt = timestamp(value["start"], f"{where}.start")
    end, end_dt = timestamp(value["end"], f"{where}.end")
    if end_dt <= start_dt:
        fail(f"{where}.end must be after start")
    return {
        "start": start,
        "end": end,
        "timezone": text(value["timezone"], f"{where}.timezone", max_len=64),
    }, start_dt


def scope_buyer_ref(raw_buyer_ref: str) -> str:
    value = hashlib.sha256(("commercial-offer-buyer-v1\0" + raw_buyer_ref).encode()).hexdigest()
    return "buyer_" + value


def acceptance_rows(offer: Mapping[str, Any], offer_sha256: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(offer["deliverables"]):
        item = exact(raw, {"id", "title", "acceptance_criteria", "evidence_sha256"}, f"offer.deliverables[{i}]")
        did = identifier(item["id"], f"offer.deliverables[{i}].id")
        title = text(item["title"], f"offer.deliverables[{i}].title", max_len=MAX_SHORT)
        criteria = text(item["acceptance_criteria"], f"offer.deliverables[{i}].acceptance_criteria")
        evidence_sha = sha(item["evidence_sha256"], f"offer.deliverables[{i}].evidence_sha256")
        row_id = "acc_" + hashlib.sha256((offer["offer_id"] + "\0" + did).encode()).hexdigest()[:24]
        if row_id in seen:
            fail("derived acceptance row collision")
        seen.add(row_id)
        rows.append({
            "id": row_id,
            "given": (
                f"Accepted commercial offer {offer['offer_id']} at {offer_sha256}; "
                f"deliverable {did} evidence commitment {evidence_sha}."
            ),
            "when": title,
            "then": criteria,
            "evidence_required": ["public_ref", "sha256"],
        })
    return rows


def build_scope_terms(
    verified_contract: Mapping[str, Any], catalog: Mapping[str, Any], service_window: Mapping[str, Any],
) -> dict[str, Any]:
    offer = verified_contract["offer"]
    sku_id = scope_identifier(offer["opportunity_id"], "offer.opportunity_id")
    catalog_currency, catalog_total = catalog_quote(catalog, sku_id)
    offer_amount = Decimal(offer["total_amount_minor"]) / Decimal(100)
    if catalog_currency != offer["currency"] or catalog_total != offer_amount:
        fail("accepted offer price/currency does not equal canonical catalog listing")
    window, _ = normalize_service_window(service_window)
    return {
        "sku_id": sku_id,
        "quote": {"currency": "USD", "amount": f"{offer_amount:.2f}"},
        "window": window,
        "intake_sentence": (
            f"Execute exact accepted commercial offer {offer['offer_id']} "
            f"with offer SHA-256 {verified_contract['offer_sha256']}."
        ),
        "acceptance_rows": acceptance_rows(offer, verified_contract["offer_sha256"]),
        "exclusions": copy.deepcopy(offer["exclusions"]),
        "refund_choice": REFUND_CHOICE,
    }


def terms_digest(scope_terms: Mapping[str, Any]) -> str:
    exact(scope_terms, TERMS_KEYS, "scope_terms")
    return digest(dict(scope_terms))
