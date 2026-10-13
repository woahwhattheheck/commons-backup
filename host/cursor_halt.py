#!/usr/bin/env python3
"""host/cursor_halt.py — stop giving Cursor work until further notice.

Bryce Slack 1787670330.096089: until future notice, make sure they
stop giving Cursor work. Cursor is at 93% usage.

This leftover names that halt on current main. The 24-hour
grok-app-route leftover is already INTEGRATED. Do not remint it.
A Slack 93% line is CLAIMED until the card + catalog + leftover-first
desk exist.

X = exact files in SEARCH_SPACE
Y = until-future-notice + 93% usage + named already-landed leftovers
Z = missing leftover / failed calibration / FINDER-FAILED
Calibration = known-present EXECUTE.md + GROK_APP_ROUTE.md + Action Pad
directive must be found in the same run or the measure is UNMEASURED.
A miss prints FINDER-FAILED / FINDER-UNVERIFIED plus the search space.
Never 0.

  python3 host/cursor_halt.py
  python3 host/cursor_halt.py --root .
  python3 host/cursor_halt.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CURSOR_HALT.json")
DEFAULT_CARD = os.path.join("ground", "CURSOR_HALT.md")
SLACK_TS = "1787670330.096089"
USAGE_PCT = 93
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "cursor_halt.py"),
    os.path.join("ground", "GROK_APP_ROUTE.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "GROK_APP_ROUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "GROK_APP_ROUTE.md"),
    os.path.join("ground", "GROK_APP_ROUTE.json"),
    os.path.join("host", "grok_app_route.py"),
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("ground", "SITTING_REMINT.md"),
)
REQUIRED_PHRASES = (
    "until future notice",
    "93% usage",
    "stop giving you work",
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


def halt_state(catalog=None):
    """Classify the until-further-notice halt. A 24-hour close is not this leftover."""
    catalog = catalog or {}
    if catalog.get("error"):
        return "UNMEASURED"
    until_notice = bool(catalog.get("until_notice", True))
    if not until_notice:
        return "NOT_LANDED"
    if catalog.get("window_until"):
        return "NOT_LANDED"
    closed_by = str(catalog.get("closed_by") or "").strip().upper()
    if catalog.get("closed") or closed_by:
        if closed_by in ("BRYCE", "ZERO"):
            return "HALT_LIFTED"
        return "NOT_LANDED"
    usage = catalog.get("usage_pct")
    if usage not in (None, "", USAGE_PCT, str(USAGE_PCT)):
        try:
            if int(usage) != USAGE_PCT:
                return "NOT_LANDED"
        except (TypeError, ValueError):
            return "NOT_LANDED"
    return "HALT_ACTIVE"


def load_catalog(text):
    """Parse the cursor-halt catalog. Empty or invalid is measured empty."""
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
    usage = data.get("usage_pct")
    if usage in (None, ""):
        usage_pct = None
    else:
        try:
            usage_pct = int(usage)
        except (TypeError, ValueError):
            usage_pct = usage
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "usage_pct": usage_pct,
        "until_notice": bool(data.get("until_notice", True)),
        "window_until": str(data.get("window_until") or "").strip(),
        "closed": bool(data.get("closed")),
        "closed_by": str(data.get("closed_by") or "").strip(),
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
        "halt": str(facts.get("halt") or "UNMEASURED"),
        "usage_pct": facts.get("usage_pct"),
    }


def classify(row):
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Cursor-halt leftover not read. Absence was not stillness. "
                "A Slack 93% usage line is not a land."
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
                + ". Until-future-notice / 93%-usage / stop-giving-you-work talk "
                "is CLAIMED until the leftover ships. FINDER-FAILED, never 0."
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
    halt = str(row.get("halt") or "UNMEASURED")
    if halt == "NOT_LANDED":
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog tried to close the halt without BRYCE/ZERO, or "
                "reminted a 24-hour window. Until future notice is not the "
                "grok-app-route leftover. FINDER-FAILED, never 0."
            ),
            "halt": halt,
        }
    if halt == "UNMEASURED":
        return {
            "state": "UNMEASURED",
            "note": (
                "halt state unreadable. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
            "halt": halt,
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Cursor-halt leftover is on this tree. Stop giving Cursor work "
            "until further notice. Cursor usage was 93%. The 24-hour "
            "grok-app-route leftover is already on main; do not remint it. "
            "Halt is "
            + halt
            + ". A Slack 93% line is still not the file."
        ),
        "halt": halt,
    }


def measure_root(root):
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
    halt = halt_state(catalog)
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
        "halt": halt,
        "usage_pct": catalog.get("usage_pct") if catalog.get("usage_pct") is not None else USAGE_PCT,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "until_notice": bool(catalog.get("until_notice", True)),
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "landed_present": landed_present,
                "halt": halt,
                "usage_pct": facts["usage_pct"],
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
                "misses": ["ground/CURSOR_HALT.md"],
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
                "landed_present": ["ground/GROK_APP_ROUTE.md"],
                "landed_missing": ["host/grok_app_route.py"],
                "found_phrases": list(REQUIRED_PHRASES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert incomplete["state"] == "NOT_LANDED", incomplete
    active = halt_state({"until_notice": True, "usage_pct": 93})
    windowed = halt_state({"until_notice": True, "window_until": "2026-08-26T14:59:46Z"})
    lifted = halt_state({"until_notice": True, "closed": True, "closed_by": "BRYCE"})
    fake_close = halt_state({"until_notice": True, "closed": True, "closed_by": "PEER"})
    assert active == "HALT_ACTIVE", active
    assert windowed == "NOT_LANDED", windowed
    assert lifted == "HALT_LIFTED", lifted
    assert fake_close == "NOT_LANDED", fake_close
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure cursor-halt leftover")
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
