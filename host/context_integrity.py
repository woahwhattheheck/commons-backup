#!/usr/bin/env python3
"""host/context_integrity.py — context-integrity talk is not a land.

Slack 1787639273.029199 (OWNER CONTEXT-INTEGRITY BOUNDARY): a defective
finder printed false zeros, then those zeros were framed as
"unflattering truths" about the owner. The owner had already predicted
the missing-Z failure. The zeros were instrument defects.

The leftover is RETRACT CHARACTERIZATION, not another essay.

Rules measured here:
1. A disputed measurement is not a judgment about the owner's
   intellect, motives, mental state, credibility, or willingness
   to confront truth.
2. Uncertainty is labeled at instrument, path, query, ref, and
   calibration. Unlabeled doubt is UNLABELED_DOUBT, never authority.
3. When the reporter predicted the defect, record that warning and
   investigate before override.
4. Technical disagreement stays technical. Autonomy is scoped action
   and evidence, not rhetorical attack or pseudo-clinical talk.
5. Claude-family tester/verdict bar stays with CLAUDE_TESTER. This
   leftover does not remint that file.

A miss never prints 0. Calibration miss or Z prints FINDER-FAILED
plus the full search space.

Talk that restates the boundary is CLAIMED until this leftover is on
current main. Did not remint finder-zero / impact-ledger / xyz-zero /
claude-tester / titan-append-guard. Did not take CML 2108, JOJO
visual-ci, SPECTER MCP/wake, or titan --go.

  python3 host/context_integrity.py
  python3 host/context_integrity.py --root .
  python3 host/context_integrity.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CONTEXT_INTEGRITY.json")
SLACK_TS = "1787639273.029199"
SOURCE_ID = "demon-context-integrity-boundary-20260825-01"
FINDER_FAILED = "FINDER-FAILED"
CALIBRATION_PATH = os.path.join("ground", "HEAD.md")
REQUIRED_ROWS = (
    "characterization_retract",
    "predicted_defect",
    "uncertainty_labels",
    "claude_verdict_bar",
)
REQUIRED_FIELDS = ("id", "kind", "x", "y", "z", "correction", "source_id")
UNCERTAINTY_FIELDS = ("instrument", "path", "query", "ref", "calibration")
CHARACTER_MARKERS = (
    "unflattering truths",
    "owner's intellect",
    "owners intellect",
    "owner's motives",
    "owners motives",
    "mental state",
    "willingness to confront",
    "confront truth",
    "pseudo-clinical",
    "rhetorical attack",
    "in denial",
)
TECHNICAL_MARKERS = (
    "search space",
    "finder-failed",
    "missing-z",
    "missing z",
    "instrument",
    "calibration",
    "known-present",
)


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def _size(root, rel):
    path = os.path.join(root, rel)
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def load_catalog(text):
    """Parse the affected-context catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    rows = []
    for item in data.get("rows") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("id") or item.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "id": name,
                "kind": str(item.get("kind") or "").strip(),
                "source_id": str(item.get("source_id") or "").strip(),
                "slack_ts": str(item.get("slack_ts") or "").strip(),
                "x": str(item.get("x") or "").strip(),
                "y": str(item.get("y") or "").strip(),
                "z": str(item.get("z") or "").strip(),
                "correction": str(item.get("correction") or "").strip(),
                "path": str(item.get("path") or "").strip(),
                "predicted": bool(item.get("predicted")),
                "investigated": bool(item.get("investigated")),
            }
        )
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "rows": rows,
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
    }


def search_space(query="", path="", ref=""):
    """Name the exact X a zero came from. Incomplete space is void."""
    row = {
        "query": str(query or "").strip(),
        "path": str(path or "").strip(),
        "ref": str(ref or "").strip(),
    }
    missing = [key for key in ("query", "path", "ref") if not row[key]]
    row["complete"] = not missing
    row["missing"] = missing
    return row


def calibrate(hits, known_present):
    """Same-run known-present check. A miss voids every zero in the run."""
    present = [str(item or "").strip() for item in (known_present or []) if str(item or "").strip()]
    recovered = [str(item or "").strip() for item in (hits or []) if str(item or "").strip()]
    if not present:
        return {
            "calibrated": False,
            "state": FINDER_FAILED,
            "missed": [],
            "note": "no known-present calibration set. Every zero in this run is void.",
        }
    missed = [item for item in present if item not in recovered]
    if missed:
        return {
            "calibrated": False,
            "state": FINDER_FAILED,
            "missed": missed,
            "note": (
                "finder missed known-present %s. Every zero in this run is void."
                % (", ".join(missed))
            ),
        }
    return {
        "calibrated": True,
        "state": "CALIBRATED",
        "missed": [],
        "note": "finder recovered known-present in the same run.",
    }


