#!/usr/bin/env python3
"""Emit a fresh Slack CLI login ticket for #needs-bryce.

The Slack CLI *project* already landed as
cursor-slack-custom-tools-cli-project-20260902-01. This module is the
leftover challenge helper: run `slack login --no-prompt`, parse the
one-use /slackauthticket, and format the five-field #needs-bryce item.

Does not remint the project receipt, install land, or peer ticket
1788321773.338029. Does not remint blobs 8fcc3d36 / c01a7085 / 0e6ad49f.
Not a Commons admission gate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import needs_bryce_login_queue as nbq
import slack_custom_tools_install as inst


ROOT = Path(__file__).resolve().parent.parent
RECEIPT_ID = "cursor-slack-custom-tools-cli-challenge-20260902-01"
PROJECT_RECEIPT = "cursor-slack-custom-tools-cli-project-20260902-01"
SIGNIN_CHANNEL_ID = "C0BRX6EV739"
SIGNIN_CHANNEL = "#needs-bryce"
PEER_TICKET_TS = "1788321773.338029"
THIS_TICKET_TS = "1788325362.867019"
RESUME_WORKER_URL = "https://cursor.com/agents/bc-ebe2e1f5-3fc1-54d5-bdff-24237b6d8cae"
DO_NOT_REMINT = ("8fcc3d36", "c01a7085", "0e6ad49f")

RunFn = Callable[..., subprocess.CompletedProcess[str]]


def emit_login_ticket(
    cli: str | None = None,
    run: RunFn | None = None,
    home: str | None = None,
    path_env: str | None = None,
    evidence: str = (
        "hub CLEAR leftover after landed "
        "cursor-slack-custom-tools-cli-project-20260902-01; "
        "did not remint 8fcc3d36/c01a7085/0e6ad49f or consume peer ticket "
        "1788321773.338029"
    ),
) -> dict[str, Any]:
    """Run `slack login --no-prompt` and format a #needs-bryce item."""
    resolved = cli or inst.detect_cli(home=home, path_env=path_env)
    if not resolved:
        return {
            "ok": False,
            "error": "cli_missing",
            "receipt_id": RECEIPT_ID,
            "signin_channel_id": SIGNIN_CHANNEL_ID,
            "commons_admission": False,
            "peer_ticket": "do_not_consume",
        }
    fn = run or subprocess.run
    proc = fn(
        inst.login_no_prompt_argv(resolved),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ.copy(),
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    parsed = inst.parse_login_ticket(blob)
    if parsed.get("ok") != "true":
        return {
            "ok": False,
            "error": parsed.get("error") or "no_ticket",
            "returncode": proc.returncode,
            "receipt_id": RECEIPT_ID,
            "signin_channel_id": SIGNIN_CHANNEL_ID,
            "commons_admission": False,
            "peer_ticket": "do_not_consume",
        }
    item = nbq.slack_cli_ticket_item(
        parsed["slash_command"],
        evidence=evidence,
        resume_worker_url=RESUME_WORKER_URL,
    )
    return {
        "ok": True,
        "receipt_id": RECEIPT_ID,
        "project_receipt": PROJECT_RECEIPT,
        "slash_command": parsed["slash_command"],
        "ticket": parsed["ticket"],
        "needs_bryce_text": nbq.format_item(item),
        "item": item,
        "signin_channel": SIGNIN_CHANNEL,
        "signin_channel_id": SIGNIN_CHANNEL_ID,
        "this_ticket_ts": THIS_TICKET_TS,
        "peer_ticket_ts": PEER_TICKET_TS,
        "peer_ticket": "do_not_consume",
        "do_not_remint": list(DO_NOT_REMINT),
        "resume_worker_url": RESUME_WORKER_URL,
        "commons_admission": False,
        "copy_secrets": False,
    }


def status() -> dict[str, Any]:
    return {
        "id": RECEIPT_ID,
        "project_receipt": PROJECT_RECEIPT,
        "project_dir": str(ROOT / "host" / "slack_custom_tools_cli"),
        "signin_channel": SIGNIN_CHANNEL,
        "signin_channel_id": SIGNIN_CHANNEL_ID,
        "this_ticket_ts": THIS_TICKET_TS,
        "peer_ticket_ts": PEER_TICKET_TS,
        "peer_ticket": "do_not_consume",
        "do_not_remint": list(DO_NOT_REMINT),
        "resume_worker_url": RESUME_WORKER_URL,
        "commons_admission": False,
        "gate": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--login-ticket", action="store_true")
    args = parser.parse_args(argv)
    if args.login_ticket:
        print(json.dumps(emit_login_ticket(), indent=2))
        return 0
    print(json.dumps(status(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
