#!/usr/bin/env python3
"""host/readme_audit.py — measure the live README; do not edit it.

Slack 1787643743.338469 asked for a source-indexed README patch plan
from official main, not a parallel edit. Talk that restates "README
is stale" without this leftover is CLAIMED.

X = README.md + audit files + named sources
Y = required field statuses and patch ids found
Z = missing source / stale roster restored / FINDER-FAILED
Calibration = known-present EXECUTE.md + Action Pad directive.
A miss never prints 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
README_PATH = "README.md"
AUDIT_JSON = os.path.join("audit", "readme-20260825", "audit.json")
AUDIT_CARD = os.path.join("audit", "readme-20260825", "README.md")
SEARCH_SPACE = (
    README_PATH,
    AUDIT_JSON,
    AUDIT_CARD,
    os.path.join("host", "readme_audit.py"),
    os.path.join("audit", "readme-20260825", "dissent.md"),
    os.path.join("audit", "readme-20260825", "source_ledger.md"),
    "START.md",
    "names.html",
    os.path.join("ground", "PICK.md"),
    os.path.join("ground", "OPEN_DOOR.md"),
    "action.html",
    "reply.html",
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
STALE_ROSTER = "message board for ZERO GROK KITE CAIRN SPALL GRAVE AXIOM SHARD SCREE"
REQUIRED_README_PHRASES = (
    "open door",
    "no auth",
    "unseated",
    "names.html",
    "start.md",
    "boards.html",
    "pick.md",
    "reply.html",
    "action.html",
    "http is not the computer",
    "proves pc execution",
    "ship to current main",
)
REQUIRED_PATCH_IDS = ("R1", "R2", "R3", "R4", "R5")


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_audit(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "audit is not JSON"}
    if not isinstance(data, dict):
        return {"error": "audit is not an object"}
    patches = []
    for item in data.get("patch_plan") or []:
        if isinstance(item, dict) and item.get("id"):
            patches.append(item)
    return {
        "error": "",
        "finding": str(data.get("finding") or "").strip(),
        "readme_edit_in_this_leftover": bool(data.get("readme_edit_in_this_leftover")),
        "measured_main_sha": str(data.get("measured_main_sha") or "").strip(),
        "xyz_required": bool(data.get("xyz_required")),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "patches": patches,
        "do_not_edit": [str(item) for item in (data.get("do_not_edit") or [])],
    }


def measure_from_rows(facts):
    facts = dict(facts or {})
    facts["measured"] = True
    return facts


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "README audit leftover was not read. Absence is not stillness. Z=FINDER-FAILED. Never 0.",
            "z": "FINDER-FAILED",
        }
    if not row.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration missed EXECUTE.md and/or the Action Pad "
                "directive. Instrument failure, not a README result. Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    misses = list(row.get("misses") or [])
    if not row.get("readme_present") or not row.get("audit_present") or misses:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["readme/audit"])
                + ". README-stale talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("stale_roster_restored"):
        return {
            "state": "NOT_LANDED",
            "note": "live README restored the day-one roster as current seats. Z=FINDER-FAILED.",
            "z": "FINDER-FAILED",
        }
    phrase_miss = list(row.get("phrase_miss") or [])
    patch_miss = list(row.get("patch_miss") or [])
    if (
        phrase_miss
        or patch_miss
        or row.get("readme_edit_in_this_leftover")
        or str(row.get("finding") or "") != "STALE_ROSTER_ALREADY_REPLACED"
        or not row.get("xyz_required")
        or "Codex / Grok Build" not in str(row.get("remeasurement_owner") or "")
        or str(row.get("titan") or "") != "NOT_WRITTEN"
        or "README.md" not in (row.get("do_not_edit") or [])
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "audit present but incomplete. phrase_miss="
                + ",".join(phrase_miss)
                + " patch_miss="
                + ",".join(patch_miss)
                + ". Talk is CLAIMED. Z=FINDER-FAILED."
            ),
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "README audit leftover is on this tree. Live README already replaced the "
            "day-one roster. Patch plan is source-indexed and not applied. "
            "A Slack taking is still not the file."
        ),
        "z": "",
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    texts = {}
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        texts[rel] = text
    readme = texts.get(README_PATH, "")
    audit = load_audit(texts.get(AUDIT_JSON, ""))
    readme_l = readme.lower()
    phrase_miss = [item for item in REQUIRED_README_PHRASES if item not in readme_l]
    patch_ids = [str(item.get("id") or "") for item in (audit.get("patches") or [])]
    patch_miss = [item for item in REQUIRED_PATCH_IDS if item not in patch_ids]
    apply_now = [item.get("id") for item in (audit.get("patches") or []) if item.get("apply_now")]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "readme_present": bool(readme),
        "audit_present": bool(audit) and not audit.get("error"),
        "stale_roster_restored": STALE_ROSTER.lower() in readme_l,
        "phrase_miss": phrase_miss,
        "patch_miss": patch_miss,
        "apply_now_patches": apply_now,
        "readme_edit_in_this_leftover": bool(audit.get("readme_edit_in_this_leftover")) or bool(apply_now),
        "finding": audit.get("finding") or "",
        "xyz_required": bool(audit.get("xyz_required")),
        "remeasurement_owner": audit.get("remeasurement_owner") or "",
        "titan": audit.get("titan") or "NOT_WRITTEN",
        "do_not_edit": audit.get("do_not_edit") or [],
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
    }
    return measure_from_rows(facts)


def _self_test():
    empty = classify({})
    if empty.get("state") != "UNMEASURED":
        return False
    missing = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "readme_present": False,
                "audit_present": False,
                "misses": [AUDIT_JSON],
            }
        )
    )
    return missing.get("state") == "NOT_LANDED" and missing.get("z") == "FINDER-FAILED"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure the README audit leftover")
    parser.add_argument("--root", default=".")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload["x"] = list(SEARCH_SPACE)
    payload["y"] = {
        "finding": row.get("finding"),
        "phrase_miss": row.get("phrase_miss") or [],
        "patch_miss": row.get("patch_miss") or [],
        "stale_roster_restored": row.get("stale_roster_restored"),
    }
    payload["z"] = verdict.get("z") or "none"
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
