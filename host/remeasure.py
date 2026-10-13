#!/usr/bin/env python3
"""host/remeasure.py — non-Claude remasurement of Claude's five artifacts.

Slack 1787639575.924889 / id claude27-p0-compliance-20260825-01:
CONTAINMENT_COMPLIANCE listed affected artifacts and asked a
non-Claude seat to remasure them. Talk that restates the compliance
post is CLAIMED until this leftover measures the card, catalog,
instrument, XYZ, planted-deletion canary, and same-run calibration.

Claude is not the tester. Codex / Grok Build ran X. A miss prints
FINDER-FAILED / FINDER-UNVERIFIED plus the search space. Never 0.
This leftover does not remint FINDER_ZERO, CLAUDE_TESTER,
CLAUDE_ZERO, MEASURE_ABUSE, IMPACT_LEDGER, XYZ_ZERO, or GROK_RECOVERY.
It does not write titan. It does not smash commons.mno. It does not
add a gate. It does not take the GGUF bake-scan lane.

  python3 host/remeasure.py
  python3 host/remeasure.py --root .
  python3 host/remeasure.py --self-test

X = exact files / exact phrases / exact git commands in SEARCH_SPACE
Y = phrases / artifacts / canary / packet bytes found
Z = missing file / missing phrase / failed calibration / FINDER-FAILED
Calibration = known-present HEAD.md + Action Pad directive must be
found in the same run or the measure is UNMEASURED.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "REMEASURE.json")
DEFAULT_CARD = os.path.join("ground", "REMEASURE.md")
SLACK_TS = "1787639575.924889"
SOURCE_ID = "claude27-p0-compliance-20260825-01"
PACKET = os.path.join("excerpts", "20260823", "titan_move_packet.json")
BAKE_SCAN = os.path.join("host", "pfc_bake_scan.py")
CENSUS_POST = os.path.join("p", "claude27-pfc-bake-census-20260825-01.md")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "remeasure.py"),
    CENSUS_POST,
    PACKET,
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "containment_compliance",
    "affected artifacts from this seat",
    "7-term space-separated",
    "planted-deletion canary",
    "evidence-pending-non-claude-remeasure",
    "claude27-p0-compliance",
    "never 0",
    "codex / grok build",
)
HEAD_PHRASES = (
    "kite-help",
    "PFC bake census",
    "stranded-LocalDeviceAgent",
)
BRANCHES = (
    "sd-wx",
    "stranded/player1-publish-20260825",
    "stranded/player1-vent-final-20260825",
    "stranded/player1-vent-fix-20260825",
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


def _blob(root, rel):
    try:
        return subprocess.check_output(
            ["git", "-C", root, "rev-parse", "HEAD:" + rel],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def load_catalog(text):
    """Parse the remasurement catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "artifacts": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "artifacts": []}
    artifacts = []
    for item in data.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        artifact = str(item.get("artifact") or "").strip()
        status = str(item.get("status") or "").strip().upper()
        if artifact:
            artifacts.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "artifact": artifact,
                    "status": status or "UNMEASURED",
                    "claim": str(item.get("claim") or "").strip(),
                }
            )
    routes = []
    for item in data.get("allowed_remeasurers") or []:
        name = str(item or "").strip()
        if name:
            routes.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "source_id": str(data.get("source_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "label": str(data.get("label") or "").strip(),
        "xyz_required": bool(data.get("xyz_required", True)),
        "calibration_required": bool(data.get("calibration_required", True)),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "allowed_remeasurers": routes,
        "artifacts": artifacts,
        "error": "",
    }


def planted_deletion_canary():
    """Plant a tracked file, delete it, require diff-filter=D to see it.

    Runs in a TemporaryDirectory. Not a commons worktree. If the
    detector cannot see the planted deletion, every empty D list in
    this run is FINDER-FAILED, never 0.
    """
    tmp = tempfile.mkdtemp(prefix="remeasure-canary-")
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "remeasure"
    env["GIT_AUTHOR_EMAIL"] = "remeasure@local"
    env["GIT_COMMITTER_NAME"] = "remeasure"
    env["GIT_COMMITTER_EMAIL"] = "remeasure@local"
    try:
        subprocess.check_call(
            ["git", "init", "-q"],
            cwd=tmp,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        canary = os.path.join(tmp, "planted-deletion-canary.txt")
        with open(canary, "w", encoding="utf-8") as handle:
            handle.write("CANARY_PRESENT\n")
        subprocess.check_call(
            ["git", "add", "planted-deletion-canary.txt"],
            cwd=tmp,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_call(
            ["git", "commit", "-q", "-m", "plant canary"],
            cwd=tmp,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_call(
            ["git", "rm", "-q", "planted-deletion-canary.txt"],
            cwd=tmp,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=D", "--cached"],
            cwd=tmp,
            env=env,
            text=True,
        )
        names = [line.strip() for line in out.splitlines() if line.strip()]
        if "planted-deletion-canary.txt" not in names:
            return {
                "ok": False,
                "z": "FINDER-FAILED",
                "names": names,
                "note": "planted deletion was not visible to diff-filter=D",
            }
        return {
            "ok": True,
            "z": "",
            "names": names,
            "note": "planted-deletion canary PASS",
        }
    except (OSError, subprocess.CalledProcessError) as exc:
        return {
            "ok": False,
            "z": "FINDER-FAILED",
            "names": [],
            "note": "canary instrument failure: %s" % exc,
        }


def working_tree_deletions(root):
    """One command: git diff --name-only --diff-filter=D. Empty is not 0."""
    try:
        out = subprocess.check_output(
            ["git", "-C", root, "diff", "--name-only", "--diff-filter=D"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return {
            "ok": False,
            "names": [],
            "z": "FINDER-FAILED",
            "note": "diff-filter=D command failed. Not 0.",
        }
    names = [line.strip() for line in out.splitlines() if line.strip()]
    return {
        "ok": True,
        "names": names,
        "z": "" if names else "FINDER-UNVERIFIED",
        "note": (
            "working-tree D list has %s path(s). Empty is one repo, "
            "one command, plus canary. Sibling trees stay UNMEASURED."
            % len(names)
        ),
    }


def phrase_hits(root, phrase):
    """Exact-phrase scan of p/*.md. Miss is FINDER-UNVERIFIED, never 0."""
    hits = []
    posts = os.path.join(root, "p")
    try:
        names = os.listdir(posts)
    except OSError:
        return {
            "phrase": phrase,
            "hits": [],
            "z": "FINDER-FAILED",
            "note": "p/ unreadable. Search space p/*.md. Never 0.",
        }
    for name in names:
        if not name.endswith(".md"):
            continue
        rel = os.path.join("p", name)
        body = _read(root, rel)
        if phrase in body:
            hits.append(rel)
    if hits:
        return {"phrase": phrase, "hits": hits, "z": "", "note": "Y from found bytes"}
    return {
        "phrase": phrase,
        "hits": [],
        "z": "FINDER-UNVERIFIED",
        "note": (
            "exact phrase %r not in current-main p/*.md. "
            "Search space p/*.md. Never 0."
            % phrase
        ),
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "artifacts": list(facts.get("artifacts") or []),
        "packet_present": bool(facts.get("packet_present")),
        "packet_blob": str(facts.get("packet_blob") or ""),
        "bake_scan_present": bool(facts.get("bake_scan_present")),
        "canary_ok": bool(facts.get("canary_ok")),
        "working_tree_deletions": list(facts.get("working_tree_deletions") or []),
        "head_phrases": list(facts.get("head_phrases") or []),
        "branches": list(facts.get("branches") or []),
        "remeasurement_owner": str(facts.get("remeasurement_owner") or "").strip(),
        "allowed_remeasurers": list(facts.get("allowed_remeasurers") or []),
        "xyz_required": bool(facts.get("xyz_required")),
        "label": str(facts.get("label") or "").strip(),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured remasurement leftover into a desk state.

    A miss is FINDER-FAILED / FINDER-UNVERIFIED. It is never 0.
    """
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "remeasure leftover not read. Absence was not stillness. "
                "A Slack CONTAINMENT_COMPLIANCE post is not the file. "
                "Z=FINDER-FAILED."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("canary_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "planted-deletion canary failed. Empty D lists in this run "
                "are FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    misses = list(row.get("misses") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    phrases = list(row.get("found_phrases") or [])
    artifacts = list(row.get("artifacts") or [])
    owner = str(row.get("remeasurement_owner") or "").strip()
    routes = list(row.get("allowed_remeasurers") or [])
    xyz = bool(row.get("xyz_required"))
    label = str(row.get("label") or "").strip()
    packet = bool(row.get("packet_present"))
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". CONTAINMENT_COMPLIANCE talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    if (
        needed
        or len(artifacts) < 5
        or not packet
        or "Codex / Grok Build" not in owner
        or len(routes) < 4
        or not xyz
        or "EVIDENCE-PENDING-NON-CLAUDE-REMEASURE" not in label
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Packet + five artifacts + XYZ + Codex/Grok Build owner required. "
                "Talk is CLAIMED. Z=FINDER-FAILED."
            ),
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "remeasure leftover is on this tree. Non-Claude X/Y/Z ran. "
            "Planted-deletion canary PASS. Packet exists at excerpts/20260823/. "
            "A Slack CONTAINMENT_COMPLIANCE post is still not the file."
        ),
        "z": "",
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    search_hits = {}
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text and rel != BAKE_SCAN:
            if rel == PACKET:
                if not _exists(root, rel):
                    misses.append(rel)
            elif not _exists(root, rel):
                misses.append(rel)
        search_hits[rel] = text
    card_text = search_hits.get(DEFAULT_CARD, "")
    catalog_text = search_hits.get(DEFAULT_CATALOG, "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join(
        [
            card_text,
            catalog_text,
            search_hits.get(os.path.join("host", "remeasure.py"), ""),
        ]
    ).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    canary = planted_deletion_canary()
    deletions = working_tree_deletions(root)
    head_phrases = [phrase_hits(root, phrase) for phrase in HEAD_PHRASES]
    packet_blob = _blob(root, PACKET) if _exists(root, PACKET) else ""
    facts = {
        "card_present": bool(card_text) and "containment_compliance" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "found_phrases": found,
        "artifacts": catalog.get("artifacts") or [],
        "packet_present": _exists(root, PACKET),
        "packet_blob": packet_blob,
        "bake_scan_present": _exists(root, BAKE_SCAN),
        "canary_ok": bool(canary.get("ok")),
        "working_tree_deletions": deletions.get("names") or [],
        "head_phrases": head_phrases,
        "branches": list(BRANCHES),
        "remeasurement_owner": catalog.get("remeasurement_owner") or "",
        "allowed_remeasurers": catalog.get("allowed_remeasurers") or [],
        "xyz_required": bool(catalog.get("xyz_required")),
        "label": catalog.get("label") or "",
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "canary": canary,
        "deletions": deletions,
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = facts["slack_ts"]
    row["catalog"] = DEFAULT_CATALOG
    row["canary"] = canary
    row["deletions"] = deletions
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
    canary = planted_deletion_canary()
    return bool(canary.get("ok"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Non-Claude remasurement of Claude's five affected artifacts"
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
        "packet_blob": row.get("packet_blob") or "",
        "packet_present": row.get("packet_present"),
        "canary_ok": row.get("canary_ok"),
        "head_phrases": row.get("head_phrases") or [],
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
