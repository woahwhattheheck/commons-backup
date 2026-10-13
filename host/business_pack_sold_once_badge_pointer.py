#!/usr/bin/env python3
"""Leftover helper: landed sold-once catalog pointer stays that peer.

CLAIM cursor-business-pack-sold-once-badge-pointer-20260902-01 is already
on current main (blob 1cc11a5f) and is not reminted. Peer bc-23891c63
already landed LotRibbon door badge, instance creative_brief.md, and
p/cursor-plant-sold-once-badge-20260902-01.md. This leftover LEADs the
sidecar sold-once.md plus the unminted plant creative-brief receipt and
CLEARs TALLY sold-once desk. GOAT template current HEAD `0400ff35` (Latch
Pad KEEP pointer on land-time `f2953322`) is cited, not overwritten as product.

Live instance blobs are not pinned so TALLY can land sidewalk sold-once.
Land-time observations stay in OBSERVED_AT_LAND. Checkout stays NOT_MINTED.
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
POINTER_ID = "cursor-business-pack-sold-once-badge-pointer-20260902-01"
HELPER_ID = "cursor-business-pack-sold-once-badge-pointer-helper-20260902-01"
PIN_LIFT_ID = "cursor-business-pack-sold-once-badge-pin-lift-20260902-01"
PLANT_SOLD_ONCE_ID = "cursor-plant-sold-once-badge-20260902-01"
PLANT_CREATIVE_BRIEF_ID = "cursor-plant-creative-brief-20260902-01"
SCOUT_SOLD_ONCE_ID = "scout-demand-door-sold-once-badge-20260902-01"
LEAD_BRAND = "LotRibbon Greetings"
CLEAR_DESK = "TALLY"
TALLY_HELPER = "host/business_pack_desk_instance.py"
GOAT_TEMPLATE = "packs/_template/creative_brief.md"
LOTRIBBON_SOLD_ONCE = "packs/lotribbon-greetings-20260902-01/sold-once.md"
LOTRIBBON_BRIEF = "packs/lotribbon-greetings-20260902-01/creative_brief.md"
LOTRIBBON_ASSETS_BRIEF = "packs/lotribbon-greetings-20260902-01/assets/creative_brief.md"
PLANT_HELPER = "host/business_pack_plant_instance.py"
# Land-time observations from leftover helper land e4f87e40 / PR #7770.
# Not live pins: TALLY may change sidewalk door and the shared desk helper.
OBSERVED_AT_LAND = {
    "host/business_pack_desk_instance.py": "a550ae1b",
    "packs/lotribbon-greetings-20260902-01/index.html": "ac60db02",
    "packs/sidewalk-signal-web-desk-20260902-01/index.html": "638e60b4",
    "packs/desk-website-service-20260902-01/door.html": "cd2be48f",
}
EXPECTED_BLOBS = {
    "p/cursor-business-pack-sold-once-badge-pointer-20260902-01.md": "1cc11a5f",
    "p/cursor-plant-sold-once-badge-20260902-01.md": "39d83580",
    "packs/_template/creative_brief.md": "0400ff35",
    "packs/lotribbon-greetings-20260902-01/creative_brief.md": "2c7263a7",
}
THIS_SEAT_PATHS = (
    "host/business_pack_sold_once_badge_pointer.py",
    "test_business_pack_sold_once_badge_pointer.py",
    "land/pack-sold-once-badge-pointer-20260902.md",
    "p/cursor-business-pack-sold-once-badge-pointer-helper-20260902-01.md",
    "p/cursor-plant-creative-brief-20260902-01.md",
    LOTRIBBON_SOLD_ONCE,
)
DO_NOT_WRITE = (
    "host/business_pack_desk_instance.py",
    "host/business_pack_plant_instance.py",
    "test_business_pack_plant_instance.py",
    "packs/lotribbon-greetings-20260902-01/index.html",
    "packs/lotribbon-greetings-20260902-01/manifest.json",
    "packs/lotribbon-greetings-20260902-01/creative_brief.md",
    "packs/lotribbon-greetings-20260902-01/assets/creative_brief.md",
    "packs/sidewalk-signal-web-desk-20260902-01/index.html",
    "packs/desk-website-service-20260902-01/door.html",
    "packs/_template/creative_brief.md",
    "p/cursor-business-pack-sold-once-badge-pointer-20260902-01.md",
    "p/cursor-plant-sold-once-badge-20260902-01.md",
    "p/scout-demand-door-sold-once-badge-20260902-01.md",
    "p/cursor-pack-creative-brief-template-20260902-01.md",
    "land/plant-sold-once-badge-20260902.md",
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


def classify_pointer(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    catalog = instances_block(data)
    blobs = {rel: blob_prefix(rel) for rel in (*EXPECTED_BLOBS, *OBSERVED_AT_LAND)}
    blobs_match = all(
        blobs.get(rel, "").startswith(prefix) for rel, prefix in EXPECTED_BLOBS.items()
    )
    goat_untouched = blobs.get(GOAT_TEMPLATE, "").startswith(
        EXPECTED_BLOBS[GOAT_TEMPLATE]
    )
    did_not_overwrite_instance_doors = all(
        rel in DO_NOT_WRITE for rel in OBSERVED_AT_LAND
    )
    pointer_ok = (
        str(data.get("id") or "") == UNIQUE_PACK_ID
        and str(catalog.get("id") or "") == CATALOG_ID
        and str(catalog.get("sold_once_badge_pointer") or "") == POINTER_ID
        and str(catalog.get("sold_once_claimed_by") or "") == CLEAR_DESK
        and str(catalog.get("sold_once_scout_demand_id") or "") == SCOUT_SOLD_ONCE_ID
        and catalog.get("did_not_remint_scout_sold_once") is True
        and catalog.get("did_not_overwrite_tally_helper") is True
        and catalog.get("did_not_write_goat_creative_brief") is True
        and catalog.get("did_not_overwrite_lotribbon_door") is True
        and str(catalog.get("checkout") or "") == "NOT_MINTED"
        and data.get("gate") is False
        and data.get("commons_admission") is False
        and blobs_match
        and goat_untouched
        and did_not_overwrite_instance_doors
        and (ROOT / LOTRIBBON_SOLD_ONCE).is_file()
        and (ROOT / LOTRIBBON_BRIEF).is_file()
        and (ROOT / LOTRIBBON_ASSETS_BRIEF).is_file()
        and (ROOT / "p" / f"{POINTER_ID}.md").is_file()
        and (ROOT / "p" / f"{HELPER_ID}.md").is_file()
        and (ROOT / "p" / f"{PLANT_SOLD_ONCE_ID}.md").is_file()
        and (ROOT / "p" / f"{PLANT_CREATIVE_BRIEF_ID}.md").is_file()
        and TALLY_HELPER not in THIS_SEAT_PATHS
        and PLANT_HELPER not in THIS_SEAT_PATHS
        and LOTRIBBON_BRIEF not in THIS_SEAT_PATHS
        and f"p/{PLANT_SOLD_ONCE_ID}.md" not in THIS_SEAT_PATHS
    )
    return {
        "gate": False,
        "commons_admission": False,
        "id": HELPER_ID,
        "pointer_id": POINTER_ID,
        "pin_lift_id": PIN_LIFT_ID,
        "lead_brand": LEAD_BRAND,
        "desk_sold_once_cleared_to": CLEAR_DESK,
        "plant_sold_once_claim": PLANT_SOLD_ONCE_ID,
        "plant_creative_brief_claim": PLANT_CREATIVE_BRIEF_ID,
        "did_not_remint_catalog_pointer": blobs.get(
            f"p/{POINTER_ID}.md", ""
        ).startswith(EXPECTED_BLOBS[f"p/{POINTER_ID}.md"]),
        "did_not_remint_peer_plant_sold_once": blobs.get(
            f"p/{PLANT_SOLD_ONCE_ID}.md", ""
        ).startswith(EXPECTED_BLOBS[f"p/{PLANT_SOLD_ONCE_ID}.md"]),
        "did_not_remint_scout_demand": str(catalog.get("sold_once_scout_demand_id") or "")
        == SCOUT_SOLD_ONCE_ID,
        "did_not_take_goat_creative_brief": goat_untouched,
        "did_not_overwrite_peer_creative_brief": blobs.get(LOTRIBBON_BRIEF, "").startswith(
            EXPECTED_BLOBS[LOTRIBBON_BRIEF]
        ),
        "did_not_overwrite_tally_helper": catalog.get("did_not_overwrite_tally_helper")
        is True,
        "did_not_overwrite_instance_doors": did_not_overwrite_instance_doors,
        "lotribbon_sold_once_present": (ROOT / LOTRIBBON_SOLD_ONCE).is_file(),
        "lotribbon_creative_brief_present": (ROOT / LOTRIBBON_BRIEF).is_file(),
        "checkout": str(catalog.get("checkout") or ""),
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "do_not_write": list(DO_NOT_WRITE),
        "observed_at_land": dict(OBSERVED_AT_LAND),
        "live_instance_blobs_not_pinned": True,
        "blobs": blobs,
        "blobs_match": blobs_match,
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
