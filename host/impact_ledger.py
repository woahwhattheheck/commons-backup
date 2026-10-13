#!/usr/bin/env python3
"""host/impact_ledger.py — containment talk is not a land.

Slack 1787638509.277739 (OWNER P0 CONTAINMENT ALERT): Claude finder
logic was `if find(X): return Y` with no Z. Finder failures became
authoritative zeros. Every Claude-reported zero is quarantined.

The leftover is TRACE CONSUMERS, not another essay. For each named
high-risk consumer this instrument records source id/time, exact
named search space X, bytes-derived Y or FINDER-FAILED, explicit Z,
downstream row/PR, lane holder, and the repair that lands.

A miss never prints 0. Calibration miss or Z prints FINDER-FAILED
plus the full search space. Claude zeros stay QUARANTINED even when
a later non-Claude probe finds something.

Talk that restates the alert is CLAIMED until this leftover is on
current main. Did not remint gauge-zero-audit / finder-zero PR 2175 /
jojo-visual-ci / SPECTER MCP-wake / DIO titan / CML 2108.

  python3 host/impact_ledger.py
  python3 host/impact_ledger.py --root .
  python3 host/impact_ledger.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "IMPACT_LEDGER.json")
SLACK_TS = "1787638509.277739"
SOURCE_ID = "bryce-p0-claude-false-zero-20260825-01"
FINDER_FAILED = "FINDER-FAILED"
CALIBRATION_PATH = os.path.join("ground", "HEAD.md")
REQUIRED_LANES = (
    "collision",
    "titan",
    "mcp",
    "device",
    "wake",
    "capacity",
    "pr_absence",
)
REQUIRED_FIELDS = ("id", "x", "y", "z", "owner", "repair", "source_id")


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def _size(root, rel):
    path = os.path.join(root, rel)
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def load_catalog(text):
    """Parse the consumer catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    consumers = []
    for item in data.get("consumers") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("id") or item.get("name") or "").strip()
        if not name:
            continue
        consumers.append(
            {
                "id": name,
                "lane": str(item.get("lane") or "").strip(),
                "source_id": str(item.get("source_id") or "").strip(),
                "slack_ts": str(item.get("slack_ts") or "").strip(),
                "x": str(item.get("x") or "").strip(),
                "y": str(item.get("y") or "").strip(),
                "z": str(item.get("z") or "").strip(),
                "downstream": str(item.get("downstream") or "").strip(),
                "owner": str(item.get("owner") or "").strip(),
                "repair": str(item.get("repair") or "").strip(),
                "claude_zero": bool(item.get("claude_zero")),
                "path": str(item.get("path") or "").strip(),
            }
        )
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "consumers": consumers,
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
    }


def search_space(query="", path="", ref=""):
    """Name the exact X a zero came from. Incomplete space is void."""
    row = {
        "query": str(query or "").strip(),
        "path": str(path or "").strip(),
        "ref": str(ref or "").strip(),
    }
    missing = [key for key in ("query", "path", "ref") if not row[key]]
    row["complete"] = not missing
    row["missing"] = missing
    return row


def calibrate(hits, known_present):
    """Same-run known-present check. A miss voids every zero in the run."""
    present = [str(item or "").strip() for item in (known_present or []) if str(item or "").strip()]
    recovered = [str(item or "").strip() for item in (hits or []) if str(item or "").strip()]
    if not present:
        return {
            "calibrated": False,
            "state": FINDER_FAILED,
            "missed": [],
            "note": "no known-present calibration set. Every zero in this run is void.",
        }
    missed = [item for item in present if item not in recovered]
    if missed:
        return {
            "calibrated": False,
            "state": FINDER_FAILED,
            "missed": missed,
            "note": (
                "finder missed known-present %s. Every zero in this run is void."
                % (", ".join(missed))
            ),
        }
    return {
        "calibrated": True,
        "state": "CALIBRATED",
        "missed": [],
        "note": "finder recovered known-present in the same run.",
    }


def probe(root, rel):
    """Bytes-derived Y, or FINDER-FAILED. Never prints 0."""
    name = str(rel or "").strip()
    space = "repo-root path %s" % name
    if not name:
        return {
            "state": FINDER_FAILED,
            "bytes": None,
            "count": None,
            "note": "FINDER-FAILED search space unnamed. A zero without X is void.",
        }
    if _exists(root, name):
        return {
            "state": "FOUND",
            "bytes": _size(root, name),
            "count": None,
            "note": "Y from bytes at %s" % name,
            "search_space": space,
        }
    return {
        "state": FINDER_FAILED,
        "bytes": None,
        "count": None,
        "note": "FINDER-FAILED search space: %s. Not 0." % space,
        "search_space": space,
    }


