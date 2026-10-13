#!/usr/bin/env python3
"""host/claude_zero_damage.py — a Slack taking is not a land.

Slack 1787639239.069069 (DEMON TAKING / CLAUDE ZERO DAMAGE-CONTROL
DURABLE LEDGER): append-only incident record, retract frozen KEYB
and absence-derived Titan/KITE conclusions, refuse Claude
review/test authority, name technical + rhetorical consumers.

Talk that restates the taking is CLAIMED until this leftover is on
current main. Miss is FINDER-FAILED, never 0. Originals stay.
Do not remint IMPACT_LEDGER / CLAUDE_TESTER / STALE_MANIFEST.

  python3 host/claude_zero_damage.py
  python3 host/claude_zero_damage.py --root .
  python3 host/claude_zero_damage.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CLAUDE_ZERO_DAMAGE.json")
SLACK_TS = "1787639239.069069"
SOURCE_ID = "demon-claude-zero-damage-control-20260825"
FINDER_FAILED = "FINDER-FAILED"
CALIBRATION_PATH = os.path.join("ground", "HEAD.md")
WORKING_CATALOG = os.path.join("ground", "WORKING_BUILDS.json")
RESOURCE_CATALOG = os.path.join("ground", "RESOURCE_LEDGER.json")
STALE_SHA = (
    "a63396b59b0fb9f0ce1366d112c2abd209475aecde2d458f82f9999667f1521e"
)
TESTER_NEEDLES = (
    "tester",
    "verifier",
    "review authority",
    "final-qa",
    "final qa",
    "red-team-as-verdict",
)
REQUIRED_INCIDENT_FIELDS = ("id", "x", "y", "z", "consumer", "repair")
REQUIRED_RETRACT_FIELDS = ("id", "original_path", "original_value", "retraction")
REQUIRED_INCIDENT_IDS = (
    "keyb-stale-sha-frozen",
    "titan-kite-absence-superseded",
    "resource-ledger-claude-authority",
    "land-desk-working-builds-copy",
    "impact-ledger-seven-consumers",
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


def search_space():
    """Z prints the full search space. A miss is never 0."""
    return {
        "catalog": DEFAULT_CATALOG,
        "working": WORKING_CATALOG,
        "resource": RESOURCE_CATALOG,
        "calibration": CALIBRATION_PATH,
        "slack_ts": SLACK_TS,
        "z": FINDER_FAILED,
    }


def calibrate(root):
    """Same-run known-present calibration. Miss voids every zero."""
    body = _read(root, CALIBRATION_PATH)
    size = _size(root, CALIBRATION_PATH)
    if body and size:
        first = body.splitlines()[0] if body.splitlines() else ""
        return {
            "x": CALIBRATION_PATH,
            "y": first,
            "z": FINDER_FAILED,
            "ok": True,
            "bytes": size,
        }
    return {
        "x": CALIBRATION_PATH,
        "y": FINDER_FAILED,
        "z": FINDER_FAILED,
        "ok": False,
        "bytes": size,
        "search_space": search_space(),
    }


def load_catalog(text):
    """Parse the incident catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    incidents = []
    for item in data.get("incidents") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("id") or "").strip()
        if not name:
            continue
        row = {"id": name}
        for field in REQUIRED_INCIDENT_FIELDS:
            if field == "id":
                continue
            row[field] = str(item.get(field) or "").strip()
        row["lane"] = str(item.get("lane") or "").strip()
        incidents.append(row)
    retracted = []
    for item in data.get("retracted") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("id") or "").strip()
        if not name:
            continue
        row = {"id": name}
        for field in REQUIRED_RETRACT_FIELDS:
            if field == "id":
                continue
            row[field] = str(item.get(field) or "").strip()
        row["keep_original"] = bool(item.get("keep_original", True))
        retracted.append(row)
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "never_print_zero": bool(data.get("never_print_zero", True)),
        "preserve_originals": bool(data.get("preserve_originals", True)),
        "incidents": incidents,
        "retracted": retracted,
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
    }


