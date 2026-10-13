#!/usr/bin/env python3
"""Adopt Anthropic's open Claude Commerce Agents blueprint.

Owner BIG AND HUGE 1788388313.281509 + "We need to use that".
Cite the public clone. Do not copy the blueprint source. Do not remint AutoGTM.
--send/--go/--live/--checkout REFUSED. ANTHROPIC_API_KEY FINDER-FAILED.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ground/COMMERCE_AGENTS.json"
AUTOGTM_DOOR = ROOT / "autogtm.html"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--live", "--checkout")
PIN = "fd4d59224ab96b43c6dc6888207c67b3bd5a24cf"
ID = "cursor-claude-commerce-agents-20260902-01"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "CLAUDE_COMMERCE_AGENTS",
        "id": ID,
        "gate": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "note": (
            f"{flag} REFUSED. Clone the public blueprint. Do not invent "
            "Stripe URLs. Do not fire a live Anthropic demo from Commons."
        ),
    }


def measure() -> dict[str, Any]:
    catalog = load_catalog()
    source = catalog["source"]
    errors: list[str] = []
    if source.get("pin") != PIN:
        errors.append("source.pin")
    if source.get("copy_blueprint_source") is not False:
        errors.append("copied_blueprint")
    if catalog.get("commons_is_store") is not False:
        errors.append("commons_is_store")
    if catalog.get("invented_stripe_urls") is not False:
        errors.append("invented_stripe_urls")
    if catalog.get("charges_a_card") is not False:
        errors.append("charges_a_card")
    if catalog.get("anthropic_api_key") != "FINDER-FAILED":
        errors.append("anthropic_api_key")
    if catalog.get("checkout_hands_off") is not True:
        errors.append("checkout_hands_off")
    if not AUTOGTM_DOOR.exists():
        errors.append("autogtm_door_missing")
    return {
        "kind": "CLAUDE_COMMERCE_AGENTS",
        "id": catalog["id"],
        "gate": False,
        "login": False,
        "commons_is_store": False,
        "repo": source["repo"],
        "clone": source["clone"],
        "pin": source["pin"],
        "license": source["license"],
        "copy_blueprint_source": False,
        "shopping_agent": catalog["agents"]["shopping"],
        "merchant_agent": catalog["agents"]["merchant"],
        "verticals": list(catalog["verticals"]),
        "plugin": catalog["plugin"],
        "checkout_hands_off": True,
        "charges_a_card": False,
        "anthropic_api_key": "FINDER-FAILED",
        "invented_stripe_urls": False,
        "remint_autogtm": False,
        "sends": 0,
        "cash_usd": 0,
        "checkout": "FINDER-FAILED",
        "verdict": "FINDER-FAILED" if errors else "RENDER",
        "errors": errors,
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
                        "kind": "CLAUDE_COMMERCE_AGENTS",
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
