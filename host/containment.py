#!/usr/bin/env python3
"""host/containment.py — GAUGE stand-down is a named-artifact ledger.

Slack 1787639440.580749 (gauge-p0-compliance-20260825-01):
GAUGE stands down from verdict roles. Talk that restates the
stand-down is CLAIMED until this leftover measures the card, the
four artifacts, remesasurement owners, UNSCANNED branches, and the
packet path remesasure.

Claude/GAUGE output stays INFORMATIONAL. A miss is
FINDER-UNVERIFIED. It is never 0. Slack-only ids stay CARRIER_ONLY
until an exact carrier projection makes them DURABLE_ON_MAIN;
arbitrary same-ID files remain remints. This leftover does not write titan. It does
not smash commons.mno. It does not add a gate. It does not dump
secrets.

  python3 host/containment.py
  python3 host/containment.py --root .
  python3 host/containment.py --self-test

X = exact files in SEARCH_SPACE plus the four artifact ids
Y = artifact rows / packet bytes / branch statuses found
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
DEFAULT_CATALOG = os.path.join("ground", "CONTAINMENT.json")
DEFAULT_CARD = os.path.join("ground", "CONTAINMENT.md")
SLACK_TS = "1787639440.580749"
SOURCE_ID = "gauge-p0-compliance-20260825-01"
SOURCE_SHA256 = "fbe2e1c146c3e7460d9234f42d97bbf01b25cf38236d0035dacb79e39816a8b3"
PACKET_PATH = os.path.join("excerpts", "20260823", "titan_move_packet.json")
QUARANTINED_POST = os.path.join(
    "p", "claudelocal-titan-move-go-20260825-01.md"
)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "containment.py"),
    PACKET_PATH,
    QUARANTINED_POST,
)
CALIBRATION = (
    os.path.join("ground", "HEAD.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "containment_compliance",
    "stands down from verdict roles",
    "affected artifact",
    "unscanned",
    "informational",
    "remeasurement owner",
    "finder-unverified",
    "never 0",
    "carrier_only",
    "do not remint",
)
ALLOWED_STATUS = frozenset(
    {
        "INFORMATIONAL",
        "UNSCANNED",
        "QUARANTINED",
        "WORK_RECORD",
        "CARRIER_ONLY",
    }
)
FORBIDDEN_STATUS = frozenset({"CLEAN", "0", "CLEARED", "ABSENT-PROOF"})
REQUIRED_IDS = (
    "gauge-secret-rescan-20260825-04",
    "claudelocal-titan-move-go-20260825-01",
    "gauge-xyz-zero-audit-results-20260825-03",
    "owner-action-done-receipts-20260825",
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
    """Parse the containment catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    artifacts = []
    for item in data.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("id") or "").strip()
        status = str(item.get("status") or "").strip().upper()
        owner = str(item.get("remeasurement_owner") or "").strip()
        if artifact_id:
            artifacts.append(
                {
                    "id": artifact_id,
                    "status": status or "INFORMATIONAL",
                    "remeasurement_owner": owner,
                    "durable": str(item.get("durable") or "").strip().upper(),
                }
            )
    branches = []
    for item in data.get("branches") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            branches.append(
                {
                    "name": name,
                    "origin_head": str(item.get("origin_head") or "").strip().upper(),
                    "status": str(item.get("status") or "").strip().upper()
                    or "UNSCANNED",
                }
            )
    routes = []
    for item in data.get("allowed_remeasurers") or []:
        name = str(item or "").strip()
        if name:
            routes.append(name)
    packet = data.get("packet") if isinstance(data.get("packet"), dict) else {}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "kind": str(data.get("kind") or "").strip().upper(),
        "source_id": str(data.get("source_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "claude_output": str(data.get("claude_output") or "").strip().upper(),
        "xyz_required": bool(data.get("xyz_required", True)),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "allowed_remeasurers": routes,
        "artifacts": artifacts,
        "branches": branches,
        "packet": {
            "path": str(packet.get("path") or PACKET_PATH).strip(),
            "cat_file": str(packet.get("cat_file") or "").strip().upper(),
            "titan": str(packet.get("titan") or "").strip(),
            "reread": packet.get("reread"),
            "write_count": packet.get("write_count"),
            "reread_count": packet.get("reread_count"),
            "claimed_append_end": packet.get("claimed_append_end"),
        },
        "do_not_remint": [
            str(item).strip()
            for item in (data.get("do_not_remint") or [])
            if str(item).strip()
        ],
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/artifact facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "claude_output": str(facts.get("claude_output") or "").strip().upper(),
        "artifacts": list(facts.get("artifacts") or []),
        "branches": list(facts.get("branches") or []),
        "packet_present": bool(facts.get("packet_present")),
        "packet": facts.get("packet") or {},
        "quarantined_post_present": bool(facts.get("quarantined_post_present")),
        "source_post_present": bool(facts.get("source_post_present")),
        "source_post_state": str(
            facts.get("source_post_state") or CARRIER_ONLY
        ).strip().upper(),
        "source_provenance_ok": bool(facts.get("source_provenance_ok")),
        "source_provenance_mismatches": list(
            facts.get("source_provenance_mismatches") or []
        ),
        "remeasurement_owner": str(facts.get("remeasurement_owner") or "").strip(),
        "allowed_remeasurers": list(facts.get("allowed_remeasurers") or []),
        "xyz_required": bool(facts.get("xyz_required")),
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
                "containment leftover not read. Absence was not stillness. "
                "A Slack stand-down is not the file. Z=FINDER-UNVERIFIED."
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
    artifacts = list(row.get("artifacts") or [])
    branches = list(row.get("branches") or [])
    owner = str(row.get("remeasurement_owner") or "").strip()
    routes = list(row.get("allowed_remeasurers") or [])
    claude = str(row.get("claude_output") or "").strip().upper()
    xyz = bool(row.get("xyz_required"))
    packet_ok = bool(row.get("packet_present"))
    source_present = bool(row.get("source_post_present"))
    source_state = str(row.get("source_post_state") or CARRIER_ONLY).strip().upper()
    source_ok = (
        source_state == CARRIER_ONLY and not source_present
    ) or (
        source_state == DURABLE_ON_MAIN
        and source_present
        and bool(row.get("source_provenance_ok"))
    )
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Containment-compliance talk is CLAIMED until the leftover ships. "
                "Z=FINDER-UNVERIFIED. Never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    by_id = {str(item.get("id") or ""): item for item in artifacts}
    missing_ids = [item for item in REQUIRED_IDS if item not in by_id]
    bad_status = [
        item
        for item in artifacts
        if str(item.get("status") or "").upper() in FORBIDDEN_STATUS
        or str(item.get("status") or "").upper() not in ALLOWED_STATUS
    ]
    missing_owners = [
        item for item in artifacts if not str(item.get("remeasurement_owner") or "").strip()
    ]
    unclean = [
        item
        for item in branches
        if str(item.get("status") or "").upper() != "UNSCANNED"
    ]
    if (
        needed
        or missing_ids
        or bad_status
        or missing_owners
        or unclean
        or claude != "INFORMATIONAL"
        or "Codex / Grok Build" not in owner
        or len(routes) < 4
        or not xyz
        or not packet_ok
        or not source_ok
    ):
        extra = []
        if missing_ids:
            extra.append("missing artifacts " + ", ".join(missing_ids))
        if bad_status:
            extra.append("CLEAN/0 forbidden")
        if unclean:
            extra.append("branch not UNSCANNED")
        if not packet_ok:
            extra.append("packet path FINDER-UNVERIFIED")
        if not source_ok:
            extra.append("stand-down source lacks exact Slack carrier provenance")
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". "
                + "; ".join(extra)
                + ". Claude output must stay INFORMATIONAL. "
                "XYZ + Codex/Grok Build owner required. Talk is CLAIMED. "
                "Z=FINDER-UNVERIFIED. Never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "containment leftover is on this tree. Four artifacts contained. "
            "Claude output INFORMATIONAL. Branches UNSCANNED, not clean. "
            "Packet path remeasured. Codex/Grok Build is the non-Claude "
            "remeasurement owner. Source state "
            + source_state
            + ". A Slack stand-down without an exact carrier projection is still not the file."
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
            search_hits.get(os.path.join("host", "containment.py"), ""),
        ]
    ).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    packet_text = search_hits.get(PACKET_PATH, "")
    source = measure_slack_projection(
        root,
        os.path.join("p", SOURCE_ID + ".md"),
        post_id=SOURCE_ID,
        carrier_ts=SLACK_TS,
        sender="GAUGE",
        inner_kind="CONTAINMENT_COMPLIANCE",
        expected_sha256=SOURCE_SHA256,
    )
    facts = {
        "card_present": bool(card_text) and "containment_compliance" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "found_phrases": found,
        "claude_output": catalog.get("claude_output") or "",
        "artifacts": catalog.get("artifacts") or [],
        "branches": catalog.get("branches") or [],
        "packet_present": bool(packet_text),
        "packet": catalog.get("packet") or {},
        "quarantined_post_present": bool(search_hits.get(QUARANTINED_POST)),
        "source_post_present": source["present"],
        "source_post_state": source["state"],
        "source_provenance_ok": source["provenance_ok"],
        "source_provenance_mismatches": source["mismatches"],
        "remeasurement_owner": catalog.get("remeasurement_owner") or "",
        "allowed_remeasurers": catalog.get("allowed_remeasurers") or [],
        "xyz_required": bool(catalog.get("xyz_required")),
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
        description="Measure the GAUGE containment leftover against named artifacts"
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
    payload["x"] = list(SEARCH_SPACE) + list(REQUIRED_IDS)
    payload["y"] = {
        "found_phrases": row.get("found_phrases") or [],
        "artifacts": row.get("artifacts") or [],
        "branches": row.get("branches") or [],
        "packet_present": row.get("packet_present"),
        "packet": row.get("packet") or {},
        "calibration_hits": row.get("calibration_hits") or [],
        "remeasurement_owner": row.get("remeasurement_owner") or "",
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
