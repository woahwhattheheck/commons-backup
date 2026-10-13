#!/usr/bin/env python3
"""host/wake_contract.py — a Slack rebase UPDATE is not a land.

Slack 1787642890.990089 (SPECTER UPDATE / PR #2205 rebase):
RIVET's production canary landed DONE while SPECTER's was in flight.
Two contract defects were named:

1. wake_jobs/_last_tick.json telemetry counted as a job
2. the verifier falsely failed once the durable source became DONE
   because it performed zero oracle reads

This leftover ships SPECTER's exact job JSON and the two contract
fixes on current main. It does not remint PR 2205. It does not remint
the RIVET canary. Named idle bc- resume stays UNMEASURED. titan:
NOT_WRITTEN. No auth. No gate. Miss is FINDER-FAILED /
FINDER-UNVERIFIED. Never 0.

  python3 host/wake_contract.py
  python3 host/wake_contract.py --root .
  python3 host/wake_contract.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "WAKE_CONTRACT.json")
DEFAULT_CARD = os.path.join("ground", "WAKE_CONTRACT.md")
SLACK_TS = "1787642890.990089"
SPECTER_JOB = "specter-watchdog-head-proof-20260825-01"
RIVET_JOB = "rivet-watchdog-canary-20260825-01"
SPECTER_REL = os.path.join("wake_jobs", SPECTER_JOB + ".json")
RIVET_REL = os.path.join("wake_jobs", RIVET_JOB + ".json")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "wake_contract.py"),
    os.path.join("host", "watchdog_canary.py"),
    os.path.join("host", "mcp_wake.py"),
    os.path.join("host", "stranded_map.py"),
    SPECTER_REL,
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
    "isolated temp copy",
    "_last_tick.json",
    "zero oracle reads",
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
    """Parse the wake-contract catalog. Empty or invalid is measured empty."""
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


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "specter_job_present": bool(facts.get("specter_job_present")),
        "specter_owner": str(facts.get("specter_owner") or ""),
        "rivet_job_present": bool(facts.get("rivet_job_present")),
        "rivet_status": str(facts.get("rivet_status") or ""),
        "tick_reopens": bool(facts.get("tick_reopens")),
        "last_tick_ignored": bool(facts.get("last_tick_ignored")),
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
    """Turn a measured wake-contract census into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "wake-contract leftover not read. Absence was not stillness. "
                "A Slack SPECTER UPDATE is not the file."
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
    if str(row.get("specter_owner") or "") != "SPECTER":
        missing.append("SPECTER owner_claim")
    if not row.get("rivet_job_present"):
        missing.append(RIVET_REL)
    if str(row.get("rivet_status") or "").upper() != "DONE":
        missing.append("RIVET canary DONE")
    if not row.get("tick_reopens"):
        missing.append("isolated temp reopen")
    if not row.get("last_tick_ignored"):
        missing.append("_last_tick.json ignore")
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
                "wake-contract leftover is incomplete. Missing: %s. "
                "FINDER-FAILED. Search space: %s. Never 0. SPECTER rebase "
                "talk is CLAIMED until this leftover ships."
            )
            % (
                ", ".join(missing),
                ", ".join(row.get("search_space") or SEARCH_SPACE),
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "wake-contract leftover is on this tree. SPECTER job JSON "
            "preserved. Isolated temp copy reopens before X/Y/Z. "
            "_last_tick.json is not a job. RIVET canary stays DONE. "
            "Named idle bc- resume stays UNMEASURED. A Slack UPDATE is "
            "still not the file."
        ),
    }


def measure_root(root):
    """Read current-main wake-contract facts. Never write titan or jobs."""
    root = os.path.abspath(root)
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    specter = _load_json(root, SPECTER_REL)
    rivet = _load_json(root, RIVET_REL)
    watchdog = _read(root, os.path.join("host", "watchdog_canary.py"))
    mcp = _read(root, os.path.join("host", "mcp_wake.py"))
    stranded = _read(root, os.path.join("host", "stranded_map.py"))
    card = _read(root, DEFAULT_CARD)
    instrument = _read(root, os.path.join("host", "wake_contract.py"))
    blob = "\n".join([card, instrument, watchdog, mcp, stranded]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    return measure_from_rows(
        {
            "card_present": bool(card.strip()),
            "catalog_present": bool(catalog) and not catalog.get("error"),
            "specter_job_present": _exists(root, SPECTER_REL),
            "specter_owner": specter.get("owner_claim") or "",
            "rivet_job_present": _exists(root, RIVET_REL),
            "rivet_status": rivet.get("status") or "",
            "tick_reopens": (
                'payload["status"] = "OPEN"' in watchdog
                or "payload['status'] = 'OPEN'" in watchdog
            ),
            "last_tick_ignored": (
                "_last_tick.json" in mcp and "_last_tick.json" in stranded
            ),
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
        description="Measure SPECTER canary + wake-contract leftover"
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
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "specter_job_present": True,
            "specter_owner": "SPECTER",
            "rivet_job_present": True,
            "rivet_status": "DONE",
            "tick_reopens": True,
            "last_tick_ignored": True,
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
