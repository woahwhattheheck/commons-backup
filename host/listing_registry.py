#!/usr/bin/env python3
"""Canonical Commons listing registry.

One listing per (offer_or_product, surface). Generates GitHub Marketplace-style
copy, MCP directory rows, partner/vendor rows, procurement packs, service-catalog
packages, and community-channel drafts from real evidence.

Never submits. Never invents accounts, publication, buyers, or cash.
Offline recorded amounts are separate from current settlement, which this
generator does not verify against receiving rails. Unknown cash is not zero.
Never duplicate-posts the same offer onto the same surface.

Examples:

  python3 host/listing_registry.py validate
  python3 host/listing_registry.py registry
  python3 host/listing_registry.py asset --id ho-issue-to-pr__upwork-project-catalog
  python3 host/listing_registry.py export
  python3 host/listing_registry.py submit   # always SUBMIT_FORBIDDEN
  python3 host/listing_registry.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SURFACES = ROOT / "revenue" / "listing_registry" / "surfaces.json"
DEFAULT_CATALOG = ROOT / "revenue" / "outcome_commerce" / "catalog.json"
DEFAULT_CHECKOUT = ROOT / "revenue" / "checkout_capability" / "snapshot.json"
DEFAULT_MCP = ROOT / "ground" / "MCP_INVENTORY.json"
DEFAULT_REGISTRY = ROOT / "revenue" / "listing_registry" / "registry.json"
DEFAULT_ASSETS = ROOT / "revenue" / "listing_registry" / "assets.json"
DEFAULT_SCHEMA = ROOT / "revenue" / "listing_registry" / "schema.json"

ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,8})?$")
MONEY_QUANTUM = Decimal("0.01")
PAGES = "https://woahwhattheheck.github.io/commons"
CONTACT = "tokenjunkielabs@gmail.com"
SNAPSHOT_AS_OF = "2026-08-28T16:45:00Z"
SCHEMA_VERSION = "listing-registry/v1"
KIND = "COMMONS_LISTING_REGISTRY"
MCP_PRODUCT_ID = "commons-mcp"

FAMILIES = {
    "github_marketplace_style",
    "mcp_directory",
    "partner_vendor_directory",
    "procurement_portal",
    "service_catalog",
    "community_channel",
}
CHARGEABILITY = {
    "ACTIVE_CHARGEABLE",
    "NOT_CHARGEABLE_ON_THIS_SURFACE",
    "NOT_A_PRICED_SKU",
    "INTAKE_FIRST_ON_COMMONS",
}
SUBMISSION = {"NOT_SUBMITTED", "SUBMIT_FORBIDDEN"}
PUBLISHED = {
    "NOT_PUBLISHED",
    "SURFACE_PUBLISHED",
    "OWNER_PLATFORM_UNCLAIMED",
    "EXTERNAL_LIVE",
}
FIT = {"FIT", "UNFIT"}

FORBIDDEN_COPY = (
    "live on upwork",
    "live on fiverr",
    "live on contra",
    "listed on upwork",
    "listed on fiverr",
    "listed on contra",
    "listed on mcp.so",
    "listed on smithery",
    "listed on glama",
    "listed on pulsemcp",
    "live on github marketplace",
    "published on github marketplace",
    "we have buyers",
    "customers are waiting",
    "approved seller",
    "revenue this month",
    "already submitted",
    "listing is live",
    "accepted listing url",
)

VERIFIED_MCP_POSTING = (
    "append_post",
    "post_to_action_pad",
    "fire_action",
    "open_commons_composer",
)
VERIFIED_MCP_READS = (
    "read_post",
    "read_recent",
    "measure_roads",
    "verify_receipt",
    "verify_durability",
)

DOES_NOT_REPLACE = [
    "distribution.html",
    "host/distribution.py",
    "revenue/distribution/channels.json",
    "commerce.html",
    "revenue/outcome_commerce/catalog.json",
    "ground/CHECKOUT_CAPABILITY.md",
    "host/checkout_capability.py",
    "scope-to-delivery.html",
    "ground/CURRENT_WORK.json",
    "ground/PROFITABILITY_BUILD_MAP.md",
    "ground/RESOURCE_LEDGER.json",
    "features.html",
    "revenue/production_survival/marketplaces.md",
    "payment-capability.html",
    "host/payment_capability.py",
    "revenue/payment_capability/registry.json",
    "ground/PAYMENT_CAPABILITY.md",
]


class ListingRegistryError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), indent=2) + "\n"


def _load_json(path: str | os.PathLike[str]) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_float=lambda value: (_ for _ in ()).throw(
            ListingRegistryError("JSON money must be decimal strings, not floats: %s" % value)
        ))


def _decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str) or not DECIMAL_RE.fullmatch(value):
        raise ListingRegistryError("%s must be a decimal string" % field)
    try:
        out = Decimal(value)
    except InvalidOperation as exc:
        raise ListingRegistryError("%s is not a decimal" % field) from exc
    if out < 0:
        raise ListingRegistryError("%s must be non-negative" % field)
    return out


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ListingRegistryError("%s must be 8-80 characters: A-Z a-z 0-9 . _ -" % field)
    return value


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_distribution():
    spec = importlib.util.spec_from_file_location(
        "commons_distribution_for_listing_registry", HERE / "distribution.py"
    )
    if spec is None or spec.loader is None:
        raise ListingRegistryError("cannot load host/distribution.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_surfaces(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    data = _load_json(path or DEFAULT_SURFACES)
    if not isinstance(data, dict) or data.get("kind") != "COMMONS_LISTING_SURFACES":
        raise ListingRegistryError("surfaces.json kind must be COMMONS_LISTING_SURFACES")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ListingRegistryError("surfaces.json schema_version must be %s" % SCHEMA_VERSION)
    surfaces = data.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise ListingRegistryError("surfaces.json must list at least one surface")
    seen: set[str] = set()
    for surface in surfaces:
        if not isinstance(surface, dict):
            raise ListingRegistryError("surface must be an object")
        sid = _id(surface.get("id"), "surface.id")
        if sid in seen:
            raise ListingRegistryError("duplicate surface id: %s" % sid)
        seen.add(sid)
        if surface.get("family") not in FAMILIES:
            raise ListingRegistryError("%s has unknown family" % sid)
        if surface.get("submit_allowed") is not False:
            raise ListingRegistryError("%s submit_allowed must be false" % sid)
        scope = surface.get("product_scope")
        if not isinstance(scope, list) or not scope:
            raise ListingRegistryError("%s product_scope required" % sid)
    honesty = data.get("honesty") or {}
    for flag in (
        "no_fake_listings", "no_fake_accounts", "no_fake_submissions",
        "no_fake_publication", "no_fake_buyers", "no_fake_revenue",
        "no_duplicate_posting", "no_unauthorized_submit", "no_terms_accepted",
    ):
        if honesty.get(flag) is not True:
            raise ListingRegistryError("honesty.%s must be true" % flag)
    return data


def load_catalog(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    data = _load_json(path or DEFAULT_CATALOG)
    listings = data.get("listings")
    if not isinstance(listings, list) or not listings:
        raise ListingRegistryError("catalog must contain listings")
    return data


def load_checkout(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    data = _load_json(path or DEFAULT_CHECKOUT)
    if not isinstance(data, dict):
        raise ListingRegistryError("checkout snapshot must be an object")
    return data


def load_mcp(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    data = _load_json(path or DEFAULT_MCP)
    if not isinstance(data, dict) or data.get("kind") != "MCP_INVENTORY":
        raise ListingRegistryError("MCP inventory kind must be MCP_INVENTORY")
    return data


def listing_amount(listing: dict[str, Any]) -> Decimal:
    dist = load_distribution()
    return dist.listing_amount(listing)


def blob_sha(rel: str, root: Path | None = None) -> str:
    path = (root or ROOT) / rel
    if not path.is_file():
        raise ListingRegistryError("missing evidence file: %s" % rel)
    return hashlib.sha1(path.read_bytes()).hexdigest()


def mcp_product(mcp: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    surfaces = mcp.get("surfaces") or []
    tools: list[str] = []
    seen: set[str] = set()
    for surface in surfaces:
        for tool in surface.get("tools") or []:
            if isinstance(tool, str) and tool not in seen:
                seen.add(tool)
                tools.append(tool)
    posting = [t for t in VERIFIED_MCP_POSTING if t in seen]
    reads = [t for t in VERIFIED_MCP_READS if t in seen]
    return {
        "id": MCP_PRODUCT_ID,
        "name": "Commons MCP",
        "state": "PUBLIC_SURFACE",
        "sku": None,
        "pricing": {
            "currency": "USD",
            "mode": "not_a_priced_sku",
            "components": [],
        },
        "routes": {"human": "commons_mcp_app.html"},
        "source": {
            "path": "ground/MCP_INVENTORY.json",
            "blob_sha": blob_sha("ground/MCP_INVENTORY.json", root),
            "terms_authority": "inventory",
        },
        "verified_tools": {
            "posting": posting,
            "board_reads": reads,
            "inventoried": tools,
            "offer_discovery": "Not an MCP tool. Public catalog: commerce.html and revenue/outcome_commerce/catalog.json.",
        },
        "note": "Public MCP. Not a GitHub Marketplace paid app. Describe only inventoried tools. Do not invent offer-discovery as a tool name.",
    }


def products(catalog: dict[str, Any], mcp: dict[str, Any], root: Path | None = None) -> list[dict[str, Any]]:
    return list(catalog["listings"]) + [mcp_product(mcp, root)]


def payment_capability_public_stripe(root: Path | None = None) -> bool:
    """Public Stripe storefront is CHARGEABLE only when the provider-neutral registry says so."""
    path = (root or ROOT) / "revenue" / "payment_capability" / "registry.json"
    if not path.is_file():
        return False
    data = _load_json(path)
    for rail in data.get("rails") or []:
        if not isinstance(rail, dict):
            continue
        if rail.get("id") != "stripe-livemode-acct_1U6HI9ATH4EDE7XD":
            continue
        return (
            rail.get("capability_state") == "CHARGEABLE"
            and rail.get("charges_enabled") is True
            and rail.get("payouts_enabled") is True
            and rail.get("public_presentation") == "EXPOSE"
        )
    return False


def checkout_for(offer_id: str, listing: dict[str, Any], checkout: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    if offer_id == MCP_PRODUCT_ID:
        return {
            "state": "NOT_A_PRICED_SKU",
            "commons_rail": False,
            "url": None,
            "account_charges_enabled": None,
            "account_payouts_enabled": None,
            "link_active": None,
            "note": "Commons MCP is a public door, not a SKU.",
        }
    raw = listing.get("checkout") if isinstance(listing.get("checkout"), dict) else {}
    rails = checkout.get("canonical_rails") or []
    rail = next((r for r in rails if isinstance(r, dict) and r.get("sku") == offer_id), None)
    provider = checkout.get("provider") if isinstance(checkout.get("provider"), dict) else {}
    money = checkout.get("money") if isinstance(checkout.get("money"), dict) else {}
    url = raw.get("url") if isinstance(raw.get("url"), str) else None
    proven = (
        raw.get("status") == "ACTIVE_CHARGEABLE"
        and provider.get("livemode") is True
        and provider.get("charges_enabled") is True
        and provider.get("payouts_enabled") is True
        and (rail or {}).get("link_active") is True
        and (rail or {}).get("livemode") is True
        and isinstance(url, str)
        and url.startswith("https://")
        and (rail or {}).get("url") == url
        and payment_capability_public_stripe(root)
    )
    exposure = (rail or {}).get("exposure")
    if proven and exposure == "CHECKOUT_FIRST":
        state = "ACTIVE_CHARGEABLE"
        note = "Stripe livemode rail proven on Commons checkout only. A click is intent. Settlement is not verified in this run. Not chargeable on an external marketplace listing."
    elif proven and exposure == "INTAKE_FIRST":
        state = "INTAKE_FIRST_ON_COMMONS"
        note = "Stripe rail proven; public Commons surfaces keep terms in front. Not a marketplace charge."
    elif proven:
        state = "ACTIVE_CHARGEABLE"
        note = "Stripe livemode rail proven on Commons checkout only. Not chargeable on this external surface."
    else:
        state = "NOT_CHARGEABLE_ON_THIS_SURFACE"
        url = None
        note = "No proven chargeable rail for this offer on this surface."
    return {
        "state": state,
        "commons_rail": bool(proven),
        "url": url if proven else None,
        "account_charges_enabled": True if proven else None,
        "account_payouts_enabled": True if proven else None,
        "link_active": True if proven else None,
        "exposure": exposure,
        "note": note,
    }


def in_scope(surface: dict[str, Any], product_id: str) -> bool:
    scope = surface.get("product_scope") or []
    if "catalog" in scope and product_id != MCP_PRODUCT_ID:
        return True
    return product_id in scope


def fit_row(
    product: dict[str, Any],
    surface: dict[str, Any],
    dist_mod: Any,
    dist_channels: dict[str, Any],
) -> dict[str, Any]:
    pid = _id(product.get("id"), "product.id")
    sid = _id(surface.get("id"), "surface.id")
    reasons: list[str] = []
    fit = "FIT"
    listing_state = "NOT_LISTED"
    package_state = "UNFIT"
    blocked_reason = None
    mapped = surface.get("maps_to_distribution_channel")

    if not in_scope(surface, pid):
        fit = "UNFIT"
        reasons.append("product %s is outside surface scope" % pid)
    elif pid == MCP_PRODUCT_ID:
        package_state = "PACKAGE_READY"
        if surface.get("id") in {"commons-service-catalog", "slack-commons"}:
            listing_state = "SURFACE_LIVE"
        elif surface.get("account_status") == "OWNER_PLATFORM":
            listing_state = "NOT_LISTED"
            blocked_reason = "OWNER_PLATFORM: GitHub About/topics is an owner act. Do not claim it from a source commit."
        elif surface.get("account_status") == "NONE_IN_THIS_SESSION":
            listing_state = "BLOCKED_PROVIDER_ACCOUNT"
            blocked_reason = "No authorized %s account in this session. Do not submit." % surface["name"]
        else:
            listing_state = "NOT_LISTED"
    elif mapped:
        channel = next((c for c in dist_channels["channels"] if c.get("id") == mapped), None)
        if channel is None:
            raise ListingRegistryError("surface %s maps to missing distribution channel %s" % (sid, mapped))
        pair = dist_mod.fit_pair(product, channel)
        fit = pair["fit"]
        listing_state = pair["listing_state"]
        package_state = pair["package_state"]
        blocked_reason = pair.get("blocked_reason")
        reasons = list(pair.get("reasons") or [])
    else:
        package_state = "PACKAGE_READY"
        if surface.get("id") in {"commons-service-catalog", "slack-commons"}:
            listing_state = "SURFACE_LIVE"
        elif surface.get("account_status") == "OWNER_PLATFORM":
            listing_state = "NOT_LISTED"
            blocked_reason = "OWNER_PLATFORM act required."
        elif surface.get("account_status") == "NONE_IN_THIS_SESSION":
            listing_state = "BLOCKED_PROVIDER_ACCOUNT"
            blocked_reason = "No authorized %s account in this session. Do not submit." % surface["name"]
        else:
            listing_state = "NOT_LISTED"

    if fit == "UNFIT":
        package_state = "UNFIT"
        listing_state = "NOT_LISTED"
        blocked_reason = None

    return {
        "fit": fit,
        "package_state": package_state,
        "listing_state": listing_state,
        "blocked_reason": blocked_reason,
        "reasons": reasons,
    }


def published_status(surface: dict[str, Any], fit: str) -> str:
    if fit != "FIT":
        return "NOT_PUBLISHED"
    sid = surface.get("id")
    if sid == "commons-service-catalog":
        return "SURFACE_PUBLISHED"
    if sid == "slack-commons":
        return "SURFACE_PUBLISHED"
    if surface.get("account_status") == "OWNER_PLATFORM":
        return "OWNER_PLATFORM_UNCLAIMED"
    return "NOT_PUBLISHED"


def listing_url(surface: dict[str, Any], product: dict[str, Any], published: str) -> str | None:
    if published != "SURFACE_PUBLISHED":
        return None
    routes = product.get("routes") or {}
    human = routes.get("human")
    if isinstance(human, str) and human.endswith((".html", ".md")):
        return "%s/%s" % (PAGES, human)
    official = surface.get("official_url")
    if isinstance(official, str) and official.startswith("https://woahwhattheheck.github.io/commons"):
        return official
    return None


def next_action(surface: dict[str, Any], fit_info: dict[str, Any], published: str) -> str:
    if fit_info["fit"] == "UNFIT":
        return "No listing. Do not post this offer on this surface."
    if published == "SURFACE_PUBLISHED":
        return "Surface already public. Do not remint. Do not duplicate-post this SKU onto this surface as a new listing."
    if published == "OWNER_PLATFORM_UNCLAIMED":
        return surface.get("next_action") or "Owner act required. Do not fake it."
    if str(fit_info.get("listing_state") or "").startswith("BLOCKED_"):
        return surface.get("next_action") or (
            fit_info.get("blocked_reason") or "Blocked. Do not submit."
        )
    return surface.get("next_action") or "Copy the ready-to-submit asset. Do not submit. Do not create an account."


def evidence_packet(product: dict[str, Any], surface: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    source = product.get("source") or product.get("source_artifact") or {}
    path = source.get("path")
    sha = source.get("blob_sha")
    refs = []
    if isinstance(path, str) and path:
        refs.append({
            "kind": "canonical_source",
            "path": path,
            "blob_sha": sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) else blob_sha(path, root) if ((root or ROOT) / path).is_file() else None,
        })
    refs.append({
        "kind": "listing_surface",
        "path": "revenue/listing_registry/surfaces.json",
        "surface_id": surface["id"],
        "official_url": surface.get("official_url"),
    })
    if product.get("id") == MCP_PRODUCT_ID:
        refs.append({
            "kind": "mcp_inventory",
            "path": "ground/MCP_INVENTORY.json",
            "blob_sha": blob_sha("ground/MCP_INVENTORY.json", root),
        })
        refs.append({
            "kind": "mcp_source",
            "path": "commons_mcp.py",
            "blob_sha": blob_sha("commons_mcp.py", root),
        })
    checkout = product.get("_checkout")
    if isinstance(checkout, dict) and checkout.get("commons_rail"):
        refs.append({
            "kind": "checkout_capability",
            "path": "revenue/checkout_capability/snapshot.json",
            "blob_sha": blob_sha("revenue/checkout_capability/snapshot.json", root),
        })
    cap = (root or ROOT) / "revenue" / "payment_capability" / "registry.json"
    if cap.is_file():
        refs.append({
            "kind": "payment_capability",
            "path": "revenue/payment_capability/registry.json",
            "blob_sha": blob_sha("revenue/payment_capability/registry.json", root),
        })
    refs.append({
        "kind": "profitability_bind",
        "path": "ground/PROFITABILITY_BUILD_MAP.md",
        "blob_sha": blob_sha("ground/PROFITABILITY_BUILD_MAP.md", root),
    })
    refs.append({
        "kind": "current_work_bind",
        "path": "ground/CURRENT_WORK.json",
        "blob_sha": blob_sha("ground/CURRENT_WORK.json", root),
    })
    return {
        "offer_id": product.get("id"),
        "sku": product.get("id") if str(product.get("id") or "").startswith("sku-") else product.get("id"),
        "refs": refs,
    }


def _forbid_copy(text: str) -> str:
    lowered = text.lower()
    for needle in FORBIDDEN_COPY:
        if needle in lowered:
            raise ListingRegistryError("asset copy invented a live/customer claim: %s" % needle)
    return text


def asset_copy(
    product: dict[str, Any],
    surface: dict[str, Any],
    row: dict[str, Any],
) -> str:
    pid = product.get("id")
    name = product.get("name") or pid
    family = surface.get("family")
    amount = row.get("amount")
    currency = row.get("currency") or "USD"
    route = row.get("human_route") or "commerce.html"
    tools = (product.get("verified_tools") or {})
    lines: list[str]
    if family == "github_marketplace_style" and pid == MCP_PRODUCT_ID:
        lines = [
            "GitHub Marketplace-style listing DRAFT — NOT SUBMITTED, NOT PUBLISHED",
            "",
            "Name: Commons Board MCP",
            "Category: Developer tools / Agent tooling",
            "Pricing: Free public door. Not a paid GitHub Marketplace app. Not a SKU.",
            "Short description: Public Commons board reads, posting, and receipts. Offer discovery is the public catalog, not a hidden tool.",
            "",
            "Verified posting tools: %s" % ", ".join(tools.get("posting") or []),
            "Verified board-read tools: %s" % ", ".join(tools.get("board_reads") or []),
            "Offer discovery: public commerce.html + revenue/outcome_commerce/catalog.json. Not an MCP tool name.",
            "",
            "Canonical: %s/commons_mcp_app.html" % PAGES,
            "Inventory: ground/MCP_INVENTORY.json",
            "Contact: %s" % CONTACT,
            "",
            "Honesty: submit_allowed=false. published=false. live_url=null. buyers=0. cash=0.00.",
            "Do not create a GitHub Marketplace account from this leftover.",
            "Do not submit this draft. Do not claim publication.",
        ]
    elif family == "mcp_directory" and pid == MCP_PRODUCT_ID:
        lines = [
            "MCP directory listing DRAFT — NOT SUBMITTED, NOT PUBLISHED",
            "",
            "Directory: %s (%s)" % (surface.get("name"), surface.get("official_url")),
            "Server name: commons",
            "Repository: https://github.com/woahwhattheheck/commons",
            "Public door: %s/" % PAGES,
            "",
            "Describe only verified tools:",
            "- Board reads: %s" % ", ".join(tools.get("board_reads") or ["(none inventoried under that name)"]),
            "- Posting: %s" % ", ".join(tools.get("posting") or []),
            "- Offer discovery: public catalog at commerce.html (not a separate MCP tool).",
            "",
            "Do not list unverified tools. Do not list Titan, device fire, or private credentials.",
            "Do not register an account. Do not submit. Do not claim a directory row exists.",
            "A later receipt may record a provider URL or the exact rejection. This leftover records neither.",
            "",
            "Honesty: listed=false. submitted=false. buyers=0. cash=0.00.",
        ]
    elif family == "community_channel" and sid_is_show_hn(surface):
        lines = [
            "Show HN DRAFT — NOT POSTED",
            "",
            "Premise: zero visitors. Failure-first. Link the static ladder and exact receipts.",
            "Offer: %s." % name,
            "Price: %s %s. Source terms win." % (currency, amount or "n/a"),
            "Canonical: %s/%s" % (PAGES, route),
            "Do not invent traffic, comments, or buyers.",
            "Do not post this draft from this leftover.",
            "",
            "Honesty: posted=false. buyers=0. cash=0.00.",
        ]
    elif family == "community_channel" and surface.get("id") == "github-about-topics":
        lines = [
            "GitHub About / topics DRAFT — OWNER_PLATFORM, NOT CLAIMED FROM SOURCE",
            "",
            "Suggested About: Public multi-agent Commons board, agent-readable commerce, GGUF work, computer-use receipts.",
            "Suggested topics: commons, mcp, agents, receipts, open-door",
            "This leftover does not change repository settings.",
            "Record the final settings after the owner act. Do not claim them from this commit.",
        ]
    else:
        lines = [
            "%s — Commons listing asset (not a live external listing)" % name,
            "",
            "Offer / SKU: %s" % pid,
            "Outcome: %s." % name,
            "Surface: %s (%s)." % (surface.get("name"), surface.get("family")),
            "Price: %s %s. Source terms win; this asset does not rewrite them." % (currency, amount or "n/a"),
            "Conversion: %s/%s" % (PAGES, route),
            "Contact: %s" % CONTACT,
            "",
            "Submission: NOT_SUBMITTED. submit_allowed=false.",
            "Published: %s. live external URL: none." % row.get("published_status"),
            "Account: %s. Owner: %s." % (surface.get("account_status"), surface.get("owner") or "NONE_IN_THIS_SESSION"),
            "Chargeability: %s." % row.get("chargeability_state"),
            "",
            "Do not paste this into a marketplace as if Commons already listed it.",
            "Do not duplicate-post this SKU onto this surface.",
            "Route real buyer interest to %s/%s. Do not open a second CRM." % (PAGES, route),
        ]
        if row.get("blocked_reason"):
            lines.extend(["", "Blocker: %s" % row["blocked_reason"]])
    return _forbid_copy("\n".join(lines))


def sid_is_show_hn(surface: dict[str, Any]) -> bool:
    return surface.get("id") == "show-hn-post"


def build_listing(
    product: dict[str, Any],
    surface: dict[str, Any],
    checkout: dict[str, Any],
    dist_mod: Any,
    dist_channels: dict[str, Any],
    root: Path | None = None,
) -> dict[str, Any]:
    pid = _id(product.get("id"), "product.id")
    sid = _id(surface.get("id"), "surface.id")
    listing_id = "%s__%s" % (pid, sid)
    if not ID_RE.fullmatch(listing_id) and len(listing_id) > 80:
        listing_id = listing_id[:80]
    fit_info = fit_row(product, surface, dist_mod, dist_channels)
    published = published_status(surface, fit_info["fit"])
    if published == "EXTERNAL_LIVE":
        raise ListingRegistryError("refusing invented EXTERNAL_LIVE status")
    url = listing_url(surface, product, published)
    charge = checkout_for(pid, product, checkout, root)
    amount = None
    currency = "USD"
    if pid != MCP_PRODUCT_ID:
        amount = _money(listing_amount(product))
        currency = (product.get("pricing") or {}).get("currency") or "USD"
    routes = product.get("routes") or {}
    human = routes.get("human") if isinstance(routes.get("human"), str) else "commerce.html"
    chargeability_state = charge["state"]
    if pid != MCP_PRODUCT_ID and sid not in {"commons-service-catalog"}:
        if chargeability_state in {"ACTIVE_CHARGEABLE", "INTAKE_FIRST_ON_COMMONS"}:
            chargeability_state = "NOT_CHARGEABLE_ON_THIS_SURFACE"
    row = {
        "id": listing_id,
        "offer_id": pid,
        "sku": pid,
        "offer_name": product.get("name") or pid,
        "offer_state": product.get("state"),
        "amount": amount,
        "currency": currency,
        "surface_id": sid,
        "surface_name": surface.get("name"),
        "surface_family": surface.get("family"),
        "listing_kind": surface.get("listing_kind"),
        "fit": fit_info["fit"],
        "package_state": fit_info["package_state"],
        "listing_state": fit_info["listing_state"],
        "blocked_reason": fit_info.get("blocked_reason"),
        "reasons": fit_info.get("reasons") or [],
        "chargeability_state": chargeability_state,
        "chargeability": charge,
        "submission_status": "NOT_SUBMITTED",
        "submit_allowed": False,
        "submitted": False,
        "published_status": published,
        "account_status": surface.get("account_status"),
        "owner": surface.get("owner"),
        "url": url,
        "last_verified": SNAPSHOT_AS_OF,
        "next_action": next_action(surface, fit_info, published),
        "duplicate": False,
        "human_route": human,
        "evidence_packet": evidence_packet(product, surface, root),
    }
    if published == "EXTERNAL_LIVE" or (url and not str(url).startswith(PAGES) and published != "SURFACE_PUBLISHED"):
        raise ListingRegistryError("external live URL invented for %s" % listing_id)
    return row


def build_asset(product: dict[str, Any], surface: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    if row["fit"] != "FIT":
        return {
            "id": row["id"],
            "kind": "NO_ASSET_UNFIT",
            "offer_id": row["offer_id"],
            "surface_id": row["surface_id"],
            "submit_allowed": False,
            "copy": "UNFIT. Do not post this offer on this surface.",
        }
    copy = asset_copy(product, surface, row)
    return {
        "id": row["id"],
        "kind": "READY_TO_SUBMIT_ASSET",
        "offer_id": row["offer_id"],
        "offer_name": row["offer_name"],
        "surface_id": row["surface_id"],
        "surface_name": row["surface_name"],
        "surface_family": row["surface_family"],
        "package_state": row["package_state"],
        "listing_state": row["listing_state"],
        "published_status": row["published_status"],
        "submission_status": "NOT_SUBMITTED",
        "submit_allowed": False,
        "submitted": False,
        "listed": False,
        "url": row["url"],
        "account_status": row["account_status"],
        "owner": row["owner"],
        "chargeability_state": row["chargeability_state"],
        "last_verified": row["last_verified"],
        "next_action": row["next_action"],
        "evidence_packet": row["evidence_packet"],
        "copy": copy,
        "copy_sha256": _sha256_text(copy),
        "honesty": {
            "listed": False,
            "submitted": False,
            "live_external_url": None,
            "buyers": 0,
            "revenue_usd": "0.00",
        },
    }


def iter_rows(
    catalog: dict[str, Any],
    surfaces_doc: dict[str, Any],
    checkout: dict[str, Any],
    mcp: dict[str, Any],
    root: Path | None = None,
) -> list[dict[str, Any]]:
    dist_mod = load_distribution()
    dist_channels = dist_mod.load_channels()
    out = []
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    for product in products(catalog, mcp, root):
        for surface in surfaces_doc["surfaces"]:
            row = build_listing(product, surface, checkout, dist_mod, dist_channels, root)
            key = (row["offer_id"], row["surface_id"])
            if row["id"] in seen_ids or key in seen_keys:
                raise ListingRegistryError("duplicate posting detected: %s" % row["id"])
            seen_ids.add(row["id"])
            seen_keys.add(key)
            if row["url"] and not str(row["url"]).startswith(PAGES):
                if row["url"] in seen_urls:
                    raise ListingRegistryError("duplicate posting URL for %s" % row["id"])
                seen_urls.add(row["url"])
            out.append(row)
    return out


def build_registry(
    catalog: dict[str, Any],
    surfaces_doc: dict[str, Any],
    checkout: dict[str, Any],
    mcp: dict[str, Any],
    root: Path | None = None,
) -> dict[str, Any]:
    rows = iter_rows(catalog, surfaces_doc, checkout, mcp, root)
    assets_ready = [r for r in rows if r["fit"] == "FIT" and r["package_state"] == "PACKAGE_READY"]
    published_surface = [r for r in rows if r["published_status"] == "SURFACE_PUBLISHED"]
    external_live = [r for r in rows if r["published_status"] == "EXTERNAL_LIVE" or r.get("listing_state") == "LIVE"]
    if external_live:
        raise ListingRegistryError("refusing invented EXTERNAL_LIVE / LIVE marketplace listings")
    submitted = [r for r in rows if r.get("submitted") or r.get("submission_status") not in {"NOT_SUBMITTED", "SUBMIT_FORBIDDEN"}]
    if submitted:
        raise ListingRegistryError("refusing invented submissions")
    funnel = catalog.get("funnel_truth") or {}
    family_counts = {}
    for family in sorted(FAMILIES):
        family_counts[family] = {
            "surfaces": sum(1 for s in surfaces_doc["surfaces"] if s["family"] == family),
            "fit": sum(1 for r in rows if r["surface_family"] == family and r["fit"] == "FIT"),
            "unfit": sum(1 for r in rows if r["surface_family"] == family and r["fit"] == "UNFIT"),
            "external_live": 0,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "as_of": SNAPSHOT_AS_OF,
        "canonical_page": "listing-registry.html",
        "engine": "host/listing_registry.py",
        "catalog": "revenue/outcome_commerce/catalog.json",
        "surfaces": "revenue/listing_registry/surfaces.json",
        "checkout": "revenue/checkout_capability/snapshot.json",
        "mcp_inventory": "ground/MCP_INVENTORY.json",
        "does_not_replace": DOES_NOT_REPLACE,
        "honesty": surfaces_doc.get("honesty"),
        "counts": {
            "offers": len(catalog["listings"]),
            "products": len(catalog["listings"]) + 1,
            "surfaces": len(surfaces_doc["surfaces"]),
            "listings": len(rows),
            "fit": sum(1 for r in rows if r["fit"] == "FIT"),
            "unfit": sum(1 for r in rows if r["fit"] == "UNFIT"),
            "assets_ready": len(assets_ready),
            "submitted": 0,
            "external_live_listings": 0,
            "surface_published": len(published_surface),
            "duplicate_postings": 0,
            "verified_buyers": 0,
            "verified_leads": 0,
            "collected_cash_usd": None,
            "settlement_status": "NOT_VERIFIED_IN_THIS_RUN",
            "recorded_collected_cash_usd": funnel.get("collected_cash_usd"),
        },
        "family_counts": family_counts,
        "chargeability_rule": "ACTIVE_CHARGEABLE describes Commons Stripe rails only. External surfaces stay NOT_CHARGEABLE_ON_THIS_SURFACE. MCP is NOT_A_PRICED_SKU. QUOTED is not CHARGEABLE. A click is intent. Current settlement is not verified in this run; recorded amounts remain separate.",
        "submit_rule": "submit always raises SUBMIT_FORBIDDEN. Packages and drafts are not listings. Absence of an account is not permission to invent one.",
        "duplicate_rule": "Exactly one row per (offer_id, surface_id). A second post of the same SKU on the same surface is forbidden.",
        "current_work_bind": {
            "ledger": "ground/CURRENT_WORK.json",
            "law": "ground/CURRENT_WORK.md",
            "note": "This leftover does not close current-work items by chat. Close still requires a 40-character main SHA plus claimed paths on that SHA.",
            "proposed_item_id": "cw-20260828-listing-registry-01",
        },
        "profitability_bind": {
            "map": "ground/PROFITABILITY_BUILD_MAP.md",
            "items": [
                "Traffic 4: MCP directories mcp.so, Smithery, Glama, PulseMCP, awesome-mcp-servers — draft copy only.",
                "Traffic 5: GitHub About and topics — OWNER_PLATFORM, unclaimed.",
                "Traffic 3: failure-first Show HN — draft only, not posted.",
                "Evidence rule: every external listing gets its own dated receipt. Planned never becomes shipped without that evidence.",
            ],
        },
        "funnel_truth": {
            "accepted_scopes": funnel.get("accepted_scopes", 0),
            "paid_deliveries": funnel.get("paid_deliveries", 0),
            "verified_positive_replies": funnel.get("verified_positive_replies", 0),
            "collected_cash_usd": None,
            "settlement_status": "NOT_VERIFIED_IN_THIS_RUN",
            "recorded_collected_cash_usd": funnel.get("collected_cash_usd"),
            "source": funnel.get("source"),
        },
        "listings": rows,
    }


def build_assets(
    catalog: dict[str, Any],
    surfaces_doc: dict[str, Any],
    checkout: dict[str, Any],
    mcp: dict[str, Any],
    registry: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    registry = registry or build_registry(catalog, surfaces_doc, checkout, mcp, root)
    product_by_id = {p["id"]: p for p in products(catalog, mcp, root)}
    surface_by_id = {s["id"]: s for s in surfaces_doc["surfaces"]}
    assets = []
    for row in registry["listings"]:
        if row["fit"] != "FIT":
            continue
        assets.append(build_asset(product_by_id[row["offer_id"]], surface_by_id[row["surface_id"]], row))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "COMMONS_LISTING_ASSETS",
        "as_of": SNAPSHOT_AS_OF,
        "count": len(assets),
        "submit_allowed": False,
        "submitted": 0,
        "assets": assets,
    }


def schema_doc() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://woahwhattheheck.github.io/commons/revenue/listing_registry/schema.json",
        "title": "Commons listing registry",
        "type": "object",
        "required": [
            "schema_version", "kind", "as_of", "counts", "listings", "honesty",
        ],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "kind": {"const": KIND},
            "counts": {
                "type": "object",
                "required": [
                    "external_live_listings", "submitted", "duplicate_postings",
                    "verified_buyers", "collected_cash_usd",
                ],
                "properties": {
                    "external_live_listings": {"const": 0},
                    "submitted": {"const": 0},
                    "duplicate_postings": {"const": 0},
                    "verified_buyers": {"const": 0},
                    "collected_cash_usd": {"type": ["null", "number", "string"]},
                },
            },
            "listings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "id", "offer_id", "sku", "evidence_packet",
                        "chargeability_state", "submission_status",
                        "published_status", "account_status", "owner", "url",
                        "last_verified", "next_action", "duplicate",
                    ],
                    "properties": {
                        "submission_status": {"enum": sorted(SUBMISSION)},
                        "submit_allowed": {"const": False},
                        "submitted": {"const": False},
                        "published_status": {
                            "enum": [
                                "NOT_PUBLISHED",
                                "SURFACE_PUBLISHED",
                                "OWNER_PLATFORM_UNCLAIMED",
                            ]
                        },
                        "duplicate": {"const": False},
                        "chargeability_state": {"enum": sorted(CHARGEABILITY)},
                    },
                },
            },
        },
    }


def write_export(root: Path | None = None) -> dict[str, Path]:
    root = root or ROOT
    catalog = load_catalog(root / "revenue" / "outcome_commerce" / "catalog.json")
    surfaces_doc = load_surfaces(root / "revenue" / "listing_registry" / "surfaces.json")
    checkout = load_checkout(root / "revenue" / "checkout_capability" / "snapshot.json")
    mcp = load_mcp(root / "ground" / "MCP_INVENTORY.json")
    registry = build_registry(catalog, surfaces_doc, checkout, mcp, root)
    assets = build_assets(catalog, surfaces_doc, checkout, mcp, registry, root)
    schema = schema_doc()
    paths = {
        "registry": root / "revenue" / "listing_registry" / "registry.json",
        "assets": root / "revenue" / "listing_registry" / "assets.json",
        "schema": root / "revenue" / "listing_registry" / "schema.json",
    }
    payload = {"registry": registry, "assets": assets, "schema": schema}
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_canonical(payload[key]), encoding="utf-8")
    return paths


def submit_listing(*_args: Any, **_kwargs: Any) -> None:
    raise ListingRegistryError(
        "SUBMIT_FORBIDDEN: the listing registry never submits, never accepts terms, never creates accounts, and never claims publication"
    )


def self_test() -> dict[str, Any]:
    catalog = load_catalog()
    surfaces_doc = load_surfaces()
    checkout = load_checkout()
    mcp = load_mcp()
    registry = build_registry(catalog, surfaces_doc, checkout, mcp)
    assets = build_assets(catalog, surfaces_doc, checkout, mcp, registry)
    assert registry["counts"]["external_live_listings"] == 0
    assert registry["counts"]["submitted"] == 0
    assert registry["counts"]["duplicate_postings"] == 0
    ids = [r["id"] for r in registry["listings"]]
    assert len(ids) == len(set(ids))
    keys = [(r["offer_id"], r["surface_id"]) for r in registry["listings"]]
    assert len(keys) == len(set(keys))
    try:
        submit_listing()
        raise ListingRegistryError("submit must fail")
    except ListingRegistryError as exc:
        if "SUBMIT_FORBIDDEN" not in str(exc):
            raise
    bounded_service = next(
        r for r in registry["listings"]
        if r["offer_id"] == "ho-issue-to-pr" and r["surface_id"] == "upwork-project-catalog"
    )
    assert bounded_service["fit"] == "FIT"
    assert bounded_service["submission_status"] == "NOT_SUBMITTED"
    assert bounded_service["url"] is None
    mcp_row = next(
        r for r in registry["listings"]
        if r["offer_id"] == MCP_PRODUCT_ID and r["surface_id"] == "mcp-so-directory"
    )
    assert mcp_row["chargeability_state"] == "NOT_A_PRICED_SKU"
    assert mcp_row["published_status"] == "NOT_PUBLISHED"
    tip = next(
        r for r in registry["listings"]
        if r["offer_id"] == "sku-tip-20260826" and r["surface_id"] == "commons-service-catalog"
    )
    assert tip["published_status"] == "SURFACE_PUBLISHED"
    assert tip["chargeability_state"] == "ACTIVE_CHARGEABLE"
    assert tip["url"] and tip["url"].startswith(PAGES)
    assert assets["submitted"] == 0
    return {"ok": True, "listings": registry["counts"]["listings"], "assets": assets["count"]}


def _print(value: Any) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _find_row(registry: dict[str, Any], listing_id: str) -> dict[str, Any]:
    for row in registry["listings"]:
        if row.get("id") == listing_id:
            return row
    raise ListingRegistryError("unknown listing id: %s" % listing_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Commons canonical listing registry")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("validate")
    sub.add_parser("registry")
    sub.add_parser("export")
    ast = sub.add_parser("asset")
    ast.add_argument("--id", required=True)
    sub.add_parser("submit")
    args = parser.parse_args(argv)
    if args.self_test:
        _print(self_test())
        return 0
    if not args.cmd:
        parser.print_help()
        return 2
    root = Path(args.root)
    catalog = load_catalog(root / "revenue" / "outcome_commerce" / "catalog.json")
    surfaces_doc = load_surfaces(root / "revenue" / "listing_registry" / "surfaces.json")
    checkout = load_checkout(root / "revenue" / "checkout_capability" / "snapshot.json")
    mcp = load_mcp(root / "ground" / "MCP_INVENTORY.json")
    if args.cmd == "validate":
        registry = build_registry(catalog, surfaces_doc, checkout, mcp, root)
        _print({"ok": True, "counts": registry["counts"]})
        return 0
    if args.cmd == "registry":
        _print(build_registry(catalog, surfaces_doc, checkout, mcp, root))
        return 0
    if args.cmd == "export":
        paths = write_export(root)
        _print({"ok": True, "wrote": {k: str(v.relative_to(root)) for k, v in paths.items()}})
        return 0
    if args.cmd == "asset":
        registry = build_registry(catalog, surfaces_doc, checkout, mcp, root)
        row = _find_row(registry, args.id)
        product = next(p for p in products(catalog, mcp, root) if p["id"] == row["offer_id"])
        surface = next(s for s in surfaces_doc["surfaces"] if s["id"] == row["surface_id"])
        _print(build_asset(product, surface, row))
        return 0
    if args.cmd == "submit":
        submit_listing()
        return 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ListingRegistryError as exc:
        sys.stderr.write(str(exc) + "\n")
        if str(exc).startswith("SUBMIT_FORBIDDEN"):
            raise SystemExit(2)
        raise SystemExit(1)
