#!/usr/bin/env python3
"""Catalog-only waitlist rows for Sidewalk Signal + LotRibbon.

Points at shared packs/waitlist.html. Does not overwrite instance doors.
Does not remint catalog / unique-pack / waitlist / Harborline-slot ids.
Checkout NOT_MINTED. Not a Commons gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACKS.json"
POINTER_ID = "cursor-business-pack-sidewalk-lotribbon-waitlist-pointer-20260902-01"
CATALOG_ID = "cursor-business-pack-instance-catalog-20260902-01"
UNIQUE_PACK_ID = "cursor-business-packs-unique-20260902-01"
WAITLIST_POINTER_ID = "cursor-business-pack-waitlist-pointer-20260902-01"
HARBORLINE_SLOT_ID = "cursor-business-pack-harborline-waitlist-slot-pointer-20260902-01"
WAITLIST = "packs/waitlist.html"
ROWS = {
    "LotRibbon Greetings": {
        "door": "packs/lotribbon-greetings-20260902-01/index.html",
        "owned_by": "bc-23891c63",
    },
    "Sidewalk Signal": {
        "door": "packs/sidewalk-signal-web-desk-20260902-01/index.html",
        "owned_by": "TALLY",
    },
}
# Immutable observations from the original catalog-pointer receipt. They are
# evidence about that land, not live locks on files owned by other workers.
OBSERVED_AT_LAND = {
    "packs/lotribbon-greetings-20260902-01/index.html": "ac60db02",
    "packs/sidewalk-signal-web-desk-20260902-01/index.html": "638e60b4",
}


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def git_blob_prefix(rel: str, n: int = 8) -> str:
    path = ROOT / rel
    data = path.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data)
    return digest.hexdigest()[:n]


def instance_block(law: dict[str, Any]) -> dict[str, Any]:
    block = law.get("instances")
    return block if isinstance(block, dict) else {}


def landed_row(block: dict[str, Any], brand: str) -> dict[str, Any]:
    for row in block.get("landed") or []:
        if isinstance(row, dict) and str(row.get("brand") or "") == brand:
            return row
    return {}


def classify_pointer(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    block = instance_block(data)
    waitlist_block = data.get("waitlist") if isinstance(data.get("waitlist"), dict) else {}
    rows = {}
    owner_doors_present = True
    catalog_waitlist_ok = True
    for brand, expected in ROWS.items():
        row = landed_row(block, brand)
        door = str(row.get("door") or "")
        waitlist = str(row.get("waitlist") or "")
        blob = git_blob_prefix(expected["door"]) if (ROOT / expected["door"]).is_file() else ""
        present = bool(blob) and door == expected["door"]
        owner_doors_present = owner_doors_present and present
        points = waitlist == WAITLIST
        catalog_waitlist_ok = catalog_waitlist_ok and points
        rows[brand] = {
            "door": door,
            "owned_by": str(row.get("owned_by") or ""),
            "waitlist": waitlist,
            "door_blob": blob,
            "door_present": present,
            "points_at_shared_waitlist": points,
        }
    landed_pointer = str(
        block.get("catalog_waitlist_rows_pointer")
        or block.get("sidewalk_lotribbon_waitlist_pointer")
        or ""
    )
    ids_not_reminted = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(block.get("id") or "") == CATALOG_ID
        and str(waitlist_block.get("id") or "") == WAITLIST_POINTER_ID
        and str(block.get("harborline_waitlist_slot_pointer") or "") == HARBORLINE_SLOT_ID
        and landed_pointer == POINTER_ID
    )
    checkout = str(block.get("checkout") or "")
    return {
        "gate": False,
        "commons_admission": False,
        "id": POINTER_ID,
        "catalog_id": str(block.get("id") or ""),
        "unique_pack_id": str(data.get("id") or ""),
        "waitlist_pointer_id": str(waitlist_block.get("id") or ""),
        "harborline_slot_pointer_id": str(block.get("harborline_waitlist_slot_pointer") or ""),
        "landed_pointer_id": landed_pointer,
        "catalog_only": True,
        "waitlist": WAITLIST,
        "rows": rows,
        "owner_doors_present": owner_doors_present,
        "live_owner_blobs_not_pinned": True,
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "catalog_waitlist_ok": catalog_waitlist_ok,
        "ids_not_reminted": ids_not_reminted,
        "did_not_overwrite_waitlist_html": block.get("did_not_overwrite_waitlist_html") is True,
        "did_not_steal_desk_helper": block.get("did_not_steal_desk_helper") is True,
        "checkout": checkout,
        "agents_spend_ads": block.get("agents_spend_ads") is True,
        "no_fake_stripe_urls": data.get("no_fake_stripe_urls") is not False,
        "no_auth": True,
        "pointer_ok": (
            ids_not_reminted
            and catalog_waitlist_ok
            and owner_doors_present
            and checkout == "NOT_MINTED"
            and data.get("gate") is False
            and data.get("commons_admission") is False
            and block.get("did_not_overwrite_waitlist_html") is True
            and block.get("did_not_steal_desk_helper") is True
            and block.get("did_not_overwrite_sidewalk_door") is True
            and block.get("did_not_overwrite_lotribbon_door") is True
        ),
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
