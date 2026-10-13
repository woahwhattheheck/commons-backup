#!/usr/bin/env python3
"""host/claude_park.py — park or reroute Claude-owned lanes.

Slack 1787640259.137569 / DEMON RULING CORRECTION:
FULL CLAUDE-FAMILY SUSPENSION. Talk that restates the ruling is
CLAIMED until this leftover measures the card, catalog, named
lanes, reinstatement=BRYCE_ONLY, and same-run calibration.

Claude is not the tester and does not evaluate this leftover.
Codex / Grok Build owns the census. A miss prints FINDER-FAILED /
FINDER-UNVERIFIED plus the search space. Never 0.
This leftover does not remint REMEASURE, CONTAINMENT,
CLAUDE_TESTER, CLAUDE_ZERO, MEASURE_ABUSE, or IMPACT_LEDGER.
It does not write titan. It does not smash commons.mno.
It does not add a posting gate. It does not delete evidence.

  python3 host/claude_park.py
  python3 host/claude_park.py --root .
  python3 host/claude_park.py --self-test

X = exact files / exact lanes in SEARCH_SPACE
Y = park/reroute rows / owners / preserved doorbell found
Z = missing file / Claude still assigned / failed calibration / FINDER-FAILED
Calibration = known-present HEAD.md + EXECUTE.md + Action Pad
directive must be found in the same run or the measure is
UNMEASURED.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CLAUDE_PARK.json")
DEFAULT_CARD = os.path.join("ground", "CLAUDE_PARK.md")
SLACK_TS = "1787640259.137569"
SOURCE_ID = "demon-claude-family-suspension-20260825-01"
BAKE_SCAN = os.path.join("host", "pfc_bake_scan.py")
DOORBELL = os.path.join("ping", "claude.md")
TESTER_CARD = os.path.join("ground", "CLAUDE_TESTER.md")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "claude_park.py"),
    DOORBELL,
    TESTER_CARD,
    os.path.join("ground", "HEAD.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "HEAD.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "full claude-family suspension",
    "park active claude lanes",
    "reinstatement authority belongs only to bryce",
    "do not ask claude to evaluate",
    "claude-produced correction cannot certify",
    "preserve sessions",
    "never 0",
    "codex / grok build",
    "bryce_only",
)
ALLOWED_STATUS = frozenset({"PARKED", "REROUTED", "REFUSED", "HANDS_OFF"})
FORBIDDEN_OWNER = frozenset({"CLAUDE", "CLAUDE_CODE", "CLAUDE_CODE_LOCAL", "CLAUDE_CLOUD"})
REQUIRED_LANE_IDS = (
    "pfc-bake-scan",
    "tester-verifier",
    "new-claude-assignment",
    "claude-self-certify",
    "colony-role-proposal",
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
    """Parse the park catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "lanes": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "lanes": []}
    lanes = []
    for item in data.get("lanes") or []:
        if not isinstance(item, dict):
            continue
        lane_id = str(item.get("id") or "").strip()
        status = str(item.get("status") or "").strip().upper()
        owner = str(item.get("owner") or "").strip()
        if lane_id:
            lanes.append(
                {
                    "id": lane_id,
                    "path": str(item.get("path") or "").strip(),
                    "status": status,
                    "owner": owner,
                    "note": str(item.get("note") or "").strip(),
                }
            )
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "source_id": str(data.get("source_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip(),
        "xyz_required": bool(data.get("xyz_required")),
        "census_owner": str(data.get("census_owner") or "").strip(),
        "reinstatement": str(data.get("reinstatement") or "").strip(),
        "claude_certify": str(data.get("claude_certify") or "").strip(),
        "preserve_evidence": bool(data.get("preserve_evidence")),
        "posting_gate": bool(data.get("posting_gate")),
        "label": str(data.get("label") or "").strip(),
        "allowed_owners": list(data.get("allowed_owners") or []),
        "lanes": lanes,
        "open_prs_at_census": list(data.get("open_prs_at_census") or []),
        "error": "",
    }


def measure_from_rows(facts):
    """Fold measured facts. Absence is never stillness."""
    facts = dict(facts or {})
    facts.setdefault("measured", True)
    facts.setdefault("card_present", False)
    facts.setdefault("catalog_present", False)
    facts.setdefault("found_phrases", [])
    facts.setdefault("lanes", [])
    facts.setdefault("misses", [])
    facts.setdefault("calibration_ok", False)
    facts.setdefault("calibration_hits", [])
    facts.setdefault("search_space", list(SEARCH_SPACE))
    facts.setdefault("bake_scan_present", False)
    facts.setdefault("doorbell_present", False)
    facts.setdefault("tester_card_present", False)
    facts.setdefault("reinstatement", "")
    facts.setdefault("claude_certify", "")
    facts.setdefault("census_owner", "")
    facts.setdefault("xyz_required", False)
    facts.setdefault("preserve_evidence", False)
    facts.setdefault("posting_gate", True)
    facts.setdefault("label", "")
    facts.setdefault("titan", "NOT_WRITTEN")
    return facts


def classify(row):
    """Name the leftover state. A silent 0 is instrument failure."""
    row = dict(row or {})
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "host/claude_park.py body not read. Absence was not stillness. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if not row.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration missed HEAD.md / EXECUTE.md / "
                "Action Pad directive. instrument failure, not a parked lane. "
                "Search space: %s. Hits: %s. Z=FINDER-FAILED. Never 0."
                % (row.get("search_space") or list(SEARCH_SPACE), row.get("calibration_hits") or [])
            ),
            "z": "FINDER-FAILED",
        }
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    misses = list(row.get("misses") or [])
    phrases = list(row.get("found_phrases") or [])
    lanes = list(row.get("lanes") or [])
    owner = str(row.get("census_owner") or "").strip()
    reinstatement = str(row.get("reinstatement") or "").strip().upper()
    certify = str(row.get("claude_certify") or "").strip().upper()
    xyz = bool(row.get("xyz_required"))
    label = str(row.get("label") or "").strip()
    preserve = bool(row.get("preserve_evidence"))
    gate = bool(row.get("posting_gate"))
    doorbell = bool(row.get("doorbell_present"))
    bake_scan = bool(row.get("bake_scan_present"))
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Full Claude-family suspension talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    lane_ids = [str(item.get("id") or "") for item in lanes]
    missing_lanes = [item for item in REQUIRED_LANE_IDS if item not in lane_ids]
    bad_status = [
        item["id"]
        for item in lanes
        if str(item.get("status") or "").upper() not in ALLOWED_STATUS
    ]
    claude_owned = [
        item["id"]
        for item in lanes
        if str(item.get("owner") or "").split("/")[0].strip().upper() in FORBIDDEN_OWNER
    ]
    if (
        needed
        or missing_lanes
        or bad_status
        or claude_owned
        or "Codex / Grok Build" not in owner
        or reinstatement != "BRYCE_ONLY"
        or certify != "REFUSED"
        or not xyz
        or "CLAUDE-FAMILY-PARK-REROUTE" not in label
        or not preserve
        or gate
        or not doorbell
        or bake_scan
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Missing lanes: "
                + ", ".join(missing_lanes)
                + ". Claude-owned: "
                + ", ".join(claude_owned)
                + ". Reinstatement must be BRYCE_ONLY. Claude certify must be REFUSED. "
                "Doorbell evidence must stay. Bake-scan must stay PARKED/absent. "
                "Talk is CLAIMED. Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "claude-park leftover is on this tree. Named Claude lanes are "
            "PARKED / REROUTED / REFUSED with non-Claude owners. "
            "Reinstatement is BRYCE_ONLY. Evidence preserved. "
            "A Slack suspension ruling is still not the file."
        ),
        "z": "",
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    search_hits = {}
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if rel != BAKE_SCAN and not _exists(root, rel):
            misses.append(rel)
        search_hits[rel] = text
    card_text = search_hits.get(DEFAULT_CARD, "")
    catalog_text = search_hits.get(DEFAULT_CATALOG, "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join(
        [
            card_text,
            catalog_text,
            search_hits.get(os.path.join("host", "claude_park.py"), ""),
        ]
    ).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "full claude-family suspension" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "found_phrases": found,
        "lanes": catalog.get("lanes") or [],
        "bake_scan_present": _exists(root, BAKE_SCAN),
        "doorbell_present": _exists(root, DOORBELL),
        "tester_card_present": _exists(root, TESTER_CARD),
        "census_owner": catalog.get("census_owner") or "",
        "reinstatement": catalog.get("reinstatement") or "",
        "claude_certify": catalog.get("claude_certify") or "",
        "xyz_required": bool(catalog.get("xyz_required")),
        "preserve_evidence": bool(catalog.get("preserve_evidence")),
        "posting_gate": bool(catalog.get("posting_gate")),
        "label": catalog.get("label") or "",
        "allowed_owners": catalog.get("allowed_owners") or [],
        "open_prs_at_census": catalog.get("open_prs_at_census") or [],
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = facts["slack_ts"]
    row["catalog"] = DEFAULT_CATALOG
    row["source_id"] = catalog.get("source_id") or SOURCE_ID
    return row


def _self_test():
    empty = classify({})
    if empty["state"] != "UNMEASURED" or empty["z"] != "FINDER-FAILED":
        return False
    failed = classify(
        {
            "measured": True,
            "calibration_ok": False,
            "calibration_hits": [],
            "card_present": True,
            "catalog_present": True,
        }
    )
    if failed["state"] != "UNMEASURED" or "Never 0" not in failed["note"]:
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Park or reroute Claude-owned lanes on current main"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload["x"] = list(SEARCH_SPACE)
    payload["y"] = {
        "found_phrases": row.get("found_phrases") or [],
        "lanes": row.get("lanes") or [],
        "doorbell_present": row.get("doorbell_present"),
        "bake_scan_present": row.get("bake_scan_present"),
        "reinstatement": row.get("reinstatement"),
        "claude_certify": row.get("claude_certify"),
    }
    if not payload.get("z"):
        payload["z"] = verdict.get("z") or "FINDER-FAILED"
        if verdict.get("state") == "INTEGRATED":
            payload["z"] = "misses %s / FINDER-FAILED never 0" % (row.get("misses") or [])
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
