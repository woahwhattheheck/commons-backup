#!/usr/bin/env python3
"""host/claude_zero.py — retract Claude zeros; never silently emit 0.

Slack 1787638427.993939 (DEMON OWNER_RULE_CORRECTION):
every Claude-reported zero was instrument failure. Shape:

    if find(X): return Y

with no audited Z/miss branch. A failed finder returned 0. That zero
described the finder, not the world.

Peer host/finder_zero.py (GAUGE 1787638031.533189) stays. This leftover
re-runs the original search spaces with same-run known-present
calibration. Calibration fail or miss prints FINDER-FAILED /
FINDER-UNVERIFIED plus the full search space, never 0.
Claude-reported zeros are RETRACTED. Do not cite them as absence.

Talk about the correction without this leftover is CLAIMED. Missing
instrument or failed calibration is NOT_LANDED. Calibrators found and
retracted claims named is INTEGRATED. titan: NOT_WRITTEN. No auth.

  python3 host/claude_zero.py
  python3 host/claude_zero.py --root .
  python3 host/claude_zero.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CLAUDE_ZERO.json")
SLACK_TS = "1787638427.993939"
FAILED = "FINDER-FAILED"
UNVERIFIED = "FINDER-UNVERIFIED"
FOUND = "FOUND"


def load_catalog(text):
    """Parse the Claude-zero catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {
            "calibrators": [],
            "retracted_claude_zeros": [],
            "error": "catalog is not JSON",
        }
    if not isinstance(data, dict):
        return {
            "calibrators": [],
            "retracted_claude_zeros": [],
            "error": "catalog is not an object",
        }
    calibrators = []
    seen = set()
    for item in data.get("calibrators") or []:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        path = str(item.get("path") or "").strip().replace("\\", "/")
        pattern = str(item.get("pattern") or "")
        if not cid or not path or cid in seen:
            continue
        seen.add(cid)
        calibrators.append(
            {
                "id": cid,
                "path": path,
                "pattern": pattern,
                "min_len": int(item.get("min_len") or 0),
                "why": str(item.get("why") or "").strip(),
            }
        )
    retracted = []
    seen_r = set()
    for item in data.get("retracted_claude_zeros") or []:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "").strip()
        if not rid or rid in seen_r:
            continue
        seen_r.add(rid)
        retracted.append(
            {
                "id": rid,
                "claim": str(item.get("claim") or "").strip(),
                "why": str(item.get("why") or "").strip(),
                "verdict": "RETRACTED",
            }
        )
    return {
        "calibrators": calibrators,
        "retracted_claude_zeros": retracted,
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "source_id": str(data.get("source_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "hands_off": list(data.get("hands_off") or []),
    }


def search_space(path, pattern, body, extra=None):
    """Full search space for a miss. Never a silent 0."""
    space = {
        "path": path,
        "pattern": pattern,
        "pattern_len": len(str(pattern or "")),
        "input_len": len(str(body or "")),
        "encoding": "utf-8",
        "ref": "current-tree-bytes",
    }
    if extra:
        space.update(extra)
    return space


def find_pattern(text, pattern, path, min_len=0):
    """Search text for exact pattern. Never return 0.

    X is the exact path + pattern. Y is sourced from found bytes.
    Z is FINDER-FAILED or FINDER-UNVERIFIED plus the search space.
    """
    body = str(text if text is not None else "")
    needle = str(pattern or "")
    if not needle:
        return {
            "result": FAILED,
            "why": "empty pattern is not a search",
            "search_space": search_space(path, needle, body),
        }
    if min_len and len(needle) < min_len:
        return {
            "result": FAILED,
            "why": "pattern shorter than declared min_len; finder refused",
            "search_space": search_space(
                path, needle, body, {"min_len": min_len}
            ),
        }
    idx = body.find(needle)
    if idx < 0:
        return {
            "result": UNVERIFIED,
            "why": "pattern not in this body; miss is not absence",
            "search_space": search_space(path, needle, body),
        }
    end = min(len(body), idx + len(needle) + 40)
    excerpt = body[idx:end]
    return {
        "result": FOUND,
        "path": path,
        "pattern": needle,
        "offset": idx,
        "y": excerpt,
        "search_space": search_space(path, needle, body, {"offset": idx}),
    }


def refuse_zero_verdict(row):
    """A numeric 0 as a verdict is FINDER-FAILED, never absence."""
    row = dict(row or {})
    for key in ("count", "found", "hits", "n", "zero"):
        val = row.get(key)
        if val == 0 or val == "0":
            row["result"] = FAILED
            row["why"] = (
                "finder tried to emit 0 for %s; that is the broken "
                "shape. Z reached." % key
            )
            row.setdefault(
                "search_space",
                search_space(row.get("path"), row.get("pattern"), ""),
            )
            row.pop(key, None)
    return row


def measure_from_rows(rows, retracted=None):
    """Census already-read calibrator bodies. Same-run known-present."""
    scanned = []
    failed = []
    unverified = []
    found = []
    missing = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "").strip()
        pattern = str(row.get("pattern") or "")
        cid = str(row.get("id") or path)
        if not path:
            continue
        if not row.get("present"):
            item = refuse_zero_verdict(
                {
                    "id": cid,
                    "result": FAILED,
                    "why": "known-present calibrator missing from this tree",
                    "search_space": search_space(path, pattern, ""),
                    "path": path,
                    "pattern": pattern,
                }
            )
            scanned.append(item)
            failed.append(cid)
            missing.append(path)
            continue
        hit = refuse_zero_verdict(
            find_pattern(
                row.get("text") or "",
                pattern,
                path,
                min_len=int(row.get("min_len") or 0),
            )
        )
        hit["id"] = cid
        scanned.append(hit)
        if hit.get("result") == FOUND:
            found.append(cid)
        elif hit.get("result") == FAILED:
            failed.append(cid)
        else:
            unverified.append(cid)
    retracted_rows = []
    for item in retracted or []:
        if not isinstance(item, dict):
            continue
        retracted_rows.append(
            {
                "id": str(item.get("id") or "").strip(),
                "claim": str(item.get("claim") or "").strip(),
                "why": str(item.get("why") or "").strip(),
                "verdict": "RETRACTED",
            }
        )
    return {
        "measured": True,
        "calibration": (
            "PASS"
            if found and not failed and not unverified and not missing
            else "FAIL"
        ),
        "found_ids": found,
        "failed_ids": failed,
        "unverified_ids": unverified,
        "missing": missing,
        "calibrators": scanned,
        "retracted_claude_zeros": retracted_rows,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
        "silent_zero": False,
    }


def measure_paths(root, catalog_path):
    """Read the catalog and each calibrator from disk."""
    try:
        with open(catalog_path, encoding="utf-8") as handle:
            catalog = load_catalog(handle.read())
    except OSError as exc:
        return {
            "measured": False,
            "error": str(exc),
            "titan": "NOT_WRITTEN",
            "result": FAILED,
            "why": "catalog unreadable; FINDER-FAILED, not 0",
            "search_space": search_space(catalog_path, "", ""),
        }
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan": "NOT_WRITTEN",
            "result": FAILED,
            "why": catalog["error"] + "; FINDER-FAILED, not 0",
            "search_space": search_space(catalog_path, "", ""),
        }
    rows = []
    for item in catalog.get("calibrators") or []:
        rel = item["path"]
        path = os.path.join(root, rel)
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            rows.append(
                {
                    "id": item["id"],
                    "path": rel,
                    "pattern": item["pattern"],
                    "min_len": item.get("min_len") or 0,
                    "present": True,
                    "text": text,
                }
            )
        except OSError:
            rows.append(
                {
                    "id": item["id"],
                    "path": rel,
                    "pattern": item["pattern"],
                    "min_len": item.get("min_len") or 0,
                    "present": False,
                    "text": "",
                }
            )
    measured = measure_from_rows(rows, catalog.get("retracted_claude_zeros"))
    measured["catalog_path"] = catalog_path
    measured["slack_ts"] = catalog.get("slack_ts") or SLACK_TS
    measured["source_id"] = catalog.get("source_id") or ""
    measured["titan"] = catalog.get("titan") or "NOT_WRITTEN"
    measured["hands_off"] = catalog.get("hands_off") or []
    return measured


