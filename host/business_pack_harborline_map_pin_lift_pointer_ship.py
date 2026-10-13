#!/usr/bin/env python3
"""SHIP leftover: unique-pack Harborline map pin-lift pointer already on main.

Pointer cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01
landed at af2b82f9a and is not reminted. This leftover only cites that
pointer and leftover Harborline pin-lift blob 8fe8a002. Unique-pack tests
do not freeze TALLY sold-once receipt absence. Checkout stays NOT_MINTED.
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
POINTER_ID = "cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01"
LEFTOVER_ID = "cursor-pack-harborline-map-pin-lift-20260902-01"
SHIP_ID = "cursor-business-pack-harborline-map-pin-lift-pointer-ship-20260902-01"
SOLD_ONCE_PIN_LIFT_ID = "cursor-business-pack-sold-once-badge-pin-lift-20260902-01"
TALLY_SOLD_ONCE_ID = "tally-door-sold-once-badge-20260902-01"
CANDIDATE_SHA = "af2b82f9a16185660e378a4a6f28c78dc827bb6e"
EXPECTED_BLOBS = {
    f"p/{LEFTOVER_ID}.md": "8fe8a002",
    f"p/{POINTER_ID}.md": "7a8987b5",
}
THIS_SEAT_PATHS = (
    "host/business_pack_harborline_map_pin_lift_pointer_ship.py",
    "test_business_pack_harborline_map_pin_lift_pointer_ship.py",
    "land/pack-harborline-map-pin-lift-pointer-ship-20260902.md",
    f"p/{SHIP_ID}.md",
)
DO_NOT_WRITE = (
    f"p/{POINTER_ID}.md",
    f"p/{LEFTOVER_ID}.md",
    f"p/{SOLD_ONCE_PIN_LIFT_ID}.md",
    "ground/BUSINESS_PACKS.json",
    "test_business_pack_unique.py",
    "business-packs.html",
    "ground/BUSINESS_PACKS.md",
    "host/business_pack_harborline_tally_map.py",
    "host/business_pack_harborline_tally_map_pointer.py",
    "host/business_pack_harborline_map_helper_pointer.py",
    "host/business_pack_desk_instance.py",
    "packs/sidewalk-signal-web-desk-20260902-01/index.html",
    "packs/lotribbon-greetings-20260902-01/index.html",
    "packs/desk-website-service-20260902-01/door.html",
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


def blob_prefix(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()[:8]


def classify_ship(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    catalog = instances_block(data)
    blobs = {rel: blob_prefix(rel) for rel in EXPECTED_BLOBS}
    leftover_blobs_ok = all(
        blobs.get(rel, "").startswith(prefix) for rel, prefix in EXPECTED_BLOBS.items()
    )
    tally_sold_once_path = ROOT / "p" / f"{TALLY_SOLD_ONCE_ID}.md"
    tally_sold_once_present = tally_sold_once_path.is_file()
    does_not_freeze_tally_sold_once_absence = (
        TALLY_SOLD_ONCE_ID not in EXPECTED_BLOBS
        and f"p/{TALLY_SOLD_ONCE_ID}.md" not in EXPECTED_BLOBS
        and f"p/{TALLY_SOLD_ONCE_ID}.md" not in THIS_SEAT_PATHS
        and f"p/{TALLY_SOLD_ONCE_ID}.md" not in DO_NOT_WRITE
    )
    ship_ok = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(catalog.get("id") or "") == CATALOG_ID
        and str(catalog.get("harborline_map_pin_lift") or "") == LEFTOVER_ID
        and str(catalog.get("harborline_map_pin_lift_blob") or "") == "8fe8a002"
        and str(catalog.get("harborline_map_pin_lift_pointer") or "") == POINTER_ID
        and catalog.get("did_not_write_harborline_map_pin_lift") is True
        and catalog.get("did_not_remint_harborline_map_pin_lift") is True
        and catalog.get("harborline_leftover_live_instance_blobs_not_pinned") is True
        and catalog.get("did_not_write_tally_sold_once_paths") is True
        and str(catalog.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and leftover_blobs_ok
        and does_not_freeze_tally_sold_once_absence
        and (ROOT / "p" / f"{POINTER_ID}.md").is_file()
        and (ROOT / "p" / f"{LEFTOVER_ID}.md").is_file()
        and (ROOT / "p" / f"{SHIP_ID}.md").is_file()
        and f"p/{POINTER_ID}.md" not in THIS_SEAT_PATHS
        and f"p/{LEFTOVER_ID}.md" not in THIS_SEAT_PATHS
        and "ground/BUSINESS_PACKS.json" not in THIS_SEAT_PATHS
        and "test_business_pack_unique.py" not in THIS_SEAT_PATHS
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": SHIP_ID,
        "pointer_id": POINTER_ID,
        "leftover_id": LEFTOVER_ID,
        "candidate_sha": CANDIDATE_SHA,
        "did_not_remint_pointer": blobs.get(f"p/{POINTER_ID}.md", "").startswith(
            EXPECTED_BLOBS[f"p/{POINTER_ID}.md"]
        ),
        "did_not_remint_leftover": blobs.get(f"p/{LEFTOVER_ID}.md", "").startswith(
            EXPECTED_BLOBS[f"p/{LEFTOVER_ID}.md"]
        ),
        "did_not_write_harborline_map_pin_lift": catalog.get(
            "did_not_write_harborline_map_pin_lift"
        )
        is True,
        "live_instance_blobs_not_pinned": True,
        "does_not_freeze_tally_sold_once_absence": does_not_freeze_tally_sold_once_absence,
        "tally_sold_once_present": tally_sold_once_present,
        "tally_sold_once_required": False,
        "tally_sold_once_forbidden": False,
        "checkout": str(catalog.get("checkout") or ""),
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "do_not_write": list(DO_NOT_WRITE),
        "blobs": blobs,
        "leftover_blobs_ok": leftover_blobs_ok,
        "ship_ok": ship_ok,
        "agents_spend_ads": False,
        "no_auth": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--law", default="", help="override unique-pack law path")
    args = parser.parse_args(argv)
    law = load_law(Path(args.law) if args.law else None)
    print(json.dumps(classify_ship(law), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
