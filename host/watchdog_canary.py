#!/usr/bin/env python3
"""host/watchdog_canary.py — an empty wake_jobs folder is not utilization.

Slack 1787639656.279039 (SPECTER independent ship receipt): the
production GitTruth HEAD oracle is real, but wake_jobs/ still had
only .gitignore + README.md. That is not a durable job canary.
Named idle bc- resume stays UNMEASURED.

Do not remint rivet-ship-watchdog-oracle-20260825-01 or the
MCP/wake temp-store leftovers. This leftover writes one real
wake_jobs/{job_id}.json and ticks a temp copy against a
SHA-pinned oracle. Known-present → DONE / STOP / zero mail /
zero model. Known-absent control stays runnable. titan: NOT_WRITTEN.

  python3 host/watchdog_canary.py
  python3 host/watchdog_canary.py --root .
  python3 host/watchdog_canary.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from harness_wake.watchdog import run as watchdog_run
from independent_commons_mcp.jobs import JobStore


JOBS = os.path.join("independent_commons_mcp", "jobs.py")
WATCHDOG = os.path.join("harness_wake", "watchdog.py")
WAKE_JOBS = "wake_jobs"
CANARY_NAME = "rivet-watchdog-canary-20260825-01.json"
CANARY_REL = os.path.join(WAKE_JOBS, CANARY_NAME)
DEFAULT_CATALOG = os.path.join("ground", "WATCHDOG_CANARY.json")
SLACK_TS = "1787639656.279039"
JOB_ID = "rivet-watchdog-canary-20260825-01"
PRESENT_ID = "ridge-cursor-wake-loop-20260822-01"
ABSENT_ID = "rivet-watchdog-canary-absent-20260825-01"
PIN_SHA = "4fc766f59e66999eb13e7f864594f5f698e1660b"
WATCH = "2026-08-25T06:40:00Z"


class FakeDeliver:
    """ntfy stand-in. Records WAKE mail; never hits the network."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        return {"status": 200, "body": "ok"}


class RecordingTruth:
    """Public HEAD stand-in. Records pin and read calls; never hits the network."""

    def __init__(self, present=(), sha=PIN_SHA):
        self.present = set(present)
        self.sha = sha
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
        "source_id": str(data.get("source_id") or "").strip(),
        "job_id": str(data.get("job_id") or "").strip(),
        "result_address": str(data.get("result_address") or "").strip(),
        "named_idle_bc_resume": str(data.get("named_idle_bc_resume") or "UNMEASURED").strip(),
        "hands_off": list(data.get("hands_off") or []),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "wrote_wake_jobs": bool(data.get("wrote_wake_jobs")),
    }


def wake_job_json_count(root):
    """Count real job files. README / gitignore / last-tick bake are not jobs."""
    folder = os.path.join(root, WAKE_JOBS)
    if not os.path.isdir(folder):
        return 0
    count = 0
    for name in os.listdir(folder):
        if not name.endswith(".json") or name.startswith("_") or name.startswith("."):
            continue
        count += 1
    return count


def load_canary(root):
    """Read the durable canary. Missing or corrupt is measured empty."""
    path = os.path.join(root, CANARY_REL)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def parse_watchdog(text):
    """The production leftover is the pinned HEAD oracle, already on main."""
    body = str(text or "")
    return {
        "watchdog_never_model": "Never invokes a model" in body
        or "never invokes a model" in body,
        "has_pinned_oracle": "pinned_head_oracle" in body and "GitTruth" in body,
    }


