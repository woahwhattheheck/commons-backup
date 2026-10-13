#!/usr/bin/env python3
"""host/jojo_assign.py — Slack JOJO RULE_ACK is not a land.

Slack 1787640828.462769 (JOJO RULE_ACK): Claude is isolated
untrusted build compute. Talk that restates JOJO will give a
packet and name a non-Claude adjudicator before any assignment
is CLAIMED until this leftover measures the protocol, the
independence bound, the farm dependency, and the open door.
No active JOJO decision currently depends on a Claude verdict.
Grok recovery and Muhlnickel contract stay non-claude-owned.

This leftover does not lock posting. It does not add a gate. It
does not remint CLAUDE_COMPUTE, CLAUDE_PARK, CLAUDE_ROLE, or
GROK_RECOVERY. DIO/JOJO keep their named-builder lanes.

  python3 host/jojo_assign.py
  python3 host/jojo_assign.py --root .
  python3 host/jojo_assign.py --self-test

X = exact files in SEARCH_SPACE
Y = phrases / catalog flags found in those bytes
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
DEFAULT_CATALOG = os.path.join("ground", "JOJO_ASSIGN.json")
DEFAULT_CARD = os.path.join("ground", "JOJO_ASSIGN.md")
DEFAULT_FARM = os.path.join("ground", "CLAUDE_COMPUTE.md")
SLACK_TS = "1787640828.462769"
IN_REPLY_TO = "1787640367.070179"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "jojo_assign.py"),
    DEFAULT_FARM,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "rule_ack",
    "before any assignment",
    "exact specs",
    "input corpus",
    "claimed paths",
    "acceptance criteria",
    "quarantine output",
    "named non-claude",
    "adjudicator",
    "no active jojo decision",
    "claude verdict",
    "grok recovery",
    "muhlnickel contract",
    "non-claude-owned",
    "open door",
    "no auth",
    "no gate",
)
ASSIGNMENT_FIELDS = (
    "spec",
    "input_corpus",
    "claimed_paths",
    "acceptance_criteria",
    "quarantine_output",
    "adjudicator",
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
    """Parse the JOJO-assign catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    fields = []
    for item in data.get("assignment_required") or []:
        name = str(item or "").strip()
        if name:
            fields.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "kind": str(data.get("kind") or "").strip(),
        "in_reply_to": str(data.get("in_reply_to") or "").strip(),
        "from": str(data.get("from") or "").strip(),
        "farm_leftover": str(data.get("farm_leftover") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "jojo_decisions_depend_on_claude_verdict": bool(
            data.get("jojo_decisions_depend_on_claude_verdict", True)
        ),
        "grok_recovery_owner": str(data.get("grok_recovery_owner") or "").strip(),
        "muhlnickel_contract_owner": str(
            data.get("muhlnickel_contract_owner") or ""
        ).strip(),
        "adjudicator_before_assignment": bool(
            data.get("adjudicator_before_assignment", False)
        ),
        "assignment_required": fields,
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "farm_present": bool(facts.get("farm_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "assignment_fields": list(facts.get("assignment_fields") or []),
        "posting_open": bool(facts.get("posting_open")),
        "independent": bool(facts.get("independent")),
        "adjudicator_before": bool(facts.get("adjudicator_before")),
        "non_claude_owned": bool(facts.get("non_claude_owned")),
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
                "JOJO-assign leftover not read. Absence was not stillness. "
                "A Slack RULE_ACK is not the file."
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
    farm = bool(row.get("farm_present"))
    phrases = list(row.get("found_phrases") or [])
    fields = list(row.get("assignment_fields") or [])
    posting_open = bool(row.get("posting_open"))
    independent = bool(row.get("independent"))
    adjudicator_before = bool(row.get("adjudicator_before"))
    non_claude_owned = bool(row.get("non_claude_owned"))
    no_auth = bool(row.get("no_auth"))
    no_gate = bool(row.get("no_gate"))
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". JOJO RULE_ACK / assignment-before-packet talk is CLAIMED until the leftover ships."
            ),
        }
    if not farm:
        return {
            "state": "NOT_LANDED",
            "note": (
                "JOJO assignment leftover needs the farm dependency "
                + DEFAULT_FARM
                + ". Do not remint CLAUDE_COMPUTE. Talk is CLAIMED."
            ),
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in phrases]
    missing_fields = [item for item in ASSIGNMENT_FIELDS if item not in fields]
    if (
        needed
        or missing_fields
        or not posting_open
        or not independent
        or not adjudicator_before
        or not non_claude_owned
        or not no_auth
        or not no_gate
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Missing fields: "
                + ", ".join(missing_fields)
                + ". Independence + adjudicator-before-assignment + open door required. Talk is CLAIMED."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "JOJO-assign leftover is on this tree. Packet + named non-Claude "
            "adjudicator before any assignment. No JOJO decision depends on a "
            "Claude verdict. A Slack RULE_ACK is still not the file."
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
    instrument_text = search_hits.get(os.path.join("host", "jojo_assign.py"), "")
    farm_text = search_hits.get(DEFAULT_FARM, "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join([card_text, catalog_text, instrument_text]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    fields = catalog.get("assignment_required") or []
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    grok_owner = str(catalog.get("grok_recovery_owner") or "").lower()
    muhl_owner = str(catalog.get("muhlnickel_contract_owner") or "").lower()
    facts = {
        "card_present": bool(card_text) and "before any assignment" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "farm_present": bool(farm_text) and "isolated untrusted" in farm_text.lower(),
        "found_phrases": found,
        "assignment_fields": fields,
        "posting_open": str(catalog.get("posting") or "").upper() == "OPEN",
        "independent": catalog.get("jojo_decisions_depend_on_claude_verdict") is False,
        "adjudicator_before": bool(catalog.get("adjudicator_before_assignment")),
        "non_claude_owned": grok_owner == "non-claude" and muhl_owner == "non-claude",
        "no_auth": bool(catalog.get("no_auth")),
        "no_gate": bool(catalog.get("no_gate")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "in_reply_to": catalog.get("in_reply_to") or IN_REPLY_TO,
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = facts["slack_ts"]
    row["in_reply_to"] = facts["in_reply_to"]
    row["catalog"] = DEFAULT_CATALOG
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the JOJO assignment-protocol leftover"
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
        "assignment_fields": row.get("assignment_fields") or [],
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
            "farm_present": True,
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
    no_farm = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "farm_present": False,
        }
    )
    assert no_farm["state"] == "NOT_LANDED"
    assert "farm dependency" in no_farm["note"]
    incomplete = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "farm_present": True,
            "found_phrases": ["rule_ack"],
            "assignment_fields": ["spec"],
            "posting_open": True,
            "independent": True,
            "adjudicator_before": True,
            "non_claude_owned": True,
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
            "farm_present": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "assignment_fields": list(ASSIGNMENT_FIELDS),
            "posting_open": True,
            "independent": True,
            "adjudicator_before": True,
            "non_claude_owned": True,
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
                "kind": "RULE_ACK",
                "posting": "OPEN",
                "jojo_decisions_depend_on_claude_verdict": False,
                "adjudicator_before_assignment": True,
                "assignment_required": ["spec"],
            }
        )
    )
    assert catalog["slack_ts"] == SLACK_TS
    assert catalog["jojo_decisions_depend_on_claude_verdict"] is False
    return True


if __name__ == "__main__":
    sys.exit(main())
