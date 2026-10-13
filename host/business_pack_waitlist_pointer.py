#!/usr/bin/env python3
"""Classify the unique-pack waitlist pointer. Not a Commons gate.

The CLAIM id cursor-business-pack-waitlist-pointer-20260902-01 is
already on current main. Waitlist files are CLEARED to bc-31c8ef9a.
This helper reads that pointer only. It does not write
packs/waitlist.html and does not remint the SCOUT demand id.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACKS.json"
POINTER_ID = "cursor-business-pack-waitlist-pointer-20260902-01"
UNIQUE_PACK_ID = "cursor-business-packs-unique-20260902-01"
SCOUT_DEMAND_ID = "scout-demand-pack-door-waitlist-20260902-01"
FILES_OWNER = "bc-31c8ef9a"
DEFAULT_WAITLIST_FILES = (
    "packs/waitlist.html",
    "packs/_template/waitlist-slot.md",
    "ground/BUSINESS_PACK_WAITLIST.json",
    "host/pack_waitlist.py",
    "test_pack_waitlist.py",
    "p/scout-demand-pack-door-waitlist-20260902-01.md",
    "land/pack-waitlist-20260902.md",
)


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def waitlist_block(law: dict[str, Any]) -> dict[str, Any]:
    for key in ("waitlist", "waitlist_pointer"):
        block = law.get(key)
        if isinstance(block, dict):
            return block
    return {}


def classify_pointer(law: dict[str, Any] | None = None) -> dict[str, Any]:
    data = law if isinstance(law, dict) else load_law()
    block = waitlist_block(data)
    files_owner = str(block.get("files_owner") or block.get("claimed_by") or "").strip()
    did_not_write = (
        block.get("did_not_write_waitlist_html") is True
        or block.get("did_not_write_waitlist_paths") is True
    )
    waitlist_files = block.get("peer_waitlist_paths")
    if not isinstance(waitlist_files, list) or not waitlist_files:
        waitlist_files = list(DEFAULT_WAITLIST_FILES)
    waitlist_files = [str(item) for item in waitlist_files]
    return {
        "gate": False,
        "commons_admission": False,
        "id": str(block.get("id") or ""),
        "unique_pack_id": str(data.get("id") or ""),
        "scout_demand_id": str(block.get("scout_demand_id") or ""),
        "did_not_remint_scout_demand": block.get("did_not_remint_scout_demand") is True,
        "files_owner": files_owner,
        "files_cleared_to_bc_31c8ef9a": files_owner == FILES_OWNER,
        "did_not_write_waitlist_html": did_not_write,
        "waitlist_door": str(block.get("waitlist_door") or block.get("door") or ""),
        "waitlist_slot": str(block.get("waitlist_slot") or ""),
        "excluded_state_shows": str(block.get("excluded_state_shows") or "waitlist_not_checkout"),
        "zero_sends": True,
        "no_auth": True,
        "checkout": str(block.get("checkout") or ""),
        "agents_spend_ads": block.get("agents_spend_ads") is True,
        "no_fake_stripe_urls": block.get("no_fake_stripe_urls") is not False,
        "owner_files_present": [rel for rel in waitlist_files if (ROOT / rel).is_file()],
        "owner_files_absent": [rel for rel in waitlist_files if not (ROOT / rel).is_file()],
        "pointer_ok": (
            str(block.get("id") or "") == POINTER_ID
            and str(data.get("id") or "") == UNIQUE_PACK_ID
            and str(block.get("scout_demand_id") or "") == SCOUT_DEMAND_ID
            and files_owner == FILES_OWNER
            and did_not_write
            and block.get("did_not_remint_scout_demand") is True
            and str(block.get("checkout") or "") == "NOT_MINTED"
            and data.get("gate") is False
            and data.get("commons_admission") is False
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
