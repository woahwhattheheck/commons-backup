#!/usr/bin/env python3
"""Project public checkout rails from measured provider truth.

A Stripe URL becomes a public checkout anchor only when livemode,
charges_enabled, payouts_enabled, and that exact link active=true are
all proven. Duplicate or unverified URLs stay inert. This module never
calls Stripe, never stores bank data, and never claims current cash. Offline
recorded amounts are separate from settlement not verified in this run;
missing receiving-rail evidence never establishes zero.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any


ROOT_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join("revenue", "checkout_capability", "snapshot.json")
CATALOG = os.path.join("revenue", "outcome_commerce", "catalog.json")
STRIPE_URL_RE = re.compile(r"^https://(?:buy|donate)\.stripe\.com/[A-Za-z0-9_-]+$")
STRIPE_HTML_URL_RE = re.compile(r"https://(?:buy|donate)\.stripe\.com/")
BUY_HOST_PATH_RE = re.compile(r"https?://buy\.stripe\.com/([A-Za-z0-9_-]+)", re.I)
DONATE_HOST_PATH_RE = re.compile(r"https?://donate\.stripe\.com/([A-Za-z0-9_-]+)", re.I)
PAY_CONVERT_SHELF_LIVE_BUYS = frozenset(
    {
        "https://buy.stripe.com/14AfZgckZ0IN0Y99h043S0e",
        "https://buy.stripe.com/28E9AS70F6378qB2SC43S0w",
        "https://buy.stripe.com/14AfZg1Gl3UZ7mxfFo43S0x",
        "https://buy.stripe.com/7sYdR8ckZgHLbCN50K43S0y",
    }
)
COMMERCE_CONVERT_SHELF_LIVE_BUYS = frozenset(
    {
        "https://buy.stripe.com/3cIdR8gBf6379uF1Oy43S0b",
        "https://buy.stripe.com/9B600i98N77b9uFeBk43S0c",
        "https://buy.stripe.com/9B66oGacR2QVdKVeBk43S0d",
        "https://buy.stripe.com/14AfZgckZ0IN0Y99h043S0e",
        "https://buy.stripe.com/7sYdR8ckZgHLbCN50K43S0y",
        "https://buy.stripe.com/14AfZg1Gl3UZ7mxfFo43S0x",
        "https://buy.stripe.com/28E9AS70F6378qB2SC43S0w",
        "https://buy.stripe.com/8x27sK2Kp3UZ9uF2SC43S07",
    }
)
WHITEBOX_HOUR_CHECKOUT = "https://buy.stripe.com/8x27sK2Kp3UZ9uF2SC43S07"
CONVERT_SHELF_LIVE_BUYS = {
    "pay.html": PAY_CONVERT_SHELF_LIVE_BUYS,
    "commerce.html": COMMERCE_CONVERT_SHELF_LIVE_BUYS,
    "owner-now-revenue.html": frozenset({WHITEBOX_HOUR_CHECKOUT}),
}
TIPS_CONVERT_SHELF_LIVE_CHECKOUTS = frozenset(
    {
        "https://donate.stripe.com/fZucN40Ch9fj7mxgJs43S08",
        "https://buy.stripe.com/3cIeVc5WB1MRgX7al443S03",
        "https://buy.stripe.com/3cIbJ0ckZgHL36h8cW43S04",
        "https://buy.stripe.com/bJe28qacR4Z3gX7bp843S05",
        "https://buy.stripe.com/3cIfZgacRezDfT39h043S06",
        WHITEBOX_HOUR_CHECKOUT,
    }
)
PAY_CONVERT_SHELF_LIVE_CHECKOUTS = (
    PAY_CONVERT_SHELF_LIVE_BUYS | TIPS_CONVERT_SHELF_LIVE_CHECKOUTS | {WHITEBOX_HOUR_CHECKOUT}
)
COMMERCE_CONVERT_SHELF_LIVE_CHECKOUTS = (
    COMMERCE_CONVERT_SHELF_LIVE_BUYS | TIPS_CONVERT_SHELF_LIVE_CHECKOUTS
)
FORBIDDEN = (
    r"\brouting[_\s-]?number\b.+\d{9}\b",
    r"\baccount[_\s-]?number\b.+\d{8,17}\b",
    r"\bIBAN\b\s*[A-Z]{2}\d{2}[A-Z0-9]{10,}",
    r"\b(?:4\d{15}|5[1-5]\d{14})\b",
    r"\bcvv\b\s*\d{3,4}\b",
    r"\bssn\b\s*\d{3}-\d{2}-\d{4}\b",
)
class CapabilityError(ValueError):
    pass


def _read(root: str, rel: str) -> str:
    path = os.path.join(root, rel)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _load(root: str, rel: str) -> Any:
    return json.loads(_read(root, rel))


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not (
        value.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", value)
    ):
        raise CapabilityError("%s must be an offset-aware ISO-8601 timestamp" % field)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    normalized = re.sub(r"(\.\d{6})\d+(?=[+-])", r"\1", normalized)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CapabilityError("%s must be a real timestamp" % field) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapabilityError("%s must include an offset" % field)
    return parsed.astimezone(timezone.utc)


def forbidden_hits(text: str) -> list[str]:
    hits = []
    for pattern in FORBIDDEN:
        if re.search(pattern, text or "", flags=re.I):
            hits.append(pattern)
    return hits


def account_ready(provider: dict[str, Any]) -> bool:
    return (
        provider.get("name") == "stripe"
        and provider.get("livemode") is True
        and provider.get("charges_enabled") is True
        and provider.get("payouts_enabled") is True
        and list(provider.get("currently_due") or []) == []
        and provider.get("card_payments") == "active"
        and provider.get("transfers") == "active"
    )


def catalog_checkouts(catalog: dict[str, Any]) -> dict[str, str]:
    """Return active Stripe checkouts, failing closed on duplicate SKU ids."""
    counts: dict[str, int] = {}
    for listing in catalog.get("listings") or []:
        if isinstance(listing, dict) and isinstance(listing.get("id"), str):
            sku = listing["id"]
            counts[sku] = counts.get(sku, 0) + 1
    out: dict[str, str] = {}
    for listing in catalog.get("listings") or []:
        if not isinstance(listing, dict) or not isinstance(listing.get("id"), str):
            continue
        sku = listing["id"]
        if counts.get(sku) != 1:
            continue
        checkout = listing.get("checkout") if isinstance(listing.get("checkout"), dict) else {}
        url = checkout.get("url")
        if (
            checkout.get("status") == "ACTIVE_CHARGEABLE"
            and checkout.get("provider") == "stripe"
            and checkout.get("link_active") is True
            and checkout.get("account_charges_enabled") is True
            and checkout.get("account_payouts_enabled") is True
            and isinstance(url, str)
            and STRIPE_URL_RE.fullmatch(url)
        ):
            out[sku] = url
    return out


def catalog_checkout_evidence(catalog: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return evidence from the same unique listing admitted as active."""
    active = catalog_checkouts(catalog)
    out: dict[str, dict[str, str]] = {}
    for listing in catalog.get("listings") or []:
        if not isinstance(listing, dict) or not isinstance(listing.get("id"), str):
            continue
        sku = listing["id"]
        checkout = listing.get("checkout") if isinstance(listing.get("checkout"), dict) else {}
        url = checkout.get("url")
        if active.get(sku) != url:
            continue
        evidence = checkout.get("capability_evidence") if isinstance(checkout.get("capability_evidence"), dict) else {}
        reference = evidence.get("reference")
        observed_at = evidence.get("observed_at")
        if not isinstance(reference, str) or not reference.strip():
            continue
        if not isinstance(observed_at, str) or not observed_at:
            continue
        try:
            _timestamp(observed_at, "%s.checkout.capability_evidence.observed_at" % sku)
        except CapabilityError:
            continue
        out[sku] = {
            "url": str(url),
            "reference": reference,
            "observed_at": observed_at,
        }
    return out


