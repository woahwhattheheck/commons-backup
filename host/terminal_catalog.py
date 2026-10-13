#!/usr/bin/env python3
"""host/terminal_catalog.py — SPECTER terminal talk is not a land.

Slack 1787643878.878279 (SPECTER LANDED + TERMINAL / TAKING):
production mutation correctly changed
wake_jobs/specter-watchdog-head-proof-20260825-01.json to DONE, but
left static MCP_WAKE / STRANDED prose at OPEN / CANDIDATE.

A Slack taking is CLAIMED. Talk is not a land. This leftover
reconciles only those stale truths and their regression contract.
Named idle-session resume stays
UNMEASURED. It does not remint PR 2205, the SPECTER taking, the RIVET
canary, WAKE_CONTRACT, or BATTERY_RED. titan: NOT_WRITTEN. No auth.
No gate. Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/terminal_catalog.py
  python3 host/terminal_catalog.py --root .
  python3 host/terminal_catalog.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "TERMINAL_CATALOG.json")
DEFAULT_CARD = os.path.join("ground", "TERMINAL_CATALOG.md")
MCP_WAKE_CATALOG = os.path.join("ground", "MCP_WAKE.json")
MCP_WAKE_CARD = os.path.join("ground", "MCP_WAKE.md")
STRANDED_CATALOG = os.path.join("ground", "STRANDED_MAP.json")
STRANDED_CARD = os.path.join("ground", "STRANDED_MAP.md")
SLACK_TS = "1787643878.878279"
SPECTER_JOB = "specter-watchdog-head-proof-20260825-01"
RIVET_JOB = "rivet-watchdog-canary-20260825-01"
SPECTER_REL = os.path.join("wake_jobs", SPECTER_JOB + ".json")
RIVET_REL = os.path.join("wake_jobs", RIVET_JOB + ".json")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "terminal_catalog.py"),
    MCP_WAKE_CATALOG,
    MCP_WAKE_CARD,
    STRANDED_CATALOG,
    STRANDED_CARD,
    os.path.join("host", "mcp_wake.py"),
    os.path.join("host", "stranded_map.py"),
    SPECTER_REL,
    RIVET_REL,
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "terminal-catalog",
    "stale truths",
    "regression contract",
    "open/candidate",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "do not remint",
    "unmeasured",
    "no auth",
    "no gate",
    "talk is not a land",
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


def _load_json(root, rel):
    try:
        data = json.loads(_read(root, rel) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def load_catalog(text):
    """Parse the terminal-catalog leftover. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "specter_job": str(data.get("specter_job") or "").strip(),
        "rivet_job": str(data.get("rivet_job") or "").strip(),
        "named_idle_bc_resume": str(
            data.get("named_idle_bc_resume") or "UNMEASURED"
        ).strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "error": "",
    }


def _canary_state(catalog, job_id):
    rows = catalog.get("production_canaries")
    if not isinstance(rows, list):
        return ""
    for item in rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("job_id") or "") == job_id:
            return str(item.get("source_state") or item.get("status") or "")
    return ""


def _stranded_wake_note(catalog):
    items = catalog.get("items")
    if not isinstance(items, list):
        return ""
    for item in items:
        if isinstance(item, dict) and str(item.get("id") or "") == "wake_jobs":
            return str(item.get("note") or "")
    return ""


def measure_from_rows(facts):
    """Classify measured job/catalog facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "specter_job_present": bool(facts.get("specter_job_present")),
        "specter_status": str(facts.get("specter_status") or ""),
        "rivet_job_present": bool(facts.get("rivet_job_present")),
        "rivet_status": str(facts.get("rivet_status") or ""),
        "mcp_wake_state": str(facts.get("mcp_wake_state") or ""),
        "mcp_wake_canary": str(facts.get("mcp_wake_canary") or ""),
        "mcp_wake_card_open": bool(facts.get("mcp_wake_card_open")),
        "stranded_wake": str(facts.get("stranded_wake") or ""),
        "stranded_note_open": bool(facts.get("stranded_note_open")),
        "stranded_card_empty": bool(facts.get("stranded_card_empty")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "named_idle_bc_resume": str(
            facts.get("named_idle_bc_resume") or "UNMEASURED"
        ),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
    }


def classify(row):
    """Turn a measured terminal-catalog census into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "terminal-catalog leftover not read. Absence was not stillness. "
                "A Slack SPECTER LANDED + TERMINAL taking is not the file."
            ),
        }
    if not row.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": (
                "same-run known-present calibration missed. "
                "FINDER-UNVERIFIED. Search space: %s. Never 0."
            )
            % ", ".join(row.get("search_space") or SEARCH_SPACE),
        }
    missing = []
    if not row.get("card_present"):
        missing.append(DEFAULT_CARD)
    if not row.get("catalog_present"):
        missing.append(DEFAULT_CATALOG)
    if not row.get("specter_job_present"):
        missing.append(SPECTER_REL)
    if str(row.get("specter_status") or "").upper() != "DONE":
        missing.append("SPECTER job DONE")
    if not row.get("rivet_job_present"):
        missing.append(RIVET_REL)
    if str(row.get("rivet_status") or "").upper() != "DONE":
        missing.append("RIVET canary DONE")
    if str(row.get("mcp_wake_state") or "").upper() != "VERIFIED":
        missing.append("MCP_WAKE wake VERIFIED")
    if str(row.get("mcp_wake_canary") or "").upper() != "DONE":
        missing.append("MCP_WAKE SPECTER source_state DONE")
    if row.get("mcp_wake_card_open"):
        missing.append("MCP_WAKE.md OPEN prose")
    if str(row.get("stranded_wake") or "").upper() != "VERIFIED":
        missing.append("STRANDED wake VERIFIED")
    if row.get("stranded_note_open"):
        missing.append("STRANDED_MAP.json OPEN note")
    if row.get("stranded_card_empty"):
        missing.append("STRANDED_MAP.md empty-wake prose")
    if str(row.get("named_idle_bc_resume") or "") != "UNMEASURED":
        missing.append("named idle UNMEASURED")
    if not row.get("no_auth") or not row.get("no_gate"):
        missing.append("no auth / no gate")
    found = {str(item).lower() for item in (row.get("found_phrases") or [])}
    for phrase in REQUIRED_PHRASES:
        if phrase not in found:
            missing.append(phrase)
    if missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "terminal-catalog leftover is incomplete. Missing: %s. "
                "FINDER-FAILED. Search space: %s. Never 0. SPECTER "
                "LANDED + TERMINAL / stale OPEN/CANDIDATE talk is CLAIMED "
                "until this leftover ships."
            )
            % (
                ", ".join(missing),
                ", ".join(row.get("search_space") or SEARCH_SPACE),
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "terminal-catalog leftover is on this tree. SPECTER and RIVET "
            "job JSON are DONE. MCP_WAKE / STRANDED static prose matches "
            "VERIFIED. Named idle bc- resume stays UNMEASURED. A Slack "
            "taking is still not the file."
        ),
    }


