#!/usr/bin/env python3
"""Sidecar leftover for the landed Harborline tally-pack map pointer.

Peer CLAIM cursor-business-pack-harborline-tally-map-pointer-20260902-01
and leftover host/business_pack_harborline_tally_map_pointer.py are already
on current main. This leftover only reads. It does not remint those ids,
overwrite the map helper, Harborline door, waitlist, TALLY helper, or
LotRibbon/Sidewalk doors. Live TALLY/LEAD instance blobs are not pinned
so owners can land sold-once. Checkout stays NOT_MINTED. Not a Commons gate.
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
PEER_HELPER_ID = "cursor-business-pack-harborline-tally-map-pointer-helper-20260902-01"
HELPER_ID = "cursor-business-pack-harborline-tally-map-helper-20260902-01"
MAP_RECEIPT = "cursor-harborline-tally-pack-map-20260902-01"
MAP_HELPER = "host/harborline_tally_pack_map.py"
MAP_OWNER = "bc-31c8ef9a"
MAP_SHA = "35ed9d78f"
WAITLIST_POINTER = "cursor-business-pack-sidewalk-lotribbon-waitlist-pointer-20260902-01"
WAITLIST_CLAIM = "cursor-business-pack-waitlist-pointer-20260902-01"
LEFTOVER_HELPER = "host/business_pack_harborline_tally_map.py"
PEER_HELPER = "host/business_pack_harborline_tally_map_pointer.py"
# Historical byte observations. Mutable pages and helpers may evolve independently
# of the catalog pointer. Canonical receipt continuity is checked separately.
EXPECTED_BLOBS = {
    "host/harborline_tally_pack_map.py": "a7a49b77",
    "test_harborline_tally_pack_map.py": "68b4fce1",
    "p/cursor-harborline-tally-pack-map-20260902-01.md": "d3e7312c",
    "p/cursor-business-pack-harborline-tally-map-pointer-20260902-01.md": "e38f1251",
    "p/cursor-business-pack-harborline-tally-map-pointer-helper-20260902-01.md": "6ec23344",
    "packs/desk-website-service-20260902-01/door.html": "cd2be48f",
    "packs/waitlist.html": "b312ed6d",
}
RECEIPT_BLOBS = {
    rel: prefix for rel, prefix in EXPECTED_BLOBS.items() if rel.startswith("p/")
}

# Land-time observations from leftover SHIP f439bf0a. Not live pins.
OBSERVED_AT_LAND = {
    "packs/sidewalk-signal-web-desk-20260902-01/index.html": "638e60b4",
    "packs/lotribbon-greetings-20260902-01/index.html": "ac60db02",
    "host/business_pack_desk_instance.py": "a550ae1b",
}
THIS_SEAT_DOES_NOT_WRITE = (
    "packs/sidewalk-signal-web-desk-20260902-01/index.html",
    "packs/lotribbon-greetings-20260902-01/index.html",
    "host/business_pack_desk_instance.py",
)


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def instance_block(law: dict[str, Any]) -> dict[str, Any]:
    block = law.get("instances")
    return block if isinstance(block, dict) else {}


def git_blob_prefix(rel: str, n: int = 8) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()[:n]


def landed_row(block: dict[str, Any], brand: str) -> dict[str, Any]:
    for row in block.get("landed") or []:
        if isinstance(row, dict) and str(row.get("brand") or "") == brand:
            return row
    return {}


def classify_pointer(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    block = instance_block(data)
    waitlist = data.get("waitlist") if isinstance(data.get("waitlist"), dict) else {}
    row = landed_row(block, "Harborline Local Sites")
    blobs = {rel: git_blob_prefix(rel) for rel in dict.fromkeys((*EXPECTED_BLOBS, *OBSERVED_AT_LAND, *RECEIPT_BLOBS))}
    blobs_match = all(blobs.get(rel) == prefix for rel, prefix in EXPECTED_BLOBS.items())
    missing_files = [rel for rel, prefix in blobs.items() if not prefix]
    receipt_blobs_match = all(
        blobs.get(rel, "") == prefix for rel, prefix in RECEIPT_BLOBS.items()
    )
    ids_not_reminted = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(block.get("id") or "") == CATALOG_ID
        and str(block.get("harborline_tally_pack_map_pointer") or "") == POINTER_ID
        and str(block.get("catalog_waitlist_rows_pointer") or "") == WAITLIST_POINTER
        and str(waitlist.get("id") or "") == WAITLIST_CLAIM
        and str(row.get("tally_pack_map_receipt") or "") == MAP_RECEIPT
        and (ROOT / "p" / f"{PEER_HELPER_ID}.md").is_file()
        and (ROOT / PEER_HELPER).is_file()
    )
    pointer_ok = (
        ids_not_reminted
        and str(block.get("harborline_tally_pack_map_sha") or "") == MAP_SHA
        and str(block.get("harborline_tally_map_leftover_helper") or "") == LEFTOVER_HELPER
        and str(row.get("owned_by") or "") == MAP_OWNER
        and str(row.get("tally_pack_map_owner") or "") == MAP_OWNER
        and str(row.get("tally_pack_map") or "") == MAP_HELPER
        and str(row.get("helper") or "") == "host/business_pack_desk_instance.py"
        and block.get("did_not_overwrite_harborline_tally_pack_map") is True
        and block.get("did_not_steal_instance_files") is True
        and block.get("did_not_steal_desk_helper") is True
        and block.get("did_not_wrap_harborline") is True
        and str(block.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and data.get("commons_admission") is False
        and not missing_files
        and receipt_blobs_match
    )
    return {
        "gate": False,
        "commons_admission": False,
        "catalog_only": True,
        "id": HELPER_ID,
        "pointer_id": POINTER_ID,
        "peer_helper_id": PEER_HELPER_ID,
        "unique_pack_id": str(data.get("id") or ""),
        "catalog_id": str(block.get("id") or ""),
        "map_receipt": str(row.get("tally_pack_map_receipt") or ""),
        "map_helper": str(row.get("tally_pack_map") or ""),
        "map_owner": str(row.get("tally_pack_map_owner") or row.get("owned_by") or ""),
        "map_sha": str(block.get("harborline_tally_pack_map_sha") or ""),
        "files_cleared_to_bc_31c8ef9a": str(row.get("tally_pack_map_owner") or "") == MAP_OWNER,
        "ids_not_reminted": ids_not_reminted,
        "did_not_overwrite_harborline_tally_pack_map": block.get(
            "did_not_overwrite_harborline_tally_pack_map"
        )
        is True,
        "did_not_steal_desk_helper": block.get("did_not_steal_desk_helper") is True,
        "did_not_wrap_harborline": block.get("did_not_wrap_harborline") is True,
        "this_seat_does_not_write": list(THIS_SEAT_DOES_NOT_WRITE),
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "live_instance_blobs_not_pinned": True,
        "checkout": str(block.get("checkout") or ""),
        "no_fake_stripe_urls": data.get("no_fake_stripe_urls") is not False,
        "agents_spend_ads": block.get("agents_spend_ads") is True,
        "no_auth": True,
        "blobs": blobs,
        "blobs_match": blobs_match,
        "receipt_blobs_match": receipt_blobs_match,
        "missing_files": missing_files,
        "pointer_ok": pointer_ok,
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
