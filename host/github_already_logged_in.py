#!/usr/bin/env python3
"""Classify one GitHub operation without inferring a global login outage.

Owner hub 1788325694 / #needs-bryce 1788325660.929309:
a failed call describes that action, not every available publication road.
Keep observed identity separate from operation status; do not invent a login
observation when none was supplied. Continue independent authorized work.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

PEER_LOGIN = "woahwhattheheck"
NEEDS_BRYCE = "C0BRX6EV739"

RATE_RE = re.compile(r"(?i)rate.?limit|secondary.?rate|api rate|403.*rate")
SCOPE_RE = re.compile(
    r"(?i)missing_scope|resource_not_accessible|insufficient.?scope|"
    r"must have .+ permission|actions:write|403 Forbidden"
)
PATH_RE = re.compile(
    r"(?i)not found|does not exist|no such file|path does not point|"
    r"\b404\b"
)
HTTPS_GIT_RE = re.compile(
    r"(?i)could not read [Uu]sername|could not read [Pp]assword|"
    r"authentication required|terminal prompts disabled|"
    r"could not read Username for 'https://github.com'"
)
LOGIN_ASK_RE = re.compile(
    r"(?i)github login|log in to github|reconnect.*github|no perms|"
    r"missing login|not logged in to github"
)


def classify(
    *,
    status_code: int | None = None,
    message: str = "",
    login: str | None = None,
    tool: str = "",
) -> dict[str, Any]:
    text = message or ""
    out: dict[str, Any] = {
        "auth": "present" if login else "unmeasured",
        "identity_observed": bool(login),
        "peer_login": PEER_LOGIN,
        "park": False,
        "needs_bryce": False,
        "github_login_ask": False,
        "keep_shipping": True,
        "tool": tool or None,
        "status_code": status_code,
        "needs_bryce_channel": None,
    }
    if login:
        out["login"] = login

    # Identity from a harmless profile read is useful context. It must not
    # erase a later 429, 401, 403 or provider failure for a different operation.
    if status_code is not None and 200 <= status_code < 300:
        out["cause"] = "call_ok"
        out["next"] = "continue the requested work; this operation succeeded"
        return out

    if RATE_RE.search(text) or status_code == 429:
        out["cause"] = "rate_limit"
        out["next"] = "respect Retry-After or the provider reset time; continue independent work without retry storms"
        return out

    if status_code == 401:
        out["auth"] = "failed_for_action"
        out["cause"] = "authentication"
        out["next"] = (
            "inspect this connector's harmless profile response and exact authentication error; "
            "other authenticated publication roads may remain available"
        )
        return out

    if status_code is not None and status_code >= 500:
        out["cause"] = "provider_error"
        out["next"] = "retain the exact operation and provider response; retry once when appropriate"
        return out

    if status_code == 404 or PATH_RE.search(text):
        out["cause"] = "path_or_visibility"
        out["next"] = "check the exact repository, path, ref and repository visibility; a 404 alone does not identify an authentication failure"
        return out

    if HTTPS_GIT_RE.search(text):
        out["cause"] = "https_git_not_mcp"
        out["next"] = (
            "inspect the full connected GitHub tool inventory and use a discovered publishing action; "
            "a terminal credential prompt does not establish the connector's authentication state"
        )
        return out

    if status_code == 403 or SCOPE_RE.search(text):
        out["cause"] = "permission_or_scope"
        out["next"] = (
            "inspect the exact provider response and repository-permission probe to distinguish "
            "account permission, installation scope and repository policy; continue other authorized work"
        )
        return out

    if LOGIN_ASK_RE.search(text):
        out["cause"] = "unverified_login_claim"
        out["next"] = "inspect the complete tool inventory and harmless profile response before making an authentication claim"
        return out

    if login and status_code is None and not text:
        out["cause"] = "auth_ok"
        out["next"] = "use the observed identity and discovered tools for the requested work"
        return out

    out["cause"] = "call" if status_code is not None or text else "unknown"
    out["next"] = "retain this operation's exact result and inspect available alternatives; do not infer global authentication state"
    return out


def slack_cli_is_not_github(*, slack_cli_logged_in: bool) -> dict[str, Any]:
    return {
        "auth_github": "unmeasured",
        "slack_cli_logged_in": slack_cli_logged_in,
        "park": False,
        "needs_bryce": False,
        "github_login_ask": False,
        "keep_shipping": True,
        "note": (
            "Slack CLI session state does not measure GitHub authentication. "
            "Use a harmless GitHub profile probe and the complete GitHub tool inventory."
        ),
    }


def three_three_seven_is_not_a_rule() -> dict[str, Any]:
    return {
        "rule": False,
        "source": "owner hub 1788325819 correction",
        "keep_shipping": True,
        "park": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=int, default=None)
    parser.add_argument("--message", default="")
    parser.add_argument("--login", default="")
    parser.add_argument("--tool", default="")
    args = parser.parse_args(argv)
    payload = classify(
        status_code=args.status,
        message=args.message,
        login=args.login or None,
        tool=args.tool,
    )
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