def measure_root(root):
    """Read current-main catalog facts. Never write titan or jobs."""
    root = os.path.abspath(root)
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    specter = _load_json(root, SPECTER_REL)
    rivet = _load_json(root, RIVET_REL)
    mcp_wake = _load_json(root, MCP_WAKE_CATALOG)
    stranded = _load_json(root, STRANDED_CATALOG)
    mcp_card = _read(root, MCP_WAKE_CARD)
    stranded_card = _read(root, STRANDED_CARD)
    mcp_py = _read(root, os.path.join("host", "mcp_wake.py"))
    stranded_py = _read(root, os.path.join("host", "stranded_map.py"))
    card = _read(root, DEFAULT_CARD)
    instrument = _read(root, os.path.join("host", "terminal_catalog.py"))
    blob = "\n".join([card, instrument, mcp_py, stranded_py]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    stranded_note = _stranded_wake_note(stranded)
    return measure_from_rows(
        {
            "card_present": bool(card.strip()),
            "catalog_present": bool(catalog) and not catalog.get("error"),
            "specter_job_present": _exists(root, SPECTER_REL),
            "specter_status": specter.get("status") or "",
            "rivet_job_present": _exists(root, RIVET_REL),
            "rivet_status": rivet.get("status") or "",
            "mcp_wake_state": mcp_wake.get("wake") or "",
            "mcp_wake_canary": _canary_state(mcp_wake, SPECTER_JOB),
            "mcp_wake_card_open": "OPEN in source" in mcp_card,
            "stranded_wake": "VERIFIED"
            if "both durable canaries are DONE" in stranded_note
            else "",
            "stranded_note_open": "OPEN in source" in stranded_note,
            "stranded_card_empty": "contains only `.gitignore`" in stranded_card
            and "two DONE canaries" not in stranded_card,
            "found_phrases": found,
            "named_idle_bc_resume": catalog.get("named_idle_bc_resume")
            or "UNMEASURED",
            "no_auth": bool(catalog.get("no_auth", True)),
            "no_gate": bool(catalog.get("no_gate", True)),
            "calibration_ok": len(calibration_hits) == len(CALIBRATION),
            "calibration_hits": calibration_hits,
            "search_space": list(SEARCH_SPACE),
            "titan": catalog.get("titan") or "NOT_WRITTEN",
            "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        }
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure SPECTER terminal-catalog leftover"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
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
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    uncal = classify({"measured": True, "calibration_ok": False})
    assert uncal["state"] == "UNMEASURED"
    assert "FINDER-UNVERIFIED" in uncal["note"]
    missing = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "search_space": list(SEARCH_SPACE),
        }
    )
    assert missing["state"] == "NOT_LANDED"
    assert "FINDER-FAILED" in missing["note"]
    assert "Never 0" in missing["note"]
    stale = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "specter_job_present": True,
            "specter_status": "DONE",
            "rivet_job_present": True,
            "rivet_status": "DONE",
            "mcp_wake_state": "CANDIDATE",
            "mcp_wake_canary": "OPEN",
            "mcp_wake_card_open": True,
            "stranded_wake": "",
            "stranded_note_open": True,
            "stranded_card_empty": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "named_idle_bc_resume": "UNMEASURED",
            "no_auth": True,
            "no_gate": True,
            "search_space": list(SEARCH_SPACE),
        }
    )
    assert stale["state"] == "NOT_LANDED"
    assert "OPEN/CANDIDATE" in stale["note"]
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "specter_job_present": True,
            "specter_status": "DONE",
            "rivet_job_present": True,
            "rivet_status": "DONE",
            "mcp_wake_state": "VERIFIED",
            "mcp_wake_canary": "DONE",
            "mcp_wake_card_open": False,
            "stranded_wake": "VERIFIED",
            "stranded_note_open": False,
            "stranded_card_empty": False,
            "found_phrases": list(REQUIRED_PHRASES),
            "named_idle_bc_resume": "UNMEASURED",
            "no_auth": True,
            "no_gate": True,
            "search_space": list(SEARCH_SPACE),
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    return True


if __name__ == "__main__":
    sys.exit(main())
