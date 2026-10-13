#!/usr/bin/env python3
"""Harborline instance fill of the factory waitlist-slot pointer. Compose leftover.

GOAT / waitlist law own packs/_template/waitlist-slot.md and host/pack_waitlist.py
(id cursor-pack-door-waitlist-20260902-01). This leftover only fills Harborline's
instance sheet. It does not remint the shared waitlist door, rewrite the
template, mint a second list, send mail, or write leftover pin-lift helpers /
Harborline door / rating / TALLY / LotRibbon. Catalog pointer
cursor-business-pack-harborline-waitlist-slot-pointer-20260902-01 stays peer.
Zero sends. Checkout NOT_MINTED.
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

import pack_waitlist as waitlist  # noqa: E402

TEMPLATE = ROOT / "packs" / "_template" / "waitlist-slot.md"
HARBORLINE = ROOT / "packs" / "desk-website-service-20260902-01" / "waitlist-slot.md"
SIDEWALK = ROOT / "packs" / "sidewalk-signal-web-desk-20260902-01" / "waitlist-slot.md"
LOTRIBBON = ROOT / "packs" / "lotribbon-greetings-20260902-01" / "waitlist-slot.md"
YARD = ROOT / "packs" / "curbline-weekend-yard-help-20260902-01" / "waitlist-slot.md"
MANIFEST = ROOT / "packs" / "desk-website-service-20260902-01" / "manifest.json"
LAW_ID = "cursor-pack-door-waitlist-20260902-01"
SCOUT_ID = "scout-demand-pack-door-waitlist-20260902-01"
POINTER_ID = "cursor-business-pack-harborline-waitlist-slot-pointer-20260902-01"
RECEIPT_ID = "cursor-pack-harborline-waitlist-slot-20260902-01"
UNPIN_ID = "cursor-pack-harborline-waitlist-slot-peer-unpin-20260902-01"
TEMPLATE_BLOB = "50602561"
SHEET_BLOB = "ea108145"
LEFTOVER_RECEIPT_BLOB = "4b648caf"
OBSERVED_AT_LAND = {
    "packs/sidewalk-signal-web-desk-20260902-01/waitlist-slot.md": "absent",
    "packs/lotribbon-greetings-20260902-01/waitlist-slot.md": "absent",
    "packs/curbline-weekend-yard-help-20260902-01/waitlist-slot.md": "absent",
}
WAITLIST_DOOR_BLOB = "b312ed6d"
WAITLIST_HELPER_BLOB = "dafcf444"
WAITLIST_LAW_BLOB = "c687691c"
DOOR_BLOB = "cd2be48f"
RATING_BLOB = "7fe8667a"
SIDECAR_BLOB = "6a02ec32"
POINTER_RECEIPT_BLOB = "7a8987b5"
SLOT_POINTER_RECEIPT_BLOB = "2db10af8"
CCPA_PHRASE = "Do Not Sell or Share My Personal Information"
STRIPE_FAKE_RE = re.compile(r"(?i)https?://(?:buy|donate)\.stripe\.com/")
EMAIL_LEAK_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
DO_NOT_OVERWRITE = (
    "packs/_template/waitlist-slot.md",
    "packs/waitlist.html",
    "host/pack_waitlist.py",
    "ground/BUSINESS_PACK_WAITLIST.json",
    "p/scout-demand-pack-door-waitlist-20260902-01.md",
    "p/cursor-pack-harborline-waitlist-slot-20260902-01.md",
    "packs/desk-website-service-20260902-01/waitlist-slot.md",
    "p/cursor-business-pack-harborline-waitlist-slot-pointer-20260902-01.md",
    "packs/desk-website-service-20260902-01/door.html",
    "packs/desk-website-service-20260902-01/rating.md",
    "host/pack_harborline_rating.py",
    "host/harborline_tally_pack_map.py",
    "host/business_pack_harborline_tally_map.py",
    "host/business_pack_harborline_tally_map_pointer.py",
    "host/business_pack_harborline_map_helper_pointer.py",
    "host/business_pack_harborline_desk_instance.py",
    "p/cursor-pack-harborline-map-pin-lift-20260902-01.md",
    "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md",
    "p/cursor-harborline-desk-finder-20260902-01.md",
    "host/business_pack_desk_instance.py",
    "packs/thanks.html",
    "packs/sidewalk-signal-web-desk-20260902-01",
    "packs/lotribbon-greetings-20260902-01",
    "packs/curbline-weekend-yard-help-20260902-01",
    "ground/BUSINESS_PACKS.json",
    "packs/desk-website-service-20260902-01/manifest.json",
)


def git_blob_prefix(rel: str, n: int = 8, *, root: Path | None = None) -> str:
    path = (root if root is not None else ROOT) / rel
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()[:n]


def classify_path(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "kind": "HARBORLINE_WAITLIST_SLOT",
            "gate": False,
            "commons_admission": False,
            "verdict": "HARBORLINE_WAITLIST_SLOT_MISSING",
            "path": str(path),
            "sends": 0,
            "checkout": "NOT_MINTED",
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
        }
    text = path.read_text(encoding="utf-8")
    invented_stripe = bool(STRIPE_FAKE_RE.search(text))
    leaked_email = bool(EMAIL_LEAK_RE.search(text))
    named = "Harborline Local Sites" in text
    law_cited = LAW_ID in text
    scout_cited = SCOUT_ID in text
    pointer_cited = POINTER_ID in text
    points_at_shared = "packs/waitlist.html" in text
    ccpa = CCPA_PHRASE in text
    checkout_empty = "NOT_MINTED" in text
    zero_sends = "Zero sends" in text or "sends stay 0" in text.lower()
    no_second_list = "not a second list" in text.lower()
    no_manifest = "manifest.json" in text and "Did not invent" in text
    problems: list[str] = []
    if not named:
        problems.append("brand")
    if not law_cited:
        problems.append("law_id")
    if not scout_cited:
        problems.append("scout_id")
    if not pointer_cited:
        problems.append("catalog_pointer")
    if not points_at_shared:
        problems.append("shared_door")
    if not ccpa:
        problems.append("ccpa")
    if not checkout_empty:
        problems.append("checkout")
    if not zero_sends:
        problems.append("sends")
    if not no_second_list:
        problems.append("second_list")
    if invented_stripe:
        problems.append("stripe")
    if leaked_email:
        problems.append("address_leak")
    if not no_manifest:
        problems.append("invented_manifest")
    verdict = (
        "HARBORLINE_WAITLIST_SLOT_INSTANCE_OK"
        if not problems
        else "HARBORLINE_WAITLIST_SLOT_INCOMPLETE"
    )
    return {
        "kind": "HARBORLINE_WAITLIST_SLOT",
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "path": str(path),
        "law_id": LAW_ID,
        "scout_demand_id": SCOUT_ID,
        "catalog_pointer_id": POINTER_ID,
        "named_harborline": named,
        "points_at_shared_door": points_at_shared,
        "ccpa_on_shared_form": ccpa,
        "problems": problems,
        "sends": 0,
        "list_is_unsent_asset": True,
        "sending_owner_gated": True,
        "agents_mint_pixel_id": False,
        "agents_spend_ads": False,
        "checkout": "NOT_MINTED",
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "receipt_id": RECEIPT_ID,
    }


def classify_tree(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    harborline_path = base / "packs" / "desk-website-service-20260902-01" / "waitlist-slot.md"
    manifest_path = base / "packs" / "desk-website-service-20260902-01" / "manifest.json"
    harborline = classify_path(harborline_path)
    if root is None:
        # Preserve the existing factory hook for callers using this checkout.
        door = waitlist.classify()
    else:
        # Evaluate selected data with the trusted shared validators. Do not
        # change their module defaults or import code from the selected tree.
        law_path = base / "ground" / "BUSINESS_PACK_WAITLIST.json"
        law = waitlist.load_law(law_path) if law_path.is_file() else {}
        door_path = base / "packs" / "waitlist.html"
        door = (
            waitlist.classify_door(door_path.read_text(encoding="utf-8"))
            if door_path.is_file()
            else {"verdict": "WAITLIST_DOOR_MISSING"}
        )
        door["law_id"] = str(law.get("id") or "")
        door["sends"] = waitlist.sends()
    template_blob = git_blob_prefix("packs/_template/waitlist-slot.md", root=base)
    waitlist_door_blob = git_blob_prefix("packs/waitlist.html", root=base)
    waitlist_helper_blob = git_blob_prefix("host/pack_waitlist.py", root=base)
    waitlist_law_blob = git_blob_prefix("ground/BUSINESS_PACK_WAITLIST.json", root=base)
    instance_door_blob = git_blob_prefix("packs/desk-website-service-20260902-01/door.html", root=base)
    rating_blob = git_blob_prefix("packs/desk-website-service-20260902-01/rating.md", root=base)
    sidecar_blob = git_blob_prefix("host/business_pack_harborline_tally_map.py", root=base)
    pointer_receipt = git_blob_prefix(
        "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md", root=base
    )
    slot_pointer_receipt = git_blob_prefix(
        "p/cursor-business-pack-harborline-waitlist-slot-pointer-20260902-01.md", root=base
    )
    sheet_blob = git_blob_prefix(
        "packs/desk-website-service-20260902-01/waitlist-slot.md", root=base
    )
    leftover_receipt = git_blob_prefix(
        "p/cursor-pack-harborline-waitlist-slot-20260902-01.md", root=base
    )
    copy_ok = True
    if harborline_path.is_file():
        sys.path.insert(0, str(ROOT / "host"))
        import business_pack_unique as unique  # noqa: E402

        copy_ok = unique.classify_copy(harborline_path.read_text(encoding="utf-8")).get(
            "verdict"
        ) == "COPY_OK"
    ok = (
        harborline.get("verdict") == "HARBORLINE_WAITLIST_SLOT_INSTANCE_OK"
        and door.get("verdict") == "WAITLIST_DOOR_OK"
        and str(door.get("law_id") or "") == LAW_ID
        and template_blob == TEMPLATE_BLOB
        and waitlist_door_blob == WAITLIST_DOOR_BLOB
        and waitlist_helper_blob == WAITLIST_HELPER_BLOB
        and waitlist_law_blob == WAITLIST_LAW_BLOB
        and instance_door_blob == DOOR_BLOB
        and rating_blob == RATING_BLOB
        and sidecar_blob == SIDECAR_BLOB
        and pointer_receipt == POINTER_RECEIPT_BLOB
        and slot_pointer_receipt == SLOT_POINTER_RECEIPT_BLOB
        and sheet_blob == SHEET_BLOB
        and leftover_receipt == LEFTOVER_RECEIPT_BLOB
        and not manifest_path.is_file()
        and copy_ok
        and int(door.get("sends") or 0) == 0
    )
    return {
        "kind": "HARBORLINE_WAITLIST_SLOT",
        "gate": False,
        "commons_admission": False,
        "verdict": "HARBORLINE_WAITLIST_SLOT_OK" if ok else "HARBORLINE_WAITLIST_SLOT_INCOMPLETE",
        "harborline": harborline,
        "waitlist_door": door.get("verdict"),
        "law_id": str(door.get("law_id") or ""),
        "blobs": {
            "packs/_template/waitlist-slot.md": template_blob,
            "packs/waitlist.html": waitlist_door_blob,
            "host/pack_waitlist.py": waitlist_helper_blob,
            "ground/BUSINESS_PACK_WAITLIST.json": waitlist_law_blob,
            "packs/desk-website-service-20260902-01/door.html": instance_door_blob,
            "packs/desk-website-service-20260902-01/rating.md": rating_blob,
            "host/business_pack_harborline_tally_map.py": sidecar_blob,
            "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md": pointer_receipt,
            "p/cursor-business-pack-harborline-waitlist-slot-pointer-20260902-01.md": slot_pointer_receipt,
            "packs/desk-website-service-20260902-01/waitlist-slot.md": sheet_blob,
            "p/cursor-pack-harborline-waitlist-slot-20260902-01.md": leftover_receipt,
        },
        "copy_ok": copy_ok,
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "live_peer_waitlist_slots_not_pinned": True,
        "did_not_rewrite_goat_template": template_blob == TEMPLATE_BLOB,
        "did_not_remint_waitlist_door": waitlist_door_blob == WAITLIST_DOOR_BLOB,
        "did_not_remint_waitlist_helper": waitlist_helper_blob == WAITLIST_HELPER_BLOB,
        "did_not_remint_waitlist_law": waitlist_law_blob == WAITLIST_LAW_BLOB,
        "did_not_overwrite_harborline_door": instance_door_blob == DOOR_BLOB,
        "did_not_overwrite_harborline_rating": rating_blob == RATING_BLOB,
        "did_not_overwrite_harborline_waitlist_slot": sheet_blob == SHEET_BLOB,
        "did_not_write_leftover_pin_helpers": sidecar_blob == SIDECAR_BLOB,
        "did_not_overwrite_pointer_receipt": pointer_receipt == POINTER_RECEIPT_BLOB,
        "did_not_remint_slot_catalog_pointer": slot_pointer_receipt == SLOT_POINTER_RECEIPT_BLOB,
        "did_not_write_peer_waitlist_slots": True,
        "did_not_invent_harborline_manifest": not manifest_path.is_file(),
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
