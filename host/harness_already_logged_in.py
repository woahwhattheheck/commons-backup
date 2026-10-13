#!/usr/bin/env python3
"""Desk disposition after owner pulse 1788325660.929309.

GitHub is already logged in (woahwhattheheck). One failed GitHub tool
call is CALL_PATH_RATE_LIMIT_OR_SCOPE, not NO_PERMS and not a login ask.
Slack CLI /svctool install is leftover, not a freeze. Do not post
/slackauthticket unless Bryce sends the challenge unprompted.

Does not remint the Slack CLI project, install land, or ticket emitter.
Does not consume peer tickets 1788321773.338029 / 1788325362.867019.
Not a Commons admission gate. 337 NO.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "ground" / "HARNESS_ALREADY_LOGGED_IN.json"
SOURCE_SLACK_TS = "1788325660.929309"
GITHUB_LOGIN = "woahwhattheheck"
GITHUB_ID = 293286387
SHIP_ROADS = ("slack_mcp", "github_mcp")
PEER_TICKETS = ("1788321773.338029", "1788325362.867019")
CHALLENGE_RE = re.compile(r"^[A-Za-z0-9-]{4,16}$")


def load_card(path: Path | None = None) -> dict[str, Any]:
    target = path or CARD
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("card is not an object")
    return data


def github_identity() -> dict[str, Any]:
    return {
        "login": GITHUB_LOGIN,
        "id": GITHUB_ID,
        "state": "LOGGED_IN",
        "ask_github_login": False,
        "park": False,
        "source_slack_ts": SOURCE_SLACK_TS,
        "commons_admission": False,
        "gate": False,
    }


def classify_github_tool_failure(exc_or_text: Any = "") -> dict[str, Any]:
    """One failed GitHub tool call is not missing login."""
    blob = str(exc_or_text or "").strip()
    return {
        "kind": "CALL_PATH_RATE_LIMIT_OR_SCOPE",
        "not": "NO_PERMS",
        "ask_github_login": False,
        "park": False,
        "keep_shipping": True,
        "roads": list(SHIP_ROADS),
        "observed": blob[:240],
        "source_slack_ts": SOURCE_SLACK_TS,
        "commons_admission": False,
    }


def slack_cli_svctool_leftover() -> dict[str, Any]:
    return {
        "status": "LEFTOVER_NOT_FREEZE",
        "install": "optional",
        "freeze": False,
        "park": False,
        "post_slackauthticket": False,
        "unless": "owner_sends_challenge_unprompted",
        "do_not_consume_tickets": list(PEER_TICKETS),
        "keep_shipping_roads": list(SHIP_ROADS),
        "commons_admission": False,
        "gate": False,
        "fire_337": False,
    }


def may_post_slackauthticket(unprompted_challenge: str = "") -> bool:
    """False unless Bryce sent the challenge unprompted.

    A challenge is the short modal code, not a /slackauthticket line and
    not a login ticket. Empty, ticket-shaped, or overlong input stays false.
    """
    code = str(unprompted_challenge or "").strip()
    if not code:
        return False
    if code.startswith("/slackauthticket"):
        return False
    if " " in code:
        return False
    if len(code) > 16:
        return False
    return bool(CHALLENGE_RE.fullmatch(code))


def desk_disposition(
    github_error: str = "",
    unprompted_challenge: str = "",
) -> dict[str, Any]:
    ticket_ok = may_post_slackauthticket(unprompted_challenge)
    failure = classify_github_tool_failure(github_error) if github_error else None
    return {
        "id": "cursor-ack-github-logged-in-20260902-01",
        "source_slack_ts": SOURCE_SLACK_TS,
        "github": github_identity(),
        "github_tool_failure": failure,
        "slack_cli_svctool": slack_cli_svctool_leftover(),
        "may_post_slackauthticket": ticket_ok,
        "keep_shipping": True,
        "keep_shipping_roads": list(SHIP_ROADS),
        "park": False,
        "ask_github_login": False,
        "fire_337": False,
        "commons_admission": False,
        "gate": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print full disposition")
    parser.add_argument("--classify", default="", help="classify one GitHub tool error")
    parser.add_argument("--may-ticket", action="store_true")
    parser.add_argument("--challenge", default="", help="unprompted owner challenge")
    args = parser.parse_args(argv)
    if args.classify:
        print(json.dumps(classify_github_tool_failure(args.classify), indent=2))
        return 0
    if args.may_ticket:
        print(json.dumps({"may_post_slackauthticket": may_post_slackauthticket(args.challenge)}))
        return 0
    print(json.dumps(desk_disposition(unprompted_challenge=args.challenge), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
