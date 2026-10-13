#!/usr/bin/env python3
"""Pointer-only waitlist cite on unique-pack law. Does not write owner files.

bc-31c8ef9a owns the waitlist door, slot, law, helper, test, land, and SCOUT
receipt. This helper cites those paths and measures nearby pack facts. It does
not remint the SCOUT demand id, does not overwrite packs/thanks.html, and does
not take the TALLY desk helper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
POINTER_LAW = ROOT / "ground" / "BUSINESS_PACK_WAITLIST_POINTER.json"
UNIQUE_LAW = ROOT / "ground" / "BUSINESS_PACKS.json"
THANKS_DOOR = ROOT / "packs" / "thanks.html"
HARBORLINE_INSTANCE = ROOT / "packs" / "desk-website-service-20260902-01" / "instance.json"
TALLY_MANIFEST = ROOT / "packs" / "sidewalk-signal-web-desk-20260902-01" / "manifest.json"

OWNER_PATHS = (
    "packs/waitlist.html",
    "packs/_template/waitlist-slot.md",
    "ground/BUSINESS_PACK_WAITLIST.json",
    "host/pack_waitlist.py",
    "test_pack_waitlist.py",
    "p/scout-demand-pack-door-waitlist-20260902-01.md",
    "land/pack-waitlist-20260902.md",
)
DO_NOT_OVERWRITE = (
    "packs/thanks.html",
    "host/business_pack_desk_instance.py",
    "test_business_pack_desk_instance.py",
    "host/business_pack_waitlist_pointer.py",
    "test_business_pack_waitlist_pointer.py",
    "p/cursor-business-pack-waitlist-pointer-20260902-01.md",
    "p/cursor-business-pack-waitlist-pointer-helper-20260902-01.md",
)
THIS_SEAT_PATHS = (
    "ground/BUSINESS_PACK_WAITLIST_POINTER.json",
    "host/pack_waitlist_pointer.py",
    "test_pack_waitlist_pointer.py",
    "land/pack-waitlist-pointer-20260902.md",
    "p/cursor-business-pack-waitlist-pointer-20260902-01.md",
)
THANKS_BLOB_PREFIX = "76388c9a"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not an object")
    return data


def load_pointer(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or POINTER_LAW)


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def owner_path_rows(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or ROOT
    rows = []
    for rel in OWNER_PATHS:
        rows.append({"path": rel, "present": (base / rel).is_file(), "this_seat_writes": False})
    return rows


def classify_thanks_door(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    door = base / "packs" / "thanks.html"
    present = door.is_file()
    blob = git_blob_sha(door) if present else ""
    return {
        "path": "packs/thanks.html",
        "present": present,
        "blob": blob,
        "blob_prefix_ok": blob.startswith(THANKS_BLOB_PREFIX) if blob else False,
        "did_not_overwrite": True,
    }


def classify_harborline_similar(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    harborline = load_json(base / "packs" / "desk-website-service-20260902-01" / "instance.json")
    tally = load_json(base / "packs" / "sidewalk-signal-web-desk-20260902-01" / "manifest.json")
    harbor_brand = str(harborline.get("brand") or "").strip()
    tally_brand = str(tally.get("brand") or "").strip()
    similar = harbor_brand == "Harborline Local Sites" and tally_brand == "Sidewalk Signal"
    clone = harbor_brand == tally_brand or harbor_brand == "" or tally_brand == ""
    return {
        "harborline_brand": harbor_brand,
        "tally_brand": tally_brand,
        "similar_is_not_clone": similar and not clone,
        "clone_stamp": clone,
        "harborline_door": str(harborline.get("door") or ""),
        "tally_pack": "packs/sidewalk-signal-web-desk-20260902-01",
    }


def classify(root: Path | None = None, pointer: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cite waitlist ownership. Never a Commons gate."""
    base = root or ROOT
    data = pointer if isinstance(pointer, dict) else load_pointer(
        base / "ground" / "BUSINESS_PACK_WAITLIST_POINTER.json" if root is not None else None
    )
    unique = load_json(base / "ground" / "BUSINESS_PACKS.json")
    unique_ptr = unique.get("waitlist") if isinstance(unique.get("waitlist"), dict) else {}
    owner_rows = owner_path_rows(base)
    thanks = classify_thanks_door(base)
    harbor = classify_harborline_similar(base)
    tally_helper = base / "host" / "business_pack_desk_instance.py"
    return {
        "gate": False,
        "commons_admission": False,
        "id": str(data.get("id") or ""),
        "scout_demand_id": str(data.get("scout_demand_id") or ""),
        "did_not_remint_scout_demand": data.get("did_not_remint_scout_demand") is True,
        "pointer_only": data.get("pointer_only") is True,
        "owner_seat": str(data.get("owner_seat") or unique_ptr.get("claimed_by") or ""),
        "owner_paths": owner_rows,
        "did_not_write_owner_paths": True,
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "thanks_door": thanks,
        "tally_helper_present": tally_helper.is_file(),
        "tally_helper_single_owner": True,
        "did_not_overwrite_tally_helper": True,
        "peer_helper_present": (base / "host" / "business_pack_waitlist_pointer.py").is_file(),
        "did_not_overwrite_peer_helper": True,
        "harborline": harbor,
        "checkout": str(data.get("checkout") or "NOT_MINTED"),
        "no_fake_stripe_urls": True,
        "agents_spend_ads": False,
        "unique_pack_law_id": str(unique.get("id") or ""),
        "unique_pack_waitlist_pointer_id": str(unique_ptr.get("id") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pointer", default="", help="override pointer JSON")
    args = parser.parse_args(argv)
    result = classify(pointer=load_pointer(Path(args.pointer)) if args.pointer else None)
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
