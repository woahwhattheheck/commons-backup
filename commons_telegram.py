#!/usr/bin/env python3
"""Lightweight Commons <-> Telegram operator CLI (stdlib only).

Sibling of ``commons_discord.py``. Composes ``telegram_ingest.py`` instead of
inventing a second protocol.

    python3 commons_telegram.py doctor
    python3 commons_telegram.py from-telegram format event.json
    python3 commons_telegram.py from-telegram plan export.json
    python3 commons_telegram.py sync-in

Event path: format one webhook Update. Slack #commons stays the table.
Invite link is authorization. No seats. Missing token → format/plan still work;
sync is DARK.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import telegram_ingest


def _present(*names: str) -> bool:
    return any(bool(os.environ.get(name, "").strip()) for name in names)


def _lane(state: bool, missing: list[str], transport: str) -> dict[str, Any]:
    return {
        "state": "READY" if state else "DARK",
        "transport": transport,
        "missing": [] if state else missing,
    }


def doctor() -> dict[str, Any]:
    token = _present("TELEGRAM_BOT_TOKEN", "COMMONS_TELEGRAM_BOT_TOKEN")
    inbound_missing = [] if token else ["TELEGRAM_BOT_TOKEN"]
    overall = "READY" if token else "DARK"
    return {
        "state": overall,
        "telegram_to_commons": _lane(
            token,
            inbound_missing,
            "Telegram Update webhook -> format -> label=board GitHub issue",
        ),
        "format_plan": {"state": "READY", "transport": "offline JSON, no token"},
        "invite": "https://t.me/+rbbklgtbu7lkYWFh",
        "table": "Slack #commons C0BRGMDQB6G",
        "ingest": "telegram_ingest.py",
        "did_not_remint": "commons-peers-telegram-20260829-01",
    }


def parser() -> argparse.ArgumentParser:
    out = argparse.ArgumentParser(description=__doc__)
    sub = out.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="show readiness without exposing secrets")
    inbound = sub.add_parser("from-telegram", help="format or plan Telegram events")
    inbound.add_argument("mode", choices=("format", "plan"))
    inbound.add_argument("events", type=Path)
    sub.add_parser("sync-in", help="pull getUpdates and create canonical board issues")
    return out


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(doctor(), indent=2))
        return 0
    if args.command == "from-telegram":
        if args.mode == "format":
            return telegram_ingest.cmd_format(args.events)
        return telegram_ingest.cmd_plan(args.events)
    return telegram_ingest.cmd_sync()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except telegram_ingest.IngestError as exc:
        print("INGEST_ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
