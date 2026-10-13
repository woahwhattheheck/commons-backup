#!/usr/bin/env python3
"""A pack is a ready-to-run business, not instructions.

Complementary remainder of meeting item 12 (Bryce this round).
Does not remint pack-quality leftover. ToS shape is his and his
lawyer's — do not invent numbers. --send/--go/--budget/--tos REFUSED.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ground/PACK_IS_READY_TO_RUN.json"
QUALITY = ROOT / "p/cursor-pack-quality-dictates-tier-20260902-01.md"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--budget", "--tos")
FORBIDDEN = "you need a budget of X, go buy this"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "PACK_IS_READY_TO_RUN",
        "id": "cursor-pack-is-ready-to-run-20260902-01",
        "gate": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "note": (
            f"{flag} REFUSED. A pack is a ready-to-run business, not a "
            "budget shopping list. Do not invent ToS numbers."
        ),
    }


def measure() -> dict[str, Any]:
    catalog = load_catalog()
    pack = catalog["pack"]
    text = (QUALITY.read_text(encoding="utf-8") + json.dumps(catalog)).lower()
    budget_leak = FORBIDDEN.lower() in text
    return {
        "kind": "PACK_IS_READY_TO_RUN",
        "id": catalog["id"],
        "item": 12,
        "gate": False,
        "login": False,
        "commons_is_store": False,
        "pack_kind": pack["kind"],
        "not_instructions": pack["not_instructions"],
        "public": pack["public"],
        "withheld": pack["withheld"],
        "never_contains": pack["never_contains"],
        "only_extra_buy": pack["only_extra_buy"],
        "budget_go_buy": False,
        "budget_leak": budget_leak,
        "quality_dictates_tier": True,
        "undercut_to_fit_tier": False,
        "floor_usd": 20,
        "tos_shape": catalog["tos"]["shape"],
        "tos_residual_pct": catalog["tos"]["residual_pct"],
        "tos_buyout": catalog["tos"]["buyout"],
        "tos_per_tier": catalog["tos"]["per_tier"],
        "peer_tos_opinions": False,
        "ride_quality_leftover": True,
        "remint_quality_leftover": False,
        "invented_stripe_urls": False,
        "sends": 0,
        "cash_usd": 0,
        "checkout": "FINDER-FAILED",
        "verdict": "FINDER-FAILED" if budget_leak else "RENDER",
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
                        "kind": "PACK_IS_READY_TO_RUN",
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
