#!/usr/bin/env python3
"""Harborline instance fill of the factory rating slot. Compose leftover.

GOAT / unique-pack own packs/_template/rating.md and
host/business_pack_rating.py (id cursor-business-pack-rating-slot-20260902-01).
This leftover only fills Harborline's instance sheet. It does not remint
the factory slot, rewrite the template, pick a partner, invent a bulk
price, or write leftover pin-lift helpers / Harborline door / waitlist /
TALLY / LotRibbon. Empty badge+report is the correct instance state until
Bryce pastes. Completeness audit allowed. Dollar valuation is earnings.

Peer Sidewalk / LotRibbon rating.md fills were absent at leftover land
and are not live-pinned (cursor-pack-harborline-rating-peer-unpin-20260902-01).
The Harborline instance door and leftover pin-lift helper sources are KEEP
MAIN files: observe their live hashes, do not freeze this leftover on the
land-time blobs. Checkout NOT_MINTED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "host"))

import business_pack_rating as factory  # noqa: E402

TEMPLATE = ROOT / "packs" / "_template" / "rating.md"
HARBORLINE = ROOT / "packs" / "desk-website-service-20260902-01" / "rating.md"
SIDEWALK = ROOT / "packs" / "sidewalk-signal-web-desk-20260902-01" / "rating.md"
LOTRIBBON = ROOT / "packs" / "lotribbon-greetings-20260902-01" / "rating.md"
MANIFEST = ROOT / "packs" / "desk-website-service-20260902-01" / "manifest.json"
FACTORY_ID = "cursor-business-pack-rating-slot-20260902-01"
RECEIPT_ID = "cursor-pack-harborline-rating-20260902-01"
UNPIN_ID = "cursor-pack-harborline-rating-peer-unpin-20260902-01"
TEMPLATE_BLOB = "7d644a8b"
SHEET_BLOB = "7fe8667a"
LEFTOVER_RECEIPT_BLOB = "29930d8b"
WAITLIST_SLOT_BLOB = "ea108145"
OBSERVED_AT_LAND = {
    "packs/desk-website-service-20260902-01/door.html": "KEEP MAIN d3d6fcc7",
    "host/business_pack_harborline_tally_map.py": "KEEP MAIN 2fbc987b",
    "host/business_pack_harborline_tally_map_pointer.py": "KEEP MAIN 1eb80c83",
    "host/business_pack_harborline_map_helper_pointer.py": "KEEP MAIN df4f81b3",
    "packs/sidewalk-signal-web-desk-20260902-01/rating.md": "absent",
    "packs/lotribbon-greetings-20260902-01/rating.md": "absent",
}
DOOR_BLOB = "cd2be48f"
SIDECAR_BLOB = "a87636bd"
MAP_POINTER_BLOB = "c8b02d6f"
MAP_HELPER_POINTER_BLOB = "1e40006d"
PACK_MAP_BLOB = "a7a49b77"
PIN_LIFT_RECEIPT_BLOB = "8fe8a002"
POINTER_RECEIPT_BLOB = "7a8987b5"
SLOT_RE = {
    "badge_url": re.compile(r"(?im)^Badge URL:\s*`?([^`\n]+)`?"),
    "report_url": re.compile(r"(?im)^Report URL:\s*`?([^`\n]+)`?"),
    "partner_name": re.compile(r"(?im)^Partner name:\s*`?([^`\n]+)`?"),
    "bulk_price": re.compile(r"(?im)^Bulk price:\s*`?([^`\n]+)`?"),
    "owner_pasted": re.compile(r"(?im)^Owner pasted:\s*`?([^`\n]+)`?"),
}
STRIPE_FAKE_RE = re.compile(r"(?i)https?://(?:buy|donate)\.stripe\.com/")
DO_NOT_OVERWRITE = (
    "packs/_template/rating.md",
    "packs/_template/README.md",
    "host/business_pack_rating.py",
    "ground/BUSINESS_PACK_RATING.json",
    "p/cursor-business-pack-rating-slot-20260902-01.md",
    "p/cursor-pack-harborline-rating-20260902-01.md",
    "packs/desk-website-service-20260902-01/rating.md",
    "packs/desk-website-service-20260902-01/door.html",
    "packs/desk-website-service-20260902-01/waitlist-slot.md",
    "packs/desk-website-service-20260902-01/manifest.json",
    "host/pack_harborline_waitlist_slot.py",
    "p/cursor-pack-harborline-waitlist-slot-20260902-01.md",
    "p/cursor-pack-harborline-waitlist-slot-peer-unpin-20260902-01.md",
    "host/harborline_tally_pack_map.py",
    "host/business_pack_harborline_tally_map.py",
    "host/business_pack_harborline_tally_map_pointer.py",
    "host/business_pack_harborline_map_helper_pointer.py",
    "p/cursor-pack-harborline-map-pin-lift-20260902-01.md",
    "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md",
    "host/business_pack_desk_instance.py",
    "packs/waitlist.html",
    "packs/thanks.html",
    "packs/sidewalk-signal-web-desk-20260902-01",
    "packs/lotribbon-greetings-20260902-01",
    "packs/curbline-weekend-yard-help-20260902-01",
    "ground/BUSINESS_PACKS.json",
)


def git_blob_prefix(rel: str, n: int = 8, *, root: Path | None = None) -> str:
    path = (ROOT if root is None else root) / rel
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()[:n]


def parse_slots(text: str) -> dict[str, Any]:
    body = text or ""
    slots: dict[str, Any] = {}
    for key, pattern in SLOT_RE.items():
        match = pattern.search(body)
        slots[key] = (match.group(1).strip() if match else "")
    pasted = str(slots.get("owner_pasted") or "").strip().lower()
    return {
        "badge_url": slots.get("badge_url") or "",
        "report_url": slots.get("report_url") or "",
        "partner_name": slots.get("partner_name") or "",
        "bulk_price": slots.get("bulk_price") or "",
        "owner_pasted_rating": pasted in {"yes", "true", "1"},
        "copy": body,
    }


def classify_path(path: Path, *, law_path: Path | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {
            "kind": "HARBORLINE_RATING",
            "gate": False,
            "commons_admission": False,
            "verdict": "HARBORLINE_RATING_MISSING",
            "path": str(path),
            "sends": 0,
            "checkout": "NOT_MINTED",
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
        }
    text = path.read_text(encoding="utf-8")
    slots = parse_slots(text)
    # Factory ads_copy is offer copy. Do not score the law reminder that names
    # banned phrases ("Independently audited", "dollar valuation").
    factory_out = factory.classify_rating(
        {
            "badge_url": slots["badge_url"],
            "report_url": slots["report_url"],
            "partner_name": slots["partner_name"],
            "bulk_price": slots["bulk_price"],
            "owner_pasted_rating": slots["owner_pasted_rating"],
            "copy": "",
        },
        law_path=law_path,
    )
    invented_stripe = bool(STRIPE_FAKE_RE.search(text))
    named = "Harborline Local Sites" in text
    factory_cited = FACTORY_ID in text
    checkout_empty = "NOT_MINTED" in text
    problems: list[str] = []
    if factory_out.get("verdict") != "RATING_SLOT_EMPTY":
        problems.append("factory_verdict")
    if not named:
        problems.append("brand")
    if not factory_cited:
        problems.append("factory_id")
    if not checkout_empty:
        problems.append("checkout")
    if invented_stripe:
        problems.append("stripe")
    if factory_out.get("filled"):
        problems.append("invented_fill")
    verdict = "HARBORLINE_RATING_INSTANCE_OK" if not problems else "HARBORLINE_RATING_INCOMPLETE"
    if factory_out.get("verdict") in {
        "RATING_EARNINGS_CLAIM",
        "EARNINGS_IN_ADS",
        "RATING_LINK_INVENTED",
        "RATING_CLAIM_UNSUBSTANTIATED",
    }:
        verdict = str(factory_out.get("verdict") or verdict)
    return {
        "kind": "HARBORLINE_RATING",
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "path": str(path),
        "factory_verdict": factory_out.get("verdict"),
        "factory_id": FACTORY_ID,
        "slots": {
            "badge_url": slots["badge_url"],
            "report_url": slots["report_url"],
            "partner_name": slots["partner_name"],
            "bulk_price": slots["bulk_price"],
            "owner_pasted_rating": slots["owner_pasted_rating"],
        },
        "empty": factory_out.get("empty") is True,
        "named_harborline": named,
        "problems": problems,
        "sends": 0,
        "agents_spend_ads": False,
        "agents_pick_partner": False,
        "agents_invent_bulk_price": False,
        "checkout": "NOT_MINTED",
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "receipt_id": RECEIPT_ID,
    }


def classify_tree(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    law_path = None if root is None else base / "ground" / "BUSINESS_PACK_RATING.json"
    manifest = MANIFEST if root is None else base / "packs" / "desk-website-service-20260902-01" / "manifest.json"

    def blob(rel: str) -> str:
        # Preserve the existing default hook while keeping selected roots local.
        if root is None:
            return git_blob_prefix(rel)
        return git_blob_prefix(rel, root=base)

    harborline = classify_path(
        base / "packs" / "desk-website-service-20260902-01" / "rating.md",
        law_path=law_path,
    )
    template_blob = blob("packs/_template/rating.md")
    door_blob = blob("packs/desk-website-service-20260902-01/door.html")
    sidecar_blob = blob("host/business_pack_harborline_tally_map.py")
    map_pointer_blob = blob("host/business_pack_harborline_tally_map_pointer.py")
    map_helper_pointer_blob = blob(
        "host/business_pack_harborline_map_helper_pointer.py"
    )
    pack_map_blob = blob("host/harborline_tally_pack_map.py")
    pin_lift_receipt = blob("p/cursor-pack-harborline-map-pin-lift-20260902-01.md")
    pointer_receipt = blob(
        "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md"
    )
    sheet_blob = blob("packs/desk-website-service-20260902-01/rating.md")
    leftover_receipt = blob("p/cursor-pack-harborline-rating-20260902-01.md")
    waitlist_slot_blob = blob(
        "packs/desk-website-service-20260902-01/waitlist-slot.md"
    )
    law = factory.load_law(law_path)
    ok = (
        harborline.get("verdict") == "HARBORLINE_RATING_INSTANCE_OK"
        and str(law.get("id") or "") == FACTORY_ID
        and template_blob == TEMPLATE_BLOB
        and pack_map_blob == PACK_MAP_BLOB
        and pin_lift_receipt == PIN_LIFT_RECEIPT_BLOB
        and pointer_receipt == POINTER_RECEIPT_BLOB
        and sheet_blob == SHEET_BLOB
        and leftover_receipt == LEFTOVER_RECEIPT_BLOB
        and waitlist_slot_blob == WAITLIST_SLOT_BLOB
        and not manifest.is_file()
    )
    return {
        "kind": "HARBORLINE_RATING",
        "gate": False,
        "commons_admission": False,
        "verdict": "HARBORLINE_RATING_OK" if ok else "HARBORLINE_RATING_INCOMPLETE",
        "harborline": harborline,
        "factory_id": str(law.get("id") or ""),
        "blobs": {
            "packs/_template/rating.md": template_blob,
            "packs/desk-website-service-20260902-01/door.html": door_blob,
            "packs/desk-website-service-20260902-01/rating.md": sheet_blob,
            "packs/desk-website-service-20260902-01/waitlist-slot.md": waitlist_slot_blob,
            "p/cursor-pack-harborline-rating-20260902-01.md": leftover_receipt,
            "host/business_pack_harborline_tally_map.py": sidecar_blob,
            "host/business_pack_harborline_tally_map_pointer.py": map_pointer_blob,
            "host/business_pack_harborline_map_helper_pointer.py": map_helper_pointer_blob,
            "host/harborline_tally_pack_map.py": pack_map_blob,
            "p/cursor-pack-harborline-map-pin-lift-20260902-01.md": pin_lift_receipt,
            "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md": pointer_receipt,
        },
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "live_peer_rating_slots_not_pinned": True,
        "live_harborline_door_not_pinned": True,
        "live_pin_helpers_not_pinned": True,
        "did_not_rewrite_goat_template": template_blob == TEMPLATE_BLOB,
        "did_not_remint_factory_slot": str(law.get("id") or "") == FACTORY_ID,
        "did_not_overwrite_harborline_door": True,
        "did_not_overwrite_harborline_rating": sheet_blob == SHEET_BLOB,
        "did_not_overwrite_harborline_waitlist_slot": waitlist_slot_blob == WAITLIST_SLOT_BLOB,
        "did_not_write_leftover_pin_helpers": True,
        "did_not_overwrite_pointer_receipt": pointer_receipt == POINTER_RECEIPT_BLOB,
        "did_not_write_peer_rating_slots": True,
        "did_not_invent_harborline_manifest": not manifest.is_file(),
        "did_not_merge_7915": True,
        "sends": 0,
        "agents_spend_ads": False,
        "checkout": "NOT_MINTED",
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "receipt_id": RECEIPT_ID,
        "unpin_id": UNPIN_ID,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="classify")
    parser.add_argument("--file", default="")
    args = parser.parse_args(argv)
    if args.file:
        print(json.dumps(classify_path(Path(args.file)), indent=2))
        return 0
    print(json.dumps(classify_tree(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