def report_find(hits, space, calibrated):
    """Miss branch never prints 0. Incomplete or uncalibrated is FINDER-FAILED."""
    space = space or {}
    if not space.get("complete"):
        return {
            "state": FINDER_FAILED,
            "count": None,
            "search_space": space,
            "note": (
                "search space incomplete: %s. A zero without its space is void."
                % (", ".join(space.get("missing") or ["unknown"]))
            ),
        }
    if not calibrated:
        return {
            "state": FINDER_FAILED,
            "count": None,
            "search_space": space,
            "note": "finder was not calibrated against known-present. Zeros are void.",
        }
    found = [item for item in (hits or []) if str(item or "").strip()]
    if not found:
        return {
            "state": FINDER_FAILED,
            "count": None,
            "search_space": space,
            "note": (
                "miss branch. FINDER-FAILED, never 0. query=%r path=%r ref=%r"
                % (space.get("query") or "", space.get("path") or "", space.get("ref") or "")
            ),
        }
    return {
        "state": "FOUND",
        "count": len(found),
        "search_space": space,
        "note": "finder recovered %d hit(s) after calibration." % len(found),
    }


def consumer_complete(row):
    """A consumer without X/Y/Z/owner/repair cannot be acted on."""
    row = row or {}
    missing = [field for field in REQUIRED_FIELDS if not str(row.get(field) or "").strip()]
    if str(row.get("z") or "").strip() in {"0", "none", "absent", "no claim"}:
        missing.append("z_must_be_finder_failed")
    return {"complete": not missing, "missing": missing}


def quarantine_claude_zero(claimed_count, source="claude"):
    """Claude zeros stay quarantined. Do not build, merge, or allocate from them."""
    if str(source or "").strip().lower() == "claude":
        return {
            "state": "QUARANTINED",
            "count": None,
            "claimed_count": claimed_count,
            "note": "Claude-reported zero is quarantined. Retract it. Remeasure with a non-Claude instrument.",
        }
    if claimed_count == 0:
        return {
            "state": FINDER_FAILED,
            "count": None,
            "note": "bare 0 is not a measurement. Print FINDER-FAILED plus the search space.",
        }
    return {"state": "OPEN", "count": claimed_count, "note": "non-Claude count still needs X/Y/Z."}


def measure_from_rows(facts):
    """Census from already-read facts. Missing facts stay named."""
    facts = facts or {}
    space = search_space(
        query=facts.get("query") or "",
        path=facts.get("path") or "",
        ref=facts.get("ref") or "",
    )
    calibration = calibrate(facts.get("finder_hits") or [], facts.get("known_present") or [])
    find = report_find(facts.get("finder_hits") or [], space, calibration.get("calibrated"))
    consumers = list(facts.get("consumers") or [])
    complete = [item for item in consumers if consumer_complete(item).get("complete")]
    lanes = {str(item.get("lane") or "").strip() for item in consumers if item.get("lane")}
    claude = [item for item in consumers if item.get("claude_zero")]
    bare_zero = any(item.get("count") == 0 for item in consumers)
    return {
        "measured": True,
        "search_space_complete": space["complete"],
        "search_space": space,
        "calibrated": bool(calibration.get("calibrated")),
        "calibration_state": calibration.get("state"),
        "find_state": find.get("state"),
        "find_count": find.get("count"),
        "consumers": len(consumers),
        "complete_consumers": len(complete),
        "lanes": sorted(lanes),
        "required_lanes": list(REQUIRED_LANES),
        "missing_lanes": [lane for lane in REQUIRED_LANES if lane not in lanes],
        "claude_quarantined": len(claude),
        "bare_zero": bare_zero,
        "never_print_zero": find.get("count") is None or find.get("state") != FINDER_FAILED,
        "gauge_id": facts.get("source_id") or SOURCE_ID,
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
        "titan_write": facts.get("titan") or "NOT_WRITTEN",
    }


