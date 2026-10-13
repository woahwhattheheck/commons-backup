#!/usr/bin/env python3
"""Independent MATCH that GitHub PR #7915 is CLOSED unmerged.

Does not reopen. Does not merge. Harborline /qualify live-probe paths stay
theirs. Unique-pack pointer leftover on main stays KEEP. --reopen / --merge /
--go / --send / --apply are REFUSED (sent=0, reopened=False, merged=False).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

PR_NUMBER = 7915
PR_API = "https://api.github.com/repos/woahwhattheheck/commons/pulls/7915"
PR_URL = "https://github.com/woahwhattheheck/commons/pull/7915"
HEAD_SHA = "fa046ce059009f0ddece9d91eaa5d60a1f281f39"
HEAD_REF = "cursor/harborline-map-pin-lift-pointer-ae54"
CLOSED_AT = "2026-09-02T19:44:19Z"
POINTER_BLOB = "7a8987b52fb27d6848e0fd55c1f0c4e3f60cf51f"
POINTER_LAND = "af2b82f9a16185660e378a4a6f28c78dc827bb6e"
KEEP7915_BLOB = "9d28dd61069b0db4c8c73df4b536c19e97530085"
HARBORLINE_PIN_BLOB = "8fe8a002d189336f1a11ef1fae7b315073d96c59"
DO_NOT_STEAL = (
    "host/harborline_qualify_live_probe.py",
    "test_harborline_qualify_live_probe.py",
    "p/cursor-harborline-qualify-live-probe-20260902-01.md",
)
DO_NOT_REMINT = (
    "p/cursor-business-pack-harborline-map-pin-lift-pointer-20260902-01.md",
    "p/cursor-pack-harborline-map-pin-lift-20260902-01.md",
    "p/cursor-ack-moth-stamp-cz03-keep7915-20260902-01.md",
    "p/cursor-harborline-qualify-live-probe-20260902-01.md",
    "autogtm.html",
    "boards.html",
    "door.js",
)

Opener = Callable[[str], tuple[int, bytes]]


def live_opener(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "commons-pr7915-closed-unmerged/1",
            "Accept": "application/vnd.github+json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as err:
        return int(err.code), err.read()
    except OSError as err:
        return 0, str(err).encode("utf-8", errors="replace")


def refuse(flag: str) -> dict[str, Any]:
    return {
        "kind": "PR7915_CLOSED_UNMERGED",
        "schema": "commons-pr7915-closed-unmerged/v1",
        "flag": flag,
        "state": "REFUSED",
        "sent": 0,
        "reopened": False,
        "merged": False,
        "permission": False,
        "note": (
            f"--{flag} is refused. #7915 stays closed unmerged. "
            "Refuse is not a reopen, not a merge, and not a send."
        ),
        "do_not_steal": list(DO_NOT_STEAL),
        "do_not_remint": list(DO_NOT_REMINT),
    }


def classify(code: int, body: bytes) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "PR7915_CLOSED_UNMERGED",
        "schema": "commons-pr7915-closed-unmerged/v1",
        "pr": PR_NUMBER,
        "url": PR_URL,
        "api": PR_API,
        "http": code,
        "permission": False,
        "sent": 0,
        "reopened": False,
        "no_auth": True,
        "no_gate": True,
        "do_not_steal": list(DO_NOT_STEAL),
        "do_not_remint": list(DO_NOT_REMINT),
        "keep": {
            "pointer_blob": POINTER_BLOB,
            "pointer_land": POINTER_LAND,
            "harborline_pin_blob": HARBORLINE_PIN_BLOB,
            "keep7915_blob": KEEP7915_BLOB,
        },
        "expected": {
            "state": "closed",
            "merged": False,
            "closed_at": CLOSED_AT,
            "head_sha": HEAD_SHA,
            "head_ref": HEAD_REF,
        },
    }
    if code == 0:
        base.update(
            {
                "state": "FINDER-FAILED",
                "merged": False,
                "note": "network miss on GitHub PR API is FINDER-FAILED, never silent 0, never CLEAR to reopen",
                "body_prefix": body[:240].decode("utf-8", errors="replace"),
            }
        )
        return base
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        base.update(
            {
                "state": "FINDER-FAILED",
                "merged": False,
                "note": "non-JSON GitHub PR body is FINDER-FAILED, never silent 0",
                "body_prefix": body[:240].decode("utf-8", errors="replace"),
            }
        )
        return base
    state = str(payload.get("state") or "")
    merged = bool(payload.get("merged"))
    closed_at = payload.get("closed_at")
    merged_at = payload.get("merged_at")
    head = payload.get("head") or {}
    head_sha = str(head.get("sha") or "")
    head_ref = str(head.get("ref") or "")
    match = (
        code == 200
        and state == "closed"
        and merged is False
        and merged_at is None
        and head_sha == HEAD_SHA
    )
    base.update(
        {
            "github_state": state,
            "merged": merged,
            "closed_at": closed_at,
            "merged_at": merged_at,
            "head_sha": head_sha,
            "head_ref": head_ref,
            "title": payload.get("title"),
            "state": "MATCH" if match else "FINDER-FAILED",
            "note": (
                "HTTP 200 closed unmerged MATCH. Will not reopen. Will not merge. "
                "Pointer leftover already on main KEEP. Harborline /qualify live-probe paths not stolen."
                if match
                else "GitHub PR #7915 did not MATCH closed-unmerged expected bytes. Never silent 0. Will not reopen from a miss."
            ),
        }
    )
    return base


def measure(*, opener: Opener = live_opener) -> dict[str, Any]:
    code, body = opener(PR_API)
    return classify(code, body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--reopen", action="store_true")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--go", action="store_true")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.reopen or args.merge or args.go or args.send or args.apply:
        flag = (
            "reopen"
            if args.reopen
            else "merge"
            if args.merge
            else "go"
            if args.go
            else "send"
            if args.send
            else "apply"
        )
        sys.stdout.write(json.dumps(refuse(flag), indent=2, sort_keys=True) + "\n")
        return 2
    row = measure()
    sys.stdout.write(json.dumps(row, indent=2, sort_keys=True) + "\n")
    if args.json or True:
        pass
    return 0 if row.get("state") == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
