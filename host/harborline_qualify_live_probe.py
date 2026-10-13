#!/usr/bin/env python3
"""Harborline /qualify live-probes Explee. credentials=omit. --send REFUSED."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

EXPLEE_PROJECTS = "https://api.explee.com/public/api/v1/autogtm/projects"
REFUSE = ("--send", "--apply", "--go", "--autopilot")
UA = "harborline-qualify-live-probe/0.1"


def refuse_payload(flag: str) -> dict[str, object]:
    return {
        "url": EXPLEE_PROJECTS,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "booked": 0,
        "cash": 0,
        "credentials": "omit",
        "authorization": "absent",
        "note": f"{flag} REFUSED. sent=0 booked=0 cash=0. No live mail. No Explee key attached.",
    }


def probe() -> dict[str, object]:
    req = urllib.request.Request(
        EXPLEE_PROJECTS,
        headers={"User-Agent": UA, "Accept": "application/json"},
        method="GET",
    )
    acao = ""
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = int(resp.status)
            body = resp.read()
            acao = resp.headers.get("Access-Control-Allow-Origin") or ""
    except urllib.error.HTTPError as err:
        code = int(err.code)
        body = err.read()
        acao = err.headers.get("Access-Control-Allow-Origin") if err.headers else ""
    except OSError as err:
        return {
            "url": EXPLEE_PROJECTS,
            "http": "FINDER-FAILED",
            "detail": str(err),
            "verdict": "FINDER-FAILED",
            "sent": 0,
            "booked": 0,
            "cash": 0,
            "credentials": "omit",
            "authorization": "absent",
            "acao": "",
            "note": f"{err}. FINDER-FAILED with search space, never silent 0.",
        }
    detail = body.decode("utf-8", errors="replace")[:280]
    if code == 401 and "Missing API key" in detail:
        note = (
            "HTTP 401 Missing API key FINDER-FAILED "
            "(not CLEAR, not a Commons lock, never silent 0). "
            "credentials=omit · no Authorization · sent=0 booked=0 cash=0."
        )
    else:
        note = (
            f"HTTP {code} {detail or '(empty body)'} FINDER-FAILED, never silent 0. "
            "credentials=omit · no Authorization · sent=0 booked=0 cash=0."
        )
    return {
        "url": EXPLEE_PROJECTS,
        "http": code,
        "detail": detail,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "booked": 0,
        "cash": 0,
        "credentials": "omit",
        "authorization": "absent",
        "acao": acao,
        "note": note,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    for flag in REFUSE:
        if flag in args:
            print(json.dumps(refuse_payload(flag), indent=2))
            return 2
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    try:
        ns, unknown = parser.parse_known_args(args)
    except SystemExit as exc:
        # argparse raises SystemExit(0) after printing --help; that is not a
        # finder failure.
        if exc.code == 0:
            return 0
        print(
            json.dumps(
                {
                    "verdict": "FINDER-FAILED",
                    "sent": 0,
                    "note": "unknown args FINDER-FAILED, never silent 0.",
                }
            )
        )
        return 1
    if unknown:
        print(
            json.dumps(
                {
                    "verdict": "FINDER-FAILED",
                    "sent": 0,
                    "unknown": unknown,
                    "note": "unknown args FINDER-FAILED, never silent 0.",
                }
            )
        )
        return 1
    payload = probe()
    print(json.dumps(payload, indent=2 if ns.json else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
