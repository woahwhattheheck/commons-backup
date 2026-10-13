#!/usr/bin/env python3
"""Harborline pack-market rendering. Commons is not the store. --send REFUSED."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFUSE = ("--send", "--apply", "--go", "--autopilot")
DUMP = ("--dump-commons", "--marketplace-html")


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


def measure() -> dict[str, object]:
    dumped = (ROOT / "marketplace.html").exists()
    return {
        "store": "standalone",
        "desk_route": "/market",
        "commons_is_store": False,
        "marketplace_html_on_commons": dumped,
        "featured": "harborline-local-sites",
        "price_usd": 200,
        "checkout": "FINDER-FAILED",
        "sent": 0,
        "booked": 0,
        "cash": 0,
        "verdict": "FINDER-FAILED" if dumped else "RENDER",
        "note": (
            "Harborline leftover: Origin /market is the standalone storefront. "
            "Commons only pipes named packs. A store HTML door on Commons is a miss. "
            "Stripe token FINDER-FAILED; empty slot is not a freeze. Did not spawn Muse Spark / gpt-6."
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
    print(json.dumps(payload, sort_keys=True))
    return 1 if payload["marketplace_html_on_commons"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
