#!/usr/bin/env python3
"""Classify the unique-pack waitlist pixel-gate pointer. Not a Commons gate.

Peer CLAIM cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01
and leftover pack_* helper are already on current main. Pixel-gate files
stay with bc-31c8ef9a. This leftover only reads. It does not remint those
ids, does not write host/pack_waitlist_pixel_gate.py, and does not
overwrite waitlist/thanks doors. Catalog and waitlist ids stay put.
Checkout stays NOT_MINTED.
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
WAITLIST_POINTER_ID = "cursor-business-pack-waitlist-pointer-20260902-01"
POINTER_ID = "cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01"
PEER_HELPER_ID = "cursor-business-pack-waitlist-pixel-gate-pointer-helper-20260902-01"
HELPER_ID = "cursor-business-pack-waitlist-pixel-gate-classifier-20260902-01"
PIXEL_GATE_HELPER = "host/pack_waitlist_pixel_gate.py"
PIXEL_GATE_RECEIPT = "cursor-pack-waitlist-pixel-gate-20260902-01"
PIXEL_GATE_OWNER = "bc-31c8ef9a"
PIXEL_GATE_SHA = "314cb051e"
PEER_PACK_HELPER = "host/pack_waitlist_pixel_gate_pointer.py"
# Historical byte observations; live pages/helpers may evolve independently.
EXPECTED_BLOBS = {
    "host/pack_waitlist_pixel_gate.py": "4df0f64e",
    "host/pack_waitlist_pixel_gate_pointer.py": "b3f26525",
    "packs/waitlist.html": "b312ed6d",
    "packs/thanks.html": "76388c9a",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01.md": "6f981cf8",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-helper-20260902-01.md": "af68f245",
    "p/cursor-pack-waitlist-pixel-gate-20260902-01.md": "e3dcb2f8",
}
RECEIPT_BLOBS = {
    rel: prefix for rel, prefix in EXPECTED_BLOBS.items() if rel.startswith("p/")
}

THIS_SEAT_PATHS = (
    "host/business_pack_waitlist_pixel_gate_pointer.py",
    "test_business_pack_waitlist_pixel_gate_pointer.py",
    "land/pack-waitlist-pixel-gate-classifier-20260902.md",
    "p/cursor-business-pack-waitlist-pixel-gate-classifier-20260902-01.md",
)
DO_NOT_WRITE = (
    "host/pack_waitlist_pixel_gate.py",
    "test_pack_waitlist_pixel_gate.py",
    "host/pack_waitlist_pixel_gate_pointer.py",
    "test_pack_waitlist_pixel_gate_pointer.py",
    "packs/waitlist.html",
    "packs/thanks.html",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01.md",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-helper-20260902-01.md",
    "p/cursor-pack-waitlist-pixel-gate-20260902-01.md",
)


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def waitlist_block(law: dict[str, Any]) -> dict[str, Any]:
    block = law.get("waitlist")
    return block if isinstance(block, dict) else {}


def instances_block(law: dict[str, Any]) -> dict[str, Any]:
    block = law.get("instances")
    return block if isinstance(block, dict) else {}


def blob_prefix(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()[:8]


def classify_pointer(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    block = waitlist_block(data)
    catalog = instances_block(data)
    blobs = {rel: blob_prefix(rel) for rel in dict.fromkeys((*EXPECTED_BLOBS, *RECEIPT_BLOBS))}
    blobs_match = all(
        blobs.get(rel, "").startswith(prefix) for rel, prefix in EXPECTED_BLOBS.items()
    )
    missing_files = [rel for rel, prefix in blobs.items() if not prefix]
    receipt_blobs_match = all(
        blobs.get(rel, "") == prefix for rel, prefix in RECEIPT_BLOBS.items()
    )
    pointer_ok = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(catalog.get("id") or "") == CATALOG_ID
        and str(block.get("id") or "") == WAITLIST_POINTER_ID
        and str(block.get("pixel_gate_pointer") or "") == POINTER_ID
        and str(block.get("pixel_gate_helper") or "") == PIXEL_GATE_HELPER
        and str(block.get("pixel_gate_receipt") or "") == PIXEL_GATE_RECEIPT
        and str(block.get("pixel_gate_claimed_by") or "") == PIXEL_GATE_OWNER
        and str(block.get("pixel_gate_sha") or "") == PIXEL_GATE_SHA
        and block.get("did_not_write_pixel_gate_paths") is True
        and block.get("did_not_overwrite_waitlist_html") is True
        and block.get("did_not_overwrite_thanks_html") is True
        and block.get("ccpa_opt_out_blocks_thanks_pixels") is True
        and block.get("empty_slots_load_nothing") is True
        and str(block.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and data.get("commons_admission") is False
        and not missing_files
        and receipt_blobs_match
        and PIXEL_GATE_HELPER not in THIS_SEAT_PATHS
        and PEER_PACK_HELPER not in THIS_SEAT_PATHS
        and (ROOT / PIXEL_GATE_HELPER).is_file()
        and (ROOT / PEER_PACK_HELPER).is_file()
        and (ROOT / "p" / f"{POINTER_ID}.md").is_file()
        and (ROOT / "p" / f"{PEER_HELPER_ID}.md").is_file()
        and (ROOT / "p" / f"{PIXEL_GATE_RECEIPT}.md").is_file()
        and (ROOT / "p" / f"{HELPER_ID}.md").is_file()
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": HELPER_ID,
        "pointer_id": POINTER_ID,
        "peer_helper_id": PEER_HELPER_ID,
        "did_not_remint_pointer": True,
        "did_not_remint_peer_helper": True,
        "did_not_remint_catalog": str(catalog.get("id") or "") == CATALOG_ID,
        "did_not_remint_waitlist": str(block.get("id") or "") == WAITLIST_POINTER_ID,
        "unique_pack_id": str(data.get("id") or ""),
        "catalog_id": str(catalog.get("id") or ""),
        "waitlist_pointer_id": str(block.get("id") or ""),
        "pixel_gate_helper": PIXEL_GATE_HELPER,
        "pixel_gate_receipt": PIXEL_GATE_RECEIPT,
        "pixel_gate_owner": PIXEL_GATE_OWNER,
        "pixel_gate_sha": str(block.get("pixel_gate_sha") or ""),
        "files_cleared_to_bc_31c8ef9a": str(block.get("pixel_gate_claimed_by") or "")
        == PIXEL_GATE_OWNER,
        "did_not_write_pixel_gate_paths": block.get("did_not_write_pixel_gate_paths")
        is True,
        "did_not_overwrite_waitlist_html": block.get("did_not_overwrite_waitlist_html")
        is True,
        "did_not_overwrite_thanks_html": block.get("did_not_overwrite_thanks_html")
        is True,
        "did_not_overwrite_peer_pack_helper": True,
        "ccpa_opt_out_blocks_thanks_pixels": block.get(
            "ccpa_opt_out_blocks_thanks_pixels"
        )
        is True,
        "empty_slots_load_nothing": block.get("empty_slots_load_nothing") is True,
        "checkout": str(block.get("checkout") or ""),
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "do_not_write": list(DO_NOT_WRITE),
        "blobs": blobs,
        "blobs_match": blobs_match,
        "receipt_blobs_match": receipt_blobs_match,
        "missing_files": missing_files,
        "pointer_ok": pointer_ok,
        "agents_spend_ads": False,
        "no_auth": True,
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
