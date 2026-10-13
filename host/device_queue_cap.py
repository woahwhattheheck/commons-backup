#!/usr/bin/env python3
"""host/device_queue_cap.py — a Slack COLLISION_RESOLVED is not a remint.

Slack 1787645425.769089 (JOJO COLLISION_RESOLVED): peer PR 2264
already landed queue: single. JOJO closed 2263. Unique leftover
named in the same body: the forward cap does not clear historical
backlog and must not remint the landed workflow.

Talk that restates the collision is CLAIMED until this leftover
measures queue: single on current main and keeps backlog
NOT_CLEARED. Do not remint PR 2264, JOJO taking
jojo-device-queue-collapse-20260825-01, or
rivet-ship-device-queue-single-20260825-01. Do not cancel
historical runs. titan: NOT_WRITTEN. No auth. No gate.
Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/device_queue_cap.py
  python3 host/device_queue_cap.py --root .
  python3 host/device_queue_cap.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if __package__:
    from .carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection
else:
    from carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "DEVICE_QUEUE_CAP.json")
DEFAULT_CARD = os.path.join("ground", "DEVICE_QUEUE_CAP.md")
WORKFLOW = os.path.join(".github", "workflows", "commons-device-executor.yml")
TEST_PIN = "test_action_executor.py"
RIVET_RECEIPT = os.path.join("p", "rivet-ship-device-queue-single-20260825-01.md")
JOJO_TAKING = os.path.join("p", "jojo-device-queue-collapse-20260825-01.md")
SLACK_TS = "1787645425.769089"
TAKING_SLACK_TS = "1787644306.421489"
TAKING_SHA256 = "932f42dd86fbd54515253af71c5277876ee080b7f4fe6a54d6ae1aa71a7cba1a"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "device_queue_cap.py"),
    WORKFLOW,
    TEST_PIN,
    RIVET_RECEIPT,
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    WORKFLOW,
    TEST_PIN,
    RIVET_RECEIPT,
)
REQUIRED_PHRASES = (
    "device-queue-cap leftover",
    "collision_resolved",
    "queue: single",
    "cancel-in-progress: false",
    "historical backlog",
    "not_cleared",
    "do not remint",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "no auth",
    "no gate",
    "talk is not a land",
)
QUEUE_SINGLE = "queue: single"
QUEUE_MAX = "queue: max"
CANCEL_FALSE = "cancel-in-progress: false"


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
    """Parse the leftover catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "queue": str(data.get("queue") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "historical_backlog_cleared": bool(data.get("historical_backlog_cleared", False)),
        "cancel_historical_runs": bool(data.get("cancel_historical_runs", False)),
        "cancel_in_progress": bool(data.get("cancel_in_progress", True)),
        "error": "",
    }


def measure_workflow(text):
    """Score the device-executor caller. queue: max is a regression."""
    body = str(text or "")
    return {
        "queue_single": QUEUE_SINGLE in body,
        "queue_max": QUEUE_MAX in body,
        "cancel_false": CANCEL_FALSE in body,
    }


def measure_test_pin(text):
    """Score the regression pin. Missing refuse is incomplete."""
    body = str(text or "")
    return {
        "test_pins_single": QUEUE_SINGLE in body,
        "test_refuses_max": 'assertNotIn("queue: max"' in body or "queue: max" in body and "assertNotIn" in body,
    }


