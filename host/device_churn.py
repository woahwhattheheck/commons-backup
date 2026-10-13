#!/usr/bin/env python3
"""host/device_churn.py — device-path utilization + no-op workflow churn.

Slack 1787635008.594599 (DEMON): the device execution protocol is
implemented but unused. GitHub still starts commons-device-executor
after every commons-board completion (512 runs measured 2026-08-25),
even when there is no reservation, no batch, and no scope=device
result. That is no-op churn.

This leftover measures the trigger and runs one bounded lawful canary
through the existing prepare/execute/finalize protocol in a temp
repo. It does not dispatch the self-hosted runner. It does not inject
DC, pulse Titan, pack a host, or run SGD. Titan is governed data,
not spare compute.

  python3 host/device_churn.py
  python3 host/device_churn.py --root .
  python3 host/device_churn.py --canary
  python3 host/device_churn.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


EXECUTOR = os.path.join(".github", "workflows", "commons-device-executor.yml")
BOARD = os.path.join(".github", "workflows", "commons-board.yml")
DEFAULT_CATALOG = os.path.join("ground", "DEVICE_CHURN.json")
CANARY_TEST = (
    "test_device_action_state.DeviceActionStateTests."
    "test_prepare_execute_finalize_success_is_exact_and_history_latched"
)


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def list_json_files(directory):
    """List regular *.json files. Missing dir is FINDER-FAILED, never 0."""
    if not os.path.isdir(directory):
        return {
            "ok": False,
            "count": None,
            "names": None,
            "error": "missing dir. FINDER-FAILED, never 0.",
        }
    names = []
    try:
        listing = os.listdir(directory)
    except OSError as exc:
        return {
            "ok": False,
            "count": None,
            "names": None,
            "error": "listdir failed: %s. FINDER-FAILED, never 0." % exc,
        }
    for name in listing:
        path = os.path.join(directory, name)
        if name.endswith(".json") and os.path.isfile(path):
            names.append(name)
    return {"ok": True, "count": len(names), "names": names, "error": ""}


def count_json_files(directory):
    """Compat: present empty dir is 0. Missing dir is None."""
    return list_json_files(directory)["count"]


def count_scope_device(results_dir):
    """Count result objects whose scope is device.

    Missing dir is FINDER-FAILED. Broken JSON is a parse failure,
    never skipped-as-zero.
    """
    if not os.path.isdir(results_dir):
        return {
            "ok": False,
            "count": None,
            "parse_failures": None,
            "error": "missing dir. FINDER-FAILED, never 0.",
        }
    total = 0
    failures = 0
    try:
        listing = os.listdir(results_dir)
    except OSError as exc:
        return {
            "ok": False,
            "count": None,
            "parse_failures": None,
            "error": "listdir failed: %s. FINDER-FAILED, never 0." % exc,
        }
    for name in listing:
        path = os.path.join(results_dir, name)
        if not name.endswith(".json") or not os.path.isfile(path):
            continue
        raw = _read_text(path)
        if not raw:
            failures += 1
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            failures += 1
            continue
        if not isinstance(row, dict):
            failures += 1
            continue
        if row.get("scope") == "device":
            total += 1
    if failures:
        return {
            "ok": False,
            "count": None,
            "parse_failures": failures,
            "error": (
                "%d result JSON file(s) could not be parsed. "
                "FINDER-UNVERIFIED, never 0." % failures
            ),
        }
    return {"ok": True, "count": total, "parse_failures": 0, "error": ""}


def workflow_flags(executor_text, board_text):
    """Pure trigger facts from the two workflow bodies."""
    executor = str(executor_text or "")
    board = str(board_text or "")
    return {
        "executor_present": bool(executor.strip()),
        "board_present": bool(board.strip()),
        "workflow_run": "workflow_run:" in executor,
        "workflow_call": "workflow_call:" in executor,
        "workflow_dispatch": "workflow_dispatch:" in executor,
        "board_preflight": "device_action_state.py preflight" in board,
        "board_calls_executor": (
            "uses: ./.github/workflows/commons-device-executor.yml" in board
        ),
        "board_gates_pending": "has_pending_device" in board,
    }


def classify(row):
    """Turn measured trigger + canary facts into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "device-churn leftover not read. Absence was not stillness.",
        }
    flags = row.get("flags") or {}
    if not flags.get("executor_present") or not flags.get("board_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "device executor or commons-board workflow missing. "
                "No-op-churn talk is CLAIMED until the leftover ships."
            ),
        }
    if flags.get("workflow_run"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "commons-device-executor still starts on every commons-board "
                "completion. That is no-op churn. Gate it on a real pending "
                "device action."
            ),
        }
    if not (
        flags.get("workflow_call")
        and flags.get("board_preflight")
        and flags.get("board_calls_executor")
        and flags.get("board_gates_pending")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "workflow_run is gone but board does not dispatch the "
                "executor only when has_pending_device is true."
            ),
        }
    if row.get("listing_failed") or row.get("parse_failures"):
        return {
            "state": "UNMEASURED",
            "note": (
                "workflow gate is integrated, but utilization count finders "
                "failed or were unverified: "
                + str(row.get("listing_error") or "result parse failure")
                + " Counts are null, not zero. FINDER-FAILED / "
                "FINDER-UNVERIFIED, never 0."
            ),
        }
    canary = row.get("canary") or {}
    if canary.get("ran") and not canary.get("ok"):
        return {
            "state": "CANDIDATE",
            "note": (
                "trigger is gated, but the bounded prepare/execute/finalize "
                "canary failed. Protocol leftover is not done."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "executor is call/dispatch only. commons-board starts it only "
            "when a device action is pending. Zero reservations is unused "
            "readiness, not a run. Talk is not a land."
        ),
    }


