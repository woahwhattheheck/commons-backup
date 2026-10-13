#!/usr/bin/env python3
"""Pack quality dictates tier. Do not undercut $20 to fit a cheaper rung.

Not KEEP/SELL factory. Not the Harborline storefront. ToS shape is an
open question — do not invent residual / buyout / per-tier numbers.
--send/--go/--undercut REFUSED.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ground/PACK_QUALITY_DICTATES_TIER.json"
KEEP_SELL = ROOT / "ground/BUSINESS_PACK_KEEP_SELL.json"
FLOOR = 20
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--undercut")


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))


def keep_sell_tiers(path: Path | None = None) -> list[int]:
    data = json.loads((path or KEEP_SELL).read_text(encoding="utf-8"))
    tiers = data.get("tiers_usd") or []
    return [int(x) for x in tiers]


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "PACK_QUALITY_DICTATES_TIER",
        "id": "cursor-pack-quality-dictates-tier-20260902-01",
        "gate": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "undercut_to_fit_tier": False,
        "note": f"{flag} REFUSED. Do not undercut $20 to fit a tier. Do not invent ToS numbers.",
    }


def measure() -> dict[str, Any]:
    catalog = load_catalog()
    tiers = keep_sell_tiers()
    example = catalog["example"]
    undercut = int(example["price_usd"]) < FLOOR
    return {
        "kind": "PACK_QUALITY_DICTATES_TIER",
        "id": catalog["id"],
        "item": 12,
        "gate": False,
        "login": False,
        "commons_is_store": False,
        "quality_dictates_tier": True,
        "undercut_to_fit_tier": False,
        "floor_usd": FLOOR,
        "catalog_tiers_usd": tiers,
        "fifty_usd_catalog": catalog["fifty_usd_catalog"],
        "tos_shape": catalog["tos"]["shape"],
        "tos_residual_pct": catalog["tos"]["residual_pct"],
        "tos_buyout": catalog["tos"]["buyout"],
        "tos_per_tier": catalog["tos"]["per_tier"],
        "example": example,
        "example_undercut": undercut,
        "ride_keep_sell_tiers": True,
        "remint_keep_sell": False,
        "invented_stripe_urls": False,
        "sends": 0,
        "cash_usd": 0,
        "checkout": "FINDER-FAILED",
        "verdict": "FINDER-FAILED" if undercut or 20 not in tiers else "RENDER",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "PACK_QUALITY_DICTATES_TIER",
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