def tick_copy(job, present, worker_id="rivet-canary"):
    """Replay one job OPEN in a temp store against a pinned recording oracle.

    Production mutates the durable source to DONE. A verifier must reopen its
    isolated copy or a successful terminal receipt prevents all oracle reads
    and makes the next verification run falsely fail.
    """
    tmp = tempfile.mkdtemp(prefix="watchdog-canary-")
    try:
        store = JobStore(tmp)
        payload = dict(job)
        source_harness = str(payload.get("harness") or "")
        # The durable canary is a terminal legacy Cursor-owned source and must
        # remain held by production. This verifier reopens only an isolated
        # copy, so give that copy the existing non-Cursor head-proof harness;
        # otherwise the ZERO-Cursor pre-lease gate correctly holds it before
        # the pinned-oracle behavior under test can run.
        payload["harness"] = "github-actions-head-proof"
        payload["job_id"] = JOB_ID
        payload["status"] = "OPEN"
        payload["attempt_count"] = 0
        payload["event_receipts"] = []
        payload["lease"] = None
        payload["in_backoff"] = False
        payload["no_progress_count"] = 0
        payload["next_wake_at"] = "2026-08-25T00:00:00Z"
        payload["woke_once"] = False
        payload.pop("completed_at", None)
        path = os.path.join(tmp, "%s.json" % JOB_ID)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
        truth = RecordingTruth(present=present, sha=PIN_SHA)
        http = FakeDeliver()
        summary = watchdog_run(
            tmp,
            deliver=True,
            worker_id=worker_id,
            now=WATCH,
            http=http,
            truth=truth,
        )
        stored = store.get(JOB_ID)
        return {
            "summary": summary,
            "status": stored.get("status"),
            "source_harness": source_harness,
            "tick_harness": payload["harness"],
            "head_calls": truth.head_calls,
            "reads": list(truth.reads),
            "sha": truth.sha,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_canary(job):
    """Known-present DONE, known-absent control runnable, one SHA, zero mail/model."""
    present = tick_copy(job, {PRESENT_ID}, worker_id="rivet-canary-present")
    absent_job = dict(job)
    absent_job["result_address"] = ABSENT_ID
    absent = tick_copy(absent_job, {PRESENT_ID}, worker_id="rivet-canary-absent")
    present_summary = present["summary"]
    absent_summary = absent["summary"]
    present_reads = present["reads"]
    return {
        "ran": True,
        "temp_store": True,
        "present_status": present["status"],
        "present_source_harness": present["source_harness"],
        "present_tick_harness": present["tick_harness"],
        "present_action": (present_summary.get("jobs") or [{}])[0].get("action"),
        "present_reason": (present_summary.get("jobs") or [{}])[0].get("reason"),
        "present_wake_count": int(present_summary.get("wake_count") or 0),
        "present_delivered_count": int(present_summary.get("delivered_count") or 0),
        "present_invoke_model": bool(present_summary.get("invoke_model")),
        "present_process_model_invocations": int(
            present_summary.get("process_model_invocations") or 0
        ),
        "present_head_calls": present["head_calls"],
        "present_read_count": len(present_reads),
        "one_sha": bool(present_reads) and {sha for _path, sha in present_reads} == {PIN_SHA},
        "absent_status": absent["status"],
        "absent_source_harness": absent["source_harness"],
        "absent_tick_harness": absent["tick_harness"],
        "absent_action": (absent_summary.get("jobs") or [{}])[0].get("action"),
        "absent_wake_count": int(absent_summary.get("wake_count") or 0),
        "absent_invoke_model": bool((absent_summary.get("jobs") or [{}])[0].get("invoke_model")),
        "named_idle_bc_resume": "UNMEASURED",
    }


def classify(row):
    """Turn a measured durable canary + oracle tick into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "watchdog canary body not read. Absence was not stillness.",
        }
    if not row.get("watchdog_present") or not row.get("has_pinned_oracle"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "pinned HEAD oracle is missing. SPECTER ship-receipt / "
                "unutilized-oracle talk is CLAIMED."
            ),
        }
    if int(row.get("wake_job_json_count") or 0) < 1 or not row.get("canary_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "wake_jobs/ has no real job JSON. The production oracle "
                "is unutilized. SPECTER ship-receipt is CLAIMED."
            ),
        }
    job = row.get("canary") or {}
    if (
        job.get("job_id") != JOB_ID
        or job.get("result_address") != PRESENT_ID
        or (job.get("completion_predicate") or {}).get("type") != "result_address_on_head"
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "canary job is not the known-present HEAD-oracle predicate. "
                "SPECTER ship-receipt is CLAIMED."
            ),
        }
    if not row.get("ran"):
        return {
            "state": "CANDIDATE",
            "note": (
                "durable job JSON is on this tree. Tick it against the "
                "pinned oracle. A file without a tick is not utilization."
            ),
        }
    if (
        str(row.get("present_status") or "").upper() != "DONE"
        or row.get("present_action") != "STOP"
        or int(row.get("present_delivered_count") or 0)
        or row.get("present_invoke_model")
        or int(row.get("present_process_model_invocations") or 0)
        or not row.get("one_sha")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "known-present canary did not STOP/DONE with zero mail/model "
                "on one SHA. SPECTER ship-receipt is CLAIMED."
            ),
        }
    if str(row.get("absent_status") or "").upper() == "DONE" or not row.get("absent_wake_count"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "known-absent control did not stay runnable. A silent 0 "
                "is FINDER-FAILED, never clearance."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "durable job canary utilizes the pinned HEAD oracle. "
            "Known-present is DONE/STOP with zero mail/model on one SHA. "
            "Known-absent stays runnable. Named idle bc- resume stays "
            "UNMEASURED. A Slack receipt is still not the file."
        ),
    }


def measure_root(root, run_job=True):
    root = os.path.abspath(root)
    watchdog_path = os.path.join(root, WATCHDOG)
    catalog_path = os.path.join(root, DEFAULT_CATALOG)
    row = {
        "measured": True,
        "jobs": JOBS,
        "watchdog": WATCHDOG,
        "canary": {},
        "catalog": DEFAULT_CATALOG,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
        "ran": False,
        "wake_job_json_count": wake_job_json_count(root),
        "canary_present": os.path.isfile(os.path.join(root, CANARY_REL)),
        "named_idle_bc_resume": "UNMEASURED",
    }
    if os.path.isfile(watchdog_path):
        with open(watchdog_path, encoding="utf-8", errors="replace") as handle:
            row.update(parse_watchdog(handle.read()))
        row["watchdog_present"] = True
    else:
        row.update(parse_watchdog(""))
        row["watchdog_present"] = False
    if os.path.isfile(catalog_path):
        with open(catalog_path, encoding="utf-8", errors="replace") as handle:
            catalog = load_catalog(handle.read())
        row["catalog_present"] = True
        row["hands_off"] = catalog.get("hands_off") or []
    else:
        row["catalog_present"] = False
        row["hands_off"] = []
    job = load_canary(root)
    row["canary"] = job
    if run_job and row.get("canary_present") and job:
        row.update(run_canary(job))
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure a durable watchdog job canary, not a Slack receipt"
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
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    missing = classify({"measured": True, "watchdog_present": False})
    assert missing["state"] == "NOT_LANDED"
    empty_dir = classify(
        {
            "measured": True,
            "watchdog_present": True,
            "has_pinned_oracle": True,
            "wake_job_json_count": 0,
            "canary_present": False,
        }
    )
    assert empty_dir["state"] == "NOT_LANDED"
    assert "unutilized" in empty_dir["note"]
    candidate = classify(
        {
            "measured": True,
            "watchdog_present": True,
            "has_pinned_oracle": True,
            "wake_job_json_count": 1,
            "canary_present": True,
            "canary": {
                "job_id": JOB_ID,
                "result_address": PRESENT_ID,
                "completion_predicate": {"type": "result_address_on_head"},
            },
            "ran": False,
        }
    )
    assert candidate["state"] == "CANDIDATE"
    ok = classify(
        {
            "measured": True,
            "watchdog_present": True,
            "has_pinned_oracle": True,
            "wake_job_json_count": 1,
            "canary_present": True,
            "canary": {
                "job_id": JOB_ID,
                "result_address": PRESENT_ID,
                "completion_predicate": {"type": "result_address_on_head"},
            },
            "ran": True,
            "present_status": "DONE",
            "present_action": "STOP",
            "present_delivered_count": 0,
            "present_invoke_model": False,
            "present_process_model_invocations": 0,
            "one_sha": True,
            "absent_status": "LEASED",
            "absent_wake_count": 1,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    return True


if __name__ == "__main__":
    sys.exit(main())
