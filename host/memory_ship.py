#!/usr/bin/env python3
"""Component implementation and operation."""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "MEMORY_SHIP.json")
DEFAULT_CARD = os.path.join("ground", "MEMORY_SHIP.md")
SLACK_TS = "1787641807.145549"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "memory_ship.py"),
    os.path.join("memory_board.py"),
    os.path.join("memory", "index.html"),
    os.path.join("ground", "SITTING_REMINT.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("memory_board.py"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "SITTING_REMINT.md"),
    os.path.join("memory_board.py"),
    os.path.join("memory", "index.html"),
)
REQUIRED_PHRASES = (
    "use the memory feature",
    "unused memory board",
    "role-only",
    "ship_state",
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


def load_catalog(text):
    """Parse the memory-ship catalog. Empty or invalid is measured empty."""
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
        "has_ship_state": bool(facts.get("has_ship_state")),
        "has_ship_column": bool(facts.get("has_ship_column")),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "closes_door": bool(facts.get("closes_door")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Memory-ship leftover not read. Absence was not stillness. "
                "An unused ROLE-only memory board is talk, not a land."
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
    if row.get("closes_door"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover tried to close the door. Memory stays optional context. "
                "FINDER-FAILED, never 0."
            ),
        }
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Use-the-memory-feature talk is CLAIMED until the leftover "
                "ships. FINDER-FAILED, never 0."
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
    if not row.get("has_ship_state") or not row.get("has_ship_column"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "memory projection missing ship_state or the index ship column. "
                "ROLE-only boards stay invisible talk. FINDER-FAILED, never 0."
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
    return {
        "state": "INTEGRATED",
        "note": (
            "Memory-ship leftover is on this tree. Unused ROLE-only boards "
            "are named. WORK_STATE must cite current main to be SHIPPED. "
            "Memory stays optional context. A Slack ask is still not the file."
        ),
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
    board_src = _read(root, os.path.join("memory_board.py"))
    index_html = _read(root, os.path.join("memory", "index.html"))
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
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "has_ship_state": "def ship_state_for_board" in board_src,
        "has_ship_column": ">ship<" in index_html.lower() and "UNUSED" in index_html,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "closes_door": False,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "landed_present": landed_present,
                "has_ship_state": facts["has_ship_state"],
                "has_ship_column": facts["has_ship_column"],
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
                "misses": ["ground/MEMORY_SHIP.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    gated = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "memory_is_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert gated["state"] == "NOT_LANDED", gated
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure memory-ship leftover")
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
