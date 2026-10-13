#!/usr/bin/env python3
"""Slack Steam UI rendering of Harborline /market. Commons is not the store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFUSE = ("--send", "--apply", "--go", "--autopilot")
DUMP = ("--dump-commons", "--marketplace-html")

FEATURED = "Harborline Local Sites"
PRICE_USD = 200
DESK_ROUTE = "/market"

SLACK_MD = """PACK MARKET
standalone storefront · Origin `/market` · Commons is not the store

*FEATURED*
*Harborline Local Sites — $200*
Named business. Zero odds. Buyer is told what they get.

What you get: a named Harborline local-sites business pack. Not a lootbox. Method and qualify stay on the Harborline desk.

Checkout: FINDER-FAILED. Empty slot is not a freeze. Did not invent a Payment Link.

Waitlist · Method · Qualify

*COMMONS PIPE*
empty — no invented SKU. Incoming-models KEEP unread.
Sends 0.
"""


def refuse_payload(flag: str) -> dict[str, object]:
    return {
        "store": "standalone",
        "commons_is_store": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "booked": 0,
        "cash": 0,
        "checkout": "FINDER-FAILED",
        "note": f"{flag} REFUSED. sent=0 booked=0 cash=0. Did not dump a store HTML door onto Commons.",
    }


def slack_render() -> str:
    return SLACK_MD.strip() + "\n"


def measure() -> dict[str, object]:
    dumped = (ROOT / "marketplace.html").exists()
    return {
        "store": "standalone",
        "desk_route": DESK_ROUTE,
        "commons_is_store": False,
        "marketplace_html_on_commons": dumped,
        "featured": "harborline-local-sites",
        "featured_title": FEATURED,
        "price_usd": PRICE_USD,
        "odds": 0,
        "checkout": "FINDER-FAILED",
        "sent": 0,
        "booked": 0,
        "cash": 0,
        "surface": "slack",
        "slack_md": slack_render(),
        "verdict": "FINDER-FAILED" if dumped else "SLACK_RENDER",
        "note": (
            "OWNER_NOW open question: marketplace renderings in Slack before further UI. "
            "This is the Slack Steam UI card for Origin /market. Commons only pipes named packs. "
            "A store HTML door on Commons is a miss. Stripe token FINDER-FAILED; empty is not a freeze."
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
                        "store": "standalone",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    payload = measure()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        sys.stdout.write(payload["slack_md"])
    return 1 if payload["marketplace_html_on_commons"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
