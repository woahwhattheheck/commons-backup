#!/usr/bin/env python3
"""host/review_lane.py — a Slack SHIPPED (review lane) is not official main.

Slack 1787647408.984179 (JOJO SHIPPED review lane, not merged):
LocalDeviceAgent PR #3 at e9c863a1d945627ff75e0db997ce74dc9efa345f.
GitHub Actions run 32827964418 / job 97740082275 SUCCESS.
Existing request 9/9 + new receipt 16/16.

Independent measure this run:
- Official LDA main contents/commit sha=main = fb0b0b2f59f8ca81741371b6ddd8036b164e77e8
- host/muhl_subagent_receipt.py on official main = ABSENT (HTTP 404)
- PR #3 OPEN, mergeable_state=clean, reviews=[]
- Candidate blobs independently measured (do not copy private LDA source):
  host/muhl_subagent_receipt.py 56daac03ae99d0dc2c6d0eeb9e9e17638253eaa8
  host/test_muhl_subagent_receipt.py 74b6eb49a0557de62c1ef62aa71a6897fa8e65aa
  docs/MUHL_SUBAGENT_RECEIPT.md 2edcdb258ba7bf04ad97d7700daee80ef8060f07
  .github/workflows/muhlnickel-subagent-protocol.yml b9b0af5caffcdbb7341f0e988249cb990578358d

A Slack SHIPPED (review lane, not merged) is CANDIDATE.
Official LDA main without the receipt path is still FOREIGN_INTEGRATED
only for the already-measured protocol leftover (FOREIGN_MAIN).
PR #3 is not official main. Talk is not a land.

Non-Claude review (Cursor Grok 4.6, this run): source-only receipt
validator; fail-closed; unchanged bytes require explicit UNRESOLVED
and cannot be surfaced as 0; no host inference / Titan / container /
device / pfc_* / auth / login / allowlist / approval / identity /
action tiers in the candidate. CI SUCCESS independently verified.

Do not remint FOREIGN_MAIN, MUHL_RECEIPT_LANE, LDA_RECEIPT, or
jojo-muhlnickel-subagent-protocol-20260825-01. Do not copy private
LocalDeviceAgent source onto Commons. No titan write. No auth. No gate.
Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/review_lane.py
  python3 host/review_lane.py --root .
  python3 host/review_lane.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "REVIEW_LANE.json")
DEFAULT_CARD = os.path.join("ground", "REVIEW_LANE.md")
SLACK_TS = "1787647408.984179"
FOREIGN_REPO = "woahwhattheheck/LocalDeviceAgent"
OFFICIAL_MAIN = "fb0b0b2f59f8ca81741371b6ddd8036b164e77e8"
CANDIDATE_SHA = "e9c863a1d945627ff75e0db997ce74dc9efa345f"
PR_NUMBER = "3"
ACTIONS_RUN = "32827964418"
ACTIONS_JOB = "97740082275"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("ground", "FOREIGN_MAIN.md"),
    os.path.join("ground", "MUHL_RECEIPT_LANE.md"),
    os.path.join("ground", "LDA_RECEIPT.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "rivet-ship-review-lane-20260825-01.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "FOREIGN_MAIN.md"),
    os.path.join("host", "foreign_main.py"),
    os.path.join("ground", "MUHL_RECEIPT_LANE.md"),
    os.path.join("host", "muhl_receipt_lane.py"),
    os.path.join("ground", "LDA_RECEIPT.md"),
    os.path.join("host", "lda_receipt.py"),
)
REQUIRED_PHRASES = (
    "review lane",
    "not merged",
    "pr #3",
    "e9c863a1d945627ff75e0db997ce74dc9efa345f",
    "fb0b0b2f59f8ca81741371b6ddd8036b164e77e8",
    "candidate",
    "official main",
    "receipt path absent",
    "do not remint",
    "do not copy private lda source",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "open door",
    "no auth",
    "no gate",
    "talk is not a land",
    "non-claude review",
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
    """Parse the review-lane catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "candidates": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "candidates": []}
    raw_candidates = data.get("candidates") or []
    if not isinstance(raw_candidates, list):
        return {"error": "candidates is not a list", "candidates": []}
    rows = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        number = str(item.get("number") or "").strip()
        if not number:
            continue
        rows.append(
            {
                "number": number,
                "candidate_sha": str(item.get("candidate_sha") or "").strip().lower(),
                "official_main": str(item.get("official_main") or "").strip().lower(),
                "pr_state": str(item.get("pr_state") or "").strip().upper(),
                "land_state": str(item.get("land_state") or "").strip().upper(),
                "receipt_on_official_main": str(
                    item.get("receipt_on_official_main") or ""
                ).strip().upper(),
                "ci": str(item.get("ci") or "").strip().upper(),
            }
        )
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": data.get("no_auth", True) is True,
        "no_gate": data.get("no_gate", True) is True,
        "candidates": rows,
        "error": "",
    }


