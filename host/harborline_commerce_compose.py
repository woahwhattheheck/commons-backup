#!/usr/bin/env python3
"""Compose StorefrontBackend contracts against Harborline Pack Market.

Cite github.com/anthropics/commerce-agents (Apache-2.0). Do not copy the tree.
LEAD leftover cursor-claude-commerce-agents-20260902-01 already pinned the
public clone. Unique-pack leftover cursor-big-huge-commerce-agents-20260902-01
owns the cite-only shopper/merchant loop. This leftover maps shopping-agent
StorefrontBackend contracts onto Harborline Local Sites ($200).

checkout_handoff is FINDER-FAILED until a real owner-pasted Stripe token
exists. Do not invent buy.stripe.com. The model never sees a checkout URL.
Cart fills. Merchant writes stay staged. Origin /shop over leftover /market.
--send/--go REFUSED sent=0. ANTHROPIC_API_KEY FINDER-FAILED.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
LEAD_HELPER = ROOT / "host" / "commerce_agents.py"
MARKET_HELPER = ROOT / "host" / "harborline_pack_market_render.py"
INSTANCE = ROOT / "packs" / "desk-website-service-20260902-01" / "instance.json"
CHECKOUT_SLOT = ROOT / "packs" / "desk-website-service-20260902-01" / "checkout.md"
ID = "cursor-harborline-commerce-compose-20260902-01"
PRODUCT_ID = "harborline-local-sites"
CITE = "https://github.com/anthropics/commerce-agents"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--live")
DUMP = ("--dump-commons", "--marketplace-html")
DO_NOT_REMINT = (
    "p/cursor-claude-commerce-agents-20260902-01.md",
    "host/commerce_agents.py",
    "ground/COMMERCE_AGENTS.json",
    "p/cursor-big-huge-commerce-agents-20260902-01.md",
    "p/cursor-harborline-pack-market-render-20260902-01.md",
    "host/harborline_pack_market_render.py",
    "p/cursor-what-a-pack-is-20260902-01.md",
    "p/cursor-pack-is-ready-to-run-20260902-01.md",
    "p/cursor-pack-quality-dictates-tier-20260902-01.md",
)
SHOPPING_SKILLS = (
    "search-discovery",
    "purchase-research",
    "planning-goals",
    "customer-care",
    "memory-personalization",
)
MERCHANT_SKILLS = (
    "performance-insights",
    "catalog-listings",
    "inventory-operations",
    "pricing-promotions",
    "marketing-campaigns",
)


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"FINDER-FAILED: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_instance(path: Path | None = None) -> dict[str, Any]:
    loaded = json.loads((path or INSTANCE).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("FINDER-FAILED: Harborline instance.json is not an object")
    return loaded


def catalog_product(instance: dict[str, Any] | None = None) -> dict[str, Any]:
    row = instance or load_instance()
    return {
        "product_id": PRODUCT_ID,
        "title": row.get("brand") or "Harborline Local Sites",
        "price_usd": int(row.get("tier_usd") or 200),
        "sale_id": row.get("sale_id"),
        "family": row.get("family"),
        "vertical": row.get("vertical") or "local_website_service",
        "checkout_slot": row.get("checkout") or "OWNER_PASTE_REQUIRED",
        "no_fake_stripe_urls": bool(row.get("no_fake_stripe_urls", True)),
        "sold_once": bool(row.get("unique_instance_sell")),
        "provenance": "harborline-pack-market",
    }


def search_discovery(query: str, session: dict[str, Any]) -> list[dict[str, Any]]:
    product = catalog_product()
    hay = " ".join(
        str(product.get(key) or "")
        for key in ("product_id", "title", "sale_id", "family", "vertical")
    ).lower()
    needles = [part for part in query.lower().split() if part]
    if not needles or not any(part in hay for part in needles):
        return []
    seen = session.setdefault("seen_ids", [])
    if product["product_id"] not in seen:
        seen.append(product["product_id"])
    return [product]


def add_to_cart(product_id: str, session: dict[str, Any]) -> dict[str, Any]:
    seen = set(session.get("seen_ids") or [])
    if product_id not in seen:
        return {
            "status": "blocked",
            "gate": "cart_provenance",
            "filled": False,
            "lines": list(session.get("cart") or []),
            "note": "Cart writes accept only product ids a catalog tool returned this session.",
        }
    product = catalog_product()
    if product_id != product["product_id"]:
        return {
            "status": "blocked",
            "gate": "unknown_product",
            "filled": False,
            "lines": list(session.get("cart") or []),
        }
    cart = session.setdefault("cart", [])
    for line in cart:
        if line["product_id"] == product_id:
            line["qty"] = int(line.get("qty") or 1) + 1
            break
    else:
        cart.append(
            {
                "product_id": product["product_id"],
                "title": product["title"],
                "price_usd": product["price_usd"],
                "qty": 1,
            }
        )
    return {"status": "ok", "filled": True, "lines": list(cart)}


def checkout_handoff(stripe_token: str | None = None) -> dict[str, Any]:
    token = (stripe_token or "").strip()
    invented = "buy.stripe.com" in token.lower() or "donate.stripe.com" in token.lower()
    if invented or not token:
        return {
            "state": "FINDER-FAILED",
            "url": None,
            "model_sees_url": False,
            "invented_stripe_urls": False,
            "note": (
                "No real Stripe token on this Harborline instance. "
                "Do not invent a Payment Link. Host-only handoff stays empty. "
                "The model never sees a checkout URL."
            ),
        }
    if not token.startswith("https://"):
        return {
            "state": "FINDER-FAILED",
            "url": None,
            "model_sees_url": False,
            "invented_stripe_urls": False,
            "note": "Stripe token is not an https owner paste. FINDER-FAILED, never silent 0.",
        }
    return {
        "state": "HOST_ONLY",
        "url": token,
        "model_sees_url": False,
        "invented_stripe_urls": False,
        "note": "Host renders the owner-pasted URL after the model call. Model never sees it.",
    }


def checkout(session: dict[str, Any], stripe_token: str | None = None) -> dict[str, Any]:
    cart = list(session.get("cart") or [])
    handoff = checkout_handoff(stripe_token)
    model_visible = {
        "cart": cart,
        "filled": bool(cart),
        "checkout": "STAGED",
        "checkout_url": None,
        "charges_a_card": False,
    }
    return {
        "model_visible": model_visible,
        "host_only": {"checkout_handoff": handoff},
        "state": handoff["state"],
        "model_sees_url": False,
    }


def stage_merchant_write(
    kind: str,
    listing_id: str,
    session: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seen = set(session.get("seen_ids") or [])
    if listing_id not in seen:
        return {
            "status": "blocked",
            "gate": "staging_provenance",
            "applied": False,
            "approved": False,
            "note": "Staged writes accept only listing ids a tool returned this session.",
        }
    change_id = f"chg-{len(session.get('staged') or []) + 1:02d}"
    change = {
        "change_id": change_id,
        "kind": kind,
        "listing_id": listing_id,
        "payload": payload or {},
        "applied": False,
        "approved": False,
        "approver": "BRYCE",
    }
    session.setdefault("staged", []).append(change)
    return {"status": "staged", **change}


def apply_change(change_id: str, session: dict[str, Any], host_approved: bool) -> dict[str, Any]:
    for change in session.get("staged") or []:
        if change.get("change_id") == change_id:
            if not host_approved:
                return {
                    "status": "blocked",
                    "gate": "host_approval",
                    "change_id": change_id,
                    "applied": False,
                    "approved": False,
                    "note": "apply_change succeeds only for ids the host marked approved. Bryce is the approval surface.",
                }
            change["approved"] = True
            change["applied"] = True
            return {"status": "applied", **change}
    return {
        "status": "blocked",
        "gate": "unknown_change",
        "change_id": change_id,
        "applied": False,
    }


def anthropic_key_state() -> dict[str, Any]:
    present = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {
        "state": "FINDER-FAILED",
        "present": present,
        "permission": False,
        "called": False,
        "note": (
            "ANTHROPIC_API_KEY FINDER-FAILED. Live Messages API / Agent SDK / "
            "Managed Agents stay unfired. Measurement, not a Commons lock."
        ),
    }


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "HARBORLINE_COMMERCE_COMPOSE",
        "id": ID,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "checkout": "FINDER-FAILED",
        "model_sees_url": False,
        "invented_stripe_urls": False,
        "note": (
            f"{flag} REFUSED. Cart may fill. checkout_handoff stays FINDER-FAILED "
            "until a real Stripe token exists. Did not invent a Payment Link."
        ),
    }


def measure(
    query: str = "harborline local sites",
    stripe_token: str | None = None,
    host_approve: bool = False,
) -> dict[str, Any]:
    lead = _load(LEAD_HELPER, "commerce_agents").measure()
    market = _load(MARKET_HELPER, "harborline_pack_market_render").measure()
    instance = load_instance()
    product = catalog_product(instance)
    session: dict[str, Any] = {"seen_ids": [], "cart": [], "staged": []}
    hits = search_discovery(query, session)
    cart = add_to_cart(PRODUCT_ID, session) if hits else {
        "status": "blocked",
        "gate": "no_search_hit",
        "filled": False,
        "lines": [],
    }
    billed = checkout(session, stripe_token)
    staged = stage_merchant_write(
        "price-move",
        PRODUCT_ID,
        session,
        {"price_usd": product["price_usd"], "note": "quality dictates tier; host approves"},
    )
    applied = apply_change(staged.get("change_id") or "chg-00", session, host_approve)
    dumped = (ROOT / "marketplace.html").exists()
    errors: list[str] = []
    if lead.get("copy_blueprint_source"):
        errors.append("copied_blueprint")
    if billed["model_visible"].get("checkout_url"):
        errors.append("model_saw_url")
    if billed["host_only"]["checkout_handoff"].get("invented_stripe_urls"):
        errors.append("invented_stripe_urls")
    if dumped:
        errors.append("marketplace_html")
    if instance.get("no_fake_stripe_urls") is not True:
        errors.append("instance_allows_fake_stripe")
    if not cart.get("filled"):
        errors.append("cart_empty")
    if applied.get("applied") and not host_approve:
        errors.append("merchant_write_applied_without_host")
    return {
        "kind": "HARBORLINE_COMMERCE_COMPOSE",
        "id": ID,
        "cite": CITE,
        "license": "Apache-2.0",
        "copy_blueprint_source": False,
        "lead_leftover": lead.get("id"),
        "lead_pin": lead.get("pin"),
        "unique_pack_leftover": "cursor-big-huge-commerce-agents-20260902-01",
        "unique_pack_owned": "cite-only shopper/merchant loop",
        "did_not_remint": list(DO_NOT_REMINT),
        "commons_is_store": False,
        "desk_route": "/shop",
        "over": "/market",
        "market_featured": market.get("featured"),
        "product": product,
        "shopping_skills": list(SHOPPING_SKILLS),
        "merchant_skills": list(MERCHANT_SKILLS),
        "search": hits,
        "cart": cart,
        "checkout": billed,
        "merchant_staged": staged,
        "merchant_apply": applied,
        "anthropic_api_key": anthropic_key_state(),
        "marketplace_html_on_commons": dumped,
        "invented_stripe_urls": False,
        "model_sees_url": False,
        "sent": 0,
        "cash": 0,
        "verdict": "FINDER-FAILED" if errors or billed["state"] == "FINDER-FAILED" else "RENDER",
        "errors": errors,
        "note": (
            "Origin /shop over leftover /market. Harborline Local Sites $200 fills "
            "the cart. checkout_handoff FINDER-FAILED until a real Stripe token. "
            "Merchant writes stay staged for Bryce. Did not steal LEAD leftover, "
            "unique-pack leftover, or Harborline leftover 54c348dc."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--query", default="harborline local sites")
    parser.add_argument("--stripe-token", default="")
    parser.add_argument("--host-approve", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE or flag in DUMP:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "HARBORLINE_COMMERCE_COMPOSE",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    packet = measure(
        query=args.query,
        stripe_token=args.stripe_token or None,
        host_approve=args.host_approve,
    )
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["cart"].get("filled") and not packet["marketplace_html_on_commons"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
