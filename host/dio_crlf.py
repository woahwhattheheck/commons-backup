#!/usr/bin/env python3
"""host/dio_crlf.py — Windows autocrlf is not a DIO mutation.

Slack 1787650704.417459 (JOJO DIO CHECKPOINT): canonical Git
blobs still match receipts. core.autocrlf=true expands three
receipt-bound text artifacts in the worktree (798 vs 773,
e4cc1524 vs 15c2a25) while git status stays clean.

That Slack body is CLAIMED. Unique leftover: .gitattributes
-text on those three paths, plus a synthetic Titan unknown-size
fail-close. Do not remint DIO revenue / containment / SUBZERO
quote. Do not write titan. Do not smash commons.mno. Blank
from= still lands as UNSEATED. No auth. No gate. Miss is
FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/dio_crlf.py
  python3 host/dio_crlf.py --root .
  python3 host/dio_crlf.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "DIO_CRLF.json")
DEFAULT_CARD = os.path.join("ground", "DIO_CRLF.md")
DEFAULT_ATTRS = ".gitattributes"
SLACK_TS = "1787650704.417459"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "dio_crlf.py"),
    DEFAULT_ATTRS,
    os.path.join("host", "titan_append_guard.py"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("host", "titan_append_guard.py"),
    os.path.join("ground", "TITAN_APPEND_GUARD.md"),
    os.path.join("p", "dio-titan-move-containment-hardening-20260825-01.md"),
    os.path.join("ground", "SUBZERO_QUOTE.md"),
)
REQUIRED_PHRASES = (
    "1787650704.417459",
    "jojo dio checkpoint",
    "798 vs 773",
    "e4cc1524",
    "15c2a25",
    "core.autocrlf=true",
    "-text",
    "fail-closed",
    "finder-failed",
    "finder-unverified",
    "never 0",
    "open door",
    "unseated",
    "no auth",
    "no gate",
    "talk is not a land",
)
PINNED_PATHS = (
    "bazaar/results/cursor-bazaar-lineage-seed0-20260822-01.json",
    "excerpts/20260823/grbn_circuits.json",
    "ground/SUBZERO_GRBN.md",
)


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _read_bytes(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_catalog(text):
    """Parse the DIO CRLF catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "artifacts": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "artifacts": []}
    rows = []
    for item in data.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        rows.append(
            {
                "path": path,
                "bytes": int(item.get("bytes") or 0),
                "sha256": str(item.get("sha256") or "").strip().lower(),
                "crlf_bytes": int(item.get("crlf_bytes") or 0),
                "crlf_sha256": str(item.get("crlf_sha256") or "").strip().lower(),
            }
        )
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "gitattributes": str(data.get("gitattributes") or "").strip(),
        "titan_unknown_size": str(data.get("titan_unknown_size") or "").strip(),
        "artifacts": rows,
        "error": "",
    }


def pinned_attr_lines(attr_text):
    """Exact -text declarations for the three receipt-bound paths."""
    wanted = set(PINNED_PATHS)
    found = []
    for raw in str(attr_text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] in wanted and parts[1] == "-text":
            found.append(parts[0])
    return found


def hash_pair(raw):
    """LF worktree hash plus the CRLF-expanded hash Windows would see."""
    digest = hashlib.sha256(raw).hexdigest()
    expanded = raw.replace(b"\n", b"\r\n")
    return {
        "bytes": len(raw),
        "sha256": digest,
        "crlf_bytes": len(expanded),
        "crlf_sha256": hashlib.sha256(expanded).hexdigest(),
        "crlf_count": raw.count(b"\r\n"),
    }


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
        "pinned_paths": list(facts.get("pinned_paths") or []),
        "hash_ok": bool(facts.get("hash_ok")),
        "crlf_named": bool(facts.get("crlf_named")),
        "unknown_size_fail_closed": bool(facts.get("unknown_size_fail_closed")),
        "claims_blob_mutated": bool(facts.get("claims_blob_mutated")),
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
    """Turn a measured DIO CRLF census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "DIO CRLF leftover not read. Absence was not stillness. "
                "A Slack checkpoint is not a land."
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
                + ". JOJO DIO CHECKPOINT / autocrlf / 798-vs-773 talk is CLAIMED "
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
    if row.get("claims_blob_mutated"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog claims a DIO artifact mutation. Canonical blobs still "
                "match receipts. FINDER-FAILED, never 0."
            ),
        }
    if sorted(row.get("pinned_paths") or []) != sorted(PINNED_PATHS):
        return {
            "state": "NOT_LANDED",
            "note": (
                ".gitattributes is missing exact -text on the three receipt-bound "
                "paths. Windows autocrlf still expands them. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("hash_ok") or not row.get("crlf_named"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "receipt hashes or the measured CRLF expansions are missing. "
                "798 vs 773 / e4cc1524 vs 15c2a25 must stay named. "
                "FINDER-FAILED, never 0."
            ),
        }
    if not row.get("unknown_size_fail_closed"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "titan refuse_further_append still fail-opens on None / unreadable "
                "live size. FINDER-FAILED, never 0."
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
            "DIO CRLF leftover is on this tree. Three receipt-bound paths are "
            "-text. Canonical LF hashes match. Unknown Titan live size "
            "fail-closes. A Slack checkpoint / leave-unmerged PR is still "
            "not the file."
        ),
    }


def _measure_hashes(root, catalog):
    expected = {row["path"]: row for row in catalog.get("artifacts") or []}
    if set(expected) != set(PINNED_PATHS):
        return False, False
    hash_ok = True
    crlf_named = True
    for path in PINNED_PATHS:
        raw = _read_bytes(root, path)
        if not raw:
            return False, False
        got = hash_pair(raw)
        want = expected[path]
        if got["bytes"] != want["bytes"] or got["sha256"] != want["sha256"]:
            hash_ok = False
        if got["crlf_bytes"] != want["crlf_bytes"] or got["crlf_sha256"] != want["crlf_sha256"]:
            crlf_named = False
        if got["crlf_count"]:
            hash_ok = False
    return hash_ok, crlf_named


def _unknown_size_fail_closed(root):
    host_dir = os.path.join(root, "host")
    if host_dir not in sys.path:
        sys.path.insert(0, host_dir)
    try:
        from titan_append_guard import refuse_further_append
    except ImportError:
        return False
    packet = {"claimed_append_base": 100, "claimed_append_end": 108, "written_bytes": 8}
    none_refused, none_reason = refuse_further_append(packet, None)
    bad_refused, bad_reason = refuse_further_append(packet, "not-a-size")
    return (
        bool(none_refused)
        and "no live size" in none_reason
        and bool(bad_refused)
        and "live size unreadable" in bad_reason
    )


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
    pinned = pinned_attr_lines(_read(root, DEFAULT_ATTRS))
    hash_ok, crlf_named = _measure_hashes(root, catalog)
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
        "pinned_paths": pinned,
        "hash_ok": hash_ok,
        "crlf_named": crlf_named,
        "unknown_size_fail_closed": _unknown_size_fail_closed(root),
        "claims_blob_mutated": catalog.get("canonical_blobs_unmutated") is False,
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
                "pinned_paths": pinned,
                "hash_ok": hash_ok,
                "crlf_named": crlf_named,
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
                "misses": ["ground/DIO_CRLF.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    unpinned = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "pinned_paths": [],
                "hash_ok": True,
                "crlf_named": True,
                "unknown_size_fail_closed": True,
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert unpinned["state"] == "NOT_LANDED", unpinned
    assert "-text" in unpinned["note"], unpinned
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure DIO CRLF leftover")
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