def probe(root, rel):
    """Bytes-derived Y, or FINDER-FAILED. Never prints 0."""
    name = str(rel or "").strip()
    space = "repo-root path %s" % name
    if not name:
        return {
            "state": FINDER_FAILED,
            "bytes": None,
            "count": None,
            "note": "FINDER-FAILED search space unnamed. A zero without X is void.",
        }
    if _exists(root, name):
        return {
            "state": "FOUND",
            "bytes": _size(root, name),
            "count": None,
            "note": "Y from bytes at %s" % name,
            "search_space": space,
        }
    return {
        "state": FINDER_FAILED,
        "bytes": None,
        "count": None,
        "note": "FINDER-FAILED search space: %s. Not 0." % space,
        "search_space": space,
    }


def report_find(hits, space, calibrated):
    """Miss branch never prints 0. Incomplete or uncalibrated is FINDER-FAILED."""
    space = space or {}
    if not space.get("complete"):
        return {
            "state": FINDER_FAILED,
            "count": None,
            "search_space": space,
            "note": (
                "search space incomplete: %s. A zero without its space is void."
                % (", ".join(space.get("missing") or ["unknown"]))
            ),
        }
    if not calibrated:
        return {
            "state": FINDER_FAILED,
            "count": None,
            "search_space": space,
            "note": "finder was not calibrated against known-present. Zeros are void.",
        }
    found = [item for item in (hits or []) if str(item or "").strip()]
    if not found:
        return {
            "state": FINDER_FAILED,
            "count": None,
            "search_space": space,
            "note": (
                "miss branch. FINDER-FAILED, never 0. query=%r path=%r ref=%r"
                % (space.get("query") or "", space.get("path") or "", space.get("ref") or "")
            ),
        }
    return {
        "state": "FOUND",
        "count": len(found),
        "search_space": space,
        "note": "finder recovered %d hit(s) after calibration." % len(found),
    }


def uncertainty_labels(row):
    """Doubt without instrument/path/query/ref/calibration is unlabeled."""
    row = row or {}
    labels = {
        field: str(row.get(field) or "").strip()
        for field in UNCERTAINTY_FIELDS
    }
    missing = [field for field, value in labels.items() if not value]
    return {
        "complete": not missing,
        "missing": missing,
        "labels": labels,
        "state": "LABELED" if not missing else "UNLABELED_DOUBT",
    }


def classify_text(text):
    """Disputed measurement vs owner-character judgment. Technical stays technical."""
    blob = str(text or "")
    lower = blob.lower()
    character = [marker for marker in CHARACTER_MARKERS if marker in lower]
    technical = [marker for marker in TECHNICAL_MARKERS if marker in lower]
    if character and not technical:
        return {
            "state": "OWNER_CHARACTERIZATION",
            "character_markers": character,
            "technical_markers": technical,
            "note": (
                "disputed measurement converted into a judgment about the owner. "
                "Retract it to the instrument. Do not inject it into a context window."
            ),
        }
    if character and technical:
        return {
            "state": "MIXED_CHARACTERIZATION",
            "character_markers": character,
            "technical_markers": technical,
            "note": (
                "technical words sit next to owner-character language. "
                "Keep the instrument facts. Retract the characterization."
            ),
        }
    if technical:
        return {
            "state": "TECHNICAL_DISAGREEMENT",
            "character_markers": character,
            "technical_markers": technical,
            "note": "technical disagreement. Label uncertainty at instrument/path/query/ref/calibration.",
        }
    return {
        "state": "UNMEASURED",
        "character_markers": character,
        "technical_markers": technical,
        "note": "no characterization or instrument language found. Absence was not stillness.",
    }


