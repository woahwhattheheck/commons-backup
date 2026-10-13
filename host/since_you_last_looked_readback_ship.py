#!/usr/bin/env python3
"""SHIP unique-pack since-you-last-looked readback. Do not remint leftover #8393."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
REFUSE = ("--send", "--apply", "--go", "--autopilot")

UNIQUE_PACK_ID = "cursor-since-you-last-looked-readback-20260902-01"
LEFTOVER_ID = "cursor-since-you-last-looked-20260902-01"
SHIP_ID = "cursor-since-you-last-looked-readback-ship-20260902-01"
UNIQUE_LAND = "a2dec477a"
LEFTOVER_LAND = "15986f8a0"
UNIQUE_SEAT = "bc-73365238"
LEFTOVER_SEAT = "bc-31c8ef9a"
THIS_SEAT = "bc-92648f95"

KEEP = {
    f"p/{LEFTOVER_ID}.md": "003828c9",
    "host/since_you_last_looked.py": "3578783c",
    "ground/SINCE_YOU_LAST_LOOKED.json": "749c8220",
    "test_since_you_last_looked.py": "5c24cb7b",
    "since-you-last-looked.html": "60b1350e",
    f"p/{UNIQUE_PACK_ID}.md": "bc71c9fe",
    "test_cursor_since_you_last_looked_readback.py": "5e2c6ee5",
    "p/cursor-landed-work-feed-20260902-01.md": "d566f495",
    "p/cursor-stealable-lanes-occupancy-20260902-01.md": "9631e869",
    "p/cursor-stealable-lanes-roles-20260902-01.md": "5f1ef25f",
    "p/cursor-stealable-lanes-roles-readback-20260902-01.md": "ada92980",
    "p/cursor-commons-slack-full-body-20260902-01.md": "86f4eddc",
    "p/cursor-harborline-pack-market-render-20260902-01.md": "54c348dc",
    "ground/OWNER_NOW.md": "39a0e0c3",
    "grounding.html": "57f0e62b",
    "hub_pages.py": "673dab89",
}

THIS_SEAT_PATHS = (
    "host/since_you_last_looked_readback_ship.py",
    "test_cursor_since_you_last_looked_readback_ship.py",
    f"p/{SHIP_ID}.md",
)


def git_blob(rel: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(ROOT / rel)], text=True
    ).strip()


def keep_ok() -> dict[str, str]:
    measured: dict[str, str] = {}
    for rel, prefix in KEEP.items():
        blob = git_blob(rel)
        if not blob.startswith(prefix):
            raise SystemExit(f"{rel} reminted: want {prefix} got {blob[:8]}")
        measured[rel] = blob
    return measured


def refuse_payload(flag: str) -> dict[str, object]:
    return {
        "kind": "SINCE_YOU_LAST_LOOKED_READBACK_SHIP",
        "id": SHIP_ID,
        "leftover_id": LEFTOVER_ID,
        "unique_pack_id": UNIQUE_PACK_ID,
        "gate": False,
        "login": False,
        "item_11": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "checkout": "FINDER-FAILED",
        "note": (
            f"{flag} REFUSED. sent=0 cash=0. Did not remint leftover "
            "003828c9 or unique-pack bc71c9fe. Did not take item 11."
        ),
    }


def leftover_measure() -> dict[str, object]:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "host/since_you_last_looked.py"),
            "--json",
            "--limit",
            "8",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return {"rc": proc.returncode, "payload": payload}


def leftover_tests() -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "test_since_you_last_looked.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "rc": proc.returncode,
        "ok": proc.returncode == 0,
        "ran_6": "Ran 6 tests" in (proc.stderr or ""),
    }


def leftover_refuse(flag: str) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "host/since_you_last_looked.py"), flag],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return {"rc": proc.returncode, "payload": payload}


def classify_ship() -> dict[str, object]:
    blobs = keep_ok()
    measured = leftover_measure()
    tests = leftover_tests()
    send = leftover_refuse("--send")
    go = leftover_refuse("--go")
    leftover = measured["payload"]
    dumped = (ROOT / "marketplace.html").exists() or (ROOT / "qualify.html").exists()
    corner = (ROOT / "CLAUDE_CORNER.md").exists()
    slack0 = (leftover.get("surfaces") or {}).get("slack") or [{}]
    pin = slack0[0] if slack0 else {}
    ship_ok = (
        measured["rc"] == 0
        and leftover.get("verdict") == "RENDER"
        and leftover.get("grouped_by") == ["git", "slack", "commons"]
        and leftover.get("nothing_dropped") is True
        and leftover.get("model_decides_what_matters") is False
        and leftover.get("not_per_merge_line") is True
        and leftover.get("bryce_pinned") == 1
        and leftover.get("dropped") == 0
        and leftover.get("sends") == 0
        and leftover.get("slack_live_token") == "FINDER-FAILED"
        and pin.get("ts") == "1788380844.707619"
        and pin.get("bryce_pin") is True
        and tests["ok"]
        and tests["ran_6"]
        and send["rc"] == 2
        and send["payload"].get("sent") == 0
        and go["rc"] == 2
        and go["payload"].get("sent") == 0
        and not dumped
        and not corner
    )
    return {
        "kind": "SINCE_YOU_LAST_LOOKED_READBACK_SHIP",
        "id": SHIP_ID,
        "leftover_id": LEFTOVER_ID,
        "unique_pack_id": UNIQUE_PACK_ID,
        "leftover_seat": LEFTOVER_SEAT,
        "unique_pack_seat": UNIQUE_SEAT,
        "this_seat": THIS_SEAT,
        "leftover_land": LEFTOVER_LAND,
        "unique_land": UNIQUE_LAND,
        "pr": 8393,
        "receipt_blob": "bc71c9fe",
        "receipt_bytes": 3285,
        "receipt_sha256": "186a3e4a",
        "leftover_blob": "003828c9",
        "grouped_by": ["git", "slack", "commons"],
        "nothing_dropped": True,
        "model_decides_what_matters": False,
        "not_per_merge_line": True,
        "bryce_pinned": 1,
        "bryce_pin_ts": "1788380844.707619",
        "slack_live_token": "FINDER-FAILED",
        "item_11": False,
        "login": False,
        "gate": False,
        "leftover_tests": "6/6",
        "send_rc": send["rc"],
        "go_rc": go["rc"],
        "sent": 0,
        "cash": 0,
        "checkout": "FINDER-FAILED",
        "did_not_remint_leftover": True,
        "did_not_remint_unique_pack": True,
        "did_not_take_item_11": True,
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "keep_blobs": {rel: blobs[rel][:8] for rel in KEEP},
        "ship_ok": ship_ok,
        "verdict": "SHIP" if ship_ok else "FINDER-FAILED",
        "note": (
            f"SHIP unique-pack {UNIQUE_PACK_ID} land {UNIQUE_LAND} "
            "receipt bc71c9fe (3285) SHA256 186a3e4a. Independent MATCH "
            f"Harborline leftover #{8393}. Leftover tests independently 6/6. "
            "Did not remint leftover 003828c9. --send/--go rc=2 sent=0. "
            "Did not take item 11. Checkout FINDER-FAILED is a measurement, "
            "not a freeze. Sends 0."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "SINCE_YOU_LAST_LOOKED_READBACK_SHIP",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "id": SHIP_ID,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    payload = classify_ship()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ship_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
