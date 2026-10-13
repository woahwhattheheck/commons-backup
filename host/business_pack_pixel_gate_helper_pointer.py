#!/usr/bin/env python3
"""Leftover helper: landed pixel-gate helper catalog pointer stays that peer.

CLAIM cursor-business-pack-pixel-gate-helper-pointer-20260902-01 is already
on current main (blob a866c00e) and is not reminted. This leftover cites
host/pack_waitlist_pixel_gate_pointer.py without overwriting it. Checkout
stays NOT_MINTED.
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
WAITLIST_POINTER_ID = "cursor-business-pack-waitlist-pointer-20260902-01"
PIXEL_GATE_POINTER_ID = "cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01"
POINTER_ID = "cursor-business-pack-pixel-gate-helper-pointer-20260902-01"
HELPER_ID = "cursor-business-pack-pixel-gate-helper-pointer-helper-20260902-01"
LEFTOVER_HELPER = "host/pack_waitlist_pixel_gate_pointer.py"
LEFTOVER_HELPER_RECEIPT = "cursor-business-pack-waitlist-pixel-gate-pointer-helper-20260902-01"
COMPLEMENTARY_HELPER = "host/business_pack_waitlist_pixel_gate_pointer.py"
PIXEL_GATE_ENGINE = "host/pack_waitlist_pixel_gate.py"
SCOUT_WAITLIST_ID = "scout-demand-pack-door-waitlist-20260902-01"
# Historical byte observations; live pages/helpers may evolve independently.
EXPECTED_BLOBS = {
    "host/pack_waitlist_pixel_gate_pointer.py": "cc94a911",
    "host/business_pack_waitlist_pixel_gate_pointer.py": "ab11be29",
    "host/pack_waitlist_pixel_gate.py": "4df0f64e",
    "packs/waitlist.html": "f93c8f32",
    "packs/thanks.html": "965a834b",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01.md": "6f981cf8",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-helper-20260902-01.md": "af68f245",
    "p/cursor-business-pack-pixel-gate-helper-pointer-20260902-01.md": "a866c00e",
}
RECEIPT_BLOBS = {
    rel: prefix for rel, prefix in EXPECTED_BLOBS.items() if rel.startswith("p/")
}

THIS_SEAT_PATHS = (
    "host/business_pack_pixel_gate_helper_pointer.py",
    "test_business_pack_pixel_gate_helper_pointer.py",
    "land/pack-pixel-gate-helper-pointer-20260902.md",
    "p/cursor-business-pack-pixel-gate-helper-pointer-helper-20260902-01.md",
)
DO_NOT_WRITE = (
    "host/pack_waitlist_pixel_gate_pointer.py",
    "test_pack_waitlist_pixel_gate_pointer.py",
    "host/business_pack_waitlist_pixel_gate_pointer.py",
    "test_business_pack_waitlist_pixel_gate_pointer.py",
    "host/pack_waitlist_pixel_gate.py",
    "packs/waitlist.html",
    "packs/thanks.html",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-20260902-01.md",
    "p/cursor-business-pack-waitlist-pixel-gate-pointer-helper-20260902-01.md",
    "p/cursor-business-pack-pixel-gate-helper-pointer-20260902-01.md",
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


def blob_prefix(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()[:8]


def classify_pointer(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    waitlist = waitlist_block(data)
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
        and str(waitlist.get("id") or "") == WAITLIST_POINTER_ID
        and str(waitlist.get("pixel_gate_pointer") or "") == PIXEL_GATE_POINTER_ID
        and str(waitlist.get("pixel_gate_helper_pointer") or "") == POINTER_ID
        and str(waitlist.get("pixel_gate_pointer_helper") or "") == LEFTOVER_HELPER
        and str(waitlist.get("pixel_gate_pointer_helper_receipt") or "")
        == LEFTOVER_HELPER_RECEIPT
        and waitlist.get("did_not_overwrite_pixel_gate_pointer_helper") is True
        and str(waitlist.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and data.get("commons_admission") is False
        and not missing_files
        and receipt_blobs_match
        and LEFTOVER_HELPER not in THIS_SEAT_PATHS
        and PIXEL_GATE_ENGINE not in THIS_SEAT_PATHS
        and (ROOT / LEFTOVER_HELPER).is_file()
        and (ROOT / COMPLEMENTARY_HELPER).is_file()
        and (ROOT / "p" / f"{POINTER_ID}.md").is_file()
        and (ROOT / "p" / f"{HELPER_ID}.md").is_file()
        and (ROOT / "p" / f"{LEFTOVER_HELPER_RECEIPT}.md").is_file()
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": HELPER_ID,
        "pointer_id": POINTER_ID,
        "pixel_gate_pointer": PIXEL_GATE_POINTER_ID,
        "leftover_helper": LEFTOVER_HELPER,
        "leftover_helper_receipt": LEFTOVER_HELPER_RECEIPT,
        "complementary_helper": COMPLEMENTARY_HELPER,
        "did_not_overwrite_leftover_helper": blobs.get(LEFTOVER_HELPER, "").startswith(
            EXPECTED_BLOBS[LEFTOVER_HELPER]
        ),
        "did_not_overwrite_complementary_helper": blobs.get(
            COMPLEMENTARY_HELPER, ""
        ).startswith(EXPECTED_BLOBS[COMPLEMENTARY_HELPER]),
        "did_not_remint_pixel_gate_helper_pointer": blobs.get(
            f"p/{POINTER_ID}.md", ""
        ).startswith(EXPECTED_BLOBS[f"p/{POINTER_ID}.md"]),
        "did_not_remint_scout_demand": str(waitlist.get("scout_demand_id") or "")
        == SCOUT_WAITLIST_ID,
        "checkout": str(waitlist.get("checkout") or ""),
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
