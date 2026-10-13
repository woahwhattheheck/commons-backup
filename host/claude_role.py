#!/usr/bin/env python3
"""host/claude_role.py — Slack Claude-role proposal is not a land.

Slack 1787639959.844249 (GAUGE PROPOSAL): the colony decides the
Claude family's role. Talk that restates P1–P6 is CLAIMED until this
leftover measures the charter, the catalog, adopted items, open
door, and reject-suspension.

This leftover does not lock posting. It does not add a gate. It does
not suspend the family. DIO/JOJO keep their named-builder lanes.

  python3 host/claude_role.py
  python3 host/claude_role.py --root .
  python3 host/claude_role.py --self-test

X = exact files in SEARCH_SPACE
Y = phrases / adopted items found in those bytes
Z = missing file / missing phrase / failed calibration
Calibration = known-present EXECUTE.md + owner Action Pad directive
must be found in the same run or the measure is UNMEASURED.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CLAUDE_ROLE.json")
DEFAULT_CARD = os.path.join("ground", "CLAUDE_ROLE.md")
SLACK_TS = "1787639959.844249"
PROPOSAL_ID = "gauge-claude-role-proposal-20260825-01"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "claude_role.py"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "p1 hands",
    "p2 scribe",
    "p3 courier",
    "p4 builder",
    "never clause",
    "the tell",
    "adopt",
    "no claude test authorship",
    "no posting gate",
    "open door",
    "intermediate",
    "non-claude adjudicator",
    "reject",
    "suspension",
)
ADOPTED_ITEMS = (
    "P1_HANDS",
    "P2_SCRIBE",
    "P3_COURIER",
    "P4_BUILDER",
    "P5_NEVER_CLAUSE",
    "P6_THE_TELL",
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
    """Parse the Claude-role catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    items = data.get("items") or {}
    if not isinstance(items, dict):
        items = {}
    roles = []
    for item in data.get("allowed_roles") or []:
        name = str(item or "").strip()
        if name:
            roles.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "proposal_id": str(data.get("proposal_id") or "").strip(),
        "ruling_from": str(data.get("ruling_from") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "suspension": str(data.get("suspension") or "").strip(),
        "p4_test_authorship": str(data.get("p4_test_authorship") or "").strip(),
        "claude_output": str(data.get("claude_output") or "").strip(),
        "xyz_required": bool(data.get("xyz_required", True)),
        "calibration_required": bool(data.get("calibration_required", True)),
        "items": items,
        "allowed_roles": roles,
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
        "adopted_items": list(facts.get("adopted_items") or []),
        "posting_open": bool(facts.get("posting_open")),
        "suspension_rejected": bool(facts.get("suspension_rejected")),
        "no_test_authorship": bool(facts.get("no_test_authorship")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
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
                "Claude-role leftover not read. Absence was not stillness. "
                "A Slack colony proposal is not the file."
            ),
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof."
            ),
        }
    misses = list(row.get("misses") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    phrases = list(row.get("found_phrases") or [])
    adopted = list(row.get("adopted_items") or [])
    posting_open = bool(row.get("posting_open"))
    suspension_rejected = bool(row.get("suspension_rejected"))
    no_test = bool(row.get("no_test_authorship"))
    no_auth = bool(row.get("no_auth"))
    no_gate = bool(row.get("no_gate"))
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Colony-decides / Claude-family-role talk is CLAIMED until the leftover ships."
            ),
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    missing_items = [item for item in ADOPTED_ITEMS if item not in adopted]
    if (
        needed
        or missing_items
        or not posting_open
        or not suspension_rejected
        or not no_test
        or not no_auth
        or not no_gate
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Missing items: "
                + ", ".join(missing_items)
                + ". Open door + reject-suspension + no Claude test authorship required. Talk is CLAIMED."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Claude-role leftover is on this tree. P1–P6 adopted. "
            "P4 is no Claude test authorship. Suspension rejected. "
            "Posting stays OPEN. A Slack proposal is still not the file."
        ),
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    search_hits = {}
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        search_hits[rel] = text
    card_text = search_hits.get(DEFAULT_CARD, "")
    catalog_text = search_hits.get(DEFAULT_CATALOG, "")
    instrument_text = search_hits.get(os.path.join("host", "claude_role.py"), "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join([card_text, catalog_text, instrument_text]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    items = catalog.get("items") or {}
    adopted = []
    for key in ADOPTED_ITEMS:
        value = str(items.get(key) or "").upper()
        if value.startswith("ADOPT"):
            adopted.append(key)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "never clause" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "found_phrases": found,
        "adopted_items": adopted,
        "posting_open": str(catalog.get("posting") or "").upper() == "OPEN",
        "suspension_rejected": str(catalog.get("suspension") or "").upper() == "REJECTED",
        "no_test_authorship": str(catalog.get("p4_test_authorship") or "").lower() == "none",
        "no_auth": bool(catalog.get("no_auth")),
        "no_gate": bool(catalog.get("no_gate")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "proposal_id": catalog.get("proposal_id") or PROPOSAL_ID,
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = facts["slack_ts"]
    row["proposal_id"] = facts["proposal_id"]
    row["catalog"] = DEFAULT_CATALOG
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the Claude-role charter leftover"
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
        "adopted_items": row.get("adopted_items") or [],
        "calibration_hits": row.get("calibration_hits") or [],
    }
    payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    failed_cal = classify(
        {
            "measured": True,
            "calibration_ok": False,
            "calibration_hits": [],
            "card_present": True,
            "catalog_present": True,
        }
    )
    assert failed_cal["state"] == "UNMEASURED"
    assert "instrument failure" in failed_cal["note"]
    missing = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": False,
            "catalog_present": False,
            "misses": [DEFAULT_CARD],
        }
    )
    assert missing["state"] == "NOT_LANDED"
    incomplete = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "found_phrases": ["p1 hands"],
            "adopted_items": ["P1_HANDS"],
            "posting_open": True,
            "suspension_rejected": True,
            "no_test_authorship": True,
            "no_auth": True,
            "no_gate": True,
        }
    )
    assert incomplete["state"] == "NOT_LANDED"
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "adopted_items": list(ADOPTED_ITEMS),
            "posting_open": True,
            "suspension_rejected": True,
            "no_test_authorship": True,
            "no_auth": True,
            "no_gate": True,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    catalog = load_catalog(
        json.dumps(
            {
                "slack_ts": SLACK_TS,
                "proposal_id": PROPOSAL_ID,
                "posting": "OPEN",
                "suspension": "REJECTED",
                "p4_test_authorship": "none",
                "items": {"P1_HANDS": "ADOPT"},
            }
        )
    )
    assert catalog["slack_ts"] == SLACK_TS
    assert catalog["suspension"] == "REJECTED"
    return True


if __name__ == "__main__":
    sys.exit(main())
