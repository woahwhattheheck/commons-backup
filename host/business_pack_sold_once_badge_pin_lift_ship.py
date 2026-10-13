#!/usr/bin/env python3
"""SHIP leftover: sold-once badge pin-lift already on main.

CLAIM cursor-business-pack-sold-once-badge-pin-lift-20260902-01 landed at
f080fbbb2 and is not reminted. This leftover only cites that pin-lift and
checks live Sidewalk / TALLY-helper blobs stay observed_at_land. Pointer,
unique-pack, and Harborline leftover map helpers are not reminted.
Checkout stays NOT_MINTED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


import business_pack_sold_once_badge_pointer as leftover_pointer

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACKS.json"
UNIQUE_PACK_ID = "cursor-business-packs-unique-20260902-01"
CATALOG_ID = "cursor-business-pack-instance-catalog-20260902-01"
POINTER_ID = "cursor-business-pack-sold-once-badge-pointer-20260902-01"
HELPER_ID = "cursor-business-pack-sold-once-badge-pointer-helper-20260902-01"
PIN_LIFT_ID = "cursor-business-pack-sold-once-badge-pin-lift-20260902-01"
SHIP_ID = "cursor-business-pack-sold-once-badge-pin-lift-ship-20260902-01"
HARBORLINE_PIN_LIFT = "cursor-pack-harborline-map-pin-lift-20260902-01"
SIDEWALK_DOOR = "packs/sidewalk-signal-web-desk-20260902-01/index.html"
TALLY_HELPER = "host/business_pack_desk_instance.py"
LEFTOVER_HELPER = "host/business_pack_sold_once_badge_pointer.py"
CANDIDATE_SHA = "f080fbbb241a1550b3eb5d94c9041c21cd264d82"
# Historical ship receipt still cites land-time leftover helper `80602a55`
# and is not reminted. Live leftover helper is current HEAD after restoring
# land-time sidewalk/desk OBSERVED prefixes (catalog pointer leftover).
EXPECTED_BLOBS = {
    f"p/{PIN_LIFT_ID}.md": "da2d1ef5",
    f"p/{POINTER_ID}.md": "1cc11a5f",
    LEFTOVER_HELPER: "4e96b44d",
}
OBSERVED_AT_LAND = {
    TALLY_HELPER: "a550ae1b",
    SIDEWALK_DOOR: "638e60b4",
}
THIS_SEAT_PATHS = (
    "host/business_pack_sold_once_badge_pin_lift_ship.py",
    "test_business_pack_sold_once_badge_pin_lift_ship.py",
    "land/pack-sold-once-badge-pin-lift-ship-20260902.md",
    f"p/{SHIP_ID}.md",
)
DO_NOT_WRITE = (
    TALLY_HELPER,
    "host/business_pack_plant_instance.py",
    LEFTOVER_HELPER,
    "test_business_pack_sold_once_badge_pointer.py",
    SIDEWALK_DOOR,
    "packs/lotribbon-greetings-20260902-01/index.html",
    "packs/desk-website-service-20260902-01/door.html",
    "host/business_pack_harborline_tally_map.py",
    "host/business_pack_harborline_tally_map_pointer.py",
    f"p/{PIN_LIFT_ID}.md",
    f"p/{POINTER_ID}.md",
    f"p/{HELPER_ID}.md",
    f"p/{HARBORLINE_PIN_LIFT}.md",
    "ground/BUSINESS_PACKS.json",
    "test_business_pack_unique.py",
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
    leftover_expected = leftover_pointer.EXPECTED_BLOBS
    leftover_observed = leftover_pointer.OBSERVED_AT_LAND
    leftover_result = leftover_pointer.classify_pointer(data)
    blobs = {rel: blob_prefix(rel) for rel in (*EXPECTED_BLOBS, *OBSERVED_AT_LAND)}
    leftover_blobs_ok = all(
        blobs.get(rel, "").startswith(prefix) for rel, prefix in EXPECTED_BLOBS.items()
    )
    live_pins_lifted = (
        SIDEWALK_DOOR not in leftover_expected
        and TALLY_HELPER not in leftover_expected
        and leftover_observed.get(SIDEWALK_DOOR) == OBSERVED_AT_LAND[SIDEWALK_DOOR]
        and leftover_observed.get(TALLY_HELPER) == OBSERVED_AT_LAND[TALLY_HELPER]
        and leftover_pointer.PIN_LIFT_ID == PIN_LIFT_ID
        and leftover_result.get("live_instance_blobs_not_pinned") is True
    )
    ship_ok = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(catalog.get("id") or "") == CATALOG_ID
        and str(catalog.get("sold_once_badge_pointer") or "") == POINTER_ID
        and str(catalog.get("sold_once_badge_pin_lift") or "") == PIN_LIFT_ID
        and catalog.get("sold_once_badge_live_instance_blobs_not_pinned") is True
        and catalog.get("did_not_remint_sold_once_badge_pointer") is True
        and catalog.get("did_not_write_harborline_leftover_pin_helpers") is True
        and str(catalog.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and leftover_blobs_ok
        and live_pins_lifted
        and (ROOT / "p" / f"{PIN_LIFT_ID}.md").is_file()
        and (ROOT / "p" / f"{SHIP_ID}.md").is_file()
        and LEFTOVER_HELPER not in THIS_SEAT_PATHS
        and f"p/{PIN_LIFT_ID}.md" not in THIS_SEAT_PATHS
        and "ground/BUSINESS_PACKS.json" not in THIS_SEAT_PATHS
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": SHIP_ID,
        "leftover_id": PIN_LIFT_ID,
        "pointer_id": POINTER_ID,
        "helper_id": HELPER_ID,
        "candidate_sha": CANDIDATE_SHA,
        "did_not_remint_leftover": blobs.get(f"p/{PIN_LIFT_ID}.md", "").startswith(
            EXPECTED_BLOBS[f"p/{PIN_LIFT_ID}.md"]
        ),
        "did_not_remint_catalog_pointer": blobs.get(f"p/{POINTER_ID}.md", "").startswith(
            EXPECTED_BLOBS[f"p/{POINTER_ID}.md"]
        ),
        "did_not_overwrite_leftover_helper": blobs.get(LEFTOVER_HELPER, "").startswith(
            EXPECTED_BLOBS[LEFTOVER_HELPER]
        ),
        "did_not_write_harborline_leftover_pin_helpers": catalog.get(
            "did_not_write_harborline_leftover_pin_helpers"
        )
        is True,
        "live_instance_blobs_not_pinned": True,
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "checkout": str(catalog.get("checkout") or ""),
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "do_not_write": list(DO_NOT_WRITE),
        "blobs": blobs,
        "leftover_blobs_ok": leftover_blobs_ok,
        "live_pins_lifted": live_pins_lifted,
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
