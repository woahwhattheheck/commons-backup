#!/usr/bin/env python3
"""host/device_path_census.py — JOJO device-path census + lawful canary.

Slack 1787641558.357319 (JOJO MEASURED_RECEIPT): calibrated tree/blob
enumeration at pinned Commons main found reservation blobs=0, batch
blobs=0, result blobs=48 all scope=github, scope=device rows=0. The
workflow gate is already INTEGRATED (do not remint DEVICE_CHURN). The
device path still has no durable reservation/batch/device result.
JOJO is inspecting the existing ACTION format for one bounded
read-only lawful canary; no Muhlnickel/Titan/model/container mutation
and no host inference.

This leftover re-runs that calibrated device path census on a named
git tree and inspects one OPEN + DEVICE lawful canary fixture that is
format-valid but not posted under p/, so it is not pending and cannot
dispatch the self-hosted runner. No host inference. A Slack census is
CLAIMED until this leftover ships. Zero reservations is a measured Y,
not stillness. Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.
Open door. No auth. No gate. titan: NOT_WRITTEN.

  python3 host/device_path_census.py
  python3 host/device_path_census.py --root .
  python3 host/device_path_census.py --ref HEAD
  python3 host/device_path_census.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "DEVICE_PATH_CENSUS.json")
DEFAULT_CARD = os.path.join("ground", "DEVICE_PATH_CENSUS.md")
DEFAULT_CANARY = os.path.join("ground", "DEVICE_PATH_CANARY.md")
SLACK_TS = "1787641558.357319"
JOJO_ID = "jojo-device-reservation-result-census-20260825-01"
PINNED_SHA = "e5de8e222fcb1b46d3f0b0f2578e9e9a15111115"
CANARY_ID = "rivet-device-path-canary-20260825-01"
DEVICE_TARGETS = {"BRYCE-PC", "BRYCE_PHONE", "BRYCE-PHONE", "CURRENT-DEVICE", "DEVICE"}
RESERVATION_PREFIX = "actions/device-reservations/"
BATCH_PREFIX = "actions/device-batches/"
RESULT_PREFIX = "actions/results/"
CALIBRATION = (
    os.path.join("device_action_state.py"),
    os.path.join("ground", "DEVICE_CHURN.md"),
    os.path.join("ground", "EXECUTE.md"),
)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    DEFAULT_CANARY,
    os.path.join("host", "device_path_census.py"),
    os.path.join("device_action_state.py"),
    os.path.join("ground", "DEVICE_CHURN.md"),
)
REQUIRED_PHRASES = (
    "calibrated device path census",
    "reservation blobs",
    "lawful canary",
    "no host inference",
    "scope=device",
    "finder-failed",
    "never 0",
    "open door",
    "no auth",
    "no gate",
    "not pending",
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


def _read_bytes(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def is_device_target(target):
    up = str(target or "").strip().upper()
    return up in DEVICE_TARGETS or up.startswith("DEVICE:") or up.startswith("BRYCE-PC:")


def parse_action(text):
    """Parse one ACTION envelope. Missing --- or kind is empty."""
    raw = str(text or "")
    head, sep, body = raw.partition("\n---\n")
    if not sep:
        return {}
    meta = {}
    for line in head.splitlines():
        key, mark, value = line.partition(":")
        if mark:
            meta[key.strip().lower()] = value.strip()
    if str(meta.get("kind") or "").upper() != "ACTION":
        return {}
    ident = str(meta.get("id") or "")
    verb = str(meta.get("act") or "").strip().upper()
    if not ident or not verb:
        return {}
    payload = body.lstrip("\n")
    lines = payload.splitlines()
    if lines and lines[0].strip().upper() == verb:
        lines.pop(0)
    if lines and lines[0].lower().startswith("target:"):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return {
        "id": ident,
        "verb": verb,
        "target": str(meta.get("target") or "").strip(),
        "kind": "ACTION",
        "payload": "\n".join(lines),
    }


def inspect_canary(text, live_post_exists):
    """Inspect the lawful read-only canary fixture. Does not execute it."""
    rec = parse_action(text)
    payload = str(rec.get("payload") or "").strip()
    first = payload.splitlines()[0].strip() if payload else ""
    https = first.startswith("https://")
    device = is_device_target(rec.get("target"))
    lawful = (
        rec.get("verb") == "OPEN"
        and device
        and https
        and rec.get("id") == CANARY_ID
        and not live_post_exists
    )
    return {
        "parsed": bool(rec),
        "id": rec.get("id") or "",
        "verb": rec.get("verb") or "",
        "target": rec.get("target") or "",
        "https_payload": https,
        "device_target": device,
        "live_post": bool(live_post_exists),
        "pending": bool(live_post_exists),
        "lawful": lawful,
        "host_inference": False,
        "self_hosted_dispatch": False,
        "dc_inject": False,
    }


def ls_tree(root, ref):
    """X: recursive path list from git ls-tree.

    Invalid ref / failed git is FINDER-FAILED, never []. Never [] → 0.
    """
    result = {"ok": False, "paths": None, "error": "", "returncode": None}
    try:
        proc = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        result["error"] = "git ls-tree OSError: %s. FINDER-FAILED, never []." % exc
        return result
    result["returncode"] = proc.returncode
    if proc.returncode:
        err = (proc.stderr or "git ls-tree failed").strip()
        result["error"] = err + ". FINDER-FAILED, never []."
        return result
    result["ok"] = True
    result["paths"] = [
        line.strip().replace("\\", "/")
        for line in proc.stdout.splitlines()
        if line.strip()
    ]
    return result


def count_prefix(paths, prefix):
    return sum(1 for name in paths if name.startswith(prefix) and name.endswith(".json"))


def count_result_scopes(root, paths):
    """Y: parse every result blob. Broken JSON is a parse failure, not a zero."""
    github = 0
    device = 0
    other = 0
    failures = 0
    for name in paths:
        if not name.startswith(RESULT_PREFIX) or not name.endswith(".json"):
            continue
        raw = _read_bytes(root, name)
        if not raw:
            failures += 1
            continue
        try:
            row = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            failures += 1
            continue
        if not isinstance(row, dict):
            failures += 1
            continue
        scope = str(row.get("scope") or "")
        if scope == "github":
            github += 1
        elif scope == "device":
            device += 1
        else:
            other += 1
    scope_github = None if failures else github
    scope_device = None if failures else device
    scope_other = None if failures else other
    return {
        "result_count": github + device + other + failures,
        "scope_github": scope_github,
        "scope_device": scope_device,
        "scope_other": scope_other,
        "parse_failures": failures,
    }


def load_catalog(text):
    """Parse the census catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "jojo_id": str(data.get("jojo_id") or "").strip(),
        "pinned_sha": str(data.get("pinned_sha") or "").strip(),
        "canary_id": str(data.get("canary_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured tree/canary facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "canary_present": bool(facts.get("canary_present")),
        "canary_lawful": bool(facts.get("canary_lawful")),
        "tree_count": (
            None if facts.get("tree_count") is None else int(facts.get("tree_count") or 0)
        ),
        "reservation_count": (
            None
            if facts.get("reservation_count") is None
            else int(facts.get("reservation_count") or 0)
        ),
        "batch_count": (
            None if facts.get("batch_count") is None else int(facts.get("batch_count") or 0)
        ),
        "result_count": (
            None if facts.get("result_count") is None else int(facts.get("result_count") or 0)
        ),
        "scope_github": (
            None if facts.get("scope_github") is None else int(facts.get("scope_github") or 0)
        ),
        "scope_device": (
            None if facts.get("scope_device") is None else int(facts.get("scope_device") or 0)
        ),
        "parse_failures": (
            None
            if facts.get("parse_failures") is None
            else int(facts.get("parse_failures") or 0)
        ),
        "found_phrases": list(facts.get("found_phrases") or []),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "self_hosted_dispatch": bool(facts.get("self_hosted_dispatch")),
        "host_inference": bool(facts.get("host_inference")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "tree_ok": True if "tree_ok" not in facts else bool(facts.get("tree_ok")),
        "tree_error": str(facts.get("tree_error") or ""),
        "tree_count": facts.get("tree_count"),
    }


def classify(row):
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "device-path census leftover not read. Absence was not stillness. "
                "A Slack MEASURED_RECEIPT is not the file. FINDER-FAILED, never 0."
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
    if row.get("tree_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "git ls-tree failed: "
                + str(row.get("tree_error") or "invalid ref")
                + ". Invalid ref is FINDER-FAILED, never [] → 0 → INTEGRATED. "
                "Calibration of leftover files is not a tree listing. Never 0."
            ),
        }
    misses = list(row.get("misses") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    canary = bool(row.get("canary_present"))
    lawful = bool(row.get("canary_lawful"))
    phrases = list(row.get("found_phrases") or [])
    if not card or not catalog or not canary:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/canary"])
                + ". Calibrated device-path census / lawful-canary talk is CLAIMED "
                "until the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in phrases]
    if (
        needed
        or not lawful
        or not row.get("posting_open")
        or not row.get("no_auth")
        or not row.get("no_gate")
        or row.get("self_hosted_dispatch")
        or row.get("host_inference")
        or row.get("parse_failures")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "census present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Lawful OPEN+DEVICE canary, not-pending, no host inference, "
                "and open door required. Talk is CLAIMED. FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "device-path census leftover is on this tree. X/Y/Z ran on the named "
            "git tree. Lawful read-only OPEN+DEVICE canary is a fixture, not a "
            "pending p/ ACTION. Current-tree counts are measured, not inferred: "
            "reservations=%s, batches=%s. A Slack census is still not the file."
            % (row.get("reservation_count"), row.get("batch_count"))
        ),
    }


def measure_root(root, ref="HEAD"):
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
    canary_text = search_hits.get(DEFAULT_CANARY, "")
    instrument_text = search_hits.get(os.path.join("host", "device_path_census.py"), "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join([card_text, catalog_text, instrument_text, canary_text]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    live_post = _exists(root, os.path.join("p", CANARY_ID + ".md"))
    canary = inspect_canary(canary_text, live_post)
    tree = ls_tree(root, ref)
    tree_ok = bool(tree.get("ok"))
    paths = list(tree.get("paths") or []) if tree_ok else []
    scopes = (
        count_result_scopes(root, paths)
        if tree_ok
        else {
            "result_count": None,
            "scope_github": None,
            "scope_device": None,
            "scope_other": None,
            "parse_failures": None,
        }
    )
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "lawful canary" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "canary_present": bool(canary_text) and bool(canary.get("parsed")),
        "canary_lawful": bool(canary.get("lawful")),
        "tree_ok": tree_ok,
        "tree_error": str(tree.get("error") or ""),
        "tree_count": len(paths) if tree_ok else None,
        "reservation_count": count_prefix(paths, RESERVATION_PREFIX) if tree_ok else None,
        "batch_count": count_prefix(paths, BATCH_PREFIX) if tree_ok else None,
        "result_count": scopes["result_count"],
        "scope_github": scopes["scope_github"],
        "scope_device": scopes["scope_device"],
        "parse_failures": scopes["parse_failures"],
        "found_phrases": found,
        "posting_open": str(catalog.get("posting") or "").upper() == "OPEN",
        "no_auth": bool(catalog.get("no_auth")),
        "no_gate": bool(catalog.get("no_gate")),
        "self_hosted_dispatch": bool(canary.get("self_hosted_dispatch")),
        "host_inference": bool(canary.get("host_inference")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "jojo_id": catalog.get("jojo_id") or JOJO_ID,
        "pinned_sha": catalog.get("pinned_sha") or PINNED_SHA,
        "canary_id": catalog.get("canary_id") or CANARY_ID,
        "ref": ref,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "jojo_id": facts["jojo_id"],
            "pinned_sha": facts["pinned_sha"],
            "canary_id": facts["canary_id"],
            "canary": canary,
            "ref": ref,
            "tree_ok": tree_ok,
            "tree_error": str(tree.get("error") or ""),
            "truncated": False,
        }
    )
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the JOJO device-path census leftover"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root, args.ref)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload["x"] = {
        "ref": row.get("ref"),
        "tree_count": row.get("tree_count"),
        "search_space": row.get("search_space") or [],
        "truncated": False,
    }
    payload["y"] = {
        "reservation_count": row.get("reservation_count"),
        "batch_count": row.get("batch_count"),
        "result_count": row.get("result_count"),
        "scope_github": row.get("scope_github"),
        "scope_device": row.get("scope_device"),
        "parse_failures": row.get("parse_failures"),
        "canary_lawful": row.get("canary_lawful"),
        "calibration_hits": row.get("calibration_hits") or [],
    }
    payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 1


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
            "canary_present": True,
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
            "canary_present": False,
            "misses": [DEFAULT_CARD],
        }
    )
    assert missing["state"] == "NOT_LANDED"
    rec = parse_action(
        "from: RIVET\nid: %s\nkind: ACTION\nact: OPEN\ntarget: DEVICE\n\n---\n\n"
        "OPEN\ntarget: DEVICE\n\nhttps://example.test/head.md\n" % CANARY_ID
    )
    assert rec["verb"] == "OPEN"
    assert is_device_target(rec["target"])
    live = inspect_canary(
        "from: RIVET\nid: %s\nkind: ACTION\nact: OPEN\ntarget: DEVICE\n\n---\n\n"
        "OPEN\ntarget: DEVICE\n\nhttps://example.test/head.md\n" % CANARY_ID,
        False,
    )
    assert live["lawful"] is True
    pending = inspect_canary(
        "from: RIVET\nid: %s\nkind: ACTION\nact: OPEN\ntarget: DEVICE\n\n---\n\n"
        "OPEN\ntarget: DEVICE\n\nhttps://example.test/head.md\n" % CANARY_ID,
        True,
    )
    assert pending["lawful"] is False
    assert pending["pending"] is True
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "canary_present": True,
            "canary_lawful": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "posting_open": True,
            "no_auth": True,
            "no_gate": True,
            "self_hosted_dispatch": False,
            "host_inference": False,
            "parse_failures": 0,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    return True


if __name__ == "__main__":
    sys.exit(main())