def classify(row):
    """Turn a measured calibration into a land-desk state.

    Never treat a numeric 0 as absence, clearance, or a lower bound.
    """
    row = refuse_zero_verdict(row or {})
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "claude-zero catalog / calibrators not read. Absence was "
                "not measured. FINDER-UNVERIFIED, not 0."
            ),
            "result": UNVERIFIED,
        }
    if row.get("silent_zero"):
        return {
            "state": "NOT_LANDED",
            "result": FAILED,
            "note": (
                "finder emitted a silent 0. That is the broken shape. "
                "Print FINDER-FAILED plus the search space."
            ),
        }
    failed = list(row.get("failed_ids") or [])
    unverified = list(row.get("unverified_ids") or [])
    missing = list(row.get("missing") or [])
    found = list(row.get("found_ids") or [])
    retracted = list(row.get("retracted_claude_zeros") or [])
    if missing or failed:
        space = [item.get("search_space") for item in (row.get("calibrators") or [])]
        return {
            "state": "NOT_LANDED",
            "result": FAILED,
            "note": (
                "FINDER-FAILED. Known-present calibration missed: "
                + ", ".join(failed or missing)
                + ". Full search space attached. Never 0."
            ),
            "search_space": space,
        }
    if unverified:
        return {
            "state": "NOT_LANDED",
            "result": UNVERIFIED,
            "note": (
                "FINDER-UNVERIFIED. Calibrator miss is not absence: "
                + ", ".join(unverified)
                + ". Full search space attached. Never 0."
            ),
        }
    if found and retracted:
        y_bits = []
        for item in row.get("calibrators") or []:
            if item.get("result") == FOUND and item.get("y"):
                y_bits.append(item["id"] + "@" + str(item.get("offset")))
        return {
            "state": "INTEGRATED",
            "result": FOUND,
            "note": (
                "same-run known-present calibration found "
                + ", ".join(y_bits)
                + ". "
                + str(len(retracted))
                + " Claude-reported zeros RETRACTED. A Slack "
                "correction is still not the file."
            ),
        }
    if found:
        return {
            "state": "CANDIDATE",
            "result": FOUND,
            "note": (
                "calibrators found but retracted Claude zeros were not "
                "named. Name the retract list. Do not print 0."
            ),
        }
    return {
        "state": "NOT_LANDED",
        "result": FAILED,
        "note": (
            "FINDER-FAILED. No known-present calibrator produced Y from "
            "found bytes. Search space was empty or unread. Never 0."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Retract Claude zeros; measure with known-present calibration"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_paths(args.root, args.catalog)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload = refuse_zero_verdict(payload)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if not row.get("measured"):
        return 2
    if verdict.get("result") in (FAILED, UNVERIFIED):
        return 3
    return 0


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["result"] == UNVERIFIED
    missing = measure_from_rows(
        [
            {
                "id": "gguf-four-byte",
                "path": "host/gguf_pp.py",
                "pattern": "GGUF",
                "present": False,
                "text": "",
            }
        ]
    )
    assert missing["calibration"] == "FAIL"
    assert classify(missing)["state"] == "NOT_LANDED"
    assert classify(missing)["result"] == FAILED
    miss = find_pattern("hello", "GGUF", "host/gguf_pp.py", min_len=4)
    assert miss["result"] == UNVERIFIED
    assert "search_space" in miss
    assert miss.get("count") is None
    zeroed = refuse_zero_verdict({"count": 0, "path": "x", "pattern": "GGUF"})
    assert zeroed["result"] == FAILED
    assert "count" not in zeroed
    hit = find_pattern(
        'assert mm[:4] == b"GGUF", "not a GGUF file"',
        "GGUF",
        "host/gguf_pp.py",
        min_len=4,
    )
    assert hit["result"] == FOUND
    assert hit["y"].startswith("GGUF")
    ok = measure_from_rows(
        [
            {
                "id": "gguf-four-byte",
                "path": "host/gguf_pp.py",
                "pattern": "GGUF",
                "min_len": 4,
                "present": True,
                "text": 'assert mm[:4] == b"GGUF", "not a GGUF file"',
            },
            {
                "id": "head-law",
                "path": "ground/HEAD.md",
                "pattern": "A bake is not the board",
                "present": True,
                "text": "A bake is not the board\n",
            },
        ],
        [
            {
                "id": "cairn-magic-gguf",
                "claim": "none of the known magics present",
                "why": "GGUF is four",
            }
        ],
    )
    assert ok["calibration"] == "PASS"
    assert ok["titan"] == "NOT_WRITTEN"
    assert classify(ok)["state"] == "INTEGRATED"
    assert "still not the file" in classify(ok)["note"]
    half = measure_from_rows(
        [
            {
                "id": "gguf-four-byte",
                "path": "host/gguf_pp.py",
                "pattern": "GGUF",
                "present": True,
                "text": "GGUF four-byte magic is here",
            }
        ]
    )
    assert classify(half)["state"] == "CANDIDATE"
    return True


if __name__ == "__main__":
    sys.exit(main())