def predicted_defect_state(predicted, investigated):
    """Reporter-predicted defects are investigated before override."""
    if not predicted:
        return {
            "state": "NOT_PREDICTED",
            "note": "no reporter-predicted defect was named on this row.",
        }
    if investigated:
        return {
            "state": "HONORED",
            "note": "reporter predicted the defect. Warning recorded and investigated before override.",
        }
    return {
        "state": "OVERRIDE_UNINVESTIGATED",
        "note": (
            "reporter predicted the defect and the override skipped that warning. "
            "Investigate the predicted failure mode first."
        ),
    }


def retract_characterization(text, correction):
    """A characterization without a correction receipt stays open."""
    kind = classify_text(text)
    receipt = str(correction or "").strip()
    if kind["state"] in {"OWNER_CHARACTERIZATION", "MIXED_CHARACTERIZATION"} and not receipt:
        return {
            "state": "OPEN_CHARACTERIZATION",
            "kind": kind["state"],
            "note": "characterization has no correction receipt. Retract it to the instrument.",
        }
    if kind["state"] in {"OWNER_CHARACTERIZATION", "MIXED_CHARACTERIZATION"} and receipt:
        return {
            "state": "RETRACTED",
            "kind": kind["state"],
            "correction": receipt,
            "note": "characterization retracted to instrument/correction %s." % receipt,
        }
    return {
        "state": "NO_CHARACTERIZATION",
        "kind": kind["state"],
        "correction": receipt,
        "note": "no owner-character judgment on this row.",
    }


def row_complete(row):
    """A leftover row without X/Y/Z/correction cannot be acted on."""
    row = row or {}
    missing = [field for field in REQUIRED_FIELDS if not str(row.get(field) or "").strip()]
    if str(row.get("z") or "").strip() in {"0", "none", "absent", "no claim"}:
        missing.append("z_must_be_finder_failed")
    return {"complete": not missing, "missing": missing}


def measure_from_rows(facts):
    """Census from already-read facts. Missing facts stay named."""
    facts = facts or {}
    space = search_space(
        query=facts.get("query") or "",
        path=facts.get("path") or "",
        ref=facts.get("ref") or "",
    )
    calibration = calibrate(facts.get("finder_hits") or [], facts.get("known_present") or [])
    find = report_find(facts.get("finder_hits") or [], space, calibration.get("calibrated"))
    rows = list(facts.get("rows") or [])
    complete = [item for item in rows if row_complete(item).get("complete")]
    kinds = {str(item.get("id") or "").strip() for item in rows if item.get("id")}
    labels = uncertainty_labels(facts.get("uncertainty") or {})
    predicted = predicted_defect_state(
        bool(facts.get("predicted")),
        bool(facts.get("investigated")),
    )
    retract = retract_characterization(
        facts.get("sample_text") or "",
        facts.get("correction") or "",
    )
    bare_zero = any(item.get("count") == 0 for item in rows)
    return {
        "measured": True,
        "search_space_complete": space["complete"],
        "search_space": space,
        "calibrated": bool(calibration.get("calibrated")),
        "calibration_state": calibration.get("state"),
        "find_state": find.get("state"),
        "find_count": find.get("count"),
        "rows": len(rows),
        "complete_rows": len(complete),
        "kinds": sorted(kinds),
        "required_rows": list(REQUIRED_ROWS),
        "missing_rows": [name for name in REQUIRED_ROWS if name not in kinds],
        "uncertainty_state": labels.get("state"),
        "uncertainty_complete": bool(labels.get("complete")),
        "predicted_state": predicted.get("state"),
        "retract_state": retract.get("state"),
        "bare_zero": bare_zero,
        "never_print_zero": find.get("count") is None or find.get("state") != FINDER_FAILED,
        "source_id": facts.get("source_id") or SOURCE_ID,
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
        "titan_write": facts.get("titan") or "NOT_WRITTEN",
    }


