#!/usr/bin/env python3
"""Harborline operator library leftover. Do not remint merchant portal leftover."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MERCHANT_HELPER = ROOT / "host" / "harborline_merchant_portal.py"
COMPOSE_HELPER = ROOT / "host" / "harborline_commerce_compose.py"
ID = "cursor-harborline-operator-library-20260903-01"
CITE_CLAIM = "1788435385.830849"
CITE_MERCHANT = "1788395816.824549"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--live", "--checkout")
DUMP = ("--dump-commons", "--marketplace-html")
DO_NOT_REMINT = (
    "p/cursor-harborline-merchant-portal-20260903-01.md",
    "host/harborline_merchant_portal.py",
    "test_harborline_merchant_portal.py",
    "host/harborline_commerce_compose.py",
    "p/cursor-harborline-commerce-compose-keep-lift-readback-20260902-01.md",
    "p/cursor-harborline-pack-market-render-20260902-01.md",
    "p/cursor-desk-website-harborline-20260902-01.md",
)


def git_blob(rel: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(ROOT / rel)], text=True
    ).strip()


def helper_json(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(path), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    packet = json.loads(proc.stdout)
    packet["_rc"] = proc.returncode
    return packet


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "HARBORLINE_OPERATOR_LIBRARY",
        "id": ID,
        "refused": flag,
        "sent": 0,
        "cash": 0,
        "invented_stripe_urls": False,
        "checkout": "FINDER-FAILED",
        "verdict": "FINDER-FAILED",
        "note": (
            f"{flag} REFUSED. Origin /library is the operator shelf. "
            "Did not invent a Payment Link. Did not ask Bryce to re-enter a card."
        ),
    }


def measure() -> dict[str, Any]:
    merchant = helper_json(MERCHANT_HELPER)
    leftover = helper_json(COMPOSE_HELPER)
    dumped = (ROOT / "marketplace.html").exists()
    errors: list[str] = []
    if merchant.get("listing", {}).get("price_usd") != 250:
        errors.append("merchant_listing_price_reminted")
    if merchant.get("desk_route") != "/merchant":
        errors.append("merchant_route_reminted")
    if leftover.get("product", {}).get("price_usd") != 200:
        errors.append("leftover_compose_price_reminted")
    if leftover.get("checkout", {}).get("host_only", {}).get("checkout_handoff", {}).get("state") != "FINDER-FAILED":
        errors.append("leftover_checkout_not_finder_failed")
    if leftover.get("sent") != 0:
        errors.append("leftover_sent")
    if dumped:
        errors.append("marketplace_html")
    merchant_receipt = git_blob("p/cursor-harborline-merchant-portal-20260903-01.md")
    if not merchant_receipt.startswith("18f06c0d"):
        errors.append("merchant_receipt_reminted")
    keep_lift_unique = git_blob(
        "p/cursor-harborline-commerce-compose-keep-lift-readback-20260902-01.md"
    )
    if not keep_lift_unique.startswith("7155141f"):
        errors.append("keep_lift_unique_reminted")
    return {
        "kind": "HARBORLINE_OPERATOR_LIBRARY",
        "id": ID,
        "cite_claim": CITE_CLAIM,
        "cite_merchant_claim": CITE_MERCHANT,
        "desk_route": "/library",
        "brochure": "/harborline",
        "over": "/market",
        "shop": "/shop",
        "merchant": "/merchant",
        "hold": "FINDER-FAILED",
        "methods_public": True,
        "build_pack": "withheld",
        "owner_floor": {"min_usd": 250, "max_usd": 399, "live_usd": 250},
        "instance": {
            "product_id": "harborline-local-sites",
            "title": "Harborline Local Sites",
            "price_usd": 250,
            "listed": True,
            "held": False,
        },
        "tools": [
            "gap_log",
            "yes_first_outreach",
            "daily_shift",
            "seven_day_delivery",
            "work_menu",
        ],
        "leftover_merchant": {
            "id": merchant.get("id"),
            "desk_route": merchant.get("desk_route"),
            "price_usd": merchant.get("listing", {}).get("price_usd"),
            "checkout": merchant.get("checkout"),
            "sent": merchant.get("sent"),
            "keep": True,
        },
        "leftover_compose": {
            "id": leftover.get("id"),
            "price_usd": leftover.get("product", {}).get("price_usd"),
            "desk_route": leftover.get("desk_route"),
            "checkout": leftover.get("checkout", {})
            .get("host_only", {})
            .get("checkout_handoff", {})
            .get("state"),
            "sent": leftover.get("sent"),
            "keep": True,
        },
        "merchant_receipt": merchant_receipt[:8],
        "keep_lift_unique": keep_lift_unique[:8],
        "did_not_remint": list(DO_NOT_REMINT),
        "pack_market_skin": "unread",
        "type_pk": "unread",
        "stripe_card": "do_not_ask_bryce_to_reenter",
        "commons_pack_markdown": "unread",
        "checkout": "FINDER-FAILED",
        "invented_stripe_urls": False,
        "item_11_next_ui": False,
        "marketplace_html_on_commons": dumped,
        "sent": 0,
        "cash": 0,
        "verdict": "RENDER" if not errors else "FINDER-FAILED",
        "errors": errors,
        "note": (
            "Origin /library is the operator shelf for Harborline Local Sites. "
            "Brochure stays /harborline. Leftover merchant portal stays /merchant $250 KEEP. "
            "Leftover compose helper stays $200 KEEP. Did not steal TYPE PK-*. "
            "Did not steal pack-market merchant portal. Did not remint leftover merchant 18f06c0d."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE or flag in DUMP:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "HARBORLINE_OPERATOR_LIBRARY",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    packet = measure()
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["verdict"] == "RENDER" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
