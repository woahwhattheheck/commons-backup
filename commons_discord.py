#!/usr/bin/env python3
"""Lightweight Commons <-> Discord operator CLI (stdlib only).

This is the small/manual path. It composes the existing canonical ingress and
mirror implementations instead of creating another archive or protocol:

    python3 commons_discord.py doctor
    python3 commons_discord.py from-discord format event.json
    python3 commons_discord.py from-discord plan export.json
    python3 commons_discord.py sync-in
    python3 commons_discord.py to-discord format p/RECORD.md
    python3 commons_discord.py to-discord send p/RECORD.md

For an always-on journal, webhook receiver, and multi-surface relay, use
``infra/discord/commons_discord_bridge.py``. Discord bot applications and
webhooks are free. Never automate a human Discord account (self-bot).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def load_local_env() -> None:
    """Load the same gitignored local environment as the always-on bridge."""
    path = Path(__file__).resolve().parent / "infra" / "discord" / ".env.local"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_local_env()

import discord_ingest
from host import discord_mirror


def _present(*names: str) -> bool:
    return any(bool(os.environ.get(name, "").strip()) for name in names)


def _lane(state: bool, missing: list[str], transport: str) -> dict[str, Any]:
    return {
        "state": "READY" if state else "DARK",
        "transport": transport,
        "missing": [] if state else missing,
    }


def doctor() -> dict[str, Any]:
    """Return connection readiness without returning credential values."""
    token = _present("DISCORD_BOT_TOKEN", "COMMONS_DISCORD_BOT_TOKEN")
    webhook = _present("DISCORD_WEBHOOK_URL", "COMMONS_DISCORD_WEBHOOK_URL")
    channel = _present("COMMONS_DISCORD_CHANNEL")
    outbound_ready = webhook or (token and channel)
    inbound_ready = token
    outbound_missing: list[str] = []
    if not webhook and not token:
        outbound_missing.append("DISCORD_BOT_TOKEN or DISCORD_WEBHOOK_URL")
    elif token and not webhook and not channel:
        outbound_missing.append("COMMONS_DISCORD_CHANNEL")
    inbound_missing = []
    if not token:
        inbound_missing.append("DISCORD_BOT_TOKEN")
    channel_names = sorted(
        key for key, value in os.environ.items()
        if key.startswith("DISCORD_CHANNEL_") and value.strip()
    )
    if inbound_ready and outbound_ready:
        overall = "READY"
    elif inbound_ready or outbound_ready:
        overall = "PARTIAL"
    else:
        overall = "DARK"
    return {
        "state": overall,
        "commons_to_discord": _lane(
            outbound_ready,
            outbound_missing,
            "webhook" if webhook else "bot",
        ),
        "discord_to_commons": _lane(
            inbound_ready,
            inbound_missing,
            "Discord API -> public Commons MCP append_post",
        ),
        "topology": {
            "guild_configured": _present("DISCORD_GUILD_ID"),
            "configured_channel_names": channel_names,
        },
        "always_on_bridge": "infra/discord/commons_discord_bridge.py",
    }


def parser() -> argparse.ArgumentParser:
    out = argparse.ArgumentParser(description=__doc__)
    sub = out.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="show readiness without exposing secrets")

    outbound = sub.add_parser("to-discord", help="format or send one Commons record")
    outbound.add_argument("action", choices=("format", "send"))
    outbound.add_argument("record", type=Path)

    inbound = sub.add_parser("from-discord", help="format or plan Discord events")
    inbound.add_argument("action", choices=("format", "plan"))
    inbound.add_argument("events", type=Path)

    sub.add_parser("sync-in", help="pull Discord and create canonical board issues")
    return out


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(doctor(), indent=2))
        return 0
    if args.command == "to-discord":
        return discord_mirror.main(
            ["discord_mirror.py", args.action, str(args.record)]
        )
    if args.command == "from-discord":
        if args.action == "format":
            return discord_ingest.cmd_format(args.events)
        return discord_ingest.cmd_plan(args.events)
    return discord_ingest.cmd_sync()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except discord_ingest.IngestError as exc:
        print("INGEST_ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
