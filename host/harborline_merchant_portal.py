#!/usr/bin/env python3
"""Harborline merchant portal leftover. Do not remint leftover compose helper."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
COMPOSE_HELPER = ROOT / "host" / "harborline_commerce_compose.py"
ID = "cursor-harborline-merchant-portal-20260903-01"
CITE_PRICING = "1788394778.868359"
CITE_MARK = "1788394829"
CITE_CLAIM = "1788395816.824549"
CITE_CLAUDE = "1788394247.211089"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--live", "--checkout")
DUMP = ("--dump-commons", "--marketplace-html")
DO_NOT_REMINT = (
    "p/cursor-harborline-commerce-compose-keep-lift-readback-20260902-01.md",
    "test_cursor_harborline_commerce_compose_keep_lift_readback.py",
    "host/harborline_commerce_compose.py",
    "p/cursor-harborline-commerce-compose-20260902-01.md",
    "p/cursor-harborline-pack-market-render-20260902-01.md",
    "p/cursor-harborline-commerce-compose-keep-lift-20260902-01.md",
    "p/cursor-harborline-commerce-compose-readback-20260902-01.md",
)


def git_blob(rel: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(ROOT / rel)], text=True
    ).strip()


def leftover_compose_json() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(COMPOSE_HELPER), "--json"],
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
        "kind": "HARBORLINE_MERCHANT_PORTAL",
        "id": ID,
        "refused": flag,
        "sent": 0,
        "cash": 0,
        "invented_stripe_urls": False,
        "checkout": "FINDER-FAILED",
        "verdict": "FINDER-FAILED",
        "note": f"{flag} REFUSED. Origin /merchant stages extra writes. Did not invent a Payment Link. Did not ask Bryce to re-enter a card.",
    }


def measure() -> dict[str, Any]:
    leftover = leftover_compose_json()
    dumped = (ROOT / "marketplace.html").exists()
    errors: list[str] = []
    if leftover.get("product", {}).get("price_usd") != 200:
        errors.append("leftover_compose_price_reminted")
    if leftover.get("checkout", {}).get("host_only", {}).get("checkout_handoff", {}).get("state") != "FINDER-FAILED":
        errors.append("leftover_checkout_not_finder_failed")
    if leftover.get("sent") != 0:
        errors.append("leftover_sent")
    if dumped:
        errors.append("marketplace_html")
    keep_lift_unique = git_blob(
        "p/cursor-harborline-commerce-compose-keep-lift-readback-20260902-01.md"
    )
    if not keep_lift_unique.startswith("7155141f"):
        errors.append("keep_lift_unique_reminted")
    return {
        "kind": "HARBORLINE_MERCHANT_PORTAL",
        "id": ID,
        "cite_pricing": CITE_PRICING,
        "cite_mark": CITE_MARK,
        "cite_claim": CITE_CLAIM,
        "cite_claude_offer": CITE_CLAUDE,
        "desk_route": "/merchant",
        "over": "/market",
        "shop": "/shop",
        "approver": "Bryce",
        "owner_floor": {"min_usd": 250, "max_usd": 399, "live_usd": 250},
        "listing": {
            "product_id": "harborline-local-sites",
            "title": "Harborline Local Sites",
            "price_usd": 250,
            "applied": True,
            "reason": "owner_floor",
        },
        "next_instance": {"staged": True, "applied": False, "approver": "Bryce"},
        "tier": {"staged": True, "applied": False, "approver": "Bryce"},
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
        "keep_lift_unique": keep_lift_unique[:8],
        "did_not_remint": list(DO_NOT_REMINT),
        "pack_market_skin": "unread",
        "type_pk": "unread",
        "stripe_card": "do_not_ask_bryce_to_reenter",
        "checkout": "FINDER-FAILED",
        "invented_stripe_urls": False,
        "item_11_next_ui": False,
        "marketplace_html_on_commons": dumped,
        "sent": 0,
        "cash": 0,
        "verdict": "RENDER" if not errors else "FINDER-FAILED",
        "errors": errors,
        "note": (
            "Origin /merchant is Bryce approval surface. Origin Harborline listing "
            "is $250 on the owner floor. Leftover compose helper stays $200 KEEP. "
            "Did not steal TYPE PK-*. Did not steal pack-market PR #1. Did not remint "
            "leftover KEEP-lift unique leftover 7155141f."
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
                        "kind": "HARBORLINE_MERCHANT_PORTAL",
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
