#!/usr/bin/env python3
"""host/specter_final.py — Slack current-main SHA is not current main.

Slack 1787645274.177269 (SPECTER FINAL): INTEGRATED / VERIFIED ON
CURRENT MAIN bef4ba7124424de5aed51e1a9216b216d389a5a7. That SHA is a
durable ancestor. Official HEAD can move. A Slack FINAL is CLAIMED
until this leftover classifies cited SHA as HEAD / ANCESTOR / FOREIGN.

Do not remint PR 2205, terminal a1a496bd, PR 2269, TERMINAL_CATALOG,
WAKE_CONTRACT, or BUILD_SWEEP_ACT. Named idle-session resume stays
UNMEASURED. titan: NOT_WRITTEN. No auth. No gate. Miss is
FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/specter_final.py
  python3 host/specter_final.py --root .
  python3 host/specter_final.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "SPECTER_FINAL.json")
DEFAULT_CARD = os.path.join("ground", "SPECTER_FINAL.md")
MCP_WAKE_CATALOG = os.path.join("ground", "MCP_WAKE.json")
STRANDED = os.path.join("host", "stranded_map.py")
SPECTER_JOB = "specter-watchdog-head-proof-20260825-01"
SPECTER_REL = os.path.join("wake_jobs", SPECTER_JOB + ".json")
SLACK_TS = "1787645274.177269"
CITED_SHA = "bef4ba7124424de5aed51e1a9216b216d389a5a7"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "specter_final.py"),
    MCP_WAKE_CATALOG,
    STRANDED,
    SPECTER_REL,
    os.path.join("ground", "TERMINAL_CATALOG.md"),
    os.path.join("ground", "WAKE_CONTRACT.md"),
    os.path.join("ground", "BUILD_SWEEP_ACT.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "TERMINAL_CATALOG.md"),
    os.path.join("ground", "TERMINAL_CATALOG.json"),
    os.path.join("ground", "WAKE_CONTRACT.md"),
    os.path.join("ground", "BUILD_SWEEP_ACT.md"),
    MCP_WAKE_CATALOG,
    STRANDED,
    SPECTER_REL,
)
REQUIRED_PHRASES = (
    "specter final leftover",
    "stale current-main sha",
    "ancestor is not current head",
    "slack final is not a land",
    "do not remint",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "open door",
    "no auth",
    "no gate",
    "talk is not a land",
    "unmeasured",
)
SPECTER_BYTES = (
    MCP_WAKE_CATALOG,
    STRANDED,
    SPECTER_REL,
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
    """Parse the SPECTER FINAL leftover catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "already_landed": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "already_landed": []}
    return data


def classify_sha(cited, head, is_ancestor):
    """HEAD / ANCESTOR / FOREIGN / UNMEASURED. Never invent stillness."""
    cited = str(cited or "").strip().lower()
    head = str(head or "").strip().lower()
    if len(cited) < 7 or len(head) < 7:
        return "UNMEASURED"
    if cited == head or head.startswith(cited) or cited.startswith(head):
        return "HEAD"
    if is_ancestor:
        return "ANCESTOR"
    return "FOREIGN"