def canonical_checkout_authority() -> dict[str, dict[str, str]]:
    """Caller-independent provider root from repository-canonical evidence."""
    try:
        snapshot = _load(ROOT_DEFAULT, SNAPSHOT)
        catalog = _load(ROOT_DEFAULT, CATALOG)
        _timestamp(snapshot.get("observed_at"), "canonical.observed_at")
    except (OSError, ValueError, json.JSONDecodeError, CapabilityError):
        return {}
    provider = snapshot.get("provider") if isinstance(snapshot.get("provider"), dict) else {}
    if not account_ready(provider):
        return {}
    checkouts = catalog_checkouts(catalog)
    checkout_evidence = catalog_checkout_evidence(catalog)
    snapshot_evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), dict) else {}
    default_evidence = {
        "reference": snapshot_evidence.get("reference"),
        "observed_at": snapshot.get("observed_at"),
    }
    out: dict[str, dict[str, str]] = {}
    duplicate: set[str] = set()
    for rail in snapshot.get("canonical_rails") or []:
        if not isinstance(rail, dict) or not isinstance(rail.get("sku"), str):
            continue
        sku = rail["sku"]
        if sku in out:
            duplicate.add(sku)
            continue
        url = str(rail.get("url") or "")
        evidence = rail.get("evidence") if isinstance(rail.get("evidence"), dict) else default_evidence
        reference = evidence.get("reference")
        observed_at = evidence.get("observed_at")
        catalog_evidence = checkout_evidence.get(sku) or {}
        if not (
            rail.get("link_active") is True
            and rail.get("livemode") is True
            and bool(STRIPE_URL_RE.fullmatch(url))
            and checkouts.get(sku) == url
            and isinstance(reference, str)
            and bool(reference.strip())
            and isinstance(observed_at, str)
            and catalog_evidence.get("url") == url
            and catalog_evidence.get("reference") == reference
            and catalog_evidence.get("observed_at") == observed_at
        ):
            continue
        try:
            _timestamp(observed_at, "%s.canonical.evidence.observed_at" % sku)
        except CapabilityError:
            continue
        out[sku] = {
            "url": url,
            "reference": reference,
            "observed_at": observed_at,
            "exposure": str(rail.get("exposure") or ""),
        }
    for sku in duplicate:
        out.pop(sku, None)
    return out


