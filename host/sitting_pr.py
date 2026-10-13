#!/usr/bin/env python3
"""host/sitting_pr.py — an open remint PR is not a land.

Slack 1787645172.017469 (DIO TITAN CONTAINMENT DURABLE) plus
ship-talk: talk is CLAIMED until this leftover names sitting
remint PRs whose leftover files are already on current main.

Measured this run:
- cash-now leftover already INTEGRATED (ground/CASH_NOW.md)
- DIO containment receipt already DURABLE_ON_MAIN
- Titan desk already reports NOT_LANDED / PAUSED
- PR 2207 is still OPEN/DIRTY and remints cash-now

A remint PR is SUPERSEDED, not a second land. Do not remint
SITTING_REMINT, CASH_NOW, DIO containment, or Titan MOVE bytes.
Do not write titan. Do not smash commons.mno. No auth. No gate.
Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/sitting_pr.py
  python3 host/sitting_pr.py --root .
  python3 host/sitting_pr.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "SITTING_PR.json")
DEFAULT_CARD = os.path.join("ground", "SITTING_PR.md")
SLACK_TS = "1787645172.017469"
DIO_RECEIPT = os.path.join("p", "dio-titan-move-containment-hardening-20260825-01.md")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("ground", "CASH_NOW.md"),
    os.path.join("host", "cash_now.py"),
    DIO_RECEIPT,
    os.path.join("ground", "SITTING_REMINT.md"),
    os.path.join("ground", "TITAN_MOVE.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "CASH_NOW.md"),
    os.path.join("host", "cash_now.py"),
    DIO_RECEIPT,
    os.path.join("ground", "SITTING_REMINT.md"),
    os.path.join("ground", "TITAN_MOVE.md"),
    os.path.join("ground", "TITAN_APPEND_GUARD.md"),
    os.path.join("ground", "BUILD_SWEEP_ACT.md"),
)
REQUIRED_PHRASES = (
    "sitting remint pr",
    "open remint",
    "remint pr is not a land",
    "2207",
    "cash-now leftover is already on main",
    "dio titan containment",
    "do not remint",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "open door",
    "no auth",
    "no gate",
    "talk is not a land",
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
    """Parse the sitting-PR catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "sitting_remints": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "sitting_remints": []}
    raw_sitting_remints = data.get("sitting_remints") or []
    if not isinstance(raw_sitting_remints, list):
        return {
            "error": "sitting_remints is not a list",
            "sitting_remints": [],
        }
    rows = []
    for item in raw_sitting_remints:
        if not isinstance(item, dict):
            continue
        number = str(item.get("number") or "").strip()
        if not number:
            continue
        rows.append(
            {
                "number": number,
                "leftover": str(item.get("leftover") or "").strip(),
                "pr_state": str(item.get("pr_state") or "").strip().upper(),
                "land_state": str(item.get("land_state") or "").strip().upper(),
            }
        )
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": data.get("no_auth", True) is True,
        "no_gate": data.get("no_gate", True) is True,
        "sitting_remints": rows,
        "error": "",
    }


def is_2207_superseded(item):
    """True only while PR 2207 is the measured open-dirty remint."""
    item = item if isinstance(item, dict) else {}
    return (
        str(item.get("number")) == "2207"
        and item.get("pr_state") == "OPEN_DIRTY"
        and item.get("land_state") == "SUPERSEDED"
    )


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
        "sitting_remints": list(facts.get("sitting_remints") or []),
        "names_2207_superseded": bool(facts.get("names_2207_superseded")),
        "claims_2207_integrated": bool(facts.get("claims_2207_integrated")),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured sitting-PR census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Sitting-PR leftover not read. Absence was not stillness. "
                "An open remint PR is not a land."
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
    if not row.get("card_present") or not row.get("catalog_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Sitting remint PR / Titan-containment-durable talk is CLAIMED "
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
    if row.get("claims_2207_integrated"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog claims PR 2207 INTEGRATED. Cash-now leftover is already "
                "on main; the remint PR is SUPERSEDED, not a second land. "
                "FINDER-FAILED, never 0."
            ),
        }
    if not row.get("names_2207_superseded"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "sitting remint PR 2207 is not named SUPERSEDED. An open remint "
                "is not a land. FINDER-FAILED, never 0."
            ),
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in (row.get("found_phrases") or [])]
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
            "Sitting-PR leftover is on this tree. Cash-now leftover is already "
            "on main. DIO Titan containment receipt is already on main. "
            "PR 2207 is SUPERSEDED, not a second land. A Slack durable "
            "announcement is still not the file."
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
    sitting = catalog.get("sitting_remints") or []
    names_2207_superseded = any(is_2207_superseded(item) for item in sitting)
    claims_2207_integrated = any(
        str(item.get("number")) == "2207" and item.get("land_state") == "INTEGRATED"
        for item in sitting
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
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "sitting_remints": sitting,
        "names_2207_superseded": names_2207_superseded,
        "claims_2207_integrated": claims_2207_integrated,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
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
                "sitting_remints": sitting,
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
                "misses": ["ground/SITTING_PR.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    claimed = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "sitting_remints": [{"number": "2207", "land_state": "INTEGRATED"}],
                "names_2207_superseded": False,
                "claims_2207_integrated": True,
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert claimed["state"] == "NOT_LANDED", claimed
    assert "SUPERSEDED" in claimed["note"], claimed
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure sitting remint PR leftover")
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