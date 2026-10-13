#!/usr/bin/env python3
"""host/grok_route.py — 24h grok.com preference is not a Cursor lock.

Slack 1787669986.483149 (BRYCE via Cursor agent): use grok more,
use cursor less, for the next 24 hours.

Prior Slack 1787669923.780099: stop routing away from grok app
and to Cursor. Burn grok.com tokens, not Cursor tokens.

Talk is CLAIMED until this leftover names the window on current
main. Prefer grok.com / SuperGrok / Grok Build through
2026-08-26T14:59:46Z. Cursor is deprioritized, not locked.
Posting stays OPEN. Blank from= still lands as UNSEATED.
Open door. No auth. No gate. titan: NOT_WRITTEN.
FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

Already landed (do not remint): GROK_HYGIENE, GROK_HARNESS,
GROK_RECEIPT, GROK_CLAUDE_HYGIENE, SUPERGROK_HEAVY.

  python3 host/grok_route.py
  python3 host/grok_route.py --root .
  python3 host/grok_route.py --now 2026-08-25T15:00:00Z
  python3 host/grok_route.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "GROK_ROUTE.json")
DEFAULT_CARD = os.path.join("ground", "GROK_ROUTE.md")
SLACK_TS = "1787669986.483149"
PRIOR_SLACK_TS = "1787669923.780099"
WINDOW_START = "2026-08-25T14:59:46Z"
WINDOW_HOURS = 24
PREFER = ("grok.com", "SuperGrok", "Grok Build")
DEPRIORITIZE = ("Cursor token burns",)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "grok_route.py"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "GROK_HARNESS.md"),
    os.path.join("ground", "GROK_RECEIPT.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "use grok more",
    "use cursor less",
    "grok.com",
    "24 hours",
    "1787669986.483149",
    "stop routing away from grok",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "open door",
    "no auth",
    "no gate",
    "talk is not a land",
    "unseated",
    "not a lock",
)


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def parse_iso(value):
    """Parse an ISO timestamp. Invalid or blank is None, never a default clock."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def window_state(now_iso, start_iso=WINDOW_START, hours=WINDOW_HOURS):
    """Measure the 24h grok.com preference. Missing clocks stay UNMEASURED."""
    now = parse_iso(now_iso)
    start = parse_iso(start_iso)
    try:
        span = int(hours)
    except (TypeError, ValueError):
        span = None
    if now is None or start is None or span is None or span <= 0:
        return {
            "state": "UNMEASURED",
            "prefer": [],
            "deprioritize": [],
            "locked": False,
            "note": (
                "window clocks were not read. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
        }
    end = start + timedelta(hours=span)
    if now < start:
        return {
            "state": "PENDING",
            "prefer": list(PREFER),
            "deprioritize": list(DEPRIORITIZE),
            "locked": False,
            "note": (
                "window has not started. grok.com preference is not active yet. "
                "Cursor is not locked."
            ),
        }
    if now < end:
        return {
            "state": "ACTIVE",
            "prefer": list(PREFER),
            "deprioritize": list(DEPRIORITIZE),
            "locked": False,
            "note": (
                "prefer grok.com / SuperGrok / Grok Build for the named 24 hours. "
                "Cursor token burns are deprioritized, not locked. Open door."
            ),
        }
    return {
        "state": "EXPIRED",
        "prefer": [],
        "deprioritize": [],
        "locked": False,
        "note": (
            "24-hour grok.com preference ended. Cursor is not locked. "
            "A Slack yell is still not the file."
        ),
    }


def load_catalog(text):
    """Parse the grok-route catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    prefer = [str(item).strip() for item in (data.get("prefer") or []) if str(item).strip()]
    deprioritize = [
        str(item).strip()
        for item in (data.get("deprioritize") or [])
        if str(item).strip()
    ]
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "prior_slack_ts": str(data.get("prior_slack_ts") or "").strip() or PRIOR_SLACK_TS,
        "window_start": str(data.get("window_start") or "").strip() or WINDOW_START,
        "window_hours": data.get("window_hours", WINDOW_HOURS),
        "prefer": prefer,
        "deprioritize": deprioritize,
        "not_a_lock": bool(data.get("not_a_lock", True)),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "names_window": bool(facts.get("names_window")),
        "names_not_a_lock": bool(facts.get("names_not_a_lock")),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "window": dict(facts.get("window") or {}),
    }


def classify(row):
    """Turn a measured grok-route census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Grok-route leftover not read. Absence was not stillness. "
                "Use-grok-more / use-cursor-less talk is not a land."
            ),
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof. "
                "FINDER-FAILED, never 0."
            ),
        }
    misses = list(row.get("misses") or [])
    if not row.get("card_present") or not row.get("catalog_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Use-grok-more / use-cursor-less / burn grok.com tokens talk "
                "is CLAIMED until the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("names_window") or not row.get("names_not_a_lock"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "24-hour grok.com window is unnamed or Cursor is treated as locked. "
                "This leftover is a preference, not a lock. FINDER-FAILED, never 0."
            ),
        }
    needed = [
        phrase for phrase in REQUIRED_PHRASES if phrase not in (row.get("found_phrases") or [])
    ]
    if needed or not row.get("posting_open") or not row.get("no_auth") or not row.get("no_gate"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Open door + no auth + no gate required. Talk is CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Grok-route leftover is on this tree. Prefer grok.com / SuperGrok / "
            "Grok Build for the named 24 hours. Cursor is deprioritized, not "
            "locked. A Slack yell is still not the file."
        ),
    }


def measure_root(root, now_iso=None):
    root = os.path.abspath(root)
    misses = []
    blobs = []
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        else:
            blobs.append(text)
    hay = "\n".join(blobs).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in hay]
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    window = window_state(
        now_iso or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        catalog.get("window_start") or WINDOW_START,
        catalog.get("window_hours") or WINDOW_HOURS,
    )
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    names_window = (
        (catalog.get("window_start") or "") == WINDOW_START
        and int(catalog.get("window_hours") or 0) == WINDOW_HOURS
        and "24 hours" in hay
        and SLACK_TS in hay
    )
    names_not_a_lock = bool(catalog.get("not_a_lock")) and "not a lock" in hay
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "found_phrases": found,
        "names_window": names_window,
        "names_not_a_lock": names_not_a_lock,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "window": window,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "window": window,
            },
            "z": "misses " + json.dumps(misses) + " / FINDER-FAILED never 0",
        }
    )
    return row


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED", empty
    before = window_state("2026-08-25T14:59:45Z")
    assert before["state"] == "PENDING", before
    assert before["locked"] is False, before
    active = window_state("2026-08-25T15:00:00Z")
    assert active["state"] == "ACTIVE", active
    assert active["prefer"] == list(PREFER), active
    assert active["locked"] is False, active
    expired = window_state("2026-08-26T14:59:46Z")
    assert expired["state"] == "EXPIRED", expired
    assert expired["locked"] is False, expired
    missing = window_state("")
    assert missing["state"] == "UNMEASURED", missing
    invalid = window_state("not-a-clock")
    assert invalid["state"] == "UNMEASURED", invalid
    absent = classify(
        measure_from_rows(
            {
                "card_present": False,
                "catalog_present": False,
                "misses": ["ground/GROK_ROUTE.md"],
                "calibration_ok": True,
            }
        )
    )
    assert absent["state"] == "NOT_LANDED", absent
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure 24h grok.com route leftover")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--now", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(args.root, args.now or None)
    verdict = classify(row)
    payload = {"verdict": verdict, "row": row}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