def project_rail(
    provider: dict[str, Any],
    rail: dict[str, Any],
    inert: set[str],
    checkouts: dict[str, str],
    default_evidence: dict[str, Any],
    checkout_evidence: dict[str, dict[str, str]],
    authority: dict[str, dict[str, str]],
) -> dict[str, Any]:
    url = str(rail.get("url") or "")
    sku = str(rail.get("sku") or "")
    evidence = rail.get("evidence") if isinstance(rail.get("evidence"), dict) else default_evidence
    evidence_ready = bool(evidence.get("reference") and evidence.get("observed_at"))
    if evidence_ready:
        try:
            _timestamp(evidence["observed_at"], "%s.evidence.observed_at" % sku)
        except CapabilityError:
            evidence_ready = False
    catalog_evidence = checkout_evidence.get(sku) or {}
    evidence_matches = (
        catalog_evidence.get("url") == url
        and catalog_evidence.get("reference") == evidence.get("reference")
        and catalog_evidence.get("observed_at") == evidence.get("observed_at")
    )
    exposure = str(rail.get("exposure") or "")
    canonical = authority.get(sku) or {}
    authority_matches = (
        canonical.get("url") == url
        and canonical.get("reference") == evidence.get("reference")
        and canonical.get("observed_at") == evidence.get("observed_at")
        and canonical.get("exposure") == exposure
    )
    ready = (
        account_ready(provider)
        and rail.get("link_active") is True
        and rail.get("livemode") is True
        and bool(STRIPE_URL_RE.fullmatch(url))
        and url not in inert
        and checkouts.get(sku) == url
        and evidence_ready
        and evidence_matches
        and authority_matches
    )
    if ready and exposure == "CHECKOUT_FIRST":
        public = "EXPOSE_CHECKOUT"
    elif ready and exposure == "INTAKE_FIRST":
        public = "EXPOSE_INTAKE_THEN_CHECKOUT"
    else:
        public = "INERT"
    return {
        "sku": sku,
        "url": url if ready else "",
        "stored_url": url,
        "link_active": bool(rail.get("link_active") is True),
        "public": public,
        "chargeable": ready,
        "payout_capable": bool(provider.get("payouts_enabled") is True),
        "evidence_reference": str(evidence.get("reference") or ""),
        "evidence_observed_at": str(evidence.get("observed_at") or ""),
    }