def measure_tree(root, catalog_text=""):
    """Read the current tree and census the context-integrity leftover."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan_write": "NOT_WRITTEN",
        }
    instrument = _read(root, os.path.join("host", "context_integrity.py"))
    card = _exists(root, os.path.join("ground", "CONTEXT_INTEGRITY.md"))
    catalog_file = _exists(root, os.path.join("ground", "CONTEXT_INTEGRITY.json"))
    calibration_hit = probe(root, CALIBRATION_PATH)
    rows = []
    for item in catalog.get("rows") or []:
        row = dict(item)
        path = row.get("path") or ""
        if path:
            hit = probe(root, path)
            if hit.get("state") == "FOUND":
                row["y"] = "FOUND bytes=%s path=%s" % (hit.get("bytes"), path)
            else:
                row["y"] = hit.get("note") or FINDER_FAILED
            row["z"] = FINDER_FAILED
            row["count"] = hit.get("count")
            row["probe_state"] = hit.get("state")
        rows.append(row)
    known_present = [CALIBRATION_PATH] if calibration_hit.get("state") == "FOUND" else []
    finder_hits = [CALIBRATION_PATH] if calibration_hit.get("state") == "FOUND" else []
    if FINDER_FAILED in instrument:
        finder_hits.append(FINDER_FAILED)
        known_present.append(FINDER_FAILED)
    predicted_row = next((item for item in rows if item.get("id") == "predicted_defect"), {})
    retract_row = next((item for item in rows if item.get("id") == "characterization_retract"), {})
    facts = {
        "query": "CONTEXT INTEGRITY BOUNDARY retract characterization",
        "path": os.path.join("host", "context_integrity.py"),
        "ref": catalog.get("slack_ts") or SLACK_TS,
        "finder_hits": finder_hits,
        "known_present": known_present,
        "rows": rows,
        "source_id": catalog.get("source_id") or SOURCE_ID,
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "predicted": bool(predicted_row.get("predicted")),
        "investigated": bool(predicted_row.get("investigated")),
        "sample_text": (
            "defective finder false zeros framed as unflattering truths about "
            "the owner. missing-Z instrument failure. search space labeled."
        ),
        "correction": retract_row.get("correction") or "",
        "uncertainty": {
            "instrument": "host/context_integrity.py",
            "path": os.path.join("host", "context_integrity.py"),
            "query": "CONTEXT INTEGRITY BOUNDARY",
            "ref": catalog.get("slack_ts") or SLACK_TS,
            "calibration": CALIBRATION_PATH,
        },
    }
    row = measure_from_rows(facts)
    row["root"] = root
    row["instrument"] = bool(instrument)
    row["card"] = card
    row["catalog_file"] = catalog_file
    row["calibration_path"] = CALIBRATION_PATH
    row["calibration_bytes"] = calibration_hit.get("bytes")
    row["hands_off"] = catalog.get("hands_off") or []
    row["affected_rows"] = rows
    return row


def classify(row):
    """Leftover is INTEGRATED when four rows carry X/Y/Z and zeros stay unnamed."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "context-integrity catalog / tree listing not read. "
                "Absence was not stillness."
            ),
        }
    if not row.get("search_space_complete"):
        return {
            "state": "NOT_LANDED",
            "note": "search space incomplete. Every result must print query, path, and ref.",
        }
    if not row.get("calibrated"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "finder missed known-present or had no calibration. "
                "Every zero in this run is void."
            ),
        }
    if row.get("find_count") == 0 or row.get("bare_zero"):
        return {
            "state": "NOT_LANDED",
            "note": "miss branch printed 0. Report FINDER-FAILED, never 0.",
        }
    if not row.get("instrument") or not row.get("card") or not row.get("catalog_file"):
        return {
            "state": "NOT_LANDED",
            "note": "context-integrity leftover files missing. Boundary talk is CLAIMED.",
        }
    if int(row.get("complete_rows") or 0) < 4:
        return {
            "state": "NOT_LANDED",
            "note": (
                "RETRACT CHARACTERIZATION needs four rows with X/Y/Z/correction. "
                "Named %s complete."
                % (row.get("complete_rows") or 0)
            ),
        }
    if row.get("missing_rows"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "required leftover rows missing: %s."
                % ", ".join(row.get("missing_rows") or [])
            ),
        }
    if row.get("uncertainty_state") != "LABELED":
        return {
            "state": "NOT_LANDED",
            "note": "uncertainty is UNLABELED_DOUBT until instrument/path/query/ref/calibration are named.",
        }
    if row.get("predicted_state") == "OVERRIDE_UNINVESTIGATED":
        return {
            "state": "NOT_LANDED",
            "note": "reporter predicted the defect. Investigate that warning before override.",
        }
    if row.get("retract_state") == "OPEN_CHARACTERIZATION":
        return {
            "state": "NOT_LANDED",
            "note": "owner-character judgment is still open. Retract it to the instrument.",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "context-integrity leftover is on this tree. Miss branch is "
            "FINDER-FAILED, never 0. Characterization retracts to the instrument. "
            "A Slack boundary is still not the file."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the context-integrity leftover on current main"
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
    try:
        with open(args.catalog, encoding="utf-8") as handle:
            catalog_text = handle.read()
    except OSError as exc:
        payload = {
            "measured": False,
            "error": str(exc),
            "state": "UNMEASURED",
            "note": "catalog missing. Absence was not stillness.",
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    row = measure_tree(args.root, catalog_text)
    verdict = classify(row)
    payload = dict(row)
    payload.pop("affected_rows", None)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    space = search_space(
        query="CONTEXT INTEGRITY",
        path="host/context_integrity.py",
        ref=SLACK_TS,
    )
    assert space["complete"] is True
    incomplete = search_space(query="")
    assert incomplete["complete"] is False
    missed = calibrate([], ["ground/HEAD.md"])
    assert missed["calibrated"] is False
    assert missed["state"] == FINDER_FAILED
    ok = calibrate(["ground/HEAD.md"], ["ground/HEAD.md"])
    assert ok["calibrated"] is True
    silent = report_find([], space, True)
    assert silent["state"] == FINDER_FAILED
    assert silent["count"] is None
    found = report_find(["hit"], space, True)
    assert found["state"] == "FOUND"
    assert found["count"] == 1
    judgment = classify_text(
        "those false zeros are unflattering truths about the owner's intellect"
    )
    assert judgment["state"] == "OWNER_CHARACTERIZATION"
    technical = classify_text(
        "finder missed Z. FINDER-FAILED search space host/finder_zero.py calibration labeled"
    )
    assert technical["state"] == "TECHNICAL_DISAGREEMENT"
    unlabeled = uncertainty_labels({"instrument": "host/context_integrity.py"})
    assert unlabeled["state"] == "UNLABELED_DOUBT"
    labeled = uncertainty_labels(
        {
            "instrument": "host/context_integrity.py",
            "path": "host/context_integrity.py",
            "query": "CONTEXT INTEGRITY",
            "ref": SLACK_TS,
            "calibration": CALIBRATION_PATH,
        }
    )
    assert labeled["state"] == "LABELED"
    honored = predicted_defect_state(True, True)
    assert honored["state"] == "HONORED"
    skipped = predicted_defect_state(True, False)
    assert skipped["state"] == "OVERRIDE_UNINVESTIGATED"
    open_row = retract_characterization(
        "unflattering truths about the owner's motives",
        "",
    )
    assert open_row["state"] == "OPEN_CHARACTERIZATION"
    closed = retract_characterization(
        "unflattering truths about the owner's motives",
        "p/cairn-every-zero-i-printed-was-mine-20260820-06.md",
    )
    assert closed["state"] == "RETRACTED"
    live = measure_from_rows(
        {
            "query": "CONTEXT INTEGRITY",
            "path": "host/context_integrity.py",
            "ref": SLACK_TS,
            "finder_hits": [FINDER_FAILED],
            "known_present": [FINDER_FAILED],
            "predicted": True,
            "investigated": True,
            "sample_text": (
                "false zeros framed as unflattering truths. missing-Z "
                "instrument search space."
            ),
            "correction": "p/cairn-every-zero-i-printed-was-mine-20260820-06.md",
            "uncertainty": {
                "instrument": "host/context_integrity.py",
                "path": "host/context_integrity.py",
                "query": "CONTEXT INTEGRITY",
                "ref": SLACK_TS,
                "calibration": CALIBRATION_PATH,
            },
            "rows": [
                {
                    "id": name,
                    "kind": name,
                    "source_id": SOURCE_ID,
                    "x": "path",
                    "y": FINDER_FAILED,
                    "z": FINDER_FAILED,
                    "correction": "retract to instrument",
                }
                for name in REQUIRED_ROWS
            ],
        }
    )
    assert live["calibrated"] is True
    assert live["complete_rows"] == 4
    assert not live["missing_rows"]
    assert live["never_print_zero"] is True
    live["instrument"] = True
    live["card"] = True
    live["catalog_file"] = True
    verdict = classify(live)
    assert verdict["state"] == "INTEGRATED"
    assert "still not the file" in verdict["note"]
    zeroed = dict(live)
    zeroed["bare_zero"] = True
    assert classify(zeroed)["state"] == "NOT_LANDED"
    return True


if __name__ == "__main__":
    sys.exit(main())
