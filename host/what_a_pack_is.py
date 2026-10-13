#!/usr/bin/env python3
"""A pack is a ready-to-run business, not instructions.

Complementary remainder of meeting item 12. Ride leftover
pack-quality helper. Do not remint it. Do not invent ToS numbers.
Do not write a legal memo. --send/--go/--tos/--budget/--legal REFUSED.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ground/WHAT_A_PACK_IS.json"
QUALITY = ROOT / "host/pack_quality_dictates_tier.py"
REFUSE = (
    "--send",
    "--apply",
    "--go",
    "--autopilot",
    "--undercut",
    "--tos",
    "--budget",
    "--legal",
)


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))


def leftover_quality() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(QUALITY), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "rc": proc.returncode, "packet": {}}
    return {"ok": True, "rc": 0, "packet": json.loads(proc.stdout)}


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "WHAT_A_PACK_IS",
        "id": "cursor-what-a-pack-is-20260902-01",
        "gate": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "peer_tos_opinions": False,
        "note": (
            f"{flag} REFUSED. A pack is a ready-to-run business. "
            "Do not invent ToS numbers. Do not write a legal memo."
        ),
    }


def measure() -> dict[str, Any]:
    catalog = load_catalog()
    quality = leftover_quality()
    packet = quality["packet"]
    example = catalog["example"]
    go_buy = not bool(catalog["never_contains_go_buy_this"])
    instructions = bool(catalog["pack_is_instructions"])
    peer_tos = bool(catalog["tos"]["peer_opinions"])
    quality_ok = (
        quality["ok"]
        and packet.get("quality_dictates_tier") is True
        and packet.get("undercut_to_fit_tier") is False
        and packet.get("tos_shape") == "OPEN_QUESTION"
    )
    ok = (
        bool(catalog["pack_is_ready_to_run_business"])
        and not instructions
        and bool(catalog["public_descriptions_and_methods"])
        and catalog["withheld"] == "build_pack_access"
        and not go_buy
        and catalog["extra_buy"] == "tjlabs_supporting_product_or_service"
        and not peer_tos
        and quality_ok
        and int(example["price_usd"]) >= 20
        and example["method_pdf"] is False
    )
    return {
        "kind": "WHAT_A_PACK_IS",
        "id": catalog["id"],
        "item": 12,
        "remainder": catalog["remainder"],
        "gate": False,
        "login": False,
        "commons_is_store": False,
        "pack_is_ready_to_run_business": catalog["pack_is_ready_to_run_business"],
        "pack_is_instructions": catalog["pack_is_instructions"],
        "public_descriptions_and_methods": catalog["public_descriptions_and_methods"],
        "withheld": catalog["withheld"],
        "never_contains_go_buy_this": catalog["never_contains_go_buy_this"],
        "extra_buy": catalog["extra_buy"],
        "includes": catalog["includes"],
        "quality_dictates_tier": packet.get("quality_dictates_tier"),
        "undercut_to_fit_tier": packet.get("undercut_to_fit_tier"),
        "floor_usd": packet.get("floor_usd"),
        "ride_pack_quality": True,
        "remint_pack_quality": False,
        "tos_shape": catalog["tos"]["shape"],
        "tos_residual_pct": catalog["tos"]["residual_pct"],
        "tos_buyout": catalog["tos"]["buyout"],
        "tos_per_tier": catalog["tos"]["per_tier"],
        "peer_tos_opinions": False,
        "example": example,
        "invented_stripe_urls": False,
        "sends": 0,
        "cash_usd": 0,
        "checkout": "FINDER-FAILED",
        "verdict": "RENDER" if ok else "FINDER-FAILED",
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
                        "kind": "WHAT_A_PACK_IS",
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