def project(snapshot: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    if snapshot.get("kind") != "CHECKOUT_CAPABILITY_SNAPSHOT":
        raise CapabilityError("snapshot kind is invalid")
    if snapshot.get("schema_version") != "commons-checkout-capability/v1":
        raise CapabilityError("snapshot schema_version is invalid")
    _timestamp(snapshot.get("observed_at"), "observed_at")
    provider = snapshot.get("provider") if isinstance(snapshot.get("provider"), dict) else {}
    money = snapshot.get("money") if isinstance(snapshot.get("money"), dict) else {}
    rails = snapshot.get("canonical_rails") if isinstance(snapshot.get("canonical_rails"), list) else []
    inert = set(snapshot.get("inert_duplicate_urls") or [])
    owner = snapshot.get("owner_action") if isinstance(snapshot.get("owner_action"), dict) else {}
    fallback = snapshot.get("fallback") if isinstance(snapshot.get("fallback"), dict) else {}
    snapshot_evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), dict) else {}
    default_evidence = {
        "reference": snapshot_evidence.get("reference"),
        "observed_at": snapshot.get("observed_at"),
    }
    checkouts = catalog_checkouts(catalog)
    checkout_evidence = catalog_checkout_evidence(catalog)
    authority = canonical_checkout_authority()
    projected = [
        project_rail(
            provider,
            rail,
            inert,
            checkouts,
            default_evidence,
            checkout_evidence,
            authority,
        )
        for rail in rails
        if isinstance(rail, dict)
    ]
    public = [row for row in projected if row["public"] != "INERT"]
    checkout_first = [row for row in public if row["public"] == "EXPOSE_CHECKOUT"]
    cash = money.get("collected_cash_usd")
    return {
        "account_ready": account_ready(provider),
        "charges_enabled": bool(provider.get("charges_enabled") is True),
        "payouts_enabled": bool(provider.get("payouts_enabled") is True),
        "collected_cash_usd": None,
        "settlement_status": "NOT_VERIFIED_IN_THIS_RUN",
        "settlement_scope": "offline_snapshot_only",
        "recorded_cash_usd": cash,
        "recorded_cash_observed_at": snapshot.get("observed_at"),
        "public_rails": public,
        "checkout_first_skus": [row["sku"] for row in checkout_first],
        "inert_urls": sorted(inert),
        "owner_action_id": str(owner.get("id") or ""),
        "fallback_url": str(fallback.get("url") or ""),
        "fallback_kind": str(fallback.get("kind") or ""),
        "authorization": str(money.get("authorization") or ""),
        "bank_available": str(money.get("bank_available") or ""),
    }


