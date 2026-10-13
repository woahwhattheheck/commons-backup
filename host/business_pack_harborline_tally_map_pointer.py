#!/usr/bin/env python3
"""Classify the Harborline-TALLY pack-map catalog pointer. Not a Commons gate.

Peer receipt cursor-business-pack-harborline-tally-map-pointer-20260902-01
is already on current main. This leftover only reads. It does not remint
that pointer, the instance catalog, the sidewalk-LotRibbon waitlist
pointer, or waitlist ids. It does not overwrite the map helper,
Harborline door, waitlist, TALLY helper, or LotRibbon/Sidewalk doors.
Live TALLY/LEAD instance blobs are not pinned so owners can land sold-once.
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
POINTER_ID = "cursor-business-pack-harborline-tally-map-pointer-20260902-01"
HELPER_ID = "cursor-business-pack-harborline-tally-map-pointer-helper-20260902-01"
WAITLIST_POINTER_ID = "cursor-business-pack-waitlist-pointer-20260902-01"
SIDEWALK_LOTRIBBON_POINTER_ID = (
    "cursor-business-pack-sidewalk-lotribbon-waitlist-pointer-20260902-01"
)
MAP_HELPER = "host/harborline_tally_pack_map.py"
MAP_RECEIPT = "cursor-harborline-tally-pack-map-20260902-01"
MAP_OWNER = "bc-31c8ef9a"
# Historical byte observations. Mutable pages and helpers may evolve independently
# of the catalog pointer. Canonical receipt continuity is checked separately.
EXPECTED_BLOBS = {
    "host/harborline_tally_pack_map.py": "a7a49b77",
    "packs/desk-website-service-20260902-01/door.html": "cd2be48f",
    "packs/waitlist.html": "b312ed6d",
}
RECEIPT_BLOBS = {
    f"p/{POINTER_ID}.md": "e38f1251",
    f"p/{MAP_RECEIPT}.md": "d3e7312c",
}

# Land-time observations from leftover SHIP 4b1e74dd / a692e5ca. Not live pins.
OBSERVED_AT_LAND = {
    "host/business_pack_desk_instance.py": "a550ae1b",
    "packs/sidewalk-signal-web-desk-20260902-01/index.html": "638e60b4",
    "packs/lotribbon-greetings-20260902-01/index.html": "ac60db02",
}
THIS_SEAT_DOES_NOT_WRITE = (
    "host/business_pack_desk_instance.py",
    "packs/sidewalk-signal-web-desk-20260902-01/index.html",
    "packs/lotribbon-greetings-20260902-01/index.html",
)


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def instances_block(law: dict[str, Any]) -> dict[str, Any]:
    block = law.get("instances")
    return block if isinstance(block, dict) else {}


def waitlist_block(law: dict[str, Any]) -> dict[str, Any]:
    block = law.get("waitlist")
    return block if isinstance(block, dict) else {}


def harborline_row(block: dict[str, Any]) -> dict[str, Any]:
    landed = block.get("landed")
    if not isinstance(landed, list):
        return {}
    for item in landed:
        if isinstance(item, dict) and item.get("brand") == "Harborline Local Sites":
            return item
    return {}


def blob_prefix(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()[:8]


def classify_pointer(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    block = instances_block(data)
    waitlist = waitlist_block(data)
    row = harborline_row(block)
    blobs = {rel: blob_prefix(rel) for rel in dict.fromkeys((*EXPECTED_BLOBS, *OBSERVED_AT_LAND, *RECEIPT_BLOBS))}
    blobs_match = all(
        blobs.get(rel, "").startswith(prefix) for rel, prefix in EXPECTED_BLOBS.items()
    )
    missing_files = [rel for rel, prefix in blobs.items() if not prefix]
    receipt_blobs_match = all(
        blobs.get(rel, "") == prefix for rel, prefix in RECEIPT_BLOBS.items()
    )
    pointer_ok = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(block.get("id") or "") == CATALOG_ID
        and str(block.get("harborline_tally_pack_map_pointer") or "") == POINTER_ID
        and str(block.get("catalog_waitlist_rows_pointer") or "")
        == SIDEWALK_LOTRIBBON_POINTER_ID
        and str(waitlist.get("id") or "") == WAITLIST_POINTER_ID
        and str(row.get("tally_pack_map") or "") == MAP_HELPER
        and str(row.get("tally_pack_map_receipt") or "") == MAP_RECEIPT
        and str(row.get("tally_pack_map_owner") or "") == MAP_OWNER
        and block.get("did_not_overwrite_harborline_tally_pack_map") is True
        and block.get("did_not_overwrite_sidewalk_door") is True
        and block.get("did_not_overwrite_lotribbon_door") is True
        and block.get("did_not_overwrite_waitlist_html") is True
        and str(block.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and data.get("commons_admission") is False
        and not missing_files
        and receipt_blobs_match
        and (ROOT / MAP_HELPER).is_file()
        and (ROOT / "p" / f"{POINTER_ID}.md").is_file()
        and (ROOT / "p" / f"{MAP_RECEIPT}.md").is_file()
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": HELPER_ID,
        "pointer_id": POINTER_ID,
        "did_not_remint_pointer": True,
        "unique_pack_id": str(data.get("id") or ""),
        "catalog_id": str(block.get("id") or ""),
        "waitlist_pointer_id": str(waitlist.get("id") or ""),
        "sidewalk_lotribbon_pointer_id": str(
            block.get("catalog_waitlist_rows_pointer") or ""
        ),
        "map_helper": MAP_HELPER,
        "map_receipt": MAP_RECEIPT,
        "map_owner": str(row.get("tally_pack_map_owner") or ""),
        "checkout": str(block.get("checkout") or ""),
        "did_not_overwrite_map_helper": block.get(
            "did_not_overwrite_harborline_tally_pack_map"
        )
        is True,
        "did_not_overwrite_harborline_door": True,
        "did_not_overwrite_waitlist": block.get("did_not_overwrite_waitlist_html")
        is True,
        "did_not_overwrite_tally_helper": True,
        "did_not_overwrite_lotribbon_door": block.get("did_not_overwrite_lotribbon_door")
        is True,
        "did_not_overwrite_sidewalk_door": block.get("did_not_overwrite_sidewalk_door")
        is True,
        "this_seat_does_not_write": list(THIS_SEAT_DOES_NOT_WRITE),
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "live_instance_blobs_not_pinned": True,
        "blobs": blobs,
        "blobs_match": blobs_match,
        "receipt_blobs_match": receipt_blobs_match,
        "missing_files": missing_files,
        "pointer_ok": pointer_ok,
        "agents_spend_ads": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--law", default="", help="override unique-pack law path")
    args = parser.parse_args(argv)
    law = load_law(Path(args.law) if args.law else None)
    print(json.dumps(classify_pointer(law), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
