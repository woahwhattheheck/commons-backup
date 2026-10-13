#!/usr/bin/env python3
"""LotRibbon instance fill of the factory waitlist slot. Compose leftover.

GOAT owns packs/_template/waitlist-slot.md and host/pack_waitlist.py
(id cursor-pack-door-waitlist-20260902-01). This leftover only fills
LotRibbon's instance sheet. It does not remint the factory slot, rewrite
the template, rewrite the LotRibbon door, copy waitlist.html, invent a
Stripe URL, or write Harborline / Sidewalk / yard-card sheets. Zero
sends. Addresses stay off this sheet. Checkout NOT_MINTED.
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

TEMPLATE = ROOT / "packs" / "_template" / "waitlist-slot.md"
LOTRIBBON = ROOT / "packs" / "lotribbon-greetings-20260902-01" / "waitlist-slot.md"
HARBORLINE = ROOT / "packs" / "desk-website-service-20260902-01" / "waitlist-slot.md"
SIDEWALK = ROOT / "packs" / "sidewalk-signal-web-desk-20260902-01" / "waitlist-slot.md"
WAITLIST_HTML = ROOT / "packs" / "waitlist.html"
DOOR = ROOT / "packs" / "lotribbon-greetings-20260902-01" / "index.html"
FACTORY_ID = "cursor-pack-door-waitlist-20260902-01"
RECEIPT_ID = "cursor-lead-lotribbon-waitlist-slot-20260902-01"
TEMPLATE_BLOB = "50602561"
WAITLIST_HTML_BLOB = "b312ed6d"
DOOR_BLOB = "4372916d"
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
STRIPE_FAKE_RE = re.compile(r"(?i)https?://(?:buy|donate)\.stripe\.com/")
DO_NOT_OVERWRITE = (
    "packs/_template/waitlist-slot.md",
    "packs/_template/README.md",
    "host/pack_waitlist.py",
    "host/business_pack_sidewalk_lotribbon_waitlist.py",
    "host/business_pack_instance_waitlist.py",
    "p/cursor-pack-door-waitlist-20260902-01.md",
    "packs/waitlist.html",
    "packs/thanks.html",
    "packs/lotribbon-greetings-20260902-01/index.html",
    "packs/desk-website-service-20260902-01/door.html",
    "packs/desk-website-service-20260902-01/waitlist-slot.md",
    "packs/desk-website-service-20260902-01/rating.md",
    "p/cursor-pack-harborline-waitlist-slot-20260902-01.md",
    "p/cursor-pack-harborline-rating-20260902-01.md",
    "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md",
    "packs/sidewalk-signal-web-desk-20260902-01",
    "packs/curbline-weekend-yard-help-20260902-01",
    "ground/BUSINESS_PACKS.json",
)


def git_blob_prefix(rel: str, n: int = 8, *, root: Path | None = None) -> str:
    """Hash within the selected checkout, defaulting to the module checkout."""
    base = ROOT if root is None else root
    path = base / rel
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()[:n]


def classify_path(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "kind": "LOTRIBBON_WAITLIST_SLOT",
            "gate": False,
            "commons_admission": False,
            "verdict": "LOTRIBBON_WAITLIST_SLOT_MISSING",
            "path": str(path),
            "sends": 0,
            "checkout": "NOT_MINTED",
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
            "receipt_id": RECEIPT_ID,
        }
    text = path.read_text(encoding="utf-8")
    invented_stripe = bool(STRIPE_FAKE_RE.search(text))
    leaked_email = bool(EMAIL_RE.search(text))
    named = "LotRibbon Greetings" in text
    factory_cited = FACTORY_ID in text
    pointer = "packs/waitlist.html" in text
    checkout_empty = "NOT_MINTED" in text
    zero_sends = "Zero sends" in text or "zero sends" in text
    door_unread = "7804ec33" in text
    problems: list[str] = []
    if not named:
        problems.append("brand")
    if not factory_cited:
        problems.append("factory_id")
    if not pointer:
        problems.append("waitlist_pointer")
    if not checkout_empty:
        problems.append("checkout")
    if not zero_sends:
        problems.append("sends")
    if not door_unread:
        problems.append("door_unread")
    if invented_stripe:
        problems.append("stripe")
    if leaked_email:
        problems.append("address")
    verdict = "LOTRIBBON_WAITLIST_SLOT_INSTANCE_OK" if not problems else "LOTRIBBON_WAITLIST_SLOT_INCOMPLETE"
    if invented_stripe:
        verdict = "WAITLIST_LINK_INVENTED"
    elif leaked_email:
        verdict = "WAITLIST_ADDRESS_LEAKED"
    return {
        "kind": "LOTRIBBON_WAITLIST_SLOT",
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "path": str(path),
        "factory_id": FACTORY_ID,
        "named_lotribbon": named,
        "problems": problems,
        "empty_public_addresses": not leaked_email,
        "sends": 0,
        "agents_spend_ads": False,
        "agents_invent_stripe": False,
        "checkout": "NOT_MINTED",
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "receipt_id": RECEIPT_ID,
    }


def classify_tree(root: Path | None = None) -> dict[str, Any]:
    base = ROOT if root is None else root
    sheet = classify_path(base / "packs" / "lotribbon-greetings-20260902-01" / "waitlist-slot.md")
    template_blob = git_blob_prefix("packs/_template/waitlist-slot.md", root=base)
    waitlist_blob = git_blob_prefix("packs/waitlist.html", root=base)
    door_blob = git_blob_prefix("packs/lotribbon-greetings-20260902-01/index.html", root=base)
    harborline_present = (base / "packs" / "desk-website-service-20260902-01" / "waitlist-slot.md").is_file()
    sidewalk_present = (base / "packs" / "sidewalk-signal-web-desk-20260902-01" / "waitlist-slot.md").is_file()
    ok = (
        sheet.get("verdict") == "LOTRIBBON_WAITLIST_SLOT_INSTANCE_OK"
        and template_blob == TEMPLATE_BLOB
        and waitlist_blob == WAITLIST_HTML_BLOB
        and door_blob == DOOR_BLOB
    )
    return {
        "kind": "LOTRIBBON_WAITLIST_SLOT",
        "gate": False,
        "commons_admission": False,
        "verdict": "LOTRIBBON_WAITLIST_SLOT_OK" if ok else "LOTRIBBON_WAITLIST_SLOT_INCOMPLETE",
        "lotribbon": sheet,
        "factory_id": FACTORY_ID,
        "blobs": {
            "packs/_template/waitlist-slot.md": template_blob,
            "packs/waitlist.html": waitlist_blob,
            "packs/lotribbon-greetings-20260902-01/index.html": door_blob,
        },
        "did_not_rewrite_goat_template": template_blob == TEMPLATE_BLOB,
        "did_not_remint_factory_slot": True,
        "did_not_overwrite_waitlist_html": waitlist_blob == WAITLIST_HTML_BLOB,
        "did_not_overwrite_lotribbon_door": door_blob == DOOR_BLOB,
        "did_not_write_harborline_slot": True,
        "harborline_slot_present": harborline_present,
        "sidewalk_slot_present": sidewalk_present,
        "did_not_merge_7915": True,
        "sends": 0,
        "agents_spend_ads": False,
        "checkout": "NOT_MINTED",
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "receipt_id": RECEIPT_ID,
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
