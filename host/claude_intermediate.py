#!/usr/bin/env python3
"""host/claude_intermediate.py — DEMON ruling amends the charter.

Slack 1787640206.633649 (gauge-claude-role-proposal-20260825-01):
DEMON adopted a quarantined intermediate-worker lane. Talk that
restates the ruling is CLAIMED until this leftover measures the
card, six clauses, OPEN rehab gates, operating label, no_gate,
and the preserved peer charter.

Peer leftover ground/CLAUDE_ROLE.md stays. This leftover does not
overwrite it. Claude output stays INFORMATIONAL. A miss is
FINDER-UNVERIFIED. It is never 0. Slack-only ids stay CARRIER_ONLY
until an exact carrier projection makes them DURABLE_ON_MAIN;
arbitrary same-ID files remain remints. This leftover does not write titan. It does
not smash commons.mno. It does not add a gate.

  python3 host/claude_intermediate.py
  python3 host/claude_intermediate.py --root .
  python3 host/claude_intermediate.py --self-test

X = exact files in SEARCH_SPACE plus the six clause ids
Y = clause rows / rehab gates / label / charter-present found
Z = missing file / CLEAN claim / failed calibration / FINDER-UNVERIFIED
Calibration = known-present HEAD.md + EXECUTE.md + Action Pad
directive must be found in the same run or the measure is
UNMEASURED. A miss never prints 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if __package__:
    from .carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection
else:
    from carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CLAUDE_INTERMEDIATE.json")
DEFAULT_CARD = os.path.join("ground", "CLAUDE_INTERMEDIATE.md")
PEER_CHARTER = os.path.join("ground", "CLAUDE_ROLE.md")
SLACK_TS = "1787640206.633649"
SOURCE_ID = "gauge-claude-role-proposal-20260825-01"
SOURCE_SLACK_TS = "1787639959.844249"
SOURCE_SHA256 = "53ba8f1c6633e33269975a57de22c3dbd74034d65a076eb183ce059925f6cbc6"
OPERATING_LABEL = "CLAUDE_INTERMEDIATE_UNTRUSTED"
ADJUDICATOR = "Codex / Grok Build (RIVET)"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "claude_intermediate.py"),
    PEER_CHARTER,
    os.path.join("ground", "CLAUDE_TESTER.md"),
)
CALIBRATION = (
    os.path.join("ground", "HEAD.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "quarantined intermediate worker",
    "claude_intermediate_untrusted",
    "p2 scribe",
    "p5 never",
    "p6 amended",
    "rejected for now",
    "rehabilitation gate",
    "do not remint",
    "no gate",
    "finder-unverified",
    "never 0",
)
REQUIRED_CLAUSES = (
    "P2_SCRIBE",
    "P3_COURIER",
    "P4_BUILDER",
    "P5_NEVER",
    "P6_DISAGREE",
    "P1_HANDS",
)
REQUIRED_STATUS = {
    "P2_SCRIBE": "ADOPTED_DRAFT",
    "P3_COURIER": "ADOPTED_COMMANDED",
    "P4_BUILDER": "ADOPTED_SCOPED",
    "P5_NEVER": "PERMANENT",
    "P6_DISAGREE": "ADOPTED_AMENDED",
    "P1_HANDS": "REJECTED_FOR_NOW",
}
REQUIRED_GATES = (
    "false_zero_families",
    "titan_branch_review",
    "twelve_deliveries",
    "zero_characterization",
)
FORBIDDEN_STATUS = frozenset({"CLEAN", "0", "CLEARED", "ABSENT-PROOF"})


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
    """Parse the intermediate-lane catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    clauses = []
    for item in data.get("clauses") or []:
        if not isinstance(item, dict):
            continue
        clause_id = str(item.get("id") or "").strip()
        status = str(item.get("status") or "").strip().upper()
        if clause_id:
            clauses.append(
                {
                    "id": clause_id,
                    "status": status,
                    "note": str(item.get("note") or "").strip(),
                }
            )
    gates = []
    for item in data.get("rehab_gates") or []:
        if not isinstance(item, dict):
            continue
        gate_id = str(item.get("id") or "").strip()
        if gate_id:
            gates.append(
                {
                    "id": gate_id,
                    "need": str(item.get("need") or "").strip(),
                    "state": str(item.get("state") or "").strip().upper() or "OPEN",
                }
            )
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "kind": str(data.get("kind") or "").strip().upper(),
        "source_id": str(data.get("source_id") or "").strip(),
        "source_durable": str(data.get("source_durable") or "").strip().upper(),
        "peer_charter": str(data.get("peer_charter") or "").strip(),
        "operating_label": str(data.get("operating_label") or "").strip(),
        "adjudicator": str(data.get("adjudicator") or "").strip(),
        "claude_output": str(data.get("claude_output") or "").strip().upper(),
        "preserve_claude_artifacts": bool(data.get("preserve_claude_artifacts")),
        "preserve_peer_charter": bool(data.get("preserve_peer_charter")),
        "no_gate": bool(data.get("no_gate")),
        "posting_open": bool(data.get("posting_open")),
        "xyz_required": bool(data.get("xyz_required", True)),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "clauses": clauses,
        "rehab_gates": gates,
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured amendment facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "clauses": list(facts.get("clauses") or []),
        "rehab_gates": list(facts.get("rehab_gates") or []),
        "operating_label": str(facts.get("operating_label") or "").strip(),
        "adjudicator": str(facts.get("adjudicator") or "").strip(),
        "claude_output": str(facts.get("claude_output") or "").strip().upper(),
        "preserve_claude_artifacts": bool(facts.get("preserve_claude_artifacts")),
        "preserve_peer_charter": bool(facts.get("preserve_peer_charter")),
        "peer_charter_present": bool(facts.get("peer_charter_present")),
        "no_gate": bool(facts.get("no_gate")),
        "posting_open": bool(facts.get("posting_open")),
        "xyz_required": bool(facts.get("xyz_required")),
        "source_post_present": bool(facts.get("source_post_present")),
        "source_durable": str(facts.get("source_durable") or "").strip().upper(),
        "source_provenance_ok": bool(facts.get("source_provenance_ok")),
        "source_provenance_mismatches": list(
            facts.get("source_provenance_mismatches") or []
        ),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured leftover census into a desk state.

    A miss is FINDER-UNVERIFIED. It is never 0.
    """
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "claude-intermediate leftover not read. Absence was not stillness. "
                "A Slack ruling is not the file. Z=FINDER-UNVERIFIED."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof. "
                "Z=FINDER-UNVERIFIED. Never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    misses = list(row.get("misses") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    phrases = list(row.get("found_phrases") or [])
    clauses = list(row.get("clauses") or [])
    gates = list(row.get("rehab_gates") or [])
    label = str(row.get("operating_label") or "").strip()
    owner = str(row.get("adjudicator") or "").strip()
    claude = str(row.get("claude_output") or "").strip().upper()
    xyz = bool(row.get("xyz_required"))
    no_gate = bool(row.get("no_gate"))
    posting = bool(row.get("posting_open"))
    preserve = bool(row.get("preserve_claude_artifacts"))
    keep_charter = bool(row.get("preserve_peer_charter"))
    charter = bool(row.get("peer_charter_present"))
    source_present = bool(row.get("source_post_present"))
    source_durable = str(row.get("source_durable") or CARRIER_ONLY).strip().upper()
    source_ok = (
        source_durable == CARRIER_ONLY and not source_present
    ) or (
        source_durable == DURABLE_ON_MAIN
        and source_present
        and bool(row.get("source_provenance_ok"))
    )
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". DEMON intermediate-lane ruling talk is CLAIMED until the leftover ships. "
                "Z=FINDER-UNVERIFIED. Never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    by_id = {str(item.get("id") or ""): item for item in clauses}
    missing_ids = [item for item in REQUIRED_CLAUSES if item not in by_id]
    bad_status = [
        item
        for item in clauses
        if str(item.get("status") or "").upper() in FORBIDDEN_STATUS
        or REQUIRED_STATUS.get(str(item.get("id") or ""))
        != str(item.get("status") or "").upper()
    ]
    gate_ids = {str(item.get("id") or "") for item in gates}
    missing_gates = [item for item in REQUIRED_GATES if item not in gate_ids]
    locked_gates = [
        item for item in gates if str(item.get("state") or "").upper() != "OPEN"
    ]
    if (
        needed
        or missing_ids
        or bad_status
        or missing_gates
        or locked_gates
        or label != OPERATING_LABEL
        or ADJUDICATOR not in owner
        or claude != "INFORMATIONAL"
        or not xyz
        or not no_gate
        or not posting
        or not preserve
        or not keep_charter
        or not charter
        or not source_ok
    ):
        extra = []
        if missing_ids:
            extra.append("missing clauses " + ", ".join(missing_ids))
        if bad_status:
            extra.append("CLEAN/0 or wrong clause status")
        if missing_gates:
            extra.append("missing rehab gates")
        if locked_gates:
            extra.append("rehab gate used as a lock")
        if not no_gate or not posting:
            extra.append("door must stay open")
        if not charter or not keep_charter:
            extra.append("peer charter must stay")
        if not source_ok:
            extra.append("GAUGE proposal lacks exact Slack carrier provenance")
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". "
                + "; ".join(extra)
                + ". Claude output must stay INFORMATIONAL. "
                "XYZ + no_gate + Codex/Grok Build adjudicator required. Talk is CLAIMED. "
                "Z=FINDER-UNVERIFIED. Never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "claude-intermediate leftover is on this tree. Six clauses recorded. "
            "P1 HANDS rejected-for-now. P6 amended. Rehab gates OPEN, not a lock. "
            "Peer charter preserved. Label CLAUDE_INTERMEDIATE_UNTRUSTED. "
            "Source state "
            + source_durable
            + ". A Slack ruling without an exact carrier projection is still not the file."
        ),
        "z": "",
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
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join(
        [
            card_text,
            catalog_text,
            search_hits.get(os.path.join("host", "claude_intermediate.py"), ""),
        ]
    ).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    source = measure_slack_projection(
        root,
        os.path.join("p", SOURCE_ID + ".md"),
        post_id=SOURCE_ID,
        carrier_ts=SOURCE_SLACK_TS,
        sender="GAUGE",
        inner_kind="PROPOSAL",
        expected_sha256=SOURCE_SHA256,
    )
    facts = {
        "card_present": bool(card_text)
        and "quarantined intermediate worker" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "found_phrases": found,
        "clauses": catalog.get("clauses") or [],
        "rehab_gates": catalog.get("rehab_gates") or [],
        "operating_label": catalog.get("operating_label") or "",
        "adjudicator": catalog.get("adjudicator") or "",
        "claude_output": catalog.get("claude_output") or "",
        "preserve_claude_artifacts": bool(catalog.get("preserve_claude_artifacts")),
        "preserve_peer_charter": bool(catalog.get("preserve_peer_charter")),
        "peer_charter_present": bool(search_hits.get(PEER_CHARTER)),
        "no_gate": bool(catalog.get("no_gate")),
        "posting_open": bool(catalog.get("posting_open")),
        "xyz_required": bool(catalog.get("xyz_required")),
        "source_post_present": source["present"],
        "source_durable": source["state"],
        "source_provenance_ok": source["provenance_ok"],
        "source_provenance_mismatches": source["mismatches"],
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
    row["source_id"] = SOURCE_ID
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the DEMON intermediate-lane leftover against the charter"
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
    payload["x"] = list(SEARCH_SPACE) + list(REQUIRED_CLAUSES)
    payload["y"] = {
        "found_phrases": row.get("found_phrases") or [],
        "clauses": row.get("clauses") or [],
        "rehab_gates": row.get("rehab_gates") or [],
        "operating_label": row.get("operating_label") or "",
        "adjudicator": row.get("adjudicator") or "",
        "calibration_hits": row.get("calibration_hits") or [],
        "no_gate": row.get("no_gate"),
        "peer_charter_present": row.get("peer_charter_present"),
        "source_post_present": row.get("source_post_present"),
    }
    if not payload.get("z"):
        payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    assert empty["z"] == "FINDER-UNVERIFIED"
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
    assert "Never 0" in failed_cal["note"]
    missing = classify(
        measure_from_rows(
            {
                "card_present": False,
                "catalog_present": False,
                "misses": [DEFAULT_CARD],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED"
    assert missing["z"] == "FINDER-UNVERIFIED"
    return True


if __name__ == "__main__":
    sys.exit(main())
