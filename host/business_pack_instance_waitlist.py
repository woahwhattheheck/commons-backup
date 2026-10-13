#!/usr/bin/env python3
"""Classify catalog waitlist rows without writing instance doors.

This helper only reads. It does not overwrite instance doors,
packs/waitlist.html, or TALLY's desk helper. Live instance blobs are
not pinned so owners can land sold-once and other door edits. Not a
Commons gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACKS.json"
UNIQUE_PACK_ID = "cursor-business-packs-unique-20260902-01"
CATALOG_ID = "cursor-business-pack-instance-catalog-20260902-01"
POINTER_ID = "cursor-business-pack-sidewalk-lotribbon-waitlist-pointer-20260902-01"
SHARED_WAITLIST = "packs/waitlist.html"
# Land-time observations from catalog pointer SHIP e9c5e8aa / receipt 2c584983.
# Not live pins: instance owners may change their doors and TALLY helper.
OBSERVED_AT_LAND = {
    "packs/sidewalk-signal-web-desk-20260902-01/index.html": "638e60b4",
    "packs/lotribbon-greetings-20260902-01/index.html": "ac60db02",
    "packs/desk-website-service-20260902-01/door.html": "cd2be48f",
    "host/business_pack_desk_instance.py": "a550ae1b",
}
# Historical byte observations; live pages/helpers may evolve independently.
EXPECTED_BLOBS = {
    "packs/waitlist.html": "b312ed6d",
}
RECEIPT_BLOBS = {f"p/{POINTER_ID}.md": "2c584983"}

THIS_SEAT_DOES_NOT_WRITE = (
    "packs/sidewalk-signal-web-desk-20260902-01/index.html",
    "packs/lotribbon-greetings-20260902-01/index.html",
    "packs/desk-website-service-20260902-01/door.html",
    "host/business_pack_desk_instance.py",
    "packs/waitlist.html",
)
WAITLIST_ON_INSTANCE_DOOR = "WAITLIST_ON_INSTANCE_DOOR"
WAITLIST_CATALOG_POINTER = "WAITLIST_CATALOG_POINTER"
WAITLIST_MISSING = "WAITLIST_MISSING"
WAITLIST_DOOR_MISSING = "WAITLIST_DOOR_MISSING"


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def instances_block(law: dict[str, Any]) -> dict[str, Any]:
    block = law.get("instances")
    return block if isinstance(block, dict) else {}


def door_has_waitlist_href(html: str) -> bool:
    return "waitlist.html" in html.lower()


def blob_prefix(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()[:8]


def classify_row(row: dict[str, Any], html: str | None) -> str:
    waitlist = str(row.get("waitlist") or "").strip()
    if html is None:
        return WAITLIST_DOOR_MISSING
    on_door = door_has_waitlist_href(html)
    if waitlist == SHARED_WAITLIST and on_door:
        return WAITLIST_ON_INSTANCE_DOOR
    if waitlist == SHARED_WAITLIST and not on_door:
        return WAITLIST_CATALOG_POINTER
    return WAITLIST_MISSING


def classify_catalog(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    block = instances_block(data)
    landed = block.get("landed")
    rows_out = []
    if isinstance(landed, list):
        for item in landed:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("door") or "")
            path = ROOT / rel if rel else None
            html = path.read_text(encoding="utf-8") if path and path.is_file() else None
            rows_out.append(
                {
                    "brand": str(item.get("brand") or ""),
                    "door": rel,
                    "waitlist": str(item.get("waitlist") or ""),
                    "owned_by": str(item.get("owned_by") or ""),
                    "verdict": classify_row(item, html),
                    "door_blob": blob_prefix(rel) if rel else "",
                }
            )
    blobs = {rel: blob_prefix(rel) for rel in dict.fromkeys((*EXPECTED_BLOBS, *OBSERVED_AT_LAND, *RECEIPT_BLOBS))}
    waitlist_blob_ok = all(
        blobs.get(rel, "").startswith(prefix) for rel, prefix in EXPECTED_BLOBS.items()
    )
    verdicts = {row["brand"]: row["verdict"] for row in rows_out}
    catalog_waitlist_ok = {
        WAITLIST_CATALOG_POINTER,
        WAITLIST_ON_INSTANCE_DOOR,
    }
    missing_files = [rel for rel, prefix in blobs.items() if not prefix]
    receipt_blobs_match = all(
        blobs.get(rel, "") == prefix for rel, prefix in RECEIPT_BLOBS.items()
    )
    pointer_ok = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(block.get("id") or "") == CATALOG_ID
        and str(block.get("catalog_waitlist_rows_pointer") or "") == POINTER_ID
        and block.get("did_not_steal_instance_files") is True
        and block.get("did_not_overwrite_sidewalk_door") is True
        and block.get("did_not_overwrite_lotribbon_door") is True
        and block.get("did_not_overwrite_waitlist_html") is True
        and str(block.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and data.get("commons_admission") is False
        and verdicts.get("LotRibbon Greetings") in catalog_waitlist_ok
        and verdicts.get("Sidewalk Signal") in catalog_waitlist_ok
        and verdicts.get("Harborline Local Sites") == WAITLIST_ON_INSTANCE_DOOR
        and not missing_files
        and receipt_blobs_match
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": POINTER_ID,
        "unique_pack_id": str(data.get("id") or ""),
        "catalog_id": str(block.get("id") or ""),
        "shared_waitlist": SHARED_WAITLIST,
        "checkout": str(block.get("checkout") or ""),
        "did_not_overwrite_sidewalk_door": block.get("did_not_overwrite_sidewalk_door") is True,
        "did_not_overwrite_lotribbon_door": block.get("did_not_overwrite_lotribbon_door") is True,
        "did_not_overwrite_waitlist_html": block.get("did_not_overwrite_waitlist_html") is True,
        "did_not_steal_instance_files": block.get("did_not_steal_instance_files") is True,
        "did_not_steal_desk_helper": block.get("did_not_steal_desk_helper") is True,
        "this_seat_does_not_write": list(THIS_SEAT_DOES_NOT_WRITE),
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "live_instance_blobs_not_pinned": True,
        "blobs": blobs,
        "waitlist_blob_ok": waitlist_blob_ok,
        "rows": rows_out,
        "receipt_blobs_match": receipt_blobs_match,
        "missing_files": missing_files,
        "pointer_ok": pointer_ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--law", default="", help="override unique-pack law path")
    args = parser.parse_args(argv)
    law = load_law(Path(args.law) if args.law else None)
    print(json.dumps(classify_catalog(law), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
