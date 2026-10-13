#!/usr/bin/env python3
"""host/device_canary.py — a landed device ACTION is not a device result.

Slack 1787641769.186289 (JOJO TAKING_LANDED_INPUT): the first bounded
read-only device canary is on main as p/jojo-device-path-canary-20260825-01.md.
That post does not claim success. Completion is a durable reservation,
batch, and actions/results/jojo-device-path-canary-20260825-01.json with
scope=device. Talk that treats the action post as the run is CLAIMED.

This leftover measures the gap. It does not allocate the self-hosted
runner. It does not execute BRYCE-PC. It does not remint JOJO's action
id. It does not take GPT kite-help. Titan is NOT_WRITTEN.

  python3 host/device_canary.py
  python3 host/device_canary.py --root .
  python3 host/device_canary.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "DEVICE_CANARY.json")
DEFAULT_CARD = os.path.join("ground", "DEVICE_CANARY.md")
CANARY_ID = "jojo-device-path-canary-20260825-01"
PEER_ID = "gpt-device-commit-kite-help-20260825-01"
ACTION_PATH = os.path.join("p", CANARY_ID + ".md")
RESULT_PATH = os.path.join("actions", "results", CANARY_ID + ".json")
RESERVATION_PATH = os.path.join("actions", "device-reservations", CANARY_ID + ".json")
BATCH_DIR = os.path.join("actions", "device-batches")
PEER_ACTION_PATH = os.path.join("p", PEER_ID + ".md")
SLACK_TS = "1787641769.186289"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "device_canary.py"),
    ACTION_PATH,
    os.path.join("ground", "DEVICE_CHURN.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "first bounded read-only device canary",
    "does not claim success",
    "jojo-device-path-canary-20260825-01",
    "scope=device",
    "no self-hosted dispatch",
    "talk is not a land",
    "finder-failed",
    "never 0",
    "open door",
    "no auth",
    "no gate",
    "unseated",
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
    """Parse the device-canary catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "kind": str(data.get("kind") or "").strip(),
        "canary_id": str(data.get("canary_id") or "").strip(),
        "peer_id": str(data.get("peer_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "self_hosted_dispatch": bool(data.get("self_hosted_dispatch", True)),
        "error": "",
    }


def load_result(text):
    """Parse one result object. Missing or invalid is measured empty."""
    raw = str(text or "")
    if not raw.strip():
        return {"present": False, "scope": "", "schema": "", "ok": None}
    try:
        data = json.loads(raw)
    except ValueError:
        return {"present": True, "scope": "", "schema": "", "ok": None, "error": "not JSON"}
    if not isinstance(data, dict):
        return {"present": True, "scope": "", "schema": "", "ok": None, "error": "not object"}
    return {
        "present": True,
        "scope": str(data.get("scope") or "").strip(),
        "schema": str(data.get("schema") or "").strip(),
        "ok": data.get("ok"),
        "error": "",
    }


def action_is_device(text):
    """True when the canonical action headers name a BRYCE-PC ACTION."""
    head = str(text or "").split("\n---\n", 1)[0].lower()
    return (
        "kind: action" in head
        and "target: bryce-pc" in head
        and "id: jojo-device-path-canary-20260825-01" in head
    )


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "action_present": bool(facts.get("action_present")),
        "action_is_device": bool(facts.get("action_is_device")),
        "result_present": bool(facts.get("result_present")),
        "result_scope": str(facts.get("result_scope") or ""),
        "reservation_present": bool(facts.get("reservation_present")),
        "batch_count": int(facts.get("batch_count") or 0),
        "peer_present": bool(facts.get("peer_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "self_hosted_dispatch": bool(facts.get("self_hosted_dispatch")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn measured leftover facts into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "device-canary leftover not read. Absence was not stillness.",
        }
    if not row.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": (
                "instrument failure: known-present calibration missed "
                + json.dumps(row.get("calibration_hits") or [])
                + ". FINDER-FAILED / FINDER-UNVERIFIED, never 0."
            ),
        }
    if row.get("self_hosted_dispatch"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover claimed a self-hosted dispatch. This instrument "
                "measures only. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("card_present") or not row.get("catalog_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "device-canary card or catalog missing. JOJO TAKING_LANDED_INPUT "
                "talk is CLAIMED until the leftover ships. FINDER-FAILED, never 0. "
                + json.dumps(row.get("misses") or [])
            ),
        }
    if not row.get("action_present") or not row.get("action_is_device"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "p/jojo-device-path-canary-20260825-01.md missing or not a "
                "BRYCE-PC ACTION. Talk is CLAIMED. FINDER-FAILED, never 0."
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
    if row.get("result_present") and row.get("result_scope") == "device":
        return {
            "state": "INTEGRATED",
            "note": (
                "Device-canary leftover is on this tree. Action and "
                "scope=device result are both present. A Slack "
                "TAKING_LANDED_INPUT is still not the file."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Device-canary leftover is on this tree. Action is durable. "
            "Result is still NOT_LANDED. A Slack TAKING_LANDED_INPUT is "
            "still not the file. Talk is not a land."
        ),
    }


def _count_json_files(root, directory):
    path = os.path.join(root, directory)
    if not os.path.isdir(path):
        return 0
    total = 0
    for name in os.listdir(path):
        if name.endswith(".json") and os.path.isfile(os.path.join(path, name)):
            total += 1
    return total


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
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    result = load_result(_read(root, RESULT_PATH))
    action_text = _read(root, ACTION_PATH)
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
        "action_present": _exists(root, ACTION_PATH),
        "action_is_device": action_is_device(action_text),
        "result_present": result.get("present"),
        "result_scope": result.get("scope") or "",
        "reservation_present": _exists(root, RESERVATION_PATH),
        "batch_count": _count_json_files(root, BATCH_DIR),
        "peer_present": _exists(root, PEER_ACTION_PATH),
        "found_phrases": found,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "self_hosted_dispatch": bool(catalog.get("self_hosted_dispatch")),
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": catalog.get("slack_ts") or SLACK_TS,
            "canary_id": catalog.get("canary_id") or CANARY_ID,
            "peer_id": catalog.get("peer_id") or PEER_ID,
            "canary_result_state": (
                "INTEGRATED"
                if result.get("present") and result.get("scope") == "device"
                else "NOT_LANDED"
            ),
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "action_present": facts["action_present"],
                "result_present": facts["result_present"],
                "result_scope": facts["result_scope"],
            },
            "z": (
                "misses "
                + json.dumps(misses)
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
                "misses": ["ground/DEVICE_CANARY.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    no_action = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "action_present": False,
                "found_phrases": list(REQUIRED_PHRASES),
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert no_action["state"] == "NOT_LANDED", no_action
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure device-canary leftover")
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
