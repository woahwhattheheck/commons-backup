#!/usr/bin/env python3
"""Pointer leftover for the waitlist CCPA pixel-gate CLEAR.

CLAIM pointer cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01
is already on current main. Peer SHIP 314cb051e / bc-31c8ef9a owns
host/pack_waitlist_pixel_gate.py. This helper cites those bytes. It does
not remint the pointer id, the waitlist pointer, or the SCOUT demand, and
it does not write waitlist.html, thanks.html, or the pixel-gate helper.
Checkout stays NOT_MINTED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
POINTER_LAW = ROOT / "ground" / "BUSINESS_PACK_WAITLIST_PIXEL_GATE_POINTER.json"
UNIQUE_LAW = ROOT / "ground" / "BUSINESS_PACKS.json"
POINTER_ID = "cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01"
WAITLIST_POINTER_ID = "cursor-business-pack-waitlist-pointer-20260902-01"
PIXEL_GATE_RECEIPT = "cursor-pack-waitlist-pixel-gate-20260902-01"
SCOUT_DEMAND_ID = "scout-demand-pack-door-waitlist-20260902-01"
OWNER_SEAT = "bc-31c8ef9a"
PIXEL_GATE_SHA = "314cb051e"
POINTER_RECEIPT_BLOB = "6f981cf87f24aa0bb1ebf573a43a50dac8812f88"
PIXEL_GATE_HELPER_BLOB_PREFIX = "4df0f64e"
WAITLIST_BLOB_PREFIX = "b312ed6d"
THANKS_BLOB_PREFIX = "76388c9a"

OWNER_PATHS = (
    "packs/waitlist.html",
    "packs/_template/waitlist-slot.md",
    "ground/BUSINESS_PACK_WAITLIST.json",
    "host/pack_waitlist.py",
    "test_pack_waitlist.py",
    "p/scout-demand-pack-door-waitlist-20260902-01.md",
    "land/pack-waitlist-20260902.md",
    "host/pack_waitlist_pixel_gate.py",
    "test_pack_waitlist_pixel_gate.py",
    "p/cursor-pack-waitlist-pixel-gate-20260902-01.md",
)
DO_NOT_OVERWRITE = (
    "packs/waitlist.html",
    "packs/thanks.html",
    "host/pack_waitlist.py",
    "host/pack_waitlist_pixel_gate.py",
    "test_pack_waitlist_pixel_gate.py",
    "p/cursor-pack-waitlist-pixel-gate-20260902-01.md",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01.md",
    "p/cursor-business-pack-waitlist-pointer-20260902-01.md",
    "host/business_pack_desk_instance.py",
    "host/harborline_tally_pack_map.py",
    "packs/lotribbon-greetings-20260902-01",
    "packs/sidewalk-signal-web-desk-20260902-01",
)
THIS_SEAT_PATHS = (
    "ground/BUSINESS_PACK_WAITLIST_PIXEL_GATE_POINTER.json",
    "host/pack_waitlist_pixel_gate_pointer.py",
    "test_pack_waitlist_pixel_gate_pointer.py",
    "land/pack-waitlist-pixel-gate-pointer-20260902.md",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-helper-20260902-01.md",
)


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


def blob_row(rel: str, prefix: str = "") -> dict[str, Any]:
    path = ROOT / rel
    present = path.is_file()
    blob = git_blob_sha(path) if present else ""
    return {
        "path": rel,
        "present": present,
        "blob": blob,
        "blob_prefix_ok": blob.startswith(prefix) if prefix and blob else False,
        "this_seat_writes": False,
    }


def classify(root: Path | None = None, pointer: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cite the landed pixel-gate CLEAR. Never a Commons gate."""
    base = root or ROOT
    data = pointer if isinstance(pointer, dict) else load_pointer()
    unique = load_json(base / "ground" / "BUSINESS_PACKS.json")
    waitlist = unique.get("waitlist") if isinstance(unique.get("waitlist"), dict) else {}
    thanks = unique.get("thanks_pixel") if isinstance(unique.get("thanks_pixel"), dict) else {}
    pointer_receipt = blob_row(
        "p/cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01.md",
        POINTER_RECEIPT_BLOB,
    )
    helper = blob_row("host/pack_waitlist_pixel_gate.py", PIXEL_GATE_HELPER_BLOB_PREFIX)
    waitlist_door = blob_row("packs/waitlist.html", WAITLIST_BLOB_PREFIX)
    thanks_door = blob_row("packs/thanks.html", THANKS_BLOB_PREFIX)
    owner_seat = str(data.get("owner_seat") or waitlist.get("pixel_gate_claimed_by") or "")
    pointer_ok = (
        str(data.get("id") or "") == POINTER_ID
        and str(waitlist.get("pixel_gate_pointer") or "") == POINTER_ID
        and str(waitlist.get("id") or "") == WAITLIST_POINTER_ID
        and str(waitlist.get("pixel_gate_receipt") or "") == PIXEL_GATE_RECEIPT
        and str(waitlist.get("pixel_gate_claimed_by") or "") == OWNER_SEAT
        and str(waitlist.get("pixel_gate_sha") or "") == PIXEL_GATE_SHA
        and waitlist.get("did_not_write_pixel_gate_paths") is True
        and waitlist.get("ccpa_opt_out_blocks_thanks_pixels") is True
        and waitlist.get("empty_slots_load_nothing") is True
        and str(waitlist.get("checkout") or "") == "NOT_MINTED"
        and str(thanks.get("pixel_gate_pointer") or "") == POINTER_ID
        and pointer_receipt["blob"] == POINTER_RECEIPT_BLOB
        and helper["blob_prefix_ok"]
        and waitlist_door["blob_prefix_ok"]
        and thanks_door["blob_prefix_ok"]
        and unique.get("gate") is False
        and unique.get("commons_admission") is False
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": str(data.get("id") or ""),
        "pointer_only": data.get("pointer_only") is True,
        "owner_seat": owner_seat,
        "files_cleared_to_bc_31c8ef9a": owner_seat == OWNER_SEAT,
        "pixel_gate_claimed_by": str(waitlist.get("pixel_gate_claimed_by") or ""),
        "pixel_gate_sha": str(waitlist.get("pixel_gate_sha") or ""),
        "pixel_gate_helper": str(waitlist.get("pixel_gate_helper") or ""),
        "pixel_gate_receipt": str(waitlist.get("pixel_gate_receipt") or ""),
        "waitlist_pointer_id": str(waitlist.get("id") or ""),
        "scout_demand_id": str(data.get("scout_demand_id") or waitlist.get("scout_demand_id") or ""),
        "did_not_remint_scout_demand": data.get("did_not_remint_scout_demand") is True,
        "did_not_remint_waitlist_pointer": str(waitlist.get("id") or "") == WAITLIST_POINTER_ID,
        "did_not_remint_pointer": pointer_receipt["blob"] == POINTER_RECEIPT_BLOB,
        "did_not_write_pixel_gate_paths": True,
        "did_not_write_owner_paths": True,
        "did_not_overwrite_waitlist_html": waitlist_door["blob_prefix_ok"],
        "did_not_overwrite_thanks_html": thanks_door["blob_prefix_ok"],
        "ccpa_opt_out_blocks_thanks_pixels": waitlist.get("ccpa_opt_out_blocks_thanks_pixels") is True,
        "empty_slots_load_nothing": waitlist.get("empty_slots_load_nothing") is True,
        "sends": 0,
        "checkout": str(data.get("checkout") or waitlist.get("checkout") or "NOT_MINTED"),
        "no_fake_stripe_urls": True,
        "agents_mint_pixel_id": False,
        "agents_spend_ads": False,
        "pointer_receipt": pointer_receipt,
        "pixel_gate_helper_row": helper,
        "waitlist_door": waitlist_door,
        "thanks_door": thanks_door,
        "owner_paths": [
            {"path": rel, "present": (base / rel).is_file(), "this_seat_writes": False}
            for rel in OWNER_PATHS
        ],
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "unique_pack_law_id": str(unique.get("id") or ""),
        "pointer_ok": pointer_ok,
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