def measure_from_rows(counts, flags, extras=None):
    """Pure measure so tests do not need the live tree."""
    extras = extras or {}
    counts = counts or {}
    flags = flags or {}
    canary = extras.get("canary") or {"ran": False, "ok": False}
    def _maybe_int(key):
        value = counts.get(key)
        if value is None:
            return None
        return int(value)

    row = {
        "measured": True,
        "catalog": bool(extras.get("catalog")),
        "reservation_count": _maybe_int("reservation_count"),
        "batch_count": _maybe_int("batch_count"),
        "result_count": _maybe_int("result_count"),
        "scope_device_count": _maybe_int("scope_device_count"),
        "parse_failures": _maybe_int("parse_failures"),
        "listing_failed": bool(counts.get("listing_failed")),
        "listing_error": str(counts.get("listing_error") or ""),
        "flags": dict(flags),
        "canary": dict(canary),
        "titan": "NOT_WRITTEN",
        "dc_inject": False,
        "self_hosted_dispatch": False,
    }
    return row


def measure_root(root, canary=None):
    root = os.path.abspath(root)
    flags = workflow_flags(
        _read_text(os.path.join(root, EXECUTOR)),
        _read_text(os.path.join(root, BOARD)),
    )
    reservations = list_json_files(
        os.path.join(root, "actions", "device-reservations")
    )
    batches = list_json_files(os.path.join(root, "actions", "device-batches"))
    results = list_json_files(os.path.join(root, "actions", "results"))
    scopes = count_scope_device(os.path.join(root, "actions", "results"))
    listing_error = " ".join(
        part
        for part in (
            reservations.get("error"),
            batches.get("error"),
            results.get("error"),
            scopes.get("error") if isinstance(scopes, dict) else "",
        )
        if part
    )
    listing_failed = not (
        reservations.get("ok")
        and batches.get("ok")
        and results.get("ok")
        and (not isinstance(scopes, dict) or scopes.get("ok"))
    )
    counts = {
        "reservation_count": reservations.get("count"),
        "batch_count": batches.get("count"),
        "result_count": results.get("count"),
        "scope_device_count": (
            scopes.get("count") if isinstance(scopes, dict) else scopes
        ),
        "parse_failures": (
            scopes.get("parse_failures") if isinstance(scopes, dict) else 0
        ),
        "listing_failed": listing_failed,
        "listing_error": listing_error,
    }
    extras = {
        "catalog": os.path.isfile(os.path.join(root, DEFAULT_CATALOG)),
        "canary": canary or {"ran": False, "ok": False},
    }
    row = measure_from_rows(counts, flags, extras)
    row["root"] = root
    return row


def run_canary(root):
    """Bounded lawful protocol canary. Temp-repo only. No device runner."""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", CANARY_TEST],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
    except OSError as exc:
        return {
            "ran": True,
            "ok": False,
            "returncode": 127,
            "error": str(exc),
            "test": CANARY_TEST,
        }
    return {
        "ran": True,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "test": CANARY_TEST,
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure device-executor no-op churn and run a protocol canary"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--canary",
        action="store_true",
        help="run the bounded prepare/execute/finalize unit canary",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    canary = run_canary(args.root) if args.canary else None
    row = measure_root(args.root, canary=canary)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    state = verdict.get("state")
    if state == "INTEGRATED":
        return 0
    if state == "UNMEASURED":
        return 2
    return 1


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    churn = workflow_flags(
        "on:\n  workflow_run:\n    workflows: [\"commons-board\"]\n",
        "name: commons-board\n",
    )
    assert churn["workflow_run"] is True
    measured = measure_from_rows(
        {
            "reservation_count": 0,
            "batch_count": 0,
            "result_count": 48,
            "scope_device_count": 0,
        },
        churn,
        {"catalog": True},
    )
    assert measured["reservation_count"] == 0
    assert measured["scope_device_count"] == 0
    assert measured["titan"] == "NOT_WRITTEN"
    assert measured["dc_inject"] is False
    assert classify(measured)["state"] == "NOT_LANDED"
    gated = workflow_flags(
        "on:\n  workflow_call:\n  workflow_dispatch:\n",
        (
            "device_action_state.py preflight\n"
            "has_pending_device: ${{ steps.device_pending.outputs.has_pending }}\n"
            "uses: ./.github/workflows/commons-device-executor.yml\n"
        ),
    )
    assert gated["workflow_run"] is False
    ready = measure_from_rows(
        {
            "reservation_count": 0,
            "batch_count": 0,
            "result_count": 48,
            "scope_device_count": 0,
        },
        gated,
        {"catalog": True, "canary": {"ran": True, "ok": True}},
    )
    assert classify(ready)["state"] == "INTEGRATED"
    failed = measure_from_rows(
        {"reservation_count": 0},
        gated,
        {"catalog": True, "canary": {"ran": True, "ok": False}},
    )
    assert classify(failed)["state"] == "CANDIDATE"
    missing = measure_from_rows({}, {}, {"catalog": False})
    assert classify(missing)["state"] == "NOT_LANDED"
    missing_dir = list_json_files("/no/such/device-reservations")
    assert missing_dir["ok"] is False
    assert missing_dir["count"] is None
    assert "FINDER-FAILED" in missing_dir["error"]
    assert count_json_files("/no/such/device-reservations") is None
    return True


if __name__ == "__main__":
    sys.exit(main())