def load_json(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _artifact(data, name):
    for item in data.get("artifacts") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == name:
            return item
    return {}


def _claude_row(data):
    for item in data.get("surfaces") or []:
        if isinstance(item, dict) and str(item.get("name") or "").lower() == "claude":
            return item
    return {}


def claude_tester_authority(backlog):
    body = str(backlog or "").lower()
    return any(needle in body for needle in TESTER_NEEDLES) and (
        "informational" not in body
    )


def measure_from_rows(facts):
    """Census from already-read filesystem facts. Missing facts stay named."""
    facts = facts or {}
    calibration = facts.get("calibration") or {}
    incidents = list(facts.get("incidents") or [])
    retracted = list(facts.get("retracted") or [])
    keyb = facts.get("keyb") or {}
    titan = facts.get("titan") or {}
    claude = facts.get("claude") or {}
    keyb_sha = str(keyb.get("container_sha256") or keyb.get("canonical_sha256") or "")
    keyb_hash_state = str(keyb.get("hash_state") or "").upper()
    keyb_stale = keyb_hash_state == "STALE" or bool(keyb.get("stale"))
    titan_disp = str(titan.get("disposition") or "").upper()
    titan_original = str(titan.get("original_disposition") or "").upper()
    titan_unreconciled = titan_disp == "UNRECONCILED"
    claude_backlog = str(claude.get("assigned_backlog") or "")
    tester = claude_tester_authority(claude_backlog)
    missing_incident_fields = any(
        not row.get(field)
        for row in incidents
        for field in REQUIRED_INCIDENT_FIELDS
    )
    missing_ids = [
        name for name in REQUIRED_INCIDENT_IDS
        if name not in {row.get("id") for row in incidents}
    ]
    retracted_ids = {row.get("id") for row in retracted}
    return {
        "measured": True,
        "calibration_ok": bool(calibration.get("ok")),
        "calibration_y": str(calibration.get("y") or ""),
        "never_print_zero": bool(facts.get("never_print_zero", True)),
        "preserve_originals": bool(facts.get("preserve_originals", True)),
        "incident_count": len(incidents),
        "retracted_count": len(retracted),
        "missing_incident_fields": missing_incident_fields,
        "missing_ids": missing_ids,
        "keyb_sha256": keyb_sha,
        "keyb_stale": keyb_stale,
        "keyb_verified": bool(keyb.get("verified")),
        "titan_disposition": titan_disp,
        "titan_original_disposition": titan_original,
        "titan_unreconciled": titan_unreconciled,
        "claude_tester_authority": tester,
        "claude_backlog": claude_backlog,
        "keyb_retracted": "keyb-verified-sha-a63396" in retracted_ids,
        "titan_retracted": "titan-superseded-from-absence" in retracted_ids,
        "titan_write": facts.get("titan_write") or "NOT_WRITTEN",
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
        "source_id": facts.get("source_id") or SOURCE_ID,
        "search_space": search_space(),
        "z": FINDER_FAILED,
    }


def measure_tree(root, catalog_text=""):
    """Read the current tree and census the damage-control leftover."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "y": FINDER_FAILED,
            "z": FINDER_FAILED,
            "search_space": search_space(),
            "titan_write": "NOT_WRITTEN",
        }
    working = load_json(_read(root, WORKING_CATALOG))
    resource = load_json(_read(root, RESOURCE_CATALOG))
    facts = {
        "calibration": calibrate(root),
        "incidents": catalog.get("incidents") or [],
        "retracted": catalog.get("retracted") or [],
        "never_print_zero": catalog.get("never_print_zero", True),
        "preserve_originals": catalog.get("preserve_originals", True),
        "keyb": _artifact(working, "keyb"),
        "titan": _artifact(working, "titan_census"),
        "claude": _claude_row(resource),
        "titan_write": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "source_id": catalog.get("source_id") or SOURCE_ID,
    }
    row = measure_from_rows(facts)
    row["root"] = root
    row["working_present"] = _exists(root, WORKING_CATALOG)
    row["resource_present"] = _exists(root, RESOURCE_CATALOG)
    row["calibration_path"] = CALIBRATION_PATH
    return row


def classify(row):
    """The leftover is INTEGRATED when retractions and X/Y/Z are named."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "claude-zero-damage catalog / tree listing not read. "
                "Absence was not stillness."
            ),
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
    if not row.get("never_print_zero"):
        return {
            "state": "NOT_LANDED",
            "note": "never_print_zero is off. A miss must print FINDER-FAILED, never 0.",
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
    if not row.get("preserve_originals"):
        return {
            "state": "NOT_LANDED",
            "note": "preserve_originals is off. Do not overwrite history.",
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
    if not row.get("calibration_ok"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "known-present calibration missed %s. %s. Search space: %s"
                % (CALIBRATION_PATH, FINDER_FAILED, json.dumps(search_space()))
            ),
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
    if row.get("missing_ids") or row.get("missing_incident_fields"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "incident record is incomplete. Missing ids %s. "
                "Every incident needs X/Y/Z/consumer/repair. %s."
                % (row.get("missing_ids") or [], FINDER_FAILED)
            ),
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
    if row.get("claude_tester_authority"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "RESOURCE_LEDGER Claude row still assigns tester/verifier/"
                "review authority. Informational only. %s."
                % FINDER_FAILED
            ),
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
    if row.get("keyb_verified") or not row.get("keyb_stale") or not row.get("keyb_retracted"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "KEYB SHA a63396 is still frozen as verified. "
                "Retract it as STALE / NOT_VERIFIED. %s."
                % FINDER_FAILED
            ),
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
    if (
        row.get("titan_disposition") == "SUPERSEDED"
        or not row.get("titan_unreconciled")
        or not row.get("titan_retracted")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "Titan/KITE SUPERSEDED-from-absence is still frozen. "
                "Absence is %s, disposition UNRECONCILED."
                % FINDER_FAILED
            ),
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "claude-zero-damage leftover is on this tree. KEYB a63396 is "
            "STALE / NOT_VERIFIED. Titan SUPERSEDED-from-absence is retracted "
            "to UNRECONCILED. Claude tester authority refused. Originals "
            "preserved. Miss is FINDER-FAILED, never 0. A Slack taking is "
            "still not the file."
        ),
        "z": FINDER_FAILED,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Append-only Claude zero damage-control ledger"
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
            "y": FINDER_FAILED,
            "z": FINDER_FAILED,
            "search_space": search_space(),
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    row = measure_tree(args.root, catalog_text)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert empty["z"] == FINDER_FAILED
    live = measure_from_rows(
        {
            "calibration": {"ok": True, "y": "# A bake is not the board"},
            "never_print_zero": True,
            "preserve_originals": True,
            "incidents": [
                {
                    "id": name,
                    "x": "path",
                    "y": "bytes",
                    "z": FINDER_FAILED,
                    "consumer": "file",
                    "repair": "retract",
                }
                for name in REQUIRED_INCIDENT_IDS
            ],
            "retracted": [
                {"id": "keyb-verified-sha-a63396"},
                {"id": "titan-superseded-from-absence"},
            ],
            "keyb": {
                "container_sha256": STALE_SHA,
                "hash_state": "STALE",
                "verified": False,
            },
            "titan": {
                "disposition": "UNRECONCILED",
                "original_disposition": "SUPERSEDED",
            },
            "claude": {
                "assigned_backlog": "informational evidence only; not tester"
            },
        }
    )
    assert live["keyb_stale"] is True
    assert live["titan_unreconciled"] is True
    assert live["claude_tester_authority"] is False
    assert classify(live)["state"] == "INTEGRATED"
    frozen = dict(live)
    frozen["titan_disposition"] = "SUPERSEDED"
    frozen["titan_unreconciled"] = False
    assert classify(frozen)["state"] == "NOT_LANDED"
    tester = dict(live)
    tester["claude_tester_authority"] = True
    assert classify(tester)["state"] == "NOT_LANDED"
    return True


if __name__ == "__main__":
    sys.exit(main())
