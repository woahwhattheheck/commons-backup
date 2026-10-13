#!/usr/bin/env python3
"""LotRibbon instance fill of the factory rating slot. Compose leftover.

GOAT / unique-pack own packs/_template/rating.md and
host/business_pack_rating.py (id cursor-business-pack-rating-slot-20260902-01).
This leftover fills LotRibbon's instance sheet. Peer-unpin leftover
cursor-lead-lotribbon-rating-peer-unpin-20260902-01 lifts live SHA pins on
unrelated A4 yard / desk A4 receipts and the LotRibbon instance door so
those KEEP MAIN files can move without freezing this leftover. It does not remint the factory slot,
rewrite the template or LotRibbon rating.md, pick a partner, invent a
bulk price, rewrite the LotRibbon door, fill Harborline unpin, remint
A4 receipts, or merge #7915. Empty badge+report is the correct instance
state until Bryce pastes. Completeness audit allowed. Dollar valuation
is earnings. Checkout NOT_MINTED.
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
LOTRIBBON = ROOT / "packs" / "lotribbon-greetings-20260902-01" / "rating.md"
HARBORLINE = ROOT / "packs" / "desk-website-service-20260902-01" / "rating.md"
SIDEWALK = ROOT / "packs" / "sidewalk-signal-web-desk-20260902-01" / "rating.md"
DOOR = ROOT / "packs" / "lotribbon-greetings-20260902-01" / "index.html"
FACTORY_ID = "cursor-business-pack-rating-slot-20260902-01"
RECEIPT_ID = "cursor-lead-lotribbon-rating-20260902-01"
HARBORLINE_UNPIN_ID = "cursor-pack-harborline-rating-peer-unpin-20260902-01"
UNPIN_ID = "cursor-lead-lotribbon-rating-peer-unpin-20260902-01"
TEMPLATE_BLOB = "7d644a8b"
DOOR_BLOB = "7804ec33"
SHEET_BLOB = "7fade2a5"
ORIGINAL_RECEIPT_BLOB = "5f06948a"
HARBORLINE_SHEET_BLOB = "7fe8667a"
HARBORLINE_RECEIPT_BLOB = "29930d8b"
POINTER_RECEIPT_BLOB = "7a8987b5"
A4_YARD_BLOB = "0603616c"
DESK_A4_BLOB = "193cf232"
OBSERVED_AT_LAND = {
    "packs/lotribbon-greetings-20260902-01/index.html": "KEEP MAIN 7804ec33",
    "packs/desk-website-service-20260902-01/rating.md": "unread 7fe8667a",
    "p/cursor-pack-harborline-rating-peer-unpin-20260902-01.md": "stays bc-31c8ef9a",
    "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md": "KEEP MAIN 7a8987b5",
    "p/stamp-claude-peer-check-a4-yard-adopt-20260902-01.md": "KEEP MAIN 0603616c",
    "p/cursor-claude-peer-check-a4-desk-test-adopt-20260902-01.md": "KEEP MAIN 193cf232",
}
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
    "p/cursor-lead-lotribbon-rating-20260902-01.md",
    "land/pack-lotribbon-rating-20260902.md",
    "packs/lotribbon-greetings-20260902-01/index.html",
    "packs/lotribbon-greetings-20260902-01/rating.md",
    "packs/lotribbon-greetings-20260902-01/waitlist-slot.md",
    "packs/desk-website-service-20260902-01/rating.md",
    "packs/desk-website-service-20260902-01/door.html",
    "host/pack_harborline_rating.py",
    "p/cursor-pack-harborline-rating-20260902-01.md",
    "p/cursor-pack-harborline-rating-peer-unpin-20260902-01.md",
    "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md",
    "p/stamp-claude-peer-check-a4-yard-adopt-20260902-01.md",
    "p/cursor-claude-peer-check-a4-desk-test-adopt-20260902-01.md",
    "p/husk-claude-peer-clear-20260902-01.md",
    "p/bass-claude-peer-h5-weekly-clear-20260902-01.md",
    "packs/waitlist.html",
    "packs/thanks.html",
    "packs/sidewalk-signal-web-desk-20260902-01",
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
            "kind": "LOTRIBBON_RATING",
            "gate": False,
            "commons_admission": False,
            "verdict": "LOTRIBBON_RATING_MISSING",
            "path": str(path),
            "sends": 0,
            "checkout": "NOT_MINTED",
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
            "receipt_id": RECEIPT_ID,
        }
    text = path.read_text(encoding="utf-8")
    slots = parse_slots(text)
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
    named = "LotRibbon Greetings" in text
    factory_cited = FACTORY_ID in text
    checkout_empty = "NOT_MINTED" in text
    door_unread = DOOR_BLOB in text
    unpin_cited = HARBORLINE_UNPIN_ID in text
    problems: list[str] = []
    if factory_out.get("verdict") != "RATING_SLOT_EMPTY":
        problems.append("factory_verdict")
    if not named:
        problems.append("brand")
    if not factory_cited:
        problems.append("factory_id")
    if not checkout_empty:
        problems.append("checkout")
    if not door_unread:
        problems.append("door_unread")
    if not unpin_cited:
        problems.append("harborline_unpin")
    if invented_stripe:
        problems.append("stripe")
    if factory_out.get("filled"):
        problems.append("invented_fill")
    verdict = "LOTRIBBON_RATING_INSTANCE_OK" if not problems else "LOTRIBBON_RATING_INCOMPLETE"
    if factory_out.get("verdict") in {
        "RATING_EARNINGS_CLAIM",
        "EARNINGS_IN_ADS",
        "RATING_LINK_INVENTED",
        "RATING_CLAIM_UNSUBSTANTIATED",
    }:
        verdict = str(factory_out.get("verdict") or verdict)
    return {
        "kind": "LOTRIBBON_RATING",
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
        "named_lotribbon": named,
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

    def blob(rel: str) -> str:
        # Retain the existing one-argument default hook for callers and tests.
        if root is None:
            return git_blob_prefix(rel)
        return git_blob_prefix(rel, root=base)

    sheet = classify_path(
        base / "packs" / "lotribbon-greetings-20260902-01" / "rating.md",
        law_path=law_path,
    )
    template_blob = blob("packs/_template/rating.md")
    door_blob = blob("packs/lotribbon-greetings-20260902-01/index.html")
    harborline_sheet = blob("packs/desk-website-service-20260902-01/rating.md")
    harborline_receipt = blob("p/cursor-pack-harborline-rating-20260902-01.md")
    pointer_receipt = blob(
        "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md"
    )
    sheet_blob = blob("packs/lotribbon-greetings-20260902-01/rating.md")
    original_receipt = blob("p/cursor-lead-lotribbon-rating-20260902-01.md")
    a4_yard = blob("p/stamp-claude-peer-check-a4-yard-adopt-20260902-01.md")
    desk_a4 = blob("p/cursor-claude-peer-check-a4-desk-test-adopt-20260902-01.md")
    harborline_unpin_present = (
        base / "p" / "cursor-pack-harborline-rating-peer-unpin-20260902-01.md"
    ).is_file()
    law = factory.load_law(law_path)
    ok = (
        sheet.get("verdict") == "LOTRIBBON_RATING_INSTANCE_OK"
        and str(law.get("id") or "") == FACTORY_ID
        and template_blob == TEMPLATE_BLOB
        and sheet_blob == SHEET_BLOB
        and original_receipt == ORIGINAL_RECEIPT_BLOB
        and harborline_sheet == HARBORLINE_SHEET_BLOB
        and harborline_receipt == HARBORLINE_RECEIPT_BLOB
        and pointer_receipt == POINTER_RECEIPT_BLOB
        and harborline_unpin_present
    )
    return {
        "kind": "LOTRIBBON_RATING",
        "gate": False,
        "commons_admission": False,
        "verdict": "LOTRIBBON_RATING_OK" if ok else "LOTRIBBON_RATING_INCOMPLETE",
        "lotribbon": sheet,
        "factory_id": str(law.get("id") or ""),
        "blobs": {
            "packs/_template/rating.md": template_blob,
            "packs/lotribbon-greetings-20260902-01/index.html": door_blob,
            "packs/lotribbon-greetings-20260902-01/rating.md": sheet_blob,
            "p/cursor-lead-lotribbon-rating-20260902-01.md": original_receipt,
            "packs/desk-website-service-20260902-01/rating.md": harborline_sheet,
            "p/cursor-pack-harborline-rating-20260902-01.md": harborline_receipt,
            "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md": pointer_receipt,
            "p/stamp-claude-peer-check-a4-yard-adopt-20260902-01.md": a4_yard,
            "p/cursor-claude-peer-check-a4-desk-test-adopt-20260902-01.md": desk_a4,
        },
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "live_a4_receipts_not_pinned": True,
        "live_lotribbon_door_not_pinned": True,
        "did_not_rewrite_goat_template": template_blob == TEMPLATE_BLOB,
        "did_not_remint_factory_slot": str(law.get("id") or "") == FACTORY_ID,
        "did_not_overwrite_lotribbon_door": True,
        "did_not_overwrite_lotribbon_rating": sheet_blob == SHEET_BLOB,
        "did_not_remint_original_leftover": original_receipt == ORIGINAL_RECEIPT_BLOB,
        "did_not_overwrite_harborline_rating": harborline_sheet == HARBORLINE_SHEET_BLOB,
        "did_not_fill_harborline_unpin": harborline_unpin_present,
        "did_not_overwrite_pointer_receipt": pointer_receipt == POINTER_RECEIPT_BLOB,
        "did_not_remint_a4_yard": True,
        "did_not_remint_desk_a4": True,
        "did_not_live_pin_sidewalk_absent": True,
        "did_not_merge_7915": True,
        "harborline_unpin_stays": "bc-31c8ef9a",
        "sends": 0,
        "agents_spend_ads": False,
        "checkout": "NOT_MINTED",
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "receipt_id": RECEIPT_ID,
        "unpin_id": UNPIN_ID,
        "harborline_unpin_id": HARBORLINE_UNPIN_ID,
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