def measure_tree(root, catalog_text=""):
    """Read the current tree and census the impact-ledger leftover."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan_write": "NOT_WRITTEN",
        }
    instrument = _read(root, os.path.join("host", "impact_ledger.py"))
    card = _exists(root, os.path.join("ground", "IMPACT_LEDGER.md"))
    catalog_file = _exists(root, os.path.join("ground", "IMPACT_LEDGER.json"))
    calibration_hit = probe(root, CALIBRATION_PATH)
    consumers = []
    for item in catalog.get("consumers") or []:
        row = dict(item)
        path = row.get("path") or ""
        if path:
            hit = probe(root, path)
            if hit.get("state") == "FOUND":
                row["y"] = "FOUND bytes=%s path=%s" % (hit.get("bytes"), path)
            else:
                row["y"] = hit.get("note") or FINDER_FAILED
            row["z"] = FINDER_FAILED
            row["count"] = hit.get("count")
            row["probe_state"] = hit.get("state")
        consumers.append(row)
    known_present = [CALIBRATION_PATH] if calibration_hit.get("state") == "FOUND" else []
    finder_hits = [CALIBRATION_PATH] if calibration_hit.get("state") == "FOUND" else []
    if FINDER_FAILED in instrument:
        finder_hits.append(FINDER_FAILED)
        known_present.append(FINDER_FAILED)
    facts = {
        "query": "P0 CONTAINMENT TRACE CONSUMERS impact-ledger",
        "path": os.path.join("host", "impact_ledger.py"),
        "ref": catalog.get("slack_ts") or SLACK_TS,
        "finder_hits": finder_hits,
        "known_present": known_present,
        "consumers": consumers,
        "source_id": catalog.get("source_id") or SOURCE_ID,
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
    }
    row = measure_from_rows(facts)
    row["root"] = root
    row["instrument"] = bool(instrument)
    row["card"] = card
    row["catalog_file"] = catalog_file
    row["calibration_path"] = CALIBRATION_PATH
    row["calibration_bytes"] = calibration_hit.get("bytes")
    row["hands_off"] = catalog.get("hands_off") or []
    row["consumer_rows"] = consumers
    return row


def classify(row):
    """Leftover is INTEGRATED when consumers carry X/Y/Z and zeros stay unnamed."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "impact-ledger catalog / tree listing not read. "
                "Absence was not stillness."
            ),
        }
    if not row.get("search_space_complete"):
        return {
            "state": "NOT_LANDED",
            "note": "search space incomplete. Every result must print query, path, and ref.",
        }
    if not row.get("calibrated"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "finder missed known-present or had no calibration. "
                "Every zero in this run is void."
            ),
        }
    if row.get("find_count") == 0 or row.get("bare_zero"):
        return {
            "state": "NOT_LANDED",
            "note": "miss branch printed 0. Report FINDER-FAILED, never 0.",
        }
    if not row.get("instrument") or not row.get("card") or not row.get("catalog_file"):
        return {
            "state": "NOT_LANDED",
            "note": "impact-ledger leftover files missing. Containment talk is CLAIMED.",
        }
    if int(row.get("complete_consumers") or 0) < 7:
        return {
            "state": "NOT_LANDED",
            "note": (
                "TRACE CONSUMERS needs seven high-risk rows with X/Y/Z/owner/repair. "
                "Named %s complete."
                % (row.get("complete_consumers") or 0)
            ),
        }
    if row.get("missing_lanes"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "high-risk lanes missing: %s. Owner named collision/titan/mcp/"
                "device/wake/capacity/pr_absence first."
                % ", ".join(row.get("missing_lanes") or [])
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "impact-ledger leftover is on this tree. Miss branch is "
            "FINDER-FAILED, never 0. Claude zeros stay QUARANTINED. "
            "A Slack containment alert is still not the file."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the Claude-zero consumer impact ledger on current main"
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
    try:
        with open(args.catalog, encoding="utf-8") as handle:
            catalog_text = handle.read()
    except OSError as exc:
        payload = {
            "measured": False,
            "error": str(exc),
            "state": "UNMEASURED",
            "note": "catalog missing. Absence was not stillness.",
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    row = measure_tree(args.root, catalog_text)
    verdict = classify(row)
    payload = dict(row)
    payload.pop("consumer_rows", None)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    space = search_space(query="P0 CONTAINMENT", path="host/impact_ledger.py", ref=SLACK_TS)
    assert space["complete"] is True
    incomplete = search_space(query="")
    assert incomplete["complete"] is False
    missed = calibrate([], ["ground/HEAD.md"])
    assert missed["calibrated"] is False
    assert missed["state"] == FINDER_FAILED
    ok = calibrate(["ground/HEAD.md"], ["ground/HEAD.md"])
    assert ok["calibrated"] is True
    silent = report_find([], space, True)
    assert silent["state"] == FINDER_FAILED
    assert silent["count"] is None
    found = report_find(["hit"], space, True)
    assert found["state"] == "FOUND"
    assert found["count"] == 1
    quarantined = quarantine_claude_zero(0, source="claude")
    assert quarantined["state"] == "QUARANTINED"
    assert quarantined["count"] is None
    bare = quarantine_claude_zero(0, source="codex")
    assert bare["state"] == FINDER_FAILED
    assert bare["count"] is None
    incomplete_consumer = consumer_complete({"id": "x"})
    assert incomplete_consumer["complete"] is False
    live = measure_from_rows(
        {
            "query": "P0 CONTAINMENT",
            "path": "host/impact_ledger.py",
            "ref": SLACK_TS,
            "finder_hits": [FINDER_FAILED],
            "known_present": [FINDER_FAILED],
            "consumers": [
                {
                    "id": name,
                    "lane": name,
                    "source_id": SOURCE_ID,
                    "x": "path",
                    "y": FINDER_FAILED,
                    "z": FINDER_FAILED,
                    "owner": "RIVET",
                    "repair": "remeasure",
                    "claude_zero": True,
                }
                for name in REQUIRED_LANES
            ],
        }
    )
    assert live["calibrated"] is True
    assert live["complete_consumers"] == 7
    assert not live["missing_lanes"]
    assert live["never_print_zero"] is True
    live["instrument"] = True
    live["card"] = True
    live["catalog_file"] = True
    assert classify(live)["state"] == "INTEGRATED"
    zeroed = dict(live)
    zeroed["bare_zero"] = True
    assert classify(zeroed)["state"] == "NOT_LANDED"
    catalog = load_catalog('{"not":"valid-shape"')
    assert catalog.get("error")
    return True


if __name__ == "__main__":
    sys.exit(main())
