#!/usr/bin/env python3
"""SHIP leftover pack-market render. Do not remint leftover or Slack Steam card."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFUSE = ("--send", "--apply", "--go", "--autopilot")
DUMP = ("--dump-commons", "--marketplace-html")

LEFTOVER_ID = "cursor-harborline-pack-market-render-20260902-01"
READBACK_ID = "cursor-harborline-pack-market-render-readback-20260902-01"
SLACK_ID = "cursor-harborline-pack-market-slack-render-20260902-01"
SHIP_ID = "cursor-harborline-pack-market-render-ship-20260902-01"
LAND = "0141bf7c8"
SLACK_LAND = "7a922545a"
PR = 8345
SLACK_PR = 8350

KEEP = {
    f"p/{LEFTOVER_ID}.md": "54c348dc",
    "host/harborline_pack_market_render.py": "cc9a3320",
    f"p/{READBACK_ID}.md": "6efbac54",
    f"p/{SLACK_ID}.md": "0d95f2ab",
    "host/harborline_pack_market_slack_render.py": "a03534da",
    "p/cursor-harborline-pack-market-render-readback-rematch-20260902-01.md": "f965e00f",
    "p/cursor-harborline-pack-market-render-readback-ack-20260902-01.md": "9d221c75",
    "ground/OWNER_NOW.md": "39a0e0c3",
}

THIS_SEAT_PATHS = (
    "host/harborline_pack_market_render_ship.py",
    "test_harborline_pack_market_render_ship.py",
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
        "store": "standalone",
        "desk_route": "/market",
        "commons_is_store": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "booked": 0,
        "cash": 0,
        "checkout": "FINDER-FAILED",
        "leftover_id": LEFTOVER_ID,
        "slack_id": SLACK_ID,
        "id": SHIP_ID,
        "note": (
            f"{flag} REFUSED. sent=0 booked=0 cash=0. "
            "Did not remint leftover or Slack Steam card. "
            "Did not dump a store HTML door onto Commons."
        ),
    }


def classify_ship() -> dict[str, object]:
    blobs = keep_ok()
    dumped = (ROOT / "marketplace.html").exists()
    leftover = subprocess.run(
        [sys.executable, str(ROOT / "host/harborline_pack_market_render.py"), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    slack = subprocess.run(
        [sys.executable, str(ROOT / "host/harborline_pack_market_slack_render.py"), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    leftover_payload = json.loads(leftover.stdout) if leftover.returncode == 0 else {}
    slack_payload = json.loads(slack.stdout) if slack.returncode == 0 else {}
    ship_ok = (
        leftover.returncode == 0
        and slack.returncode == 0
        and leftover_payload.get("verdict") == "RENDER"
        and leftover_payload.get("price_usd") == 200
        and leftover_payload.get("checkout") == "FINDER-FAILED"
        and leftover_payload.get("commons_is_store") is False
        and slack_payload.get("verdict") == "SLACK_RENDER"
        and slack_payload.get("price_usd") == 200
        and slack_payload.get("surface") == "slack"
        and not dumped
    )
    return {
        "store": "standalone",
        "desk_route": "/market",
        "commons_is_store": False,
        "marketplace_html_on_commons": dumped,
        "featured": "Harborline Local Sites",
        "price_usd": 200,
        "odds": 0,
        "checkout": "FINDER-FAILED",
        "sent": 0,
        "booked": 0,
        "cash": 0,
        "leftover_id": LEFTOVER_ID,
        "readback_id": READBACK_ID,
        "slack_id": SLACK_ID,
        "id": SHIP_ID,
        "land": LAND,
        "slack_land": SLACK_LAND,
        "pr": PR,
        "slack_pr": SLACK_PR,
        "ship_ok": ship_ok,
        "did_not_remint_leftover": True,
        "did_not_remint_readback": True,
        "did_not_remint_slack_render": True,
        "this_seat_paths": list(THIS_SEAT_PATHS),
        "keep_blobs": {rel: blobs[rel][:8] for rel in KEEP},
        "verdict": "SHIP" if ship_ok else "FINDER-FAILED",
        "note": (
            "SHIP leftover cursor-harborline-pack-market-render-20260902-01 "
            f"land {LAND} #{PR}. Peer Slack Steam card {SLACK_ID} land {SLACK_LAND} "
            f"#{SLACK_PR} KEEP unread. Commons is not the store. "
            "Stripe FINDER-FAILED; empty is not a freeze. Sends 0."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE or flag in DUMP:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "store": "standalone",
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
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["ship_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
