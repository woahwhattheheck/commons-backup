#!/usr/bin/env python3
"""host/watchdog_head_proof.py — a Slack taking is not a wake_jobs file.

Slack 1787639783.177559 (SPECTER TAKING): first production
wake_jobs HEAD-proof canary. Exact job_id
specter-watchdog-head-proof-20260825-01. The taking had no
p/{id}.md. Do not remint it.

The leftover is one canonical job JSON created through
JobStore.upsert, completion_predicate=result_address_on_head,
result_address=ridge-cursor-wake-loop-20260822-01 (already
durable). Acceptance lives on the main-push job-watchdog run:
one SHA-pinned truth read, DONE/STOP, zero WAKE, zero delivery,
zero process model invocation.

This instrument mints via upsert and measures the file. It does
not tick the production store. It does not claim named idle bc-
resume. It cannot ring a device / Muhlnickel / Titan. No Claude.

Talk about the taking without the job file is CLAIMED. Missing
or wrong-shaped file is NOT_LANDED. OPEN + correct fields is
CANDIDATE until watchdog lands DONE. DONE + correct fields is
INTEGRATED. titan: NOT_WRITTEN. No auth.

  python3 host/watchdog_head_proof.py
  python3 host/watchdog_head_proof.py --root .
  python3 host/watchdog_head_proof.py --mint
  python3 host/watchdog_head_proof.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from harness_wake.watchdog import run as watchdog_run
from independent_commons_mcp.jobs import JobStore


JOB_ID = "specter-watchdog-head-proof-20260825-01"
RESULT_ID = "ridge-cursor-wake-loop-20260822-01"
WAKE_JOBS = "wake_jobs"
DEFAULT_CATALOG = os.path.join("ground", "WATCHDOG_HEAD_PROOF.json")
SLACK_TS = "1787639783.177559"
NEXT_WAKE = "2026-08-25T00:00:00Z"
DEADLINE = "2026-12-31T00:00:00Z"
WATCH = "2026-08-25T06:36:23Z"
OBJECTIVE = (
    "HEAD-proof canary: ridge-cursor-wake-loop-20260822-01 already on HEAD. "
    "Watchdog lands DONE. No model. No device."
)
HANDS_OFF = (
    "named idle bc- resume",
    "device / Muhlnickel / Titan",
    "Claude testers",
    "JOJO visual-ci",
    "CML PR 2108",
    "rivet-ship-watchdog-oracle-20260825-01",
    "rivet-ship-mcp-wake-job-20260825-01",
    "ridge-cursor-wake-loop-20260822-01 remint",
)


def load_catalog(text):
    """Parse the leftover catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"hands_off": [], "error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"hands_off": [], "error": "catalog is not an object"}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "job_id": str(data.get("job_id") or "").strip(),
        "result_address": str(data.get("result_address") or "").strip(),
        "hands_off": list(data.get("hands_off") or []),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "named_idle_bc_resume": str(
            data.get("named_idle_bc_resume") or "UNMEASURED"
        ).strip()
        or "UNMEASURED",
    }


