#!/usr/bin/env python3
"""Classify one GitHub HTTP/MCP failure as that call, not a missing login.

Hub 1788325694.170879 records the historical connected-account declaration.
Current operation diagnostics use observed status and optional identity; one
failed call does not establish the state of every publication road.
Keep shipping independent work. Not a Commons gate.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from host.github_already_logged_in import classify as classify_operation
except ModuleNotFoundError:
    from github_already_logged_in import classify as classify_operation


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "GITHUB_CALL_NOT_LOGIN.json"

VERDICTS = (
    "OK",
    "CALL_FAILED",
    "RATE_LIMITED",
    "PATH_WRONG",
    "PATH_OR_VISIBILITY",
    "SCOPE_OF_ACTION",
    "PERMISSION_OR_SCOPE",
    "AUTHENTICATION_FAILED",
    "PROVIDER_ERROR",
    "UNKNOWN",
)
NEVER_VERDICT = "MISSING_LOGIN_FREEZE"
SCOPE_ACTION_MARKERS = (
    "workflow_dispatch",
    "createworkflowdispatch",
    "actions.createworkflowdispatch",
)
ALTERNATE_ROADS = (
    "unique-push HEAD:main",
    "contents API PUT",
    "git data API",
    "current-main git",
)

_PROHIBITION_CLAUSE = re.compile(
    r"\b(?:do not|don't|never|stop)\b(?:\s+\w+){0,16}\s+"
    r"(?:open another github login ask|"
    r"park work waiting for bryce to (?:['\"]log in['\"]|log in)|"
    r"open a github login ask)",
    re.IGNORECASE,
)
_ASK_NEEDLES = (
    "please log in to github",
    "need bryce to log in",
    "waiting for bryce to log in",
    "no github login",
    "no github perms",
    "open a github login ask",
    "park waiting for github login",
)


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def opens_github_login_ask(text: str) -> bool:
    """True when a draft asks for a GitHub login or parks on a missing login.

    Owner prohibition text that repeats 'do not open another GitHub login ask'
    is not itself an ask.
    """
    compact = " ".join((text or "").lower().split())
    stripped = _PROHIBITION_CLAUSE.sub(" ", compact)
    stripped = " ".join(stripped.split())
    return any(needle in stripped for needle in _ASK_NEEDLES)


def _status_int(status: int | str | None) -> int | None:
    if status is None or status == "":
        return None
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def classify(
    status: int | str | None = None,
    action: str = "",
    message: str = "",
    *,
    login: str | None = None,
    law_path: Path | None = None,
) -> dict[str, Any]:
    """One GitHub failure is that action. login_ask stays false."""
    law = load_law(law_path)
    code = _status_int(status)
    action_l = str(action or "").strip().lower()
    message_l = str(message or "").lower()
    blob = f"{action_l} {message_l}".strip()
    scoped = any(marker in blob for marker in SCOPE_ACTION_MARKERS)

    observation = classify_operation(status_code=code, message=str(message or ""),
                                     login=login, tool=str(action or ""))
    verdict = {
        "call_ok": "OK", "auth_ok": "OK", "rate_limit": "RATE_LIMITED",
        "authentication": "AUTHENTICATION_FAILED",
        "path_or_visibility": "PATH_OR_VISIBILITY",
        "permission_or_scope": "PERMISSION_OR_SCOPE",
        "provider_error": "PROVIDER_ERROR", "https_git_not_mcp": "CALL_FAILED",
        "call": "CALL_FAILED",
    }.get(observation["cause"], "UNKNOWN")
    if scoped and verdict == "PERMISSION_OR_SCOPE":
        verdict = "SCOPE_OF_ACTION"

    roads = list(law.get("alternate_roads") or ALTERNATE_ROADS)
    if verdict == "OK":
        roads = []

    return {
        "verdict": verdict,
        "status": code,
        "action": str(action or ""),
        "gate": False,
        "commons_admission": False,
        "login_ask": False,
        "park_for_owner_login": False,
        "freeze": False,
        "github_login": observation["auth"],
        "observed_login": login,
        "declared_github_login": law.get("harness_github_login"),
        "cause": observation["cause"],
        "next": observation["next"],
        "never_verdict": NEVER_VERDICT,
        "one_failed_call": str(
            law.get("one_failed_call") or "that_action_not_missing_login"
        ),
        "alternate_roads": roads,
        "keep_shipping": True,
        "law_id": str(law.get("id") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", default="", help="HTTP status from the failed call")
    parser.add_argument("--action", default="", help="tool or endpoint name")
    parser.add_argument("--message", default="", help="error body or tool message")
    parser.add_argument("--draft", default="", help="draft Slack/post text to scan")
    parser.add_argument("--law", default="", help="override law path")
    parser.add_argument("--login", default="", help="identity observed by a harmless profile read")
    args = parser.parse_args(argv)
    if args.law:
        load_law(Path(args.law))
    result: dict[str, Any]
    if args.draft and not args.status and not args.action:
        result = {
            "opens_github_login_ask": opens_github_login_ask(args.draft),
            "login_ask": False,
            "gate": False,
        }
    else:
        result = classify(
            status=args.status or None,
            action=args.action,
            message=args.message,
            login=args.login or None,
            law_path=Path(args.law) if args.law else None,
        )
        if args.draft:
            result["opens_github_login_ask"] = opens_github_login_ask(args.draft)
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