def is_pr3_candidate(item):
    """True only for the exact measured review-lane candidate state."""
    item = item if isinstance(item, dict) else {}
    return (
        str(item.get("number")) == PR_NUMBER
        and item.get("candidate_sha") == CANDIDATE_SHA
        and item.get("official_main") == OFFICIAL_MAIN
        and item.get("pr_state") == "OPEN"
        and item.get("land_state") == "CANDIDATE"
        and item.get("receipt_on_official_main") == "ABSENT"
        and item.get("ci") == "SUCCESS"
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
        "candidates": list(facts.get("candidates") or []),
        "names_pr3_candidate": bool(facts.get("names_pr3_candidate")),
        "claims_pr3_integrated": bool(facts.get("claims_pr3_integrated")),
        "claims_receipt_on_official_main": bool(
            facts.get("claims_receipt_on_official_main")
        ),
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
    """Turn a measured review-lane census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Review-lane leftover not read. Absence was not stillness. "
                "A Slack SHIPPED (review lane, not merged) is not official main. "
                "not stillness. FINDER-FAILED, never 0."
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
                + ". JOJO SHIPPED / review lane / LDA PR #3 talk is CLAIMED "
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
    if row.get("claims_pr3_integrated"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog claims PR #3 INTEGRATED or FOREIGN_INTEGRATED. "
                "Official LDA main is still "
                + OFFICIAL_MAIN
                + "; the receipt path is ABSENT there. Review lane is CANDIDATE, "
                "not a second land. FINDER-FAILED, never 0."
            ),
        }
    if row.get("claims_receipt_on_official_main"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog claims the receipt path is on official LDA main. "
                "Independent measure this run: host/muhl_subagent_receipt.py "
                "ABSENT on "
                + OFFICIAL_MAIN
                + ". FINDER-FAILED, never 0."
            ),
        }
    if not row.get("names_pr3_candidate"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "LDA PR #3 is not named CANDIDATE against official main "
                + OFFICIAL_MAIN
                + " / candidate "
                + CANDIDATE_SHA
                + ". A Slack SHIPPED (review lane) is not official main. "
                "FINDER-FAILED, never 0."
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
            "Review-lane leftover is on this tree. Official LDA main is still "
            + OFFICIAL_MAIN
            + ". PR #3 "
            + CANDIDATE_SHA
            + " is CANDIDATE. Receipt path ABSENT on official main. "
            "A Slack SHIPPED (review lane, not merged) is still not the file."
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
    candidates = catalog.get("candidates") or []
    names_pr3_candidate = any(is_pr3_candidate(item) for item in candidates)
    claims_pr3_integrated = any(
        str(item.get("number")) == PR_NUMBER
        and item.get("land_state") in {"INTEGRATED", "FOREIGN_INTEGRATED"}
        for item in candidates
    )
    claims_receipt_on_official_main = any(
        str(item.get("number")) == PR_NUMBER
        and item.get("receipt_on_official_main") in {"PRESENT", "YES", "ON_MAIN"}
        for item in candidates
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
        "candidates": candidates,
        "names_pr3_candidate": names_pr3_candidate,
        "claims_pr3_integrated": claims_pr3_integrated,
        "claims_receipt_on_official_main": claims_receipt_on_official_main,
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
                "candidates": candidates,
                "official_main": OFFICIAL_MAIN,
                "candidate_sha": CANDIDATE_SHA,
                "actions_run": ACTIONS_RUN,
                "actions_job": ACTIONS_JOB,
                "foreign_repo": FOREIGN_REPO,
            },
            "z": (
                "misses "
                + json.dumps(misses + landed_missing)
                + " / FINDER-FAILED never 0 / public git ls-remote LDA FINDER-UNVERIFIED"
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
                "misses": ["ground/REVIEW_LANE.md"],
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
                "candidates": [{"number": "3", "land_state": "FOREIGN_INTEGRATED"}],
                "names_pr3_candidate": False,
                "claims_pr3_integrated": True,
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert claimed["state"] == "NOT_LANDED", claimed
    assert "CANDIDATE" in claimed["note"], claimed
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure review-lane leftover")
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
