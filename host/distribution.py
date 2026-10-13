#!/usr/bin/env python3
"""Commons distribution layer.

Maps canonical sellable outcomes onto public marketplaces, partner channels,
procurement roads, and developer ecosystems. Generates truthful channel-ready
packages. Tracks listing/live/lead status without inventing any of them.
Routes buyer interest back to canonical Commons conversion paths.

This module does not submit listings, open accounts, charge cards, or create
CRM rows. A package is not a live listing. SURFACE_LIVE is a Commons page,
not a marketplace listing.

Examples:

  python3 host/distribution.py validate
  python3 host/distribution.py matrix
  python3 host/distribution.py status
  python3 host/distribution.py package --offer same-day-agent-survival-proof --channel upwork-project-catalog
  python3 host/distribution.py inbound --offer same-day-agent-survival-proof --channel contra-services
  python3 host/distribution.py export
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_CHANNELS = ROOT / "revenue" / "distribution" / "channels.json"
DEFAULT_CATALOG = ROOT / "revenue" / "outcome_commerce" / "catalog.json"
DEFAULT_PACKAGES = ROOT / "revenue" / "distribution" / "packages.json"
DEFAULT_MATRIX = ROOT / "revenue" / "distribution" / "matrix.json"
DEFAULT_STATUS = ROOT / "revenue" / "distribution" / "status.json"

ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,8})?$")
MONEY_QUANTUM = Decimal("0.01")
PAGES = "https://woahwhattheheck.github.io/commons"
CONTACT = "tokenjunkielabs@gmail.com"

FIT_CLASSES = {
    "micro_sku",
    "bounded_service",
    "high_ticket_service",
    "expertise_hour",
    "high_ticket_product",
    "developer_product",
    "data_pack",
}
FAMILIES = {
    "public_marketplace",
    "partner",
    "procurement",
    "developer_ecosystem",
    "commons_surface",
    "recorded_rail",
}
MARKETPLACE_FAMILIES = {"public_marketplace", "developer_ecosystem"}
FORBIDDEN_COPY = (
    "live on upwork",
    "live on fiverr",
    "live on contra",
    "listed on upwork",
    "listed on fiverr",
    "listed on contra",
    "customers are waiting",
    "approved seller",
    "charges enabled",
    "we have buyers",
    "revenue this month",
)
OFFER_CLASS = {
    "sku-tip-20260826": "micro_sku",
    "sku-seat-20260826": "micro_sku",
    "sku-unlock-20260826": "micro_sku",
    "sku-monthly-tip-20260826": "micro_sku",
    "sku-boost-20260826": "micro_sku",
    "sku-muhlnickel-generated-token-capacity": "micro_sku",
    "sku-whitebox-hour-20260826": "expertise_hour",
    "sku-muhlnickel-attested-inference": "bounded_service",
    "sku-muhlnickel-titan-20260826": "high_ticket_product",
}


def sku_checkout_proven(listing: dict[str, Any]) -> bool:
    checkout = listing.get("checkout") if isinstance(listing.get("checkout"), dict) else {}
    url = checkout.get("url")
    return (
        checkout.get("status") == "ACTIVE_CHARGEABLE"
        and checkout.get("provider") == "stripe"
        and checkout.get("account_charges_enabled") is True
        and checkout.get("account_payouts_enabled") is True
        and checkout.get("link_active") is True
        and isinstance(url, str)
        and url.startswith("https://")
    )


class DistributionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), indent=2) + "\n"


def _load_json(path: str | os.PathLike[str]) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_float=lambda value: (_ for _ in ()).throw(
            DistributionError("JSON money must be decimal strings, not floats: %s" % value)
        ))


def _decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or not DECIMAL_RE.fullmatch(value):
        raise DistributionError("%s must be a decimal string" % field)
    try:
        out = Decimal(value)
    except InvalidOperation as exc:
        raise DistributionError("%s is not a decimal" % field) from exc
    if out < 0:
        raise DistributionError("%s must be non-negative" % field)
    return out


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise DistributionError("%s must be 8-80 characters: A-Z a-z 0-9 . _ -" % field)
    return value


def load_channels(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    data = _load_json(path or DEFAULT_CHANNELS)
    if not isinstance(data, dict) or data.get("kind") != "COMMONS_DISTRIBUTION_LAYER":
        raise DistributionError("channels.json kind must be COMMONS_DISTRIBUTION_LAYER")
    if data.get("schema_version") != "distribution/v1":
        raise DistributionError("channels.json schema_version must be distribution/v1")
    channels = data.get("channels")
    if not isinstance(channels, list) or not channels:
        raise DistributionError("channels.json must list at least one channel")
    seen: set[str] = set()
    for channel in channels:
        if not isinstance(channel, dict):
            raise DistributionError("channel must be an object")
        cid = _id(channel.get("id"), "channel.id")
        if cid in seen:
            raise DistributionError("duplicate channel id: %s" % cid)
        seen.add(cid)
        if channel.get("family") not in FAMILIES:
            raise DistributionError("%s has unknown family" % cid)
        if channel.get("submit_allowed") is not False:
            raise DistributionError("%s submit_allowed must be false" % cid)
        fits = channel.get("fits_classes")
        if not isinstance(fits, list) or not fits or set(fits) - FIT_CLASSES:
            raise DistributionError("%s fits_classes invalid" % cid)
        for key in ("amount_min", "amount_max"):
            if channel.get(key) is not None:
                _decimal(channel[key], "%s.%s" % (cid, key))
        if not isinstance(channel.get("honest_live"), bool):
            raise DistributionError("%s honest_live must be boolean" % cid)
        if channel["honest_live"] and channel["family"] in MARKETPLACE_FAMILIES:
            raise DistributionError("%s cannot claim honest_live on a marketplace family without live evidence" % cid)
    honesty = data.get("honesty") or {}
    for flag in (
        "no_fake_listings", "no_fake_accounts", "no_fake_approvals",
        "no_fake_customers", "no_fake_interest", "no_fake_revenue",
        "no_fake_provider_readiness", "no_unauthorized_submit", "no_spam",
        "no_second_crm",
    ):
        if honesty.get(flag) is not True:
            raise DistributionError("honesty.%s must be true" % flag)
    inbound = data.get("inbound_truth") or {}
    if inbound.get("verified_leads") != 0 or inbound.get("verified_customers") != 0:
        raise DistributionError("inbound_truth must not invent leads or customers")
    if inbound.get("collected_cash_usd") != "0.00":
        raise DistributionError("inbound_truth must not invent cash")
    if inbound.get("live_marketplace_listings") != 0:
        raise DistributionError("inbound_truth must not invent live marketplace listings")
    return data


def load_catalog(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    data = _load_json(path or DEFAULT_CATALOG)
    listings = data.get("listings")
    if not isinstance(listings, list) or not listings:
        raise DistributionError("catalog must contain listings")
    return data


def listing_amount(listing: dict[str, Any]) -> Decimal:
    pricing = listing.get("pricing") or {}
    components = pricing.get("components") or []
    if not components:
        raise DistributionError("%s has no pricing components" % listing.get("id"))
    total = Decimal("0")
    found = False
    for index, component in enumerate(components):
        field = "%s.components[%s]" % (listing.get("id"), index)
        if isinstance(component.get("amount"), str):
            total += _decimal(component["amount"], field + ".amount")
            found = True
        elif isinstance(component.get("unit_amount"), str):
            total += _decimal(component["unit_amount"], field + ".unit_amount")
            found = True
    if not found:
        raise DistributionError("%s has no amount or unit_amount" % listing.get("id"))
    return total


def listing_basis(listing: dict[str, Any]) -> str:
    pricing = listing.get("pricing") or {}
    components = pricing.get("components") or []
    parts = []
    for component in components:
        basis = component.get("basis")
        if basis:
            parts.append(str(basis))
    if parts:
        return "; ".join(parts)
    return str(listing.get("name") or listing.get("id"))


def classify_offer(listing: dict[str, Any]) -> str:
    oid = _id(listing.get("id"), "listing.id")
    if oid in OFFER_CLASS:
        return OFFER_CLASS[oid]
    amount = listing_amount(listing)
    if amount >= Decimal("12000.00"):
        return "high_ticket_service"
    return "bounded_service"


def human_route(listing: dict[str, Any]) -> str:
    routes = listing.get("routes") or {}
    human = routes.get("human")
    if not isinstance(human, str) or not human:
        raise DistributionError("%s missing routes.human" % listing.get("id"))
    # QUILL moved Survival off Autopsy HTML onto the landed README.
    # A public .md offer doc is a human door; do not force a false .html.
    if not (human.endswith(".html") or human.endswith(".md")):
        raise DistributionError("%s missing routes.human" % listing.get("id"))
    return human


def source_path(listing: dict[str, Any]) -> str:
    source = listing.get("source") or listing.get("source_artifact") or {}
    path = source.get("path")
    if not isinstance(path, str) or not path:
        raise DistributionError("%s missing source path" % listing.get("id"))
    return path


def source_blob(listing: dict[str, Any]) -> str:
    source = listing.get("source") or listing.get("source_artifact") or {}
    blob = source.get("blob_sha")
    if not isinstance(blob, str) or not re.fullmatch(r"[0-9a-f]{40}", blob):
        raise DistributionError("%s missing source blob_sha" % listing.get("id"))
    return blob


def _in_amount_window(channel: dict[str, Any], amount: Decimal) -> bool:
    low = channel.get("amount_min")
    high = channel.get("amount_max")
    if low is not None and amount < _decimal(low, "amount_min"):
        return False
    if high is not None and amount > _decimal(high, "amount_max"):
        return False
    return True


def fit_pair(listing: dict[str, Any], channel: dict[str, Any]) -> dict[str, Any]:
    oid = _id(listing.get("id"), "listing.id")
    cid = _id(channel.get("id"), "channel.id")
    offer_class = classify_offer(listing)
    amount = listing_amount(listing)
    reasons: list[str] = []
    fit = "FIT"
    proven_stripe_checkout = cid == "stripe-payment-links" and sku_checkout_proven(listing)
    if proven_stripe_checkout:
        reasons.append("exact active Stripe checkout is proven on the catalog")
    elif offer_class not in channel["fits_classes"]:
        fit = "UNFIT"
        reasons.append("class %s is outside %s" % (offer_class, ",".join(channel["fits_classes"])))
    elif not _in_amount_window(channel, amount):
        fit = "UNFIT"
        reasons.append("amount %s is outside channel window" % _money(amount))

    listing_state = "NOT_LISTED"
    package_state = "UNFIT"
    blocked_reason = None

    if fit == "FIT":
        package_state = "PACKAGE_READY"
        if channel["family"] == "commons_surface" and channel.get("honest_live"):
            listing_state = "SURFACE_LIVE"
        elif channel["family"] == "partner" and channel.get("honest_live"):
            listing_state = "SURFACE_LIVE"
        elif channel.get("id") == "stripe-payment-links":
            if sku_checkout_proven(listing):
                listing_state = "NOT_LISTED"
                blocked_reason = None
            else:
                listing_state = "BLOCKED_CHARGES_DISABLED"
                package_state = "PACKAGE_READY"
                blocked_reason = "Stripe rail is not proven chargeable and payout-capable on the catalog."
        elif channel.get("requires_charges_enabled") and channel.get("account_status") == "URL_RECORDED_CHARGES_DISABLED":
            listing_state = "BLOCKED_CHARGES_DISABLED"
            package_state = "PACKAGE_READY"
            blocked_reason = "Stripe livemode URLs are recorded; account_charges_enabled=false; link_active=UNVERIFIED."
        elif channel.get("account_status") == "NONE_IN_THIS_SESSION":
            if channel.get("family") in {"procurement"} and cid in {"sam-gov-procurement", "gsa-schedule"}:
                listing_state = "BLOCKED_REGISTRATION"
                blocked_reason = "No CAGE/UEI/SAM/GSA evidence on current main."
            elif channel.get("requires_identity_kyc"):
                listing_state = "BLOCKED_PROVIDER_ACCOUNT"
                blocked_reason = "No authorized %s account in this session. Identity/KYC unmet. Do not submit." % channel["name"]
            else:
                listing_state = "BLOCKED_PROVIDER_ACCOUNT"
                blocked_reason = "No authorized %s account in this session. Do not submit." % channel["name"]
        else:
            listing_state = "NOT_LISTED"

    if channel.get("submit_allowed") is True:
        raise DistributionError("submit_allowed cannot be true without live evidence")

    return {
        "id": "%s__%s" % (cid, oid),
        "offer_id": oid,
        "offer_name": listing.get("name"),
        "offer_class": offer_class,
        "offer_state": listing.get("state"),
        "amount": _money(amount),
        "currency": (listing.get("pricing") or {}).get("currency") or "USD",
        "channel_id": cid,
        "channel_name": channel.get("name"),
        "channel_family": channel.get("family"),
        "fit": fit,
        "package_state": package_state,
        "listing_state": listing_state,
        "blocked_reason": blocked_reason,
        "reasons": reasons,
        "submit_allowed": False,
        "human_route": human_route(listing),
        "source_path": source_path(listing),
        "source_blob_sha": source_blob(listing),
    }


def _exclusions(listing: dict[str, Any], channel: dict[str, Any]) -> list[str]:
    out = [
        "This package is not a live listing.",
        "This layer does not submit through any account.",
        "Do not invent customers, interest, approvals, or cash from this package.",
    ]
    oid = listing.get("id") or ""
    if isinstance(listing.get("checkout"), dict):
        if sku_checkout_proven(listing):
            out.append("Public Commons pages expose this rail only after catalog evidence. A click is intent, not cash. This layer still does not list it on a marketplace.")
        else:
            out.append("Stripe checkout is unverified; recorded URLs are provenance only.")
    if channel.get("family") == "public_marketplace":
        out.append("No seller identity or marketplace account is authorized in this session.")
    if classify_offer(listing) in {"high_ticket_service", "high_ticket_product"}:
        out.append("High-ticket work is a named-human or procurement conversation, not a gig race.")
    return out


def _scope_lines(listing: dict[str, Any]) -> list[str]:
    outcome = listing.get("outcome") or {}
    name = listing.get("name") or listing.get("id")
    basis = listing_basis(listing)
    lines = [
        "Sellable outcome: %s." % name,
        "Price basis: %s." % basis,
        "Canonical terms stay on %s." % source_path(listing),
    ]
    if outcome.get("evidence_required"):
        lines.append("Verified outcome evidence is required before any chargeable state.")
    acceptance = outcome.get("acceptance_source")
    if acceptance:
        lines.append("Acceptance contract: %s." % acceptance)
    return lines


def channel_copy(listing: dict[str, Any], channel: dict[str, Any], pair: dict[str, Any]) -> str:
    name = listing.get("name")
    amount = pair["amount"]
    currency = pair["currency"]
    route = pair["human_route"]
    oid = pair["offer_id"]
    lines = [
        "%s — Commons channel package (not a live listing)" % name,
        "",
        "Outcome: %s." % name,
        "Price: %s %s. Source terms win; this package does not rewrite them." % (currency, amount),
        "Offer id: %s." % oid,
        "Channel: %s (%s)." % (channel["name"], channel["family"]),
        "",
        "What the buyer receives is the named outcome on the canonical Commons page, not a marketplace-only deliverable.",
        "Conversion: %s/%s" % (PAGES, route),
        "Public intake: post a non-confidential signal to the OFFER board from distribution.html or commerce.html.",
        "Contact: %s" % CONTACT,
        "Source: %s (blob %s)." % (pair["source_path"], pair["source_blob_sha"]),
        "",
        "Honesty: not a live listing. Channel=%s. submit_allowed=false. verified leads=0. verified customers=0. collected cash=0.00." % channel["name"],
    ]
    if pair.get("blocked_reason"):
        lines.extend(["", "Blocker: %s" % pair["blocked_reason"]])
    lines.extend([
        "",
        "Do not paste this into a marketplace as if Commons already listed it.",
        "Route any real buyer interest back to %s/%s — do not open a second CRM." % (PAGES, route),
    ])
    text = "\n".join(lines)
    lowered = text.lower()
    for needle in FORBIDDEN_COPY:
        if needle in lowered:
            raise DistributionError("package copy invented a live/customer claim: %s" % needle)
    return text


def build_package(listing: dict[str, Any], channel: dict[str, Any], pair: dict[str, Any] | None = None) -> dict[str, Any]:
    pair = pair or fit_pair(listing, channel)
    if pair["fit"] != "FIT":
        raise DistributionError("refusing package for UNFIT pair %s" % pair["id"])
    package = {
        "id": pair["id"],
        "kind": "CHANNEL_READY_PACKAGE",
        "offer_id": pair["offer_id"],
        "offer_name": pair["offer_name"],
        "offer_class": pair["offer_class"],
        "channel_id": pair["channel_id"],
        "channel_name": pair["channel_name"],
        "channel_family": pair["channel_family"],
        "package_state": pair["package_state"],
        "listing_state": pair["listing_state"],
        "submit_allowed": False,
        "submitted": False,
        "listed": False,
        "title": pair["offer_name"],
        "price": {
            "currency": pair["currency"],
            "amount": pair["amount"],
            "basis": listing_basis(listing),
        },
        "scope": _scope_lines(listing),
        "exclusions": _exclusions(listing, channel),
        "evidence": [
            {
                "kind": "canonical_source",
                "path": pair["source_path"],
                "blob_sha": pair["source_blob_sha"],
            },
            {
                "kind": "conversion_surface",
                "path": pair["human_route"],
                "url": "%s/%s" % (PAGES, pair["human_route"]),
            },
            {
                "kind": "distribution_door",
                "path": "distribution.html",
                "url": "%s/distribution.html" % PAGES,
            },
        ],
        "conversion": {
            "human": pair["human_route"],
            "intake": "OFFER",
            "contact": CONTACT,
            "pages": "%s/%s" % (PAGES, pair["human_route"]),
        },
        "honesty": {
            "listed": False,
            "submitted": False,
            "live_url": None,
            "customers": 0,
            "leads": 0,
            "revenue_usd": "0.00",
            "blocked_reason": pair.get("blocked_reason"),
        },
        "channel_copy": channel_copy(listing, channel, pair),
        "blocked_reason": pair.get("blocked_reason"),
    }
    return package


def inbound_template(listing: dict[str, Any], channel: dict[str, Any], pair: dict[str, Any] | None = None) -> dict[str, Any]:
    pair = pair or fit_pair(listing, channel)
    route = pair["human_route"]
    body = "\n".join([
        "PLAIN: Public, non-confidential buyer interest from a distribution channel.",
        "CHANNEL: %s" % channel["id"],
        "OFFER_ID: %s" % pair["offer_id"],
        "PUBLIC_OBJECTIVE:",
        "PUBLIC_ARTIFACT:",
        "PUBLIC_CONTACT_URL:",
        "START_WINDOW:",
        "CONVERSION: %s/%s" % (PAGES, route),
        "NOTE: This is intent only. It is not a lead, customer, or payment.",
    ])
    return {
        "kind": "INBOUND_ROUTE",
        "offer_id": pair["offer_id"],
        "channel_id": channel["id"],
        "fit": pair["fit"],
        "canonical_conversion": route,
        "canonical_conversion_url": "%s/%s" % (PAGES, route),
        "intake_board": "OFFER",
        "intake_page": "distribution.html",
        "contact": CONTACT,
        "crm": "Do not open a second CRM. Map onto revenue/production_survival/crm.md only after a real first-party signal.",
        "to": "OFFER",
        "subject": "COMMONS DISTRIBUTION INBOUND",
        "body": body,
        "not_a_lead": True,
        "verified_lead": False,
    }


def iter_pairs(catalog: dict[str, Any], channels: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for listing in catalog["listings"]:
        for channel in channels["channels"]:
            out.append(fit_pair(listing, channel))
    return out


def build_matrix(catalog: dict[str, Any], channels: dict[str, Any]) -> dict[str, Any]:
    pairs = iter_pairs(catalog, channels)
    return {
        "schema_version": "distribution/v1",
        "kind": "DISTRIBUTION_MATRIX",
        "as_of": channels["snapshot_as_of"],
        "catalog": "revenue/outcome_commerce/catalog.json",
        "channels": "revenue/distribution/channels.json",
        "offer_count": len(catalog["listings"]),
        "channel_count": len(channels["channels"]),
        "pair_count": len(pairs),
        "pairs": pairs,
    }


def build_packages(catalog: dict[str, Any], channels: dict[str, Any]) -> dict[str, Any]:
    packages = []
    channel_by_id = {c["id"]: c for c in channels["channels"]}
    listing_by_id = {l["id"]: l for l in catalog["listings"]}
    for pair in iter_pairs(catalog, channels):
        if pair["fit"] != "FIT":
            continue
        packages.append(build_package(listing_by_id[pair["offer_id"]], channel_by_id[pair["channel_id"]], pair))
    return {
        "schema_version": "distribution/v1",
        "kind": "CHANNEL_READY_PACKAGES",
        "as_of": channels["snapshot_as_of"],
        "count": len(packages),
        "packages": packages,
    }


def build_status(catalog: dict[str, Any], channels: dict[str, Any]) -> dict[str, Any]:
    pairs = iter_pairs(catalog, channels)
    fit_pairs = [p for p in pairs if p["fit"] == "FIT"]
    packages_ready = [p for p in fit_pairs if p["package_state"] == "PACKAGE_READY"]
    blocked = [p for p in fit_pairs if str(p["listing_state"]).startswith("BLOCKED_")]
    unfit = [p for p in pairs if p["fit"] == "UNFIT"]
    live_market = [
        p for p in pairs
        if p["listing_state"] == "LIVE" and p["channel_family"] in MARKETPLACE_FAMILIES
    ]
    surface_live = [p for p in pairs if p["listing_state"] == "SURFACE_LIVE"]
    if live_market:
        raise DistributionError("refusing to export invented LIVE marketplace listings")
    inbound = channels["inbound_truth"]
    channel_rows = []
    for channel in channels["channels"]:
        channel_pairs = [p for p in pairs if p["channel_id"] == channel["id"]]
        listing_states = sorted({p["listing_state"] for p in channel_pairs})
        channel_rows.append({
            "id": channel["id"],
            "family": channel["family"],
            "name": channel["name"],
            "account_status": channel["account_status"],
            "submit_allowed": False,
            "honest_live": channel["honest_live"],
            "listing_states": listing_states,
            "fit_count": sum(1 for p in channel_pairs if p["fit"] == "FIT"),
            "unfit_count": sum(1 for p in channel_pairs if p["fit"] == "UNFIT"),
        })
    return {
        "schema_version": "distribution/v1",
        "kind": "DISTRIBUTION_STATUS",
        "as_of": channels["snapshot_as_of"],
        "canonical_page": "distribution.html",
        "honesty": channels["honesty"],
        "counts": {
            "offers": len(catalog["listings"]),
            "channels": len(channels["channels"]),
            "pairs": len(pairs),
            "fit_pairs": len(fit_pairs),
            "packages_ready": len(packages_ready),
            "blocked_pairs": len(blocked),
            "unfit_pairs": len(unfit),
            "live_marketplace_listings": 0,
            "live_commons_surfaces": len(surface_live),
            "verified_leads": inbound["verified_leads"],
            "verified_customers": inbound["verified_customers"],
            "verified_positive_replies": inbound["verified_positive_replies"],
            "collected_cash_usd": inbound["collected_cash_usd"],
        },
        "channels": channel_rows,
        "conversion_rule": channels["conversion_rule"],
        "submit_rule": channels["submit_rule"],
        "does_not_replace": channels["does_not_replace"],
    }


def submit_listing(*_args: Any, **_kwargs: Any) -> None:
    raise DistributionError(
        "SUBMIT_FORBIDDEN: the distribution layer never submits through an unauthorised account and never invents provider readiness"
    )


def export_bundle(catalog: dict[str, Any], channels: dict[str, Any]) -> dict[str, Any]:
    return {
        "matrix": build_matrix(catalog, channels),
        "packages": build_packages(catalog, channels),
        "status": build_status(catalog, channels),
    }


def write_export(root: Path | None = None) -> dict[str, Path]:
    root = root or ROOT
    catalog = load_catalog(root / "revenue" / "outcome_commerce" / "catalog.json")
    channels = load_channels(root / "revenue" / "distribution" / "channels.json")
    bundle = export_bundle(catalog, channels)
    paths = {
        "matrix": root / "revenue" / "distribution" / "matrix.json",
        "packages": root / "revenue" / "distribution" / "packages.json",
        "status": root / "revenue" / "distribution" / "status.json",
    }
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_canonical(bundle[key]).encode("utf-8"))
    return paths


def _print(value: Any) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _find(listings: list[dict[str, Any]], offer_id: str) -> dict[str, Any]:
    for listing in listings:
        if listing.get("id") == offer_id:
            return listing
    raise DistributionError("unknown offer id: %s" % offer_id)


def _find_channel(channels: list[dict[str, Any]], channel_id: str) -> dict[str, Any]:
    for channel in channels:
        if channel.get("id") == channel_id:
            return channel
    raise DistributionError("unknown channel id: %s" % channel_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Commons distribution layer")
    parser.add_argument("--root", default=str(ROOT))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sub.add_parser("matrix")
    sub.add_parser("status")
    sub.add_parser("export")
    pkg = sub.add_parser("package")
    pkg.add_argument("--offer", required=True)
    pkg.add_argument("--channel", required=True)
    inn = sub.add_parser("inbound")
    inn.add_argument("--offer", required=True)
    inn.add_argument("--channel", required=True)
    sub.add_parser("submit")
    args = parser.parse_args(argv)
    root = Path(args.root)
    catalog = load_catalog(root / "revenue" / "outcome_commerce" / "catalog.json")
    channels = load_channels(root / "revenue" / "distribution" / "channels.json")
    if args.cmd == "validate":
        bundle = export_bundle(catalog, channels)
        _print({
            "ok": True,
            "offers": bundle["status"]["counts"]["offers"],
            "channels": bundle["status"]["counts"]["channels"],
            "packages_ready": bundle["status"]["counts"]["packages_ready"],
            "live_marketplace_listings": 0,
            "verified_leads": 0,
            "collected_cash_usd": "0.00",
        })
        return 0
    if args.cmd == "matrix":
        _print(build_matrix(catalog, channels))
        return 0
    if args.cmd == "status":
        _print(build_status(catalog, channels))
        return 0
    if args.cmd == "export":
        paths = write_export(root)
        _print({"ok": True, "wrote": {k: str(v.relative_to(root)) for k, v in paths.items()}})
        return 0
    if args.cmd == "package":
        listing = _find(catalog["listings"], args.offer)
        channel = _find_channel(channels["channels"], args.channel)
        _print(build_package(listing, channel))
        return 0
    if args.cmd == "inbound":
        listing = _find(catalog["listings"], args.offer)
        channel = _find_channel(channels["channels"], args.channel)
        _print(inbound_template(listing, channel))
        return 0
    if args.cmd == "submit":
        submit_listing()
        return 2
    raise DistributionError("unknown command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DistributionError as exc:
        print("distribution: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
