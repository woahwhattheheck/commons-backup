#!/usr/bin/env python3
"""Leftover helper: classify landed Harborline map pin-lift compose.

Compose cursor-business-pack-harborline-map-pin-lift-compose-20260902-01
landed at 7d6a4df1b. Peer SHIP
cursor-business-pack-harborline-map-pin-lift-compose-ship-20260902-01
blob c449e49f is not reminted. KEEP MAIN remint of pointer blob 7a8987b5.
This leftover only reads squash/claimed_by keys plus the unique land file.
Checkout stays NOT_MINTED. Not a Commons gate.
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
COMPOSE_ID = "cursor-business-pack-harborline-map-pin-lift-compose-20260902-01"
SHIP_ID = "cursor-business-pack-harborline-map-pin-lift-compose-ship-20260902-01"
HELPER_ID = "cursor-business-pack-harborline-map-pin-lift-compose-helper-20260902-01"
POINTER_ID = "cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01"
LEFTOVER_ID = "cursor-pack-harborline-map-pin-lift-20260902-01"
SOLD_ONCE_PIN_LIFT_ID = "cursor-business-pack-sold-once-badge-pin-lift-20260902-01"
POINTER_SHIP_ID = "cursor-business-pack-harborline-map-pin-lift-pointer-ship-20260902-01"
LAND_FILE = "land/pack-harborline-map-pin-lift-pointer-20260902.md"
CANDIDATE_SHA = "7d6a4df1be98b213b98f3d9b81de7bd7c08b7fa5"
KEEP_MAIN_PR = 7915
EXPECTED_BLOBS = {
    f"p/{COMPOSE_ID}.md": "4135cf8f",
    f"p/{SHIP_ID}.md": "c449e49f",
    f"p/{POINTER_ID}.md": "7a8987b5",
    f"p/{LEFTOVER_ID}.md": "8fe8a002",
    LAND_FILE: "fe01649e",
}
THIS_SEAT_PATHS = (
    "host/business_pack_harborline_map_pin_lift_compose.py",
    "test_business_pack_harborline_map_pin_lift_compose.py",
    "land/pack-harborline-map-pin-lift-compose-20260902.md",
    f"p/{HELPER_ID}.md",
)
DO_NOT_WRITE = (
    f"p/{COMPOSE_ID}.md",
    f"p/{SHIP_ID}.md",
    f"p/{POINTER_ID}.md",
    f"p/{LEFTOVER_ID}.md",
    f"p/{SOLD_ONCE_PIN_LIFT_ID}.md",
    f"p/{POINTER_SHIP_ID}.md",
    LAND_FILE,
    "ground/BUSINESS_PACKS.json",
    "test_business_pack_unique.py",
    "business-packs.html",
    "ground/BUSINESS_PACKS.md",
    "host/business_pack_harborline_map_pin_lift_pointer_ship.py",
    "host/business_pack_harborline_tally_map.py",
    "host/business_pack_harborline_tally_map_pointer.py",
    "host/business_pack_harborline_map_helper_pointer.py",
    "host/harborline_tally_pack_map.py",
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


def compose_receipt_text() -> str:
    path = ROOT / "p" / f"{COMPOSE_ID}.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def classify_compose(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    catalog = instances_block(data)
    receipt = compose_receipt_text()
    blobs = {rel: blob_prefix(rel) for rel in EXPECTED_BLOBS}
    leftover_blobs_ok = all(
        blobs.get(rel, "").startswith(prefix) for rel, prefix in EXPECTED_BLOBS.items()
    )
    keep_main = (
        "KEEP MAIN" in receipt
        and f"#{KEEP_MAIN_PR}" in receipt
        and "7a8987b5" in receipt
        and blobs.get(f"p/{POINTER_ID}.md", "").startswith("7a8987b5")
        and f"p/{POINTER_ID}.md" not in THIS_SEAT_PATHS
    )
    compose_ok = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(catalog.get("id") or "") == CATALOG_ID
        and str(catalog.get("harborline_map_pin_lift") or "") == LEFTOVER_ID
        and str(catalog.get("harborline_map_pin_lift_blob") or "") == "8fe8a002"
        and str(catalog.get("harborline_map_pin_lift_squash") or "") == "b9e6f54c"
        and str(catalog.get("harborline_map_pin_lift_claimed_by") or "") == "bc-31c8ef9a"
        and str(catalog.get("harborline_map_pin_lift_pointer") or "") == POINTER_ID
        and catalog.get("did_not_write_harborline_map_pin_lift") is True
        and catalog.get("did_not_remint_harborline_map_pin_lift") is True
        and catalog.get("did_not_remint_sold_once_badge_pin_lift") is True
        and catalog.get("harborline_leftover_live_instance_blobs_not_pinned") is True
        and catalog.get("did_not_write_tally_sold_once_paths") is True
        and str(catalog.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and leftover_blobs_ok
        and keep_main
        and "Did not merge #7915" in receipt
        and "NOT_MINTED" in receipt
        and (ROOT / "p" / f"{COMPOSE_ID}.md").is_file()
        and (ROOT / "p" / f"{POINTER_ID}.md").is_file()
        and (ROOT / "p" / f"{LEFTOVER_ID}.md").is_file()
        and (ROOT / LAND_FILE).is_file()
        and (ROOT / "p" / f"{SHIP_ID}.md").is_file()
        and (ROOT / "p" / f"{HELPER_ID}.md").is_file()
        and f"p/{COMPOSE_ID}.md" not in THIS_SEAT_PATHS
        and f"p/{SHIP_ID}.md" not in THIS_SEAT_PATHS
        and f"p/{POINTER_ID}.md" not in THIS_SEAT_PATHS
        and LAND_FILE not in THIS_SEAT_PATHS
        and "ground/BUSINESS_PACKS.json" not in THIS_SEAT_PATHS
        and "test_business_pack_unique.py" not in THIS_SEAT_PATHS
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": HELPER_ID,
        "compose_id": COMPOSE_ID,
        "ship_id": SHIP_ID,
        "pointer_id": POINTER_ID,
        "leftover_id": LEFTOVER_ID,
        "candidate_sha": CANDIDATE_SHA,
        "keep_main_pr": KEEP_MAIN_PR,
        "keep_main": keep_main,
        "did_not_remint_compose": blobs.get(f"p/{COMPOSE_ID}.md", "").startswith(
            EXPECTED_BLOBS[f"p/{COMPOSE_ID}.md"]
        ),
        "did_not_remint_compose_ship": blobs.get(f"p/{SHIP_ID}.md", "").startswith(
            EXPECTED_BLOBS[f"p/{SHIP_ID}.md"]
        ),
        "did_not_remint_pointer": blobs.get(f"p/{POINTER_ID}.md", "").startswith(
            EXPECTED_BLOBS[f"p/{POINTER_ID}.md"]
        ),
        "did_not_remint_leftover": blobs.get(f"p/{LEFTOVER_ID}.md", "").startswith(
            EXPECTED_BLOBS[f"p/{LEFTOVER_ID}.md"]
        ),
        "did_not_merge_7915": True,
        "harborline_map_pin_lift_squash": str(
            catalog.get("harborline_map_pin_lift_squash") or ""
        ),
        "harborline_map_pin_lift_claimed_by": str(
            catalog.get("harborline_map_pin_lift_claimed_by") or ""
        ),
        "land_file": LAND_FILE,
        "live_instance_blobs_not_pinned": True,
        "checkout": str(catalog.get("checkout") or ""),
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "do_not_write": list(DO_NOT_WRITE),
        "blobs": blobs,
        "leftover_blobs_ok": leftover_blobs_ok,
        "compose_ok": compose_ok,
        "agents_spend_ads": False,
        "no_auth": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--law", default="", help="override unique-pack law path")
    args = parser.parse_args(argv)
    law = load_law(Path(args.law) if args.law else None)
    print(json.dumps(classify_compose(law), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