def catalog_checkout_errors(catalog: dict[str, Any], snapshot: dict[str, Any], projected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {row["sku"]: row for row in projected["public_rails"]}
    by_id = {}
    for listing in catalog.get("listings") or []:
        if isinstance(listing, dict) and listing.get("id"):
            by_id[listing["id"]] = listing
    active = catalog_checkouts(catalog)
    for sku in active:
        listing = by_id[sku]
        checkout = listing.get("checkout") if isinstance(listing.get("checkout"), dict) else {}
        funnel = (catalog.get("funnels") or {}).get(sku) if isinstance(catalog.get("funnels"), dict) else {}
        row = expected.get(sku)
        if not row:
            errors.append("projection missing %s" % sku)
            continue
        if checkout.get("status") != "ACTIVE_CHARGEABLE":
            errors.append("%s checkout status must be ACTIVE_CHARGEABLE" % sku)
        if checkout.get("provider") != "stripe":
            errors.append("%s provider must be stripe" % sku)
        if checkout.get("url") != row["stored_url"]:
            errors.append("%s checkout url must match the canonical recorded URL" % sku)
        if checkout.get("link_active") is not True:
            errors.append("%s link_active must be true" % sku)
        if checkout.get("account_charges_enabled") is not True:
            errors.append("%s account_charges_enabled must be true" % sku)
        if checkout.get("account_payouts_enabled") is not True:
            errors.append("%s account_payouts_enabled must be true" % sku)
        cap = checkout.get("capability_evidence") if isinstance(checkout.get("capability_evidence"), dict) else {}
        if cap.get("reference") != row.get("evidence_reference"):
            errors.append("%s capability_evidence.reference must match its rail evidence" % sku)
        if cap.get("observed_at") != row.get("evidence_observed_at"):
            errors.append("%s capability_evidence.observed_at must match its rail evidence" % sku)
        if not isinstance(funnel, dict):
            errors.append("%s funnel missing" % sku)
            continue
        if funnel.get("conversion", {}).get("mode") != "ACTIVE_STRIPE_LINK":
            errors.append("%s conversion.mode must be ACTIVE_STRIPE_LINK" % sku)
        if funnel.get("conversion", {}).get("status") != "ACTIVE_CHARGEABLE":
            errors.append("%s conversion.status must be ACTIVE_CHARGEABLE" % sku)
        if row.get("public") == "EXPOSE_CHECKOUT":
            if funnel.get("readiness") != "READY_FOR_CHECKOUT":
                errors.append("%s must be READY_FOR_CHECKOUT" % sku)
            if funnel.get("measurement", {}).get("dom_action") != "checkout-open":
                errors.append("%s measurement.dom_action must be checkout-open" % sku)
        else:
            if funnel.get("readiness") != "READY_FOR_QUALIFICATION":
                errors.append("%s must be READY_FOR_QUALIFICATION" % sku)
            if funnel.get("measurement", {}).get("dom_action") != "qualification-open":
                errors.append("%s measurement.dom_action must be qualification-open" % sku)
    return errors


def live_buy_urls(html: str) -> set[str]:
    """Canonical https://buy.stripe.com/<path> identities found in HTML."""
    return {
        "https://buy.stripe.com/%s" % path
        for path in BUY_HOST_PATH_RE.findall(html)
    }


def live_stripe_checkout_urls(html: str) -> set[str]:
    """Canonical https://(buy|donate).stripe.com/<path> identities found in HTML."""
    return live_buy_urls(html) | {
        "https://donate.stripe.com/%s" % path
        for path in DONATE_HOST_PATH_RE.findall(html)
    }


def html_stripe_url_errors(name: str, text: str) -> list[str]:
    """tips/pay/commerce convert shelves reuse existing Stripe URLs; Type product buys stay exact."""
    if name == "tips.html":
        found = live_stripe_checkout_urls(text)
        if found != TIPS_CONVERT_SHELF_LIVE_CHECKOUTS | {WHITEBOX_HOUR_CHECKOUT}:
            return [
                "%s convert shelf must reuse exactly the existing tip-shelf Stripe URLs"
                % name
            ]
        return []
    if name == "pay.html":
        found = live_stripe_checkout_urls(text)
        if found != PAY_CONVERT_SHELF_LIVE_CHECKOUTS:
            return [
                "%s convert shelf must reuse exactly the existing pay Stripe URLs"
                % name
            ]
        return []
    if name == "commerce.html":
        found = live_stripe_checkout_urls(text)
        if found != COMMERCE_CONVERT_SHELF_LIVE_CHECKOUTS:
            return [
                "%s convert shelf must reuse exactly the existing commerce Stripe URLs"
                % name
            ]
        return []
    allowed = CONVERT_SHELF_LIVE_BUYS.get(name)
    if allowed is not None:
        found = live_buy_urls(text)
        if found != allowed:
            return [
                "%s convert shelf must reuse exactly the existing live buy.stripe.com URLs"
                % name
            ]
        if "donate.stripe.com" in text.lower():
            return ["%s must not invent donate.stripe.com URLs" % name]
        return []
    if STRIPE_HTML_URL_RE.search(text):
        return ["%s must keep Stripe URLs out of static HTML" % name]
    return []


def html_surface_errors(root: str) -> list[str]:
    errors: list[str] = []
    for name in ("pay.html", "tips.html", "commerce.html", "owner-now-revenue.html"):
        text = _read(root, name)
        errors.extend(html_stripe_url_errors(name, text))
        if "js-checkout-slot" not in text:
            errors.append("%s must include js-checkout-slot for catalog-driven rails" % name)
        if "mailto:tokenjunkielabs@gmail.com" not in text:
            errors.append("%s must keep the provider-neutral contact fallback" % name)
    return errors


def measure_root(root: str) -> dict[str, Any]:
    snapshot = _load(root, SNAPSHOT)
    catalog = _load(root, CATALOG)
    blob = "\n".join(
        [
            _read(root, SNAPSHOT),
            _read(root, os.path.join("ground", "CHECKOUT_CAPABILITY.md")),
            _read(root, os.path.join("host", "checkout_capability.py")),
        ]
    )
    projected = project(snapshot, catalog)
    errors = []
    hits = forbidden_hits(blob)
    if hits:
        errors.append("forbidden financial field pattern")
    if projected["owner_action_id"] != "NONE":
        errors.append("blocking owner action must stay NONE while currently_due is empty")
    if projected["fallback_kind"] != "PROVIDER_NEUTRAL_INTAKE":
        errors.append("fallback must be provider-neutral intake")
    if projected["fallback_url"] != "mailto:tokenjunkielabs@gmail.com":
        errors.append("fallback contact must stay the public email")
    expected_checkout_first = {
        sku
        for sku in catalog_checkouts(catalog)
        if (catalog.get("funnels") or {}).get(sku, {}).get("readiness") == "READY_FOR_CHECKOUT"
    }
    if set(projected["checkout_first_skus"]) != expected_checkout_first:
        errors.append("checkout-first SKUs must match READY_FOR_CHECKOUT catalog entries")
    errors.extend(catalog_checkout_errors(catalog, snapshot, projected))
    errors.extend(html_surface_errors(root))
    for listing in catalog.get("listings") or []:
        sku = listing.get("id")
        if sku not in catalog_checkouts(catalog):
            continue
        source = listing.get("source_artifact") if isinstance(listing.get("source_artifact"), dict) else {}
        path = str(source.get("path") or "")
        if not (path.startswith("land/") and path.endswith(".md")):
            continue
        path = path.replace("/", os.sep)
        text = _read(root, path)
        if "status: ACTIVE_CHARGEABLE" not in text:
            errors.append("%s must record ACTIVE_CHARGEABLE" % path)
        if "account_payouts_enabled: true" not in text:
            errors.append("%s must record payouts_enabled" % path)
        if "link_active: true" not in text:
            errors.append("%s must record link_active true" % path)
        if "Recorded URL (not a checkout):" in text:
            errors.append("%s must not still call a verified URL a non-checkout" % path)
    state = "INTEGRATED" if not errors else "NOT_LANDED"
    return {
        "state": state,
        "errors": errors,
        "projected": projected,
        "snapshot": SNAPSHOT,
        "z": "" if not errors else "FINDER-FAILED",
    }


def _self_test() -> bool:
    dead = {
        "schema_version": "commons-checkout-capability/v1",
        "kind": "CHECKOUT_CAPABILITY_SNAPSHOT",
        "observed_at": "2026-08-28T16:10:00Z",
        "provider": {
            "name": "stripe",
            "livemode": True,
            "charges_enabled": False,
            "payouts_enabled": False,
            "currently_due": ["external_account"],
            "card_payments": "inactive",
            "transfers": "inactive",
        },
        "canonical_rails": [
            {
                "sku": "sku-tip-20260826",
                "url": "https://donate.stripe.com/fZucN40Ch9fj7mxgJs43S08",
                "link_active": True,
                "livemode": True,
                "exposure": "CHECKOUT_FIRST",
            }
        ],
        "inert_duplicate_urls": [],
    }
    catalog = {
        "listings": [
            {
                "id": "sku-tip-20260826",
                "checkout": {
                    "status": "ACTIVE_CHARGEABLE",
                    "provider": "stripe",
                    "url": "https://donate.stripe.com/fZucN40Ch9fj7mxgJs43S08",
                    "link_active": True,
                    "account_charges_enabled": True,
                    "account_payouts_enabled": True,
                },
            }
        ]
    }
    projected = project(dead, catalog)
    if projected["account_ready"] or projected["public_rails"]:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project public checkout rails")
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    json.dump(row, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
