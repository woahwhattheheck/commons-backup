#!/usr/bin/env python3
"""Install Slack CLI custom tools that drive @facebook (and every catalog tag).

Complementary to host/slack_service_tag.py (catalog/router already on main).
This module locates the public Slack CLI, emits login tickets for #needs-bryce,
and writes the Bolt app manifest with function drive_tagged_service.

Owner: \"Yes you WILL install those things.\" Slack CLI auth still needs Bryce
to send /slackauthticket and return the challenge code. That is #needs-bryce,
not a Commons gate.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "host" / "slack_custom_tools_manifest.json"
CATALOG_PATH = ROOT / "ground" / "SLACK_SERVICE_TAGS.json"
APP_NAME = "Commons Service Tools"
CALLBACK_ID = "drive_tagged_service"
SLASH_COMMAND = "/svctool"

TICKET_LINE_RE = re.compile(r"(/slackauthticket\s+\S+)")
FINGERPRINT = "d41d8cd98f00b204e9800998ecf8427e"

RunFn = Callable[..., subprocess.CompletedProcess[str]]


def detect_cli(home: str | None = None, path_env: str | None = None) -> str | None:
    """Prefer ~/.slack/bin/slack (public Slack CLI install path)."""
    root = Path(home) if home is not None else Path.home()
    candidates = [
        root / ".slack" / "bin" / "slack",
        root / ".local" / "bin" / "slack",
    ]
    search_path = path_env if path_env is not None else os.environ.get("PATH", "")
    for chunk in search_path.split(os.pathsep):
        if chunk:
            candidates.append(Path(chunk) / "slack")
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        try:
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
        except OSError:
            continue
    return None


def parse_login_ticket(cli_output: str) -> dict[str, str]:
    """Parse `slack login --no-prompt` stdout for the slash command + ticket."""
    text = cli_output or ""
    match = TICKET_LINE_RE.search(text)
    if not match:
        return {"ok": "false", "error": "no_ticket"}
    slash = match.group(1).strip()
    ticket = slash.split(None, 1)[1]
    return {"ok": "true", "slash_command": slash, "ticket": ticket}


def login_no_prompt_argv(cli: str) -> list[str]:
    return [cli, "login", "--no-prompt"]


def login_complete_argv(cli: str, ticket: str, challenge: str) -> list[str]:
    return [cli, "login", "--ticket", ticket, "--challenge", challenge]


def run_argv(cli: str) -> list[str]:
    return [cli, "run", "--org-workspace-grant=all"]


def _run(
    argv: list[str],
    run: RunFn | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    fn = run or subprocess.run
    return fn(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def cli_version(cli: str, run: RunFn | None = None) -> str:
    proc = _run([cli, "version"], run=run)
    line = (proc.stdout or proc.stderr or "").strip().splitlines()
    return line[0] if line else ""


def auth_logged_in(cli: str, run: RunFn | None = None) -> bool:
    proc = _run([cli, "auth", "list"], run=run)
    blob = (proc.stdout or "") + (proc.stderr or "")
    if "You are not logged in" in blob:
        return False
    if re.search(r"\bT[A-Z0-9]{8,}\b", blob):
        return True
    return "Workspace" in blob or "Team ID" in blob


def status(
    home: str | None = None,
    run: RunFn | None = None,
    path_env: str | None = None,
) -> dict[str, Any]:
    cli = detect_cli(home=home, path_env=path_env)
    out: dict[str, Any] = {
        "cli": cli,
        "installed": bool(cli),
        "logged_in": False,
        "needs_owner_signin": True,
        "signin_channel_id": "C0BRX6EV739",
        "signin_channel": "#needs-bryce",
        "manifest_callback_id": CALLBACK_ID,
        "slash_command": SLASH_COMMAND,
        "commons_admission": False,
        "version": "",
    }
    if not cli:
        return out
    out["version"] = cli_version(cli, run=run)
    out["logged_in"] = auth_logged_in(cli, run=run)
    out["needs_owner_signin"] = not out["logged_in"]
    return out


def _catalog_services(path: Path | None = None) -> list[str]:
    target = path or CATALOG_PATH
    if not target.is_file():
        return ["facebook", "github", "gmail", "discord", "x"]
    data = json.loads(target.read_text(encoding="utf-8"))
    services = data.get("services") or {}
    if isinstance(services, dict):
        return sorted(str(k) for k in services.keys())
    return ["facebook"]


def build_manifest(catalog_path: Path | None = None) -> dict[str, Any]:
    tags = _catalog_services(catalog_path)
    tag_list = ", ".join("@" + t for t in tags[:12])
    if len(tags) > 12:
        tag_list += f", plus {len(tags) - 12} more"
    return {
        "display_information": {
            "name": APP_NAME,
            "description": (
                "Slack custom tools that drive tagged services from the message "
                f"body ({tag_list}). Owner sign-in queues to #needs-bryce. "
                "Not a Commons admission gate."
            ),
        },
        "features": {
            "app_home": {
                "home_tab_enabled": False,
                "messages_tab_enabled": True,
                "messages_tab_read_only_enabled": False,
            },
            "bot_user": {
                "display_name": "Service Tools",
                "always_online": True,
            },
            "slash_commands": [
                {
                    "command": SLASH_COMMAND,
                    "description": "Drive @facebook (or any catalog tag) from the rest of the text",
                    "usage_hint": "facebook post the drop tonight",
                    "should_escape": False,
                }
            ],
        },
        "oauth_config": {
            "scopes": {
                "bot": [
                    "app_mentions:read",
                    "channels:history",
                    "chat:write",
                    "chat:write.public",
                    "commands",
                    "groups:history",
                    "im:history",
                    "im:write",
                    "reactions:write",
                ]
            }
        },
        "settings": {
            "event_subscriptions": {
                "bot_events": [
                    "app_mention",
                    "function_executed",
                    "message.channels",
                    "message.groups",
                    "message.im",
                ]
            },
            "interactivity": {"is_enabled": True},
            "org_deploy_enabled": True,
            "socket_mode_enabled": True,
            "token_rotation_enabled": False,
            "hermes_app_type": "remote",
            "function_runtime": "remote",
        },
        "functions": {
            CALLBACK_ID: {
                "title": "Drive tagged service",
                "description": (
                    "Custom tool: take a service tag (@facebook, @github, ...) "
                    "and the remainder of the Slack message, and drive that "
                    "provider. Missing sessions queue #needs-bryce."
                ),
                "input_parameters": {
                    "tag": {
                        "type": "string",
                        "title": "Service tag",
                        "description": "Canonical tag such as facebook",
                        "is_required": True,
                        "name": "tag",
                    },
                    "body": {
                        "type": "string",
                        "title": "Message body",
                        "description": "Remainder of the tagged Slack message",
                        "is_required": True,
                        "name": "body",
                    },
                },
                "output_parameters": {
                    "state": {
                        "type": "string",
                        "title": "State",
                        "description": "READY, DRIVEN, or NEEDS_OWNER_SIGNIN",
                        "is_required": True,
                        "name": "state",
                    },
                    "result": {
                        "type": "string",
                        "title": "Result",
                        "description": "Outcome text. Never includes secrets.",
                        "is_required": True,
                        "name": "result",
                    },
                },
            }
        },
    }


def write_manifest(path: Path | None = None, catalog_path: Path | None = None) -> Path:
    target = path or MANIFEST_PATH
    payload = build_manifest(catalog_path)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def is_executable_cli(path: str) -> bool:
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--parse-ticket-file", default="")
    args = parser.parse_args(argv)
    if args.write_manifest:
        path = write_manifest()
        print(str(path))
        return 0
    if args.parse_ticket_file:
        text = Path(args.parse_ticket_file).read_text(encoding="utf-8")
        print(json.dumps(parse_login_ticket(text), indent=2))
        return 0
    payload = status()
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("installed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