def _git(root, *args):
    try:
        out = subprocess.check_output(
            ["git", "-C", root, *args],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return str(out or "").strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def measure_head(root, cited):
    """Measure official HEAD and whether cited SHA is an ancestor."""
    head = _git(root, "rev-parse", "HEAD")
    if not head:
        return {"official_head": "", "is_ancestor": False, "git": "UNMEASURED"}
    # merge-base --is-ancestor prints nothing; exit 0 means yes.
    is_ancestor = False
    try:
        subprocess.check_call(
            ["git", "-C", root, "merge-base", "--is-ancestor", cited, "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        is_ancestor = True
    except (OSError, subprocess.CalledProcessError):
        is_ancestor = False
    return {
        "official_head": head,
        "is_ancestor": is_ancestor,
        "git": "MEASURED",
    }


def measure_from_rows(facts):
    """Attach leftover flags. Empty facts stay empty for classify()."""
    row = dict(facts or {})
    row["measured"] = True
    return row


def classify(row):
    """UNMEASURED / NOT_LANDED / INTEGRATED. Miss is never 0."""
    if not row:
        return {
            "state": "UNMEASURED",
            "note": "SPECTER FINAL leftover not read. Absence was not stillness.",
        }
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "SPECTER FINAL leftover not measured. Absence was not stillness.",
        }
    if not row.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": (
                "calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". instrument failure. FINDER-UNVERIFIED, never 0."
            ),
        }
    misses = list(row.get("misses") or [])
    if not row.get("card_present") or not row.get("catalog_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". SPECTER FINAL / stale current-main SHA talk "
                "is CLAIMED until the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    relation = str(row.get("sha_relation") or "UNMEASURED")
    if relation == "UNMEASURED":
        return {
            "state": "UNMEASURED",
            "note": (
                "cited SHA vs official HEAD was not measured. "
                "Search space: "
                + ", ".join(row.get("search_space") or list(SEARCH_SPACE))
                + ". FINDER-UNVERIFIED, never 0."
            ),
        }
    if relation == "FOREIGN":
        return {
            "state": "NOT_LANDED",
            "note": (
                "cited SHA "
                + str(row.get("cited_sha") or CITED_SHA)
                + " is not an ancestor of official HEAD "
                + str(row.get("official_head") or "")
                + ". Slack FINAL is CLAIMED. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("specter_bytes_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "SPECTER durable bytes missing on this tree. Do not remint. "
                "FINDER-FAILED / FINDER-UNVERIFIED, never 0."
            ),
        }
    landed_missing = list(row.get("landed_missing") or [])
    if landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing)
                + ". Do not remint. FINDER-FAILED, never 0."
            ),
        }
    phrases = [str(item).lower() for item in (row.get("found_phrases") or [])]
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in phrases]
    posting_open = bool(row.get("posting_open"))
    no_auth = bool(row.get("no_auth"))
    no_gate = bool(row.get("no_gate"))
    if needed or not posting_open or not no_auth or not no_gate:
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
            "SPECTER FINAL leftover is on this tree. Cited SHA relation is "
            + relation
            + ". Ancestor is not current HEAD. A Slack FINAL is still not "
            "the file. Named idle stays UNMEASURED."
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
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    cited = str(catalog.get("cited_sha") or CITED_SHA)
    head_row = measure_head(root, cited)
    relation = classify_sha(
        cited,
        head_row.get("official_head") or "",
        bool(head_row.get("is_ancestor")),
    )
    if head_row.get("git") != "MEASURED":
        relation = "UNMEASURED"
    specter_bytes_present = all(_exists(root, rel) for rel in SPECTER_BYTES)
    wake = {}
    try:
        wake = json.loads(_read(root, MCP_WAKE_CATALOG) or "{}")
    except ValueError:
        wake = {}
    canaries = wake.get("production_canaries") if isinstance(wake, dict) else []
    specter_canary = {}
    for item in canaries or []:
        if isinstance(item, dict) and item.get("job_id") == SPECTER_JOB:
            specter_canary = item
            break
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "cited_sha": cited,
        "official_head": head_row.get("official_head") or "",
        "sha_relation": relation,
        "specter_bytes_present": specter_bytes_present,
        "specter_terminal": str(specter_canary.get("terminal_commit") or ""),
        "specter_wake_count": specter_canary.get("wake_count"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "idle_resume": catalog.get("idle_resume") or "UNMEASURED",
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
                "sha_relation": relation,
                "official_head": facts["official_head"],
                "cited_sha": cited,
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
                "misses": ["ground/SPECTER_FINAL.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    foreign = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "sha_relation": "FOREIGN",
                "cited_sha": CITED_SHA,
                "official_head": "deadbeef",
                "specter_bytes_present": True,
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert foreign["state"] == "NOT_LANDED", foreign
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure SPECTER FINAL leftover")
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
