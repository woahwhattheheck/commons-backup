#!/usr/bin/env python3
"""host/grok_app_route.py — prefer grok.com over Cursor for 24 hours.

Bryce Slack 1787669923.780099 / 1787669986.483149: stop routing away
from the Grok app to Cursor. Burn grok.com tokens, not Cursor tokens.
Use Grok more, Cursor less, for the next 24 hours.

This leftover names that window on current main. A Slack line is
CLAIMED until the card + catalog + leftover-first desk exist.

X = exact files in SEARCH_SPACE
Y = grok.com-first phrases + named already-landed leftovers + window
Z = missing leftover / failed calibration / FINDER-FAILED
Calibration = known-present EXECUTE.md + SUPERGROK_HEAVY.md + Action Pad
directive must be found in the same run or the measure is UNMEASURED.
A miss prints FINDER-FAILED / FINDER-UNVERIFIED plus the search space.
Never 0.

  python3 host/grok_app_route.py
  python3 host/grok_app_route.py --root .
  python3 host/grok_app_route.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "GROK_APP_ROUTE.json")
DEFAULT_CARD = os.path.join("ground", "GROK_APP_ROUTE.md")
SLACK_TS = "1787669923.780099"
SLACK_TS_TELL = "1787669986.483149"
WINDOW_START = "2026-08-25T14:58:43Z"
WINDOW_UNTIL = "2026-08-26T14:59:46Z"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "grok_app_route.py"),
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "GROK_HARNESS.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "GROK_HARNESS.md"),
    os.path.join("ground", "GROK_RECEIPT.md"),
    os.path.join("ground", "SITTING_REMINT.md"),
    os.path.join("ground", "HEAVY_LANES.md"),
)
REQUIRED_PHRASES = (
    "grok app",
    "grok.com tokens",
    "cursor tokens",
    "use grok more",
    "use cursor less",
    "next 24 hours",
    "leftover-first",
    "do not remint",
    "never 0",
    "finder-failed",
    "open door",
    "no auth",
    "no gate",
    "unseated",
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


def _parse_iso(stamp):
    text = str(stamp or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def window_state(now=None, start=WINDOW_START, until=WINDOW_UNTIL):
    """Classify the 24-hour grok.com-first window. Missing clock is UNMEASURED."""
    try:
        start_at = _parse_iso(start)
        until_at = _parse_iso(until)
    except ValueError:
        return "UNMEASURED"
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    if clock < start_at:
        return "WINDOW_PENDING"
    if clock < until_at:
        return "WINDOW_ACTIVE"
    return "WINDOW_EXPIRED"


def load_catalog(text):
    """Parse the grok-app-route catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "already_landed": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "already_landed": []}
    already = []
    for item in data.get("already_landed") or []:
        name = str(item or "").strip()
        if name:
            already.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "slack_ts_tell": str(data.get("slack_ts_tell") or "").strip(),
        "window_start": str(data.get("window_start") or WINDOW_START).strip(),
        "window_until": str(data.get("window_until") or WINDOW_UNTIL).strip(),
        "prefer": str(data.get("prefer") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "already_landed": already,
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "window": str(facts.get("window") or "UNMEASURED"),
        "prefer": str(facts.get("prefer") or ""),
    }


def classify(row):
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Grok-app-route leftover not read. Absence was not stillness. "
                "A Slack routing line is not a land."
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
    landed_missing = list(row.get("landed_missing") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    phrases = list(row.get("found_phrases") or [])
    posting_open = bool(row.get("posting_open"))
    no_auth = bool(row.get("no_auth"))
    no_gate = bool(row.get("no_gate"))
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Grok-app / grok.com-tokens / use-grok-more talk is CLAIMED "
                "until the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    if landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing)
                + ". Census is incomplete. FINDER-FAILED, never 0."
            ),
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in phrases]
    if needed or not posting_open or not no_auth or not no_gate:
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Open door + no auth + no gate required. Talk is CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
        }
    window = str(row.get("window") or "UNMEASURED")
    return {
        "state": "INTEGRATED",
        "note": (
            "Grok-app-route leftover is on this tree. Prefer grok.com / Grok app "
            "over Cursor for the named 24-hour window. Burn grok.com tokens, "
            "not Cursor tokens. Window is "
            + window
            + ". A Slack routing line is still not the file."
        ),
        "window": window,
    }


def measure_root(root, now=None):
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
    landed_present = [rel for rel in ALREADY_LANDED if _exists(root, rel)]
    landed_missing = [rel for rel in ALREADY_LANDED if not _exists(root, rel)]
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
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
    window = window_state(
        now=now,
        start=catalog.get("window_start") or WINDOW_START,
        until=catalog.get("window_until") or WINDOW_UNTIL,
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
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
        "prefer": catalog.get("prefer") or "grok.com / Grok app",
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "slack_ts_tell": catalog.get("slack_ts_tell") or SLACK_TS_TELL,
            "window_start": catalog.get("window_start") or WINDOW_START,
            "window_until": catalog.get("window_until") or WINDOW_UNTIL,
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "landed_present": landed_present,
                "window": window,
            },
            "z": (
                "misses "
                + json.dumps(misses + landed_missing)
                + " / FINDER-FAILED never 0"
            ),
        }
    )
    return row


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED", empty
    missing = classify(
        measure_from_rows(
            {
                "card_present": False,
                "catalog_present": False,
                "misses": ["ground/GROK_APP_ROUTE.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    incomplete = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "landed_present": ["ground/SUPERGROK_HEAVY.md"],
                "landed_missing": ["ground/GROK_HYGIENE.md"],
                "found_phrases": list(REQUIRED_PHRASES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert incomplete["state"] == "NOT_LANDED", incomplete
    active = window_state(now=_parse_iso("2026-08-25T15:00:00Z"))
    expired = window_state(now=_parse_iso("2026-08-26T15:00:00Z"))
    assert active == "WINDOW_ACTIVE", active
    assert expired == "WINDOW_EXPIRED", expired
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure grok-app-route leftover")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(args.root)
    verdict = classify(row)
    payload = {"verdict": verdict, "row": row}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