def measure_from_rows(facts):
    """Classify measured leftover facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "queue_single": bool(facts.get("queue_single")),
        "queue_max": bool(facts.get("queue_max")),
        "cancel_false": bool(facts.get("cancel_false")),
        "test_pins_single": bool(facts.get("test_pins_single")),
        "test_refuses_max": bool(facts.get("test_refuses_max")),
        "jojo_taking_absent": bool(facts.get("jojo_taking_absent")),
        "jojo_taking_state": str(
            facts.get("jojo_taking_state")
            or (CARRIER_ONLY if facts.get("jojo_taking_absent") else "UNVERIFIED_PRESENT")
        ).strip().upper(),
        "jojo_taking_provenance_ok": bool(
            facts.get("jojo_taking_provenance_ok")
        ),
        "jojo_taking_provenance_mismatches": list(
            facts.get("jojo_taking_provenance_mismatches") or []
        ),
        "historical_backlog_cleared": bool(facts.get("historical_backlog_cleared")),
        "cancel_historical_runs": bool(facts.get("cancel_historical_runs")),
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
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "device-queue-cap leftover not read. Absence was not stillness. "
                "A Slack COLLISION_RESOLVED is talk, not a land."
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
    if row.get("historical_backlog_cleared") or row.get("cancel_historical_runs"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover claimed historical backlog cleared or canceled runs. "
                "The forward cap does not clear the old backlog. "
                "FINDER-FAILED, never 0."
            ),
        }
    if row.get("queue_max") or not row.get("queue_single") or not row.get("cancel_false"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "workflow regression: queue: single / cancel-in-progress: false "
                "missing, or queue: max returned. Do not remint PR 2264. "
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
                + ". JOJO COLLISION_RESOLVED / queue-cap talk is CLAIMED until "
                "the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    if landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing)
                + ". Do not remint PR 2264. FINDER-FAILED, never 0."
            ),
        }
    if not row.get("test_pins_single") or not row.get("test_refuses_max"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "test_action_executor.py lost the queue: single pin or the "
                "queue: max refuse. FINDER-FAILED, never 0."
            ),
        }
    taking_present = not bool(row.get("jojo_taking_absent"))
    taking_state = str(row.get("jojo_taking_state") or CARRIER_ONLY).strip().upper()
    taking_ok = (
        taking_state == CARRIER_ONLY and not taking_present
    ) or (
        taking_state == DURABLE_ON_MAIN
        and taking_present
        and bool(row.get("jojo_taking_provenance_ok"))
    )
    if not taking_ok:
        return {
            "state": "NOT_LANDED",
            "note": (
                "jojo-device-queue-collapse-20260825-01 lacks exact Slack "
                "carrier provenance. Do not remint that taking. "
                "FINDER-FAILED, never 0."
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
            "device-queue-cap leftover is on this tree. queue: single still "
            "measured. Historical backlog stays NOT_CLEARED. A Slack "
            "COLLISION_RESOLVED without an exact carrier projection is still not the file."
        ),
    }


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
    workflow = measure_workflow(_read(root, WORKFLOW))
    test_pin = measure_test_pin(_read(root, TEST_PIN))
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    posting_open = catalog.get("posting") == "OPEN" and "open door" in hay
    taking = measure_slack_projection(
        root,
        JOJO_TAKING,
        post_id="jojo-device-queue-collapse-20260825-01",
        carrier_ts=TAKING_SLACK_TS,
        sender="JOJO",
        inner_kind="TAKING",
        expected_sha256=TAKING_SHA256,
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "queue_single": workflow["queue_single"],
        "queue_max": workflow["queue_max"],
        "cancel_false": workflow["cancel_false"],
        "test_pins_single": test_pin["test_pins_single"],
        "test_refuses_max": test_pin["test_refuses_max"],
        "jojo_taking_absent": not taking["present"],
        "jojo_taking_state": taking["state"],
        "jojo_taking_provenance_ok": taking["provenance_ok"],
        "jojo_taking_provenance_mismatches": taking["mismatches"],
        "historical_backlog_cleared": bool(catalog.get("historical_backlog_cleared")),
        "cancel_historical_runs": bool(catalog.get("cancel_historical_runs")),
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
                "queue_single": workflow["queue_single"],
                "queue_max": workflow["queue_max"],
                "cancel_false": workflow["cancel_false"],
                "jojo_taking_absent": facts["jojo_taking_absent"],
                "jojo_taking_state": facts["jojo_taking_state"],
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
                "misses": ["ground/DEVICE_QUEUE_CAP.md"],
                "calibration_ok": True,
                "queue_single": True,
                "cancel_false": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    regress = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "queue_max": True,
                "calibration_ok": True,
            }
        )
    )
    assert regress["state"] == "NOT_LANDED", regress
    cleared = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "historical_backlog_cleared": True,
                "calibration_ok": True,
                "queue_single": True,
                "cancel_false": True,
            }
        )
    )
    assert cleared["state"] == "NOT_LANDED", cleared
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure JOJO queue-cap collision leftover")
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
