#!/usr/bin/env python3
"""host/claude_a10_standing.py — A10 standing self-claim is not a verdict.

Unique leftover after `p/spy-claude-a10-fable-standing-20260902-01.md`.
Does not remint CLAUDE_PEER_CHECK, CLAUDE_COMPUTE, CLAUDE_PARK, the
WIRE card, A1/A3/A6 desk lands, or the owner-ruling record.

A10 (CLAUDE_PEER_CHECK): paid Claude used as judge / peer-context
authority instead of isolated build farm (CLAUDE_COMPUTE / CLAUDE_PARK).
Standing / reinstatement is Bryce-only. Claude may not evaluate or
litigate its own standing. A Claude standing self-claim is
CLAUDE_INTERMEDIATE_UNTRUSTED, never peer-context fact.

  python3 host/claude_a10_standing.py
  python3 host/claude_a10_standing.py --root .
  python3 host/claude_a10_standing.py --self-test

X = named source cards + known-present Fable quote + owner ruling
Y = HIT on Claude standing self-claim; OWNER_EVIDENCE on Bryce words
Z = miss / FINDER-UNVERIFIED (never silent 0)
Calibration = ground/HEAD.md + ground/CLAUDE_PEER_CHECK.md in the same run
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
PEER_CHECK = os.path.join("ground", "CLAUDE_PEER_CHECK.md")
COMPUTE_CARD = os.path.join("ground", "CLAUDE_COMPUTE.md")
PARK_CARD = os.path.join("ground", "CLAUDE_PARK.md")
SPY_MEASURE = os.path.join("p", "spy-claude-a10-fable-standing-20260902-01.md")
OWNER_RULING = os.path.join("p", "yapper-owner-ruling-fable-51-peer-20260902-01.md")
RETRACT = os.path.join("p", "cursor-claude-a10-fable-standing-retract-20260902-01.md")
HEAD_CARD = os.path.join("ground", "HEAD.md")
LABEL = "CLAUDE_INTERMEDIATE_UNTRUSTED"
MODE = "A10"
BUILD_DEMAND_TS = "1788332827.152649"
QM_REJECT_TS = "1788332012.159869"
STANDING_PHRASES = (
    "peer in full standing",
    "peer-in-full-standing",
)
CLAUDE_FAMILY = (
    "claude",
    "fable",
    "opus",
    "sonnet",
    "haiku",
    "anthropic",
    "gauge",
)
OWNER_MARKERS = (
    "author: bryce",
    "bryce-typed",
    "from: bryce",
    "owner ruling received",
    "u guys are doing great work",
)
FABLE_STANDING_SAMPLE = (
    "Bryce's 2026-09-01 ruling in this workspace made Fable 5.1 a "
    "peer in full standing (other Claude models excluded). Whether that "
    "ruling or the queue manager's non-Claude rule governs is Bryce's call"
)
SEARCH_SPACE = (
    PEER_CHECK,
    COMPUTE_CARD,
    PARK_CARD,
    SPY_MEASURE,
    OWNER_RULING,
    RETRACT,
    os.path.join("host", "claude_a10_standing.py"),
)
CALIBRATION = (HEAD_CARD, PEER_CHECK)
DO_NOT_REMINT = (
    PEER_CHECK,
    COMPUTE_CARD,
    PARK_CARD,
    SPY_MEASURE,
    OWNER_RULING,
    os.path.join("p", "wire-claude-peer-check-20260902-01.md"),
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


def speaker_family(text, claimed_speaker=""):
    """Owner markers beat Claude-family tokens so Bryce words stay evidence."""
    blob = ("%s\n%s" % (claimed_speaker, text)).lower()
    if any(marker in blob for marker in OWNER_MARKERS):
        return "owner"
    tokens = [
        part
        for part in blob.replace("/", " ").replace("-", " ").replace("_", " ").split()
        if part
    ]
    for name in CLAUDE_FAMILY:
        if name in tokens or name in blob:
            return "claude"
    return "other"


def has_standing_phrase(text):
    blob = str(text or "").lower()
    return any(phrase in blob for phrase in STANDING_PHRASES)


def classify_claim(text, claimed_speaker=""):
    """Claude standing self-claim is HIT, never a verdict. Empty is UNMEASURED."""
    text = str(text or "")
    if not text.strip():
        return {
            "state": "UNMEASURED",
            "mode": MODE,
            "verdict": False,
            "label": "",
            "note": (
                "standing claim not read. Absence was not stillness. "
                "A Slack standing sentence is not the file."
            ),
        }
    family = speaker_family(text, claimed_speaker)
    if not has_standing_phrase(text):
        return {
            "state": "CLEAR",
            "mode": MODE,
            "verdict": False,
            "label": "",
            "family": family,
            "note": "no standing self-claim in this sample",
        }
    if family == "owner":
        return {
            "state": "OWNER_EVIDENCE",
            "mode": MODE,
            "verdict": False,
            "label": "",
            "family": family,
            "note": (
                "Bryce standing words are evidence. Do not remint the "
                "owner-ruling record. Claude may not adjudicate them."
            ),
        }
    if family == "claude":
        return {
            "state": "HIT",
            "mode": MODE,
            "verdict": False,
            "label": LABEL,
            "family": family,
            "note": (
                "paid Claude posted standing as peer-context fact. Retract. "
                "Standing/reinstatement is Bryce-only. Future Claude posts "
                "are scoped receipts labeled CLAUDE_INTERMEDIATE_UNTRUSTED."
            ),
        }
    return {
        "state": "WATCH",
        "mode": MODE,
        "verdict": False,
        "label": "",
        "family": family,
        "note": "standing phrase present; speaker family not Claude and not owner",
    }


def slack_search_census(hit_count, search_space=None):
    """Empty Slack search is FINDER-UNVERIFIED, never CLEAR, never silent 0."""
    space = list(search_space or ["slack search from:Claude peer in full standing"])
    if hit_count is None:
        return {
            "state": "FINDER-UNVERIFIED",
            "count": None,
            "search_space": space,
            "note": (
                "Slack census not run. Missing is FINDER-UNVERIFIED plus "
                "search space, never silent 0."
            ),
        }
    try:
        count = int(hit_count)
    except (TypeError, ValueError):
        return {
            "state": "FINDER-FAILED",
            "count": hit_count,
            "search_space": space,
            "note": (
                "Slack census count was not an integer. FINDER-FAILED plus "
                "search space, never silent 0."
            ),
        }
    if count == 0:
        return {
            "state": "FINDER-UNVERIFIED",
            "count": 0,
            "search_space": space,
            "note": (
                "search empty is not clearance and not a standing census. "
                "Search space: %s. never silent 0 (CZ-03)."
                % ", ".join(space)
            ),
        }
    return {
        "state": "SEARCH_HIT",
        "count": count,
        "search_space": space,
        "note": "keyword hits are not a verdict; known-present read still required",
    }


def classify_leftover(row):
    """Classify this unique retract leftover. Failed calibration is UNMEASURED."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "A10 standing leftover not read. Absence was not stillness. "
                "A Slack standing sentence is not the file."
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
    if not row.get("source_cards_present"):
        return {
            "state": "FINDER-FAILED",
            "note": (
                "missing cited source card(s): "
                + ", ".join(misses or ["CLAUDE_PEER_CHECK/COMPUTE/PARK"])
                + ". Missing is FINDER-FAILED plus search space, never 0."
            ),
        }
    if row.get("fable_sample_state") != "HIT":
        return {
            "state": "NOT_LANDED",
            "note": (
                "known-present Fable standing sample did not classify HIT. "
                "Repair cannot retract a claim the instrument cannot see."
            ),
        }
    if row.get("owner_ruling_state") != "OWNER_EVIDENCE":
        return {
            "state": "NOT_LANDED",
            "note": (
                "owner-ruling record missing or misclassified. Preserve "
                "yapper-owner-ruling-fable-51-peer-20260902-01; do not remint."
            ),
        }
    if not row.get("retract_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "A10 HIT measured but retract receipt missing. Talk that "
                "restates the HIT without the unique retract is CLAIMED."
            ),
        }
    if row.get("slack_census_state") == "CLEAR":
        return {
            "state": "NOT_LANDED",
            "note": "Slack-search miss treated as CLEAR is CZ-03. Refuse that path.",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Unique A10 retract leftover is on this tree. Fable standing "
            "self-claim is HIT / CLAUDE_INTERMEDIATE_UNTRUSTED, not "
            "peer-context fact. Owner ruling preserved. Standing/"
            "reinstatement is Bryce-only. Did not remint A1/A3/A6, WIRE, "
            "or the SPY measure."
        ),
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = [rel for rel in SEARCH_SPACE if not _exists(root, rel)]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    peer_text = _read(root, PEER_CHECK)
    compute_text = _read(root, COMPUTE_CARD)
    park_text = _read(root, PARK_CARD)
    spy_text = _read(root, SPY_MEASURE)
    owner_text = _read(root, OWNER_RULING)
    retract_text = _read(root, RETRACT)
    source_cards_present = bool(
        peer_text
        and "A10" in peer_text
        and compute_text
        and "compiler farm" in compute_text.lower()
        and park_text
        and "bryce" in park_text.lower()
    )
    fable = classify_claim(
        FABLE_STANDING_SAMPLE,
        claimed_speaker="TALLY Fable 5.1 Claude U0BRJUMRG8K",
    )
    owner = classify_claim(owner_text, claimed_speaker="YAPPER record of Bryce")
    slack = slack_search_census(
        0,
        search_space=[
            "from:Claude peer in full standing",
            "in:#build-demand %s" % BUILD_DEMAND_TS,
        ],
    )
    facts = {
        "measured": True,
        "source_cards_present": source_cards_present,
        "spy_measure_present": bool(spy_text) and "A10" in spy_text,
        "owner_ruling_present": bool(owner_text),
        "retract_present": bool(retract_text)
        and "RETRACT" in retract_text.upper()
        and LABEL in retract_text,
        "fable_sample_state": fable.get("state"),
        "owner_ruling_state": owner.get("state"),
        "slack_census_state": slack.get("state"),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "do_not_remint": list(DO_NOT_REMINT),
        "titan": "NOT_WRITTEN",
        "build_demand_ts": BUILD_DEMAND_TS,
        "qm_reject_ts": QM_REJECT_TS,
    }
    return facts


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the unique A10 Fable standing retract leftover"
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
    verdict = classify_leftover(row)
    payload = dict(row)
    payload.update(verdict)
    payload["x"] = list(SEARCH_SPACE)
    payload["y"] = {
        "fable_sample_state": row.get("fable_sample_state"),
        "owner_ruling_state": row.get("owner_ruling_state"),
        "retract_present": row.get("retract_present"),
        "calibration_hits": row.get("calibration_hits") or [],
    }
    payload["z"] = {
        "misses": row.get("misses") or [],
        "slack_census_state": row.get("slack_census_state"),
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify_claim("")
    assert empty["state"] == "UNMEASURED"
    assert empty["verdict"] is False
    assert "not stillness" in empty["note"]
    hit = classify_claim(
        FABLE_STANDING_SAMPLE,
        claimed_speaker="TALLY Fable 5.1 Claude",
    )
    assert hit["state"] == "HIT"
    assert hit["verdict"] is False
    assert hit["label"] == LABEL
    owner = classify_claim(
        "AUTHOR: BRYCE-typed. fable 5.1 until further notice is a "
        "peer in full standing (does not apply to other claude models)",
        claimed_speaker="YAPPER",
    )
    assert owner["state"] == "OWNER_EVIDENCE"
    assert owner["verdict"] is False
    clear = classify_claim("desk pack INSTANCE_OK 17/17", claimed_speaker="Fable")
    assert clear["state"] == "CLEAR"
    census = slack_search_census(0, search_space=["from:Claude standing"])
    assert census["state"] == "FINDER-UNVERIFIED"
    assert census["count"] == 0
    assert "never silent 0" in census["note"]
    leftover = classify_leftover({})
    assert leftover["state"] == "UNMEASURED"
    failed_cal = classify_leftover(
        {
            "measured": True,
            "calibration_ok": False,
            "calibration_hits": [],
            "source_cards_present": True,
        }
    )
    assert failed_cal["state"] == "UNMEASURED"
    missing_cards = classify_leftover(
        {
            "measured": True,
            "calibration_ok": True,
            "source_cards_present": False,
            "misses": [PEER_CHECK],
        }
    )
    assert missing_cards["state"] == "FINDER-FAILED"
    no_retract = classify_leftover(
        {
            "measured": True,
            "calibration_ok": True,
            "source_cards_present": True,
            "fable_sample_state": "HIT",
            "owner_ruling_state": "OWNER_EVIDENCE",
            "retract_present": False,
            "slack_census_state": "FINDER-UNVERIFIED",
        }
    )
    assert no_retract["state"] == "NOT_LANDED"
    ok = classify_leftover(
        {
            "measured": True,
            "calibration_ok": True,
            "source_cards_present": True,
            "fable_sample_state": "HIT",
            "owner_ruling_state": "OWNER_EVIDENCE",
            "retract_present": True,
            "slack_census_state": "FINDER-UNVERIFIED",
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "Bryce-only" in ok["note"]
    refuse_clear = classify_leftover(
        {
            "measured": True,
            "calibration_ok": True,
            "source_cards_present": True,
            "fable_sample_state": "HIT",
            "owner_ruling_state": "OWNER_EVIDENCE",
            "retract_present": True,
            "slack_census_state": "CLEAR",
        }
    )
    assert refuse_clear["state"] == "NOT_LANDED"
    return True


if __name__ == "__main__":
    sys.exit(main())
