#!/usr/bin/env python3
"""Harborline composes against TALLY's shared desk-instance helper.

SCOUT: two unique DESK instances are legal under similar-not-clone when
fingerprints differ and the shared helper stays single-owner. TALLY owns
host/business_pack_desk_instance.py. This leftover does not overwrite that
file, does not remint Harborline instance bytes, and does not steal
Sidewalk Signal paths.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PEER_HELPER = ROOT / "host" / "business_pack_desk_instance.py"
HARBORLINE = ROOT / "packs" / "desk-website-service-20260902-01"
DO_NOT_OVERWRITE = (
    "host/business_pack_desk_instance.py",
    "test_business_pack_desk_instance.py",
    "packs/sidewalk-signal-web-desk-20260902-01",
)


def load_peer(path: Path | None = None) -> Any | None:
    target = path or PEER_HELPER
    if not target.is_file():
        return None
    spec = importlib.util.spec_from_file_location("business_pack_desk_instance", target)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compose(peer_path: Path | None = None, pack_dir: Path | None = None) -> dict[str, Any]:
    folder = pack_dir or HARBORLINE
    peer = load_peer(peer_path)
    door = folder / "door.html"
    door_text = door.read_text(encoding="utf-8") if door.is_file() else ""
    copy_verdict = ""
    if peer is not None and hasattr(peer, "_load_unique"):
        unique = peer._load_unique()
        copy_verdict = unique.classify_copy(door_text)["verdict"]
        verdict = "COMPOSE_OK" if copy_verdict == "COPY_OK" and door_text else "COMPOSE_COPY_FAIL"
    elif peer is None:
        verdict = "COMPOSE_PEER_MISSING"
    else:
        verdict = "COMPOSE_PEER_NO_UNIQUE"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "peer_helper": "host/business_pack_desk_instance.py",
        "peer_helper_present": peer is not None,
        "shared_helper_single_owner": "tally",
        "harborline_instance": "packs/desk-website-service-20260902-01",
        "did_not_overwrite_peer": True,
        "did_not_remint_harborline_instance": True,
        "copy_via_peer": copy_verdict,
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "checkout": "NOT_MINTED",
        "agents_spend_ads": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer", default="")
    parser.add_argument("--pack-dir", default="")
    args = parser.parse_args(argv)
    result = compose(
        peer_path=Path(args.peer) if args.peer else None,
        pack_dir=Path(args.pack_dir) if args.pack_dir else None,
    )
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
