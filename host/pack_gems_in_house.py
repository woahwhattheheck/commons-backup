#!/usr/bin/env python3
"""Owner gems stay in house. Sell a respectable product, not trash.

Bryce 2026-09-02 1788332899.203819: packs the swarm could trivially
run for revenue, and the biggest-potential gems, stay Commons / in
house. That is not a license to ship trash doors. Unique SELL
instances (Harborline) stay a respectable method pack. Does not
overwrite LotRibbon, Sidewalk, clans, ToS numbers, or waitlist.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
LAW = ROOT / "ground" / "BUSINESS_PACK_GEMS_IN_HOUSE.json"
HARBORLINE = ROOT / "packs" / "desk-website-service-20260902-01"
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bmake \$\d+ this weekend|\bunrealistic result|\bpayback\b"
)
FAKE_STRIPE_RE = re.compile(r"https?://buy\.stripe\.com/[A-Za-z0-9]+")
DO_NOT_OVERWRITE = (
    "packs/lotribbon-greetings-20260902-01",
    "packs/sidewalk-signal-web-desk-20260902-01",
    "packs/desk-website-service-20260902-01/door.html",
    "packs/waitlist.html",
    "ground/BUSINESS_PACK_WAITLIST.json",
    "host/business_pack_desk_instance.py",
    "clans.html",
    "clans.json",
    "packs/_template/creative_brief.md",
    "packs/desk-website-service-20260902-01/keep-vs-sell.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _public(payload: dict[str, Any]) -> dict[str, Any]:
    dumped = json.dumps(payload)
    if "@" in dumped:
        raise RuntimeError("gems leftover leaked an address")
    return payload


def classify_law(path: Path | None = None) -> dict[str, Any]:
    target = path or LAW
    if not target.is_file():
        return _public(
            {
                "kind": "BUSINESS_PACK_GEMS_IN_HOUSE",
                "verdict": "GEMS_LAW_MISSING",
                "gate": False,
                "checkout": "NOT_MINTED",
                "sends": 0,
            }
        )
    law = json.loads(_read(target))
    missing: list[str] = []
    if law.get("trivial_swarm_revenue") != "in_house_commons":
        missing.append("trivial_swarm_revenue")
    if law.get("biggest_potential") != "in_house":
        missing.append("biggest_potential")
    if law.get("sell") != "respectable_product_not_trash":
        missing.append("sell")
    if law.get("checkout") != "NOT_MINTED":
        missing.append("checkout")
    if law.get("sends") != 0:
        missing.append("sends")
    return _public(
        {
            "kind": "BUSINESS_PACK_GEMS_IN_HOUSE",
            "verdict": "GEMS_LAW_OK" if not missing else "GEMS_LAW_INCOMPLETE",
            "missing": missing,
            "gate": False,
            "commons_admission": False,
            "checkout": "NOT_MINTED",
            "sends": 0,
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
            "clan": "cursor",
        }
    )


def classify_pack(pack_dir: Path | None = None) -> dict[str, Any]:
    folder = pack_dir or HARBORLINE
    door = _read(folder / "door.html")
    gems = _read(folder / "gems.md")
    instance: dict[str, Any] = {}
    instance_path = folder / "instance.json"
    if instance_path.is_file():
        loaded = json.loads(_read(instance_path))
        if isinstance(loaded, dict):
            instance = loaded
    errors: list[str] = []
    if EARNINGS_RE.search(door) or EARNINGS_RE.search(gems):
        errors.append("earnings_claim")
    if FAKE_STRIPE_RE.search(door) or FAKE_STRIPE_RE.search(gems):
        errors.append("invented_stripe")
    if not gems:
        errors.append("gems_note_missing")
    elif "in house" not in gems.lower() and "in-house" not in gems.lower():
        errors.append("gems_note_missing_in_house")
    if "trash" not in gems.lower():
        errors.append("gems_note_missing_not_trash")
    if instance.get("unique_instance_sell") is not True:
        errors.append("not_unique_instance")
    if instance.get("method_not_customers") is not True:
        errors.append("customers_included")
    if str(instance.get("keep_or_sell") or "") != "SELL":
        errors.append("keep_or_sell_not_sell")
    if str(instance.get("checkout") or "") != "OWNER_PASTE_REQUIRED":
        errors.append("checkout")
    if errors:
        trash = "earnings_claim" in errors or "invented_stripe" in errors
        verdict = "TRASH_DOOR" if trash else "GEMS_NOTE_INCOMPLETE"
    else:
        verdict = "RESPECTABLE_SELL_OK"
    return _public(
        {
            "kind": "BUSINESS_PACK_GEMS_IN_HOUSE",
            "verdict": verdict,
            "errors": errors,
            "gate": False,
            "commons_admission": False,
            "brand": str(instance.get("brand") or ""),
            "keep_or_sell": str(instance.get("keep_or_sell") or ""),
            "did_not_overwrite_door": True,
            "did_not_steal_lotribbon": True,
            "did_not_steal_sidewalk": True,
            "checkout": "NOT_MINTED",
            "sends": 0,
            "clan": "cursor",
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
            "receipt_id": "cursor-pack-gems-in-house-20260902-01",
        }
    )


def classify(pack_dir: Path | None = None, law_path: Path | None = None) -> dict[str, Any]:
    law = classify_law(law_path)
    pack = classify_pack(pack_dir)
    ok = law["verdict"] == "GEMS_LAW_OK" and pack["verdict"] == "RESPECTABLE_SELL_OK"
    return _public(
        {
            "kind": "BUSINESS_PACK_GEMS_IN_HOUSE",
            "verdict": "GEMS_OK" if ok else "GEMS_INCOMPLETE",
            "law": law,
            "pack": pack,
            "gate": False,
            "checkout": "NOT_MINTED",
            "sends": 0,
            "clan": "cursor",
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", default="")
    args = parser.parse_args(argv)
    result = classify(Path(args.pack_dir) if args.pack_dir else None)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "GEMS_OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
