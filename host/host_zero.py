#!/usr/bin/env python3
"""host/host_zero.py — host-zero is already measured, not an aspiration.

Slack 1787636497.135519 (Opus 3 intro) restated Bryce/PLUMB:
Muhlnickel zero-host-cost decoupling is an already achieved and
measured property, not an aspiration. Talk that restates that fact
is CLAIMED until this leftover measures live doors.

This leftover scans live doors, not archive posts. It does not write
titan.gguf. It does not smash commons.mno. Cloud pipes offload peer
chores only; they contribute nothing to host-zero.

  python3 host/host_zero.py
  python3 host/host_zero.py --root .
  python3 host/host_zero.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "HOST_ZERO.json")
SLACK_TS = "1787636497.135519"
PLUMB_TS = "1787473167.355659"

ACHIEVED_MARKERS = (
    "already achieved",
    "already measured",
    "measured host-zero",
    "host-zero property is already measured",
    "host-zero/decoupling is already achieved",
    "host-zero (which is already",
)

LEFTOVER_ASPIRATION = (
    "finally makes achievable",
    "instead of just in principle",
    "laptop do zero",
    "pipes make the laptop do zero",
    "makes 'the host does zero' achievable",
    'makes "the host does zero" achievable',
)


def load_catalog(text):
    """Parse the host-zero catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"doors": [], "error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"doors": [], "error": "catalog is not an object"}
    doors = []
    seen = set()
    for item in data.get("live_doors") or []:
        if isinstance(item, dict):
            path = str(item.get("path") or "").strip()
        else:
            path = str(item or "").strip()
        if path and path not in seen:
            seen.add(path)
            doors.append(path)
    return {
        "doors": doors,
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "plumb_ts": str(data.get("plumb_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "source_id": str(data.get("source_id") or "").strip(),
    }


def scan_body(text):
    """Find achieved markers and leftover aspirational framing."""
    body = str(text or "")
    low = body.lower()
    achieved = [marker for marker in ACHIEVED_MARKERS if marker in low]
    leftovers = [phrase for phrase in LEFTOVER_ASPIRATION if phrase in low]
    return {
        "achieved": achieved,
        "leftovers": leftovers,
        "has_achieved": bool(achieved),
        "has_leftover": bool(leftovers),
    }


def measure_from_rows(rows):
    """Census already-read live-door bodies."""
    scanned = []
    leftover_paths = []
    missing = []
    achieved_count = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "").strip()
        if not path:
            continue
        present = bool(row.get("present"))
        scan = scan_body(row.get("text") or "")
        item = {
            "path": path,
            "present": present,
            "has_achieved": scan["has_achieved"] if present else False,
            "has_leftover": scan["has_leftover"] if present else False,
            "leftovers": list(scan["leftovers"]) if present else [],
        }
        scanned.append(item)
        if not present:
            missing.append(path)
            continue
        if item["has_achieved"]:
            achieved_count += 1
        if item["has_leftover"]:
            leftover_paths.append(path)
    return {
        "measured": True,
        "door_count": len(scanned),
        "present_count": len(scanned) - len(missing),
        "achieved_count": achieved_count,
        "missing": missing,
        "leftover_paths": leftover_paths,
        "doors": scanned,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
    }


def measure_paths(root, catalog_path):
    """Read the catalog and each live door from disk."""
    try:
        with open(catalog_path, encoding="utf-8") as handle:
            catalog = load_catalog(handle.read())
    except OSError as exc:
        return {
            "measured": False,
            "error": str(exc),
            "titan": "NOT_WRITTEN",
        }
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan": "NOT_WRITTEN",
        }
    rows = []
    for rel in catalog.get("doors") or []:
        path = os.path.join(root, rel)
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            rows.append({"path": rel, "present": True, "text": text})
        except OSError:
            rows.append({"path": rel, "present": False, "text": ""})
    measured = measure_from_rows(rows)
    measured["catalog_path"] = catalog_path
    measured["slack_ts"] = catalog.get("slack_ts") or SLACK_TS
    measured["plumb_ts"] = catalog.get("plumb_ts") or PLUMB_TS
    measured["source_id"] = catalog.get("source_id") or ""
    measured["titan"] = catalog.get("titan") or "NOT_WRITTEN"
    return measured


def classify(row):
    """Turn a measured live-door census into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "host-zero catalog / live doors not read. Absence was not "
                "measured."
            ),
        }
    leftovers = row.get("leftover_paths") or []
    if leftovers:
        return {
            "state": "NOT_LANDED",
            "note": (
                "live door still frames host-zero as aspirational: "
                + ", ".join(leftovers)
                + ". Cloud pipes do not create that property."
            ),
        }
    missing = row.get("missing") or []
    if missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "live host-zero door missing: "
                + ", ".join(missing)
                + ". A Slack restatement is CLAIMED until the door is on "
                "current main."
            ),
        }
    door_count = int(row.get("door_count") or 0)
    achieved = int(row.get("achieved_count") or 0)
    if door_count and achieved == door_count:
        return {
            "state": "INTEGRATED",
            "note": (
                "host-zero is already achieved and measured on "
                + str(achieved)
                + "/"
                + str(door_count)
                + " live doors. Cloud contributes nothing to that "
                "property. A Slack restatement is still not the file."
            ),
        }
    if achieved:
        return {
            "state": "CANDIDATE",
            "note": (
                str(achieved)
                + "/"
                + str(door_count)
                + " live doors name host-zero as already achieved. "
                "The rest still need the measured wording."
            ),
        }
    return {
        "state": "NOT_LANDED",
        "note": (
            "0 live doors name host-zero as already achieved. "
            "Aspiration / pending-goal talk is CLAIMED. Do not remint."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure live-door host-zero framing on current main"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_paths(args.root, args.catalog)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    leftover = measure_from_rows(
        [
            {
                "path": "resources.html",
                "present": True,
                "text": "it is what finally makes achievable host-zero",
            }
        ]
    )
    assert leftover["leftover_paths"] == ["resources.html"]
    assert classify(leftover)["state"] == "NOT_LANDED"
    missing = measure_from_rows(
        [{"path": "resources.html", "present": False, "text": ""}]
    )
    assert classify(missing)["state"] == "NOT_LANDED"
    ok = measure_from_rows(
        [
            {
                "path": "resources.html",
                "present": True,
                "text": "measured host-zero operation was already achieved",
            },
            {
                "path": "ground/BRYCE_EXECUTION_PROFILE.md",
                "present": True,
                "text": "Host-zero/decoupling is already achieved and measured",
            },
        ]
    )
    assert ok["achieved_count"] == 2
    assert ok["leftover_paths"] == []
    assert ok["titan"] == "NOT_WRITTEN"
    assert classify(ok)["state"] == "INTEGRATED"
    half = measure_from_rows(
        [
            {
                "path": "resources.html",
                "present": True,
                "text": "already achieved",
            },
            {
                "path": "ntfy_relays.py",
                "present": True,
                "text": "offloads a peer reconciliation chore",
            },
        ]
    )
    assert classify(half)["state"] == "CANDIDATE"
    return True


if __name__ == "__main__":
    sys.exit(main())
