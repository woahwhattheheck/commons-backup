#!/usr/bin/env python3
"""host/xyz_zero.py — X/Y/Z for negative finder claims.

Slack 1787638124.555469 / id gauge-xyz-zero-audit-order-20260825-01
The earlier universal wording ("every test and result") was an
incorrect scope expansion. This instrument audits only a negative
finder/search claim: a claim that a searched-for item is absent.

X — the find. Pattern, path, query, ref, SHA. If X is not written,
    the result is unauditable and does not count.
Y — the hit branch. Prints FROM the found bytes, not an assumption.
    A Y that would print the same with or without the find is not
    a measurement.
Z — the miss branch. Every way find(x) can fail without X being
    absent, named. A miss prints FINDER-UNVERIFIED + the full
    search space — never a bare 0, never "none found", never a
    silent pass. The hunted bug: `if find(x): print(y)` with no else.
Calibration — in the same finder run, point the finder at a target
    known present. If that misses, negative absence conclusions from
    that finder are void. No calibration = no valid absence claim.

This instrument has no authority over PFC attribution, computations,
tests, runtime/container receipts, performance measurements, or
numerical outputs. PFC attribution is established and is not inferred,
qualified, or overridden here.

This leftover does not remint the GAUGE id. It does not take the
SPECTER/JOJO 02:02 collision case. titan NOT_WRITTEN. No auth.

  python3 host/xyz_zero.py
  python3 host/xyz_zero.py --root .
  python3 host/xyz_zero.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "XYZ_ZERO.json")
SLACK_TS = "1787638124.555469"
SOURCE_ID = "gauge-xyz-zero-audit-order-20260825-01"
FINDER_UNVERIFIED = "FINDER-UNVERIFIED"
AUDIT_SCOPE = "NEGATIVE_FINDER_CLAIMS_ONLY"
IN_SCOPE_CLAIMS = frozenset(("ABSENCE_SEARCH", "NEGATIVE_FINDER_CLAIM"))
PROTECTED_CLAIMS = (
    "PFC_ATTRIBUTION",
    "COMPUTATION_RESULT",
    "TEST_RESULT",
    "RUNTIME_RECEIPT",
    "CONTAINER_HEALTH",
    "PERFORMANCE_MEASUREMENT",
    "NUMERICAL_OUTPUT",
)
BARE_ZERO_MARKERS = ("none found", "no matches", "0 found", "absent")
Z_FAILURE_MODES = (
    "wrong pattern",
    "wrong path",
    "unsupported operator (Slack search has NO boolean OR)",
    "stale ref",
    "moving main",
    "unparsed/truncated input",
    "encoding",
    "permissions",
    "empty glob",
)


def load_catalog(text):
    """Parse the X-Y-Z catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"finders": [], "error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"finders": [], "error": "catalog is not an object"}
    finders = []
    seen = set()
    for item in data.get("finders") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("id") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        finders.append(
            {
                "id": name,
                "x_pattern": str(item.get("x_pattern") or item.get("pattern") or "").strip(),
                "x_path": str(item.get("x_path") or item.get("path") or "").strip(),
                "x_query": str(item.get("x_query") or item.get("query") or "").strip(),
                "x_ref": str(item.get("x_ref") or item.get("ref") or "").strip(),
                "x_sha": str(item.get("x_sha") or item.get("sha") or "").strip(),
                "expect": str(item.get("expect") or "").strip().upper() or "HIT",
                "calibration": bool(item.get("calibration")),
                "claim_kind": str(item.get("claim_kind") or "ABSENCE_SEARCH").strip().upper(),
            }
        )
    return {
        "finders": finders,
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "source_id": str(data.get("source_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "audit_scope": str(data.get("audit_scope") or AUDIT_SCOPE).strip() or AUDIT_SCOPE,
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
    }


def applies_to(claim_kind):
    """True only for negative finder/search absence claims."""
    normalized = str(claim_kind or "").strip().upper().replace("-", "_").replace(" ", "_")
    return normalized in IN_SCOPE_CLAIMS


def scoped_verdict(claim_kind, original_result, audit_row=None):
    """Never rewrite an out-of-scope result with a finder verdict."""
    if not applies_to(claim_kind):
        return {
            "applies": False,
            "scope": AUDIT_SCOPE,
            "result": original_result,
            "audit_state": "OUT_OF_SCOPE",
        }
    return {
        "applies": True,
        "scope": AUDIT_SCOPE,
        "result": original_result,
        "audit_state": classify(audit_row or {})["state"],
    }


def search_space(finder):
    """X written down. If this is empty, the result does not count."""
    finder = finder or {}
    return {
        "id": str(finder.get("id") or "").strip(),
        "pattern": str(finder.get("x_pattern") or "").strip(),
        "path": str(finder.get("x_path") or "").strip(),
        "query": str(finder.get("x_query") or "").strip(),
        "ref": str(finder.get("x_ref") or "").strip(),
        "sha": str(finder.get("x_sha") or "").strip(),
        "operator": "literal substring. No boolean OR.",
        "failure_modes": list(Z_FAILURE_MODES),
    }


def x_written(finder):
    """X counts only when a pattern and a path (or query/ref/sha) are named."""
    space = search_space(finder)
    if not space["pattern"]:
        return False
    return bool(space["path"] or space["query"] or space["ref"] or space["sha"])


def y_from_hit(text, pattern, window=24):
    """Y must be sliced from the found bytes. Canned FOUND is void."""
    body = str(text or "")
    needle = str(pattern or "")
    if not needle:
        return None
    idx = body.find(needle)
    if idx < 0:
        return None
    start = max(0, idx - window)
    end = min(len(body), idx + len(needle) + window)
    excerpt = body[start:end]
    if needle not in excerpt:
        return None
    return excerpt


def y_sources_from_bytes(y_text, pattern):
    """A Y that would print the same without the find is not a measurement."""
    y_text = str(y_text or "")
    pattern = str(pattern or "")
    if not pattern or pattern not in y_text:
        return False
    canned = y_text.strip().upper()
    if canned in ("FOUND", "HIT", "YES", "TRUE", "1"):
        return False
    return True


def z_from_miss(finder):
    """Miss prints FINDER-UNVERIFIED plus the full search space."""
    return {
        "status": FINDER_UNVERIFIED,
        "search_space": search_space(finder),
    }


def z_is_verified(z_text):
    """Z must contain the marker and a parseable, full search space."""
    body = str(z_text or "").strip()
    if not body:
        return False
    low = body.lower()
    if not body.startswith(FINDER_UNVERIFIED):
        return False
    if low in ("0", "none", "none found", "no matches", "absent"):
        return False
    for marker in BARE_ZERO_MARKERS:
        if body == marker or low == marker:
            return False
    payload = body[len(FINDER_UNVERIFIED):].strip()
    try:
        space = json.loads(payload)
    except (TypeError, ValueError):
        return False
    if not isinstance(space, dict) or not str(space.get("pattern") or "").strip():
        return False
    if not any(str(space.get(key) or "").strip() for key in ("path", "query", "ref", "sha")):
        return False
    if not str(space.get("operator") or "").strip():
        return False
    modes = space.get("failure_modes")
    return isinstance(modes, list) and set(Z_FAILURE_MODES).issubset(set(modes))


def run_finder(finder, text, present, silent_miss=False):
    """Execute one find. Y comes from bytes. Miss must carry Z."""
    finder = finder or {}
    row = {
        "id": str(finder.get("id") or "").strip(),
        "calibration": bool(finder.get("calibration")),
        "expect": str(finder.get("expect") or "HIT").strip().upper() or "HIT",
        "x": search_space(finder),
        "x_written": x_written(finder),
        "hit": False,
        "y": "",
        "y_from_bytes": False,
        "z": "",
        "z_verified": False,
        "void": False,
        "void_reason": "",
        "claim_kind": str(finder.get("claim_kind") or "ABSENCE_SEARCH").strip().upper(),
        "audit_scope": AUDIT_SCOPE,
    }
    if not row["x_written"]:
        row["void"] = True
        row["void_reason"] = "X is not written. Result is unauditable and does not count."
        return row
    if not present:
        if silent_miss:
            row["z"] = "none found"
            row["z_verified"] = False
            row["void"] = True
            row["void_reason"] = (
                "silent miss: if find(x): print(y) with no else. "
                "Bare none-found is not a measurement."
            )
            return row
        z_row = z_from_miss(finder)
        row["z"] = "%s %s" % (z_row["status"], json.dumps(z_row["search_space"], sort_keys=True))
        row["z_verified"] = z_is_verified(row["z"])
        return row
    y = y_from_hit(text, finder.get("x_pattern"))
    if y is None:
        if silent_miss:
            row["z"] = "0"
            row["z_verified"] = False
            row["void"] = True
            row["void_reason"] = (
                "silent miss: if find(x): print(y) with no else. "
                "Bare 0 is not a measurement."
            )
            return row
        z_row = z_from_miss(finder)
        row["z"] = "%s %s" % (z_row["status"], json.dumps(z_row["search_space"], sort_keys=True))
        row["z_verified"] = z_is_verified(row["z"])
        return row
    row["hit"] = True
    row["y"] = y
    row["y_from_bytes"] = y_sources_from_bytes(y, finder.get("x_pattern"))
    if not row["y_from_bytes"]:
        row["void"] = True
        row["void_reason"] = "Y did not print from the found bytes."
    return row


def measure_from_rows(rows):
    """Census finder rows. A miss voids only negative finder claims."""
    scanned = []
    voids = []
    silent = []
    calibs = []
    calib_hits = 0
    hits = 0
    misses = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if not applies_to(row.get("claim_kind") or "ABSENCE_SEARCH"):
            continue
        scanned.append(row)
        if row.get("void"):
            voids.append(str(row.get("id") or "") or "unnamed")
            if "silent miss" in str(row.get("void_reason") or ""):
                silent.append(str(row.get("id") or "") or "unnamed")
        if row.get("calibration"):
            calibs.append(row)
            if row.get("hit") and row.get("y_from_bytes") and not row.get("void"):
                calib_hits += 1
        if row.get("hit"):
            hits += 1
        else:
            misses += 1
    void_run = False
    void_reason = ""
    if not calibs:
        void_run = True
        void_reason = "no known-present finder calibration. No valid absence claim."
    elif calib_hits == 0:
        void_run = True
        void_reason = (
            "calibration missed a known-present finder target. "
            "Negative finder/absence conclusions from this finder run are VOID. "
            "Unrelated computations, tests, runtime/container receipts, numerical "
            "results, and established PFC attribution are unchanged."
        )
    elif voids:
        void_run = True
        void_reason = "finder VOID: " + ", ".join(voids)
    return {
        "measured": True,
        "finder_count": len(scanned),
        "hit_count": hits,
        "miss_count": misses,
        "calibration_count": len(calibs),
        "calibration_hits": calib_hits,
        "void_count": len(voids),
        "silent_misses": silent,
        "void_run": void_run,
        "void_reason": void_reason,
        "finders": scanned,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
        "source_id": SOURCE_ID,
        "audit_scope": AUDIT_SCOPE,
        "protected_claims": list(PROTECTED_CLAIMS),
    }


def measure_tree(root, catalog_text, silent_ids=None):
    """Read each catalog finder from disk and run X/Y/Z/calibration."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan": "NOT_WRITTEN",
        }
    silent = set(silent_ids or [])
    rows = []
    base = os.path.abspath(root)
    for finder in catalog.get("finders") or []:
        rel = str(finder.get("x_path") or "").strip().replace("\\", "/")
        present = False
        text = ""
        if rel:
            full = os.path.join(base, *rel.split("/"))
            try:
                with open(full, encoding="utf-8") as handle:
                    text = handle.read()
                present = True
            except OSError:
                present = False
                text = ""
        rows.append(
            run_finder(
                finder,
                text,
                present,
                silent_miss=finder.get("id") in silent,
            )
        )
    measured = measure_from_rows(rows)
    measured["catalog_finders"] = len(catalog.get("finders") or [])
    measured["slack_ts"] = catalog.get("slack_ts") or SLACK_TS
    measured["source_id"] = catalog.get("source_id") or SOURCE_ID
    measured["titan"] = catalog.get("titan") or "NOT_WRITTEN"
    measured["hands_off"] = list(catalog.get("hands_off") or [])
    measured["audit_scope"] = AUDIT_SCOPE
    return measured


def measure_paths(root, catalog_path):
    """Read the catalog file and run the audit against root."""
    path = os.path.abspath(catalog_path)
    try:
        with open(path, encoding="utf-8") as handle:
            catalog_text = handle.read()
    except OSError as exc:
        return {
            "measured": False,
            "error": str(exc),
            "titan": "NOT_WRITTEN",
        }
    measured = measure_tree(root, catalog_text)
    measured["catalog"] = path
    measured["tree_root"] = os.path.abspath(root)
    return measured


def classify(row):
    """Classify this negative-finder instrument, never another result."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "X-Y-Z catalog / finders not read. Absence was not "
                "measured. A missing read is not stillness."
            ),
        }
    if row.get("void_run"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "FINDER CLAIM VOID. "
                + str(row.get("void_reason") or "uncalibrated zero")
                + " This verdict applies only to a negative finder/absence claim. "
                + "A Slack order is CLAIMED until a calibrated leftover "
                "is on current main."
            ),
        }
    silent = row.get("silent_misses") or []
    if silent:
        return {
            "state": "NOT_LANDED",
            "note": (
                "silent miss (if find(x): print(y) with no else): "
                + ", ".join(silent)
                + ". FINDER-UNVERIFIED + search space required."
            ),
        }
    calibs = int(row.get("calibration_count") or 0)
    calib_hits = int(row.get("calibration_hits") or 0)
    finders = int(row.get("finder_count") or 0)
    if calibs and calib_hits == calibs and finders:
        return {
            "state": "INTEGRATED",
            "note": (
                "X-Y-Z leftover is on this file. Calibration hit "
                + str(calib_hits)
                + "/"
                + str(calibs)
                + " known-present targets. "
                + str(row.get("hit_count") or 0)
                + " hits printed Y from found bytes. "
                + str(row.get("miss_count") or 0)
                + " misses printed FINDER-UNVERIFIED + search space. "
                "Scope: negative finder/absence claims only. "
                "A Slack order is still not the file."
            ),
        }
    return {
        "state": "CANDIDATE",
        "note": (
            "X-Y-Z run is partial. "
            + str(calib_hits)
            + "/"
            + str(calibs)
            + " calibrations hit. Ship the leftover, do not report a zero."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="X-Y-Z negative-finder audit: X written, Y from bytes, Z on miss, known-present calibration"
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
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") and not row.get("void_run") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]

    no_x = run_finder({"id": "blank"}, "hello", True)
    assert no_x["void"] is True
    assert "X is not written" in no_x["void_reason"]

    hit = run_finder(
        {
            "id": "calib-head",
            "x_pattern": "A bake is not the board",
            "x_path": "ground/HEAD.md",
            "calibration": True,
        },
        "# A bake is not the board\n\nBryce 2026-08-19",
        True,
    )
    assert hit["hit"] is True
    assert hit["y_from_bytes"] is True
    assert "A bake is not the board" in hit["y"]
    assert hit["void"] is False

    miss = run_finder(
        {
            "id": "absent-needle",
            "x_pattern": "THIS-STRING-IS-NOT-ON-THE-BOARD-XYZ-20260825",
            "x_path": "ground/HEAD.md",
            "expect": "MISS",
        },
        "# A bake is not the board\n",
        True,
    )
    assert miss["hit"] is False
    assert miss["z_verified"] is True
    assert FINDER_UNVERIFIED in miss["z"]
    assert "ground/HEAD.md" in miss["z"]

    silent = run_finder(
        {
            "id": "silent-zero",
            "x_pattern": "nope-not-here",
            "x_path": "ground/HEAD.md",
        },
        "# A bake is not the board\n",
        True,
        silent_miss=True,
    )
    assert silent["void"] is True
    assert "silent miss" in silent["void_reason"]
    assert silent["z_verified"] is False

    no_cal = measure_from_rows([miss])
    assert no_cal["void_run"] is True
    assert classify(no_cal)["state"] == "NOT_LANDED"

    calib_miss = measure_from_rows(
        [
            run_finder(
                {
                    "id": "calib-miss",
                    "x_pattern": "not-present-at-all",
                    "x_path": "ground/HEAD.md",
                    "calibration": True,
                },
                "# A bake is not the board\n",
                True,
            )
        ]
    )
    assert calib_miss["void_run"] is True
    assert "known-present" in calib_miss["void_reason"]
    assert classify(calib_miss)["state"] == "NOT_LANDED"

    ok = measure_from_rows([hit, miss])
    assert ok["void_run"] is False
    assert ok["calibration_hits"] == 1
    assert ok["titan"] == "NOT_WRITTEN"
    assert classify(ok)["state"] == "INTEGRATED"
    assert "still not the file" in classify(ok)["note"]
    assert not y_sources_from_bytes("FOUND", "A bake is not the board")
    assert not z_is_verified(FINDER_UNVERIFIED + " path=ground/HEAD.md")
    assert z_is_verified(miss["z"])
    assert not z_is_verified("none found")
    assert not z_is_verified("0")
    for protected in PROTECTED_CLAIMS:
        assert not applies_to(protected)
        original = {"state": "SUCCESS", "value": 42, "attribution": "PFC_ATTRIBUTED"}
        guarded = scoped_verdict(protected, original, no_cal)
        assert guarded["applies"] is False
        assert guarded["result"] is original
        assert guarded["audit_state"] == "OUT_OF_SCOPE"
    assert applies_to("absence_search")
    return True


if __name__ == "__main__":
    sys.exit(main())