def parse_job(text):
    """Read one canonical job JSON. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "job file is not JSON"}
    if not isinstance(data, dict):
        return {"error": "job file is not an object"}
    pred = data.get("completion_predicate") or {}
    if not isinstance(pred, dict):
        pred = {}
    return {
        "job_id": str(data.get("job_id") or "").strip(),
        "status": str(data.get("status") or "").strip(),
        "result_address": str(data.get("result_address") or "").strip(),
        "predicate_type": str(pred.get("type") or "").strip(),
        "owner_claim": str(data.get("owner_claim") or "").strip(),
        "harness": str(data.get("harness") or "").strip(),
        "created_at": str(data.get("created_at") or "").strip(),
        "woke_once": bool(data.get("woke_once")),
    }


def job_fields():
    """Exact upsert payload for the production canary."""
    return {
        "job_id": JOB_ID,
        "owner_claim": "SPECTER",
        "harness": "github-actions-head-proof",
        "objective": OBJECTIVE,
        "checkpoint": {},
        "next_wake_at": NEXT_WAKE,
        "deadline": DEADLINE,
        "max_attempts": 1,
        "budget_tokens": 1,
        "backoff_seconds": 60,
        "lease_seconds": 30,
        "completion_predicate": {"type": "result_address_on_head"},
        "result_address": RESULT_ID,
    }


def mint_job(root):
    """Create the canonical job through JobStore.upsert. Do not tick."""
    store = JobStore(os.path.join(os.path.abspath(root), WAKE_JOBS))
    created = store.upsert(job_fields())
    job = created.get("job") or {}
    return {
        "minted": True,
        "via": "JobStore.upsert",
        "job_id": str(job.get("job_id") or ""),
        "status": str(job.get("status") or created.get("state") or ""),
        "ticked": False,
    }


def prove_temp_tick():
    """Known-present page -> DONE/STOP, zero WAKE, zero delivery, zero model.

    Temp store only. Never tick production wake_jobs/.
    """
    with tempfile.TemporaryDirectory(prefix="watchdog-head-proof-") as tmp:
        store = JobStore(tmp)
        store.upsert(job_fields())
        truth = _RecordingTruth(present={RESULT_ID})
        summary = watchdog_run(
            tmp,
            deliver=True,
            worker_id="gh-watchdog",
            now=WATCH,
            http=_FakeDeliver(),
            truth=truth,
        )
        stored = store.get(JOB_ID)
        return {
            "ran": True,
            "temp_store": True,
            "ticked_production": False,
            "wake_count": int(summary.get("wake_count") or 0),
            "stop_count": int(summary.get("stop_count") or 0),
            "delivered_count": int(summary.get("delivered_count") or 0),
            "process_model_invocations": int(
                summary.get("process_model_invocations") or 0
            ),
            "invoke_model": bool(summary.get("invoke_model")),
            "proof_action": str((summary.get("jobs") or [{}])[0].get("action") or ""),
            "proof_reason": str((summary.get("jobs") or [{}])[0].get("reason") or ""),
            "proof_status": str(stored.get("status") or ""),
            "truth_reads": int(len(truth.reads)),
            "head_calls": int(truth.head_calls),
        }


class _RecordingTruth:
    def __init__(self, present=()):
        self.present = set(present)
        self.sha = "0123456789abcdef0123456789abcdef01234567"
        self.head_calls = 0
        self.reads = []

    def head_sha(self):
        self.head_calls += 1
        return self.sha

    def read_at_sha(self, path, sha):
        self.reads.append((path, sha))
        ident = str(path or "").replace("\\", "/").lstrip("/")
        if ident.startswith("p/") and ident.endswith(".md"):
            ident = ident[2:-3]
        if ident in self.present:
            return 200, "from: TEST\n\n---\n\npage\n"
        return 404, None


class _FakeDeliver:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"status": 0, "body": "", "error": "FakeDeliver"}


def classify(row):
    """Turn a measured job file + temp proof into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "HEAD-proof canary body not read. Absence was not stillness.",
        }
    if not row.get("job_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "wake_jobs/%s.json is missing. SPECTER HEAD-proof taking "
                "is CLAIMED."
            )
            % JOB_ID,
        }
    if row.get("job_id") != JOB_ID:
        return {
            "state": "NOT_LANDED",
            "note": (
                "job_id mismatch. Do not remint. SPECTER HEAD-proof taking "
                "is CLAIMED."
            ),
        }
    if row.get("predicate_type") != "result_address_on_head":
        return {
            "state": "NOT_LANDED",
            "note": (
                "completion_predicate is not result_address_on_head. "
                "SPECTER HEAD-proof taking is CLAIMED."
            ),
        }
    if row.get("result_address") != RESULT_ID:
        return {
            "state": "NOT_LANDED",
            "note": (
                "result_address is not ridge-cursor-wake-loop-20260822-01. "
                "SPECTER HEAD-proof taking is CLAIMED."
            ),
        }
    status = str(row.get("status") or "").upper()
    if status == "DONE":
        return {
            "state": "INTEGRATED",
            "note": (
                "canonical job JSON is on this file and watchdog landed DONE. "
                "A Slack taking is still not the file."
            ),
        }
    if status == "OPEN":
        return {
            "state": "CANDIDATE",
            "note": (
                "canonical job JSON is on this tree via JobStore.upsert. "
                "OPEN until the main-push job-watchdog lands DONE. "
                "A Slack taking is still not the file."
            ),
        }
    return {
        "state": "NOT_LANDED",
        "note": (
            "job status=%s is not OPEN or DONE. SPECTER HEAD-proof taking "
            "is CLAIMED."
        )
        % (status or "empty"),
    }


def measure_root(root, run_proof=True):
    root = os.path.abspath(root)
    job_path = os.path.join(root, WAKE_JOBS, "%s.json" % JOB_ID)
    catalog_path = os.path.join(root, DEFAULT_CATALOG)
    row = {
        "measured": True,
        "job_path": os.path.join(WAKE_JOBS, "%s.json" % JOB_ID),
        "catalog": DEFAULT_CATALOG,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
        "named_idle_bc_resume": "UNMEASURED",
        "ticked_production": False,
        "job_present": False,
    }
    if os.path.isfile(catalog_path):
        with open(catalog_path, "r", encoding="utf-8", errors="replace") as handle:
            catalog = load_catalog(handle.read())
        row["catalog_present"] = True
        row["hands_off"] = catalog.get("hands_off") or list(HANDS_OFF)
        row["titan"] = catalog.get("titan") or "NOT_WRITTEN"
    else:
        row["catalog_present"] = False
        row["hands_off"] = list(HANDS_OFF)
    if os.path.isfile(job_path):
        with open(job_path, "r", encoding="utf-8", errors="replace") as handle:
            row.update(parse_job(handle.read()))
        row["job_present"] = True
    else:
        row.update(parse_job(""))
        row["job_present"] = False
    if run_proof:
        row.update(prove_temp_tick())
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure or mint the production HEAD-proof wake job."
    )
    parser.add_argument("--root", default=ROOT)
    parser.add_argument(
        "--mint",
        action="store_true",
        help="create the canonical job via JobStore.upsert (no tick)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.mint:
        minted = mint_job(args.root)
        json.dump(minted, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    row = measure_root(args.root, run_proof=True)
    verdict = classify(row)
    out = {"row": row, "verdict": verdict}
    json.dump(out, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.self_test:
        if verdict["state"] not in {"NOT_LANDED", "CANDIDATE", "INTEGRATED"}:
            return 2
        if not row.get("ran"):
            return 2
        if (
            row.get("wake_count")
            or row.get("delivered_count")
            or row.get("process_model_invocations")
            or row.get("invoke_model")
            or row.get("ticked_production")
        ):
            return 2
        if row.get("proof_status") != "DONE" or row.get("proof_action") != "STOP":
            return 2
        if str(row.get("proof_reason") or "") != "DONE":
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
