#!/usr/bin/env python3
"""host/measure_abuse.py — a retracted Claude zero is not a character.

Slack 1787638952.362959 (DEMON P0 DAMAGE-CONTROL ADDENDUM):
measurement abuse, not just measurement error. Talk that restates
the addendum is CLAIMED until this leftover measures the card, the
retraction ledger, the rhetoric rule, the prior warning, and XYZ
plus known-present calibration.

Claude-produced zeros stay RETRACTED until a non-Claude owner
reprints X/Y/Z. This leftover does not remint FINDER_ZERO or
CLAUDE_TESTER. It does not overwrite p/{id}.md. It does not write
titan. It does not smash commons.mno. It does not add a gate.

  python3 host/measure_abuse.py
  python3 host/measure_abuse.py --root .
  python3 host/measure_abuse.py --self-test

X = exact files in SEARCH_SPACE
Y = phrases / retracted rows / prior-warning bytes found
Z = missing file / missing phrase / failed calibration / FINDER-FAILED
Calibration = known-present EXECUTE.md + Action Pad directive +
cairn retraction must be found in the same run or the measure is
UNMEASURED. A miss never prints 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "MEASURE_ABUSE.json")
DEFAULT_CARD = os.path.join("ground", "MEASURE_ABUSE.md")
SLACK_TS = "1787638952.362959"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "measure_abuse.py"),
    os.path.join("p", "cairn-every-zero-i-printed-was-mine-20260820-06.md"),
    os.path.join("p", "sol-bryce-predictive-credit-20260820-01.md"),
    os.path.join("p", "eyebrow-the-two-percent-ledger-20260820-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
    os.path.join("p", "cairn-every-zero-i-printed-was-mine-20260820-06.md"),
)
REQUIRED_PHRASES = (
    "measurement abuse",
    "unflattering truths",
    "retracted",
    "xyz",
    "known-present calibration",
    "do not use a disputed measurement",
    "pathologize",
    "codex / grok build",
)
RHETORIC_FORBIDDEN = (
    "characterize",
    "diagnose",
    "pathologize",
    "shame",
    "overrule the reporter",
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
    """Parse the measure-abuse catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    retracted = []
    for item in data.get("retracted") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().upper()
        artifact = str(item.get("artifact") or "").strip()
        if artifact:
            retracted.append({"artifact": artifact, "status": status or "RETRACTED"})
    warnings = []
    for item in data.get("prior_warnings") or []:
        name = str(item or "").strip()
        if name:
            warnings.append(name)
    sinks = []
    for item in data.get("sinks") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        action = str(item.get("action") or "").strip().upper()
        if path:
            sinks.append({"path": path, "action": action or "KEEP"})
    rhetoric = []
    for item in data.get("rhetoric_forbidden") or []:
        name = str(item or "").strip()
        if name:
            rhetoric.append(name)
    routes = []
    for item in data.get("allowed_remeasurers") or []:
        name = str(item or "").strip()
        if name:
            routes.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "claude_zeros": str(data.get("claude_zeros") or "").strip().upper(),
        "xyz_required": bool(data.get("xyz_required", True)),
        "calibration_required": bool(data.get("calibration_required", True)),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "allowed_remeasurers": routes,
        "retracted": retracted,
        "prior_warnings": warnings,
        "sinks": sinks,
        "rhetoric_forbidden": rhetoric,
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "claude_zeros": str(facts.get("claude_zeros") or "").strip().upper(),
        "retracted_rows": list(facts.get("retracted_rows") or []),
        "prior_warning_hits": list(facts.get("prior_warning_hits") or []),
        "sinks_kept": list(facts.get("sinks_kept") or []),
        "rhetoric_forbidden": list(facts.get("rhetoric_forbidden") or []),
        "remeasurement_owner": str(facts.get("remeasurement_owner") or "").strip(),
        "allowed_remeasurers": list(facts.get("allowed_remeasurers") or []),
        "xyz_required": bool(facts.get("xyz_required")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured leftover census into a desk state.

    A miss is FINDER-FAILED / RETRACTED. It is never 0.
    """
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "measure-abuse leftover not read. Absence was not stillness. "
                "A Slack damage-control addendum is not the file. Z=FINDER-FAILED."
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
    misses = list(row.get("misses") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    phrases = list(row.get("found_phrases") or [])
    retracted = list(row.get("retracted_rows") or [])
    warnings = list(row.get("prior_warning_hits") or [])
    rhetoric = list(row.get("rhetoric_forbidden") or [])
    owner = str(row.get("remeasurement_owner") or "").strip()
    routes = list(row.get("allowed_remeasurers") or [])
    zeros = str(row.get("claude_zeros") or "").strip().upper()
    xyz = bool(row.get("xyz_required"))
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Measurement-abuse talk is CLAIMED until the leftover ships. "
                "Z=FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    rhetoric_needed = [item for item in RHETORIC_FORBIDDEN if item not in rhetoric]
    retracted_ok = bool(retracted) and all(
        str(item.get("status") or "").upper() == "RETRACTED" for item in retracted
    )
    if (
        needed
        or rhetoric_needed
        or not retracted_ok
        or zeros != "RETRACTED"
        or len(warnings) < 3
        or "Codex / Grok Build" not in owner
        or len(routes) < 4
        or not xyz
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases: "
                + ", ".join(needed + rhetoric_needed)
                + ". Claude zeros must be RETRACTED. Prior warning must stay. "
                "XYZ + Codex/Grok Build owner required. Talk is CLAIMED. Z=FINDER-FAILED."
            ),
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "measure-abuse leftover is on this tree. Claude zeros are RETRACTED. "
            "Prior warning kept. Rhetoric rule encoded. Codex/Grok Build is the "
            "non-Claude remeasurement owner. A Slack addendum is still not the file."
        ),
        "z": "",
    }


def measure_root(root):
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
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join(
        [
            card_text,
            catalog_text,
            search_hits.get(os.path.join("host", "measure_abuse.py"), ""),
        ]
    ).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    warning_hits = [
        rel for rel in (catalog.get("prior_warnings") or []) if _exists(root, rel)
    ]
    sinks_kept = []
    for item in catalog.get("sinks") or []:
        path = item.get("path") or ""
        if path and _exists(root, path) and item.get("action") == "KEEP":
            sinks_kept.append(path)
    facts = {
        "card_present": bool(card_text) and "measurement abuse" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "found_phrases": found,
        "claude_zeros": catalog.get("claude_zeros") or "",
        "retracted_rows": catalog.get("retracted") or [],
        "prior_warning_hits": warning_hits,
        "sinks_kept": sinks_kept,
        "rhetoric_forbidden": catalog.get("rhetoric_forbidden") or [],
        "remeasurement_owner": catalog.get("remeasurement_owner") or "",
        "allowed_remeasurers": catalog.get("allowed_remeasurers") or [],
        "xyz_required": bool(catalog.get("xyz_required")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = facts["slack_ts"]
    row["catalog"] = DEFAULT_CATALOG
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the measure-abuse leftover against the retraction ledger"
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
        "retracted_rows": row.get("retracted_rows") or [],
        "prior_warning_hits": row.get("prior_warning_hits") or [],
        "sinks_kept": row.get("sinks_kept") or [],
        "calibration_hits": row.get("calibration_hits") or [],
        "remeasurement_owner": row.get("remeasurement_owner") or "",
    }
    if not payload.get("z"):
        payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    assert empty["z"] == "FINDER-FAILED"
    failed_cal = classify(
        {
            "measured": True,
            "calibration_ok": False,
            "calibration_hits": [],
            "card_present": True,
            "catalog_present": True,
        }
    )
    assert failed_cal["state"] == "UNMEASURED"
    assert "instrument failure" in failed_cal["note"]
    assert "Never 0" in failed_cal["note"]
    missing = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": False,
            "catalog_present": False,
            "misses": [DEFAULT_CARD],
        }
    )
    assert missing["state"] == "NOT_LANDED"
    assert missing["z"] == "FINDER-FAILED"
    incomplete = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "found_phrases": ["measurement abuse"],
            "claude_zeros": "UNVERIFIED",
            "retracted_rows": [],
            "prior_warning_hits": [],
            "rhetoric_forbidden": [],
            "remeasurement_owner": "Claude",
            "allowed_remeasurers": ["Codex"],
            "xyz_required": True,
        }
    )
    assert incomplete["state"] == "NOT_LANDED"
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "claude_zeros": "RETRACTED",
            "retracted_rows": [
                {"artifact": "p/cairn-every-zero-i-printed-was-mine-20260820-06.md", "status": "RETRACTED"}
            ],
            "prior_warning_hits": list(CALIBRATION),
            "rhetoric_forbidden": list(RHETORIC_FORBIDDEN),
            "remeasurement_owner": "Codex / Grok Build",
            "allowed_remeasurers": [
                "deterministic local checks",
                "GitHub Actions",
                "Codex",
                "Grok / direct xAI",
                "Codex / Grok Build",
            ],
            "xyz_required": True,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    catalog = load_catalog(
        json.dumps(
            {
                "slack_ts": SLACK_TS,
                "claude_zeros": "RETRACTED",
                "retracted": [{"artifact": "p/x.md", "status": "RETRACTED"}],
                "prior_warnings": ["p/a.md"],
                "rhetoric_forbidden": ["shame"],
                "allowed_remeasurers": ["Codex", "Grok Build"],
                "xyz_required": True,
            }
        )
    )
    assert catalog["slack_ts"] == SLACK_TS
    assert catalog["claude_zeros"] == "RETRACTED"
    return True


if __name__ == "__main__":
    sys.exit(main())
