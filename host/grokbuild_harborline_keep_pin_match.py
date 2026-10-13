#!/usr/bin/env python3
"""MATCH Harborline KEEP-pins to live pack-map a7a49b77 after PR #8306.

Lawful leftover grokbuild-tests-battery-never-say-opportunity-20260902-01
reminted host/harborline_tally_pack_map.py a889db44 -> a7a49b77 and
test_harborline_tally_pack_map.py 1cca2d9b -> 68b4fce1. KEEP-pin helpers
had frozen the old prefixes, so pointer_ok / rating tree went red.

This leftover MATCHES live pins. It does not remint peer leftover
receipts, Harborline door, waitlist, unique-pack, autogtm.html,
boards.html, or the pack-map leftover itself. KEEP MAIN #7754.
Checkout NOT_MINTED. Not a Commons gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "host"))

import business_pack_harborline_map_helper_pointer as map_helper_pointer  # noqa: E402
import business_pack_harborline_tally_map as sidecar  # noqa: E402
import business_pack_harborline_tally_map_pointer as map_pointer  # noqa: E402
import pack_harborline_rating as harborline_rating  # noqa: E402
import pack_harborline_waitlist_slot as waitlist_slot  # noqa: E402
import pack_lotribbon_rating as lotribbon_rating  # noqa: E402

RECEIPT_ID = "grokbuild-harborline-keep-pin-match-20260902-01"
NEVER_SAY_ID = "grokbuild-tests-battery-never-say-opportunity-20260902-01"
KEEP_MAIN_PR = 7754
PACK_MAP = "host/harborline_tally_pack_map.py"
PACK_MAP_BLOB = "a7a49b77"
PACK_MAP_TEST = "test_harborline_tally_pack_map.py"
PACK_MAP_TEST_BLOB = "68b4fce1"
DOOR = "packs/desk-website-service-20260902-01/door.html"
DOOR_BLOB = "cd2be48f"
WAITLIST = "packs/waitlist.html"
WAITLIST_BLOB = "b312ed6d"
SIDECAR = "host/business_pack_harborline_tally_map.py"
SIDECAR_BLOB = "6a02ec32"
MAP_POINTER = "host/business_pack_harborline_tally_map_pointer.py"
MAP_POINTER_BLOB = "90b0ae68"
MAP_HELPER_POINTER = "host/business_pack_harborline_map_helper_pointer.py"
MAP_HELPER_POINTER_BLOB = "22059ca4"
PEER_RECEIPTS = {
    "p/cursor-business-pack-harborline-map-helper-pointer-20260902-01.md": "269e874a",
    "p/cursor-business-pack-harborline-tally-map-pointer-20260902-01.md": "e38f1251",
    "p/cursor-business-pack-harborline-tally-map-pointer-helper-20260902-01.md": "6ec23344",
    "p/cursor-pack-harborline-map-pin-lift-20260902-01.md": "8fe8a002",
    "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md": "7a8987b5",
    "p/cursor-pack-harborline-rating-20260902-01.md": "29930d8b",
    "p/cursor-pack-harborline-waitlist-slot-20260902-01.md": "4b648caf",
    "p/cursor-business-pack-sidewalk-lotribbon-waitlist-pointer-20260902-01.md": "2c584983",
}
THIS_SEAT_DOES_NOT_WRITE = (
    PACK_MAP,
    PACK_MAP_TEST,
    DOOR,
    WAITLIST,
    "packs/desk-website-service-20260902-01/door.html",
    "autogtm.html",
    "boards.html",
    "ground/BUSINESS_PACKS.json",
    *PEER_RECEIPTS,
)


def git_blob_prefix(rel: str, n: int = 8) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()[:n]


def classify_match() -> dict[str, Any]:
    blobs = {
        PACK_MAP: git_blob_prefix(PACK_MAP),
        PACK_MAP_TEST: git_blob_prefix(PACK_MAP_TEST),
        DOOR: git_blob_prefix(DOOR),
        WAITLIST: git_blob_prefix(WAITLIST),
        SIDECAR: git_blob_prefix(SIDECAR),
        MAP_POINTER: git_blob_prefix(MAP_POINTER),
        MAP_HELPER_POINTER: git_blob_prefix(MAP_HELPER_POINTER),
        **{rel: git_blob_prefix(rel) for rel in PEER_RECEIPTS},
    }
    live_match = (
        blobs[PACK_MAP] == PACK_MAP_BLOB
        and blobs[PACK_MAP_TEST] == PACK_MAP_TEST_BLOB
        and blobs[DOOR] == DOOR_BLOB
        and blobs[WAITLIST] == WAITLIST_BLOB
        and blobs[SIDECAR] == SIDECAR_BLOB
        and blobs[MAP_POINTER] == MAP_POINTER_BLOB
        and blobs[MAP_HELPER_POINTER] == MAP_HELPER_POINTER_BLOB
    )
    receipts_unread = all(blobs.get(rel) == prefix for rel, prefix in PEER_RECEIPTS.items())
    helper_out = map_helper_pointer.classify_pointer()
    sidecar_out = sidecar.classify_pointer()
    pointer_out = map_pointer.classify_pointer()
    rating_out = harborline_rating.classify_tree()
    waitlist_out = waitlist_slot.classify_tree()
    lotribbon_out = lotribbon_rating.classify_tree()
    keep_main = helper_out.get("keep_main") is True and helper_out.get("keep_main_pr") == KEEP_MAIN_PR
    pointer_ok = (
        helper_out.get("pointer_ok") is True
        and sidecar_out.get("pointer_ok") is True
        and pointer_out.get("pointer_ok") is True
    )
    rating_ok = rating_out.get("verdict") == "HARBORLINE_RATING_OK"
    waitlist_ok = waitlist_out.get("verdict") == "HARBORLINE_WAITLIST_SLOT_OK"
    lotribbon_ok = lotribbon_out.get("verdict") == "LOTRIBBON_RATING_OK"
    never_say = (ROOT / "p" / f"{NEVER_SAY_ID}.md").is_file()
    receipt = (ROOT / "p" / f"{RECEIPT_ID}.md").is_file()
    match_ok = (
        live_match
        and receipts_unread
        and pointer_ok
        and rating_ok
        and waitlist_ok
        and lotribbon_ok
        and keep_main
        and never_say
        and receipt
        and helper_out.get("checkout") == "NOT_MINTED"
    )
    return {
        "gate": False,
        "commons_admission": False,
        "no_auth": True,
        "id": RECEIPT_ID,
        "kind": "HARBORLINE_KEEP_PIN_MATCH",
        "pack_map": PACK_MAP,
        "pack_map_blob": blobs[PACK_MAP],
        "pack_map_test_blob": blobs[PACK_MAP_TEST],
        "did_not_remint_pack_map": blobs[PACK_MAP] == PACK_MAP_BLOB,
        "did_not_remint_peer_receipts": receipts_unread,
        "did_not_overwrite_harborline_door": blobs[DOOR] == DOOR_BLOB,
        "did_not_overwrite_waitlist": blobs[WAITLIST] == WAITLIST_BLOB,
        "keep_main": keep_main,
        "keep_main_pr": KEEP_MAIN_PR,
        "pointer_ok": pointer_ok,
        "rating_verdict": rating_out.get("verdict"),
        "waitlist_verdict": waitlist_out.get("verdict"),
        "lotribbon_verdict": lotribbon_out.get("verdict"),
        "never_say_leftover_present": never_say,
        "blobs": blobs,
        "this_seat_does_not_write": list(THIS_SEAT_DOES_NOT_WRITE),
        "checkout": "NOT_MINTED",
        "sends": 0,
        "agents_spend_ads": False,
        "match_ok": match_ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="classify")
    args = parser.parse_args(argv)
    print(json.dumps(classify_match(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
