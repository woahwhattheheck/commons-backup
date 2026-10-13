#!/usr/bin/env python3
"""host/mcp_wake_job.py — a Slack pivot is not a real job.

Slack 1787637971.910749 (SPECTER PIVOT): released render ownership
and named the adjacent MCP/wake real-job verification lane. The
taking had no p/{id}.md. Do not remint a SPECTER taking. Do not
touch JOJO MCP inventory / Grok smoke / idle-resume. Do not overlap
RIDGE/PLUMB named external-wake canary. Do not write wake_jobs/.

The leftover is the job contract itself: upsert → missing page is
NOT_DURABLE → present page is DONE → next cheap tick has
invoke_model false. A YAML watchdog and empty wake_jobs/ folder
are not a completed job.

Talk about the pivot without this leftover is CLAIMED. Missing
contract files or a complete() that ignores page_exists is
NOT_LANDED. Files present without a real-job run is CANDIDATE.
A measured DONE with the missing-page refuse is INTEGRATED.
titan: NOT_WRITTEN. No auth.

  python3 host/mcp_wake_job.py
  python3 host/mcp_wake_job.py --root .
  python3 host/mcp_wake_job.py --self-test
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
from independent_commons_mcp.jobs import JobError, JobStore


JOBS = os.path.join("independent_commons_mcp", "jobs.py")
WATCHDOG = os.path.join("harness_wake", "watchdog.py")
WORKFLOW = os.path.join(".github", "workflows", "job-watchdog.yml")
WAKE_JOBS = "wake_jobs"
DEFAULT_CATALOG = os.path.join("ground", "MCP_WAKE_JOB.json")
SLACK_TS = "1787637971.910749"
JOB_ID = "rivet-mcp-wake-verify-20260825-01"
RESULT_ID = "rivet-ship-mcp-wake-job-20260825-01"
T0 = "2026-08-25T06:00:00Z"
DUE = "2026-08-25T06:10:00Z"
WATCH = "2026-08-25T06:20:00Z"
AFTER = "2026-08-25T06:21:00Z"
DEADLINE = "2026-08-25T18:00:00Z"


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
        "hands_off": list(data.get("hands_off") or []),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "wrote_wake_jobs": bool(data.get("wrote_wake_jobs")),
    }


def parse_jobs(text):
    """The durable-page gate lives in the job contract, not Slack."""
    body = str(text or "")
    return {
        "has_result_address_on_head": "result_address_on_head" in body,
        "has_page_exists": "page_exists" in body,
        "has_not_durable": "NOT_DURABLE" in body,
        "has_invoke_model": "invoke_model" in body,
    }


def parse_watchdog(text):
    """Cheap ticks never invoke a model."""
    body = str(text or "")
    return {
        "watchdog_never_model": "Never invokes a model" in body
        or "never invokes a model" in body,
        "watchdog_invoke_false": "invoke_model" in body,
    }


def parse_workflow(text):
    """The YAML is a cheap tick, not a completed job."""
    body = str(text or "")
    return {
        "workflow_present_body": "job-watchdog" in body or "harness_wake" in body,
        "workflow_never_model": "never a model" in body.lower()
        or "Never invokes a model" in body,
    }


def wake_job_json_count(root):
    """Count real job files. README / gitignore are not jobs."""
    folder = os.path.join(root, WAKE_JOBS)
    if not os.path.isdir(folder):
        return 0
    count = 0
    for name in os.listdir(folder):
        if name.endswith(".json") and not name.startswith("_"):
            count += 1
    return count


def run_real_job():
    """Upsert / refuse / complete / cheap-tick in a temp store.

    Never write wake_jobs/. Named idle bc- resume is not this leftover.
    """
    pages = set()
    with tempfile.TemporaryDirectory(prefix="mcp-wake-job-") as tmp:
        store = JobStore(tmp)
        store.upsert(
            {
                "job_id": JOB_ID,
                "owner_claim": "RIVET",
                "harness": "cursor-automation",
                "objective": "MCP/wake real-job verification leftover. Temp store only.",
                "checkpoint": {"step": 0},
                "next_wake_at": DUE,
                "deadline": DEADLINE,
                "max_attempts": 4,
                "budget_tokens": 50,
                "backoff_seconds": 60,
                "lease_seconds": 30,
                "completion_predicate": {"type": "result_address_on_head"},
                "result_address": RESULT_ID,
            }
        )
        missing_ok = False
        missing_code = ""
        try:
            store.complete(
                JOB_ID,
                result={"durable": True, "kind": "page"},
                result_address=RESULT_ID,
                page_exists=lambda ident: ident in pages,
                worker_id="rivet-verify",
                now=WATCH,
            )
        except JobError as exc:
            missing_ok = exc.code == "NOT_DURABLE" or exc.state == "NOT_DURABLE"
            missing_code = exc.code
        tick_due = store.tick(JOB_ID, now=WATCH, worker_id="rivet-verify")
        pages.add(RESULT_ID)
        done = store.complete(
            JOB_ID,
            result={"durable": True, "kind": "page"},
            result_address=RESULT_ID,
            page_exists=lambda ident: ident in pages,
            worker_id="rivet-verify",
            now=AFTER,
        )
        after = store.tick(JOB_ID, now=AFTER, worker_id="rivet-verify")
        watchdog = watchdog_run(
            tmp, deliver=False, worker_id="rivet-watchdog", now=AFTER
        )
        leftover = [
            name
            for name in os.listdir(tmp)
            if name.endswith(".json") and name not in {"_last_tick.json"}
        ]
        return {
            "ran": True,
            "temp_store": True,
            "wrote_wake_jobs": False,
            "missing_page_refused": missing_ok,
            "missing_code": missing_code,
            "due_invoke_model": bool(tick_due.get("invoke_model")),
            "done_status": str(
                (done.get("job") or {}).get("status") or done.get("state") or ""
            ),
            "after_invoke_model": bool(after.get("invoke_model")),
            "watchdog_invoke_model": bool(watchdog.get("invoke_model")),
            "watchdog_process_model_invocations": int(
                watchdog.get("process_model_invocations") or 0
            ),
            "temp_job_files": leftover,
            "created_at": T0,
        }


def classify(row):
    """Turn a measured contract + real-job run into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "MCP/wake job contract body not read. Absence was not stillness.",
        }
    if not (
        row.get("jobs_present")
        and row.get("watchdog_present")
        and row.get("workflow_present")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "job contract files are missing. SPECTER pivot / "
                "MCP-wake real-job talk is CLAIMED."
            ),
        }
    if not row.get("has_result_address_on_head") or not row.get("has_page_exists"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "job contract is missing result_address_on_head / page_exists. "
                "A Slack pivot is not a land."
            ),
        }
    if row.get("wrote_wake_jobs"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover wrote wake_jobs/. That directory is JOJO's lane. "
                "Temp-store only."
            ),
        }
    if not row.get("ran"):
        return {
            "state": "CANDIDATE",
            "note": (
                "job contract files are on this tree. A YAML watchdog is "
                "not a completed job. Run the real-job leftover."
            ),
        }
    if not row.get("missing_page_refused"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "complete() accepted a missing page. Durable proof is the "
                "gate. SPECTER pivot is CLAIMED."
            ),
        }
    done = str(row.get("done_status") or "").upper()
    if done != "DONE":
        return {
            "state": "NOT_LANDED",
            "note": (
                "real job did not reach DONE after a durable page. "
                "status=%s. SPECTER pivot is CLAIMED."
            )
            % (done or "empty"),
        }
    if (
        row.get("after_invoke_model")
        or row.get("watchdog_invoke_model")
        or int(row.get("watchdog_process_model_invocations") or 0)
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "cheap tick after DONE invoked a model. Watchdog process "
                "never invokes a model. SPECTER pivot is CLAIMED."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "real job reached DONE only after page_exists. Missing page "
            "was NOT_DURABLE. Next cheap tick has invoke_model false. "
            "A Slack pivot is still not the file."
        ),
    }


def measure_root(root, run_job=True):
    root = os.path.abspath(root)
    jobs_path = os.path.join(root, JOBS)
    watchdog_path = os.path.join(root, WATCHDOG)
    workflow_path = os.path.join(root, WORKFLOW)
    catalog_path = os.path.join(root, DEFAULT_CATALOG)
    row = {
        "measured": True,
        "jobs": JOBS,
        "watchdog": WATCHDOG,
        "workflow": WORKFLOW,
        "catalog": DEFAULT_CATALOG,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
        "ran": False,
        "wrote_wake_jobs": False,
        "wake_job_json_count": wake_job_json_count(root),
    }
    if os.path.isfile(jobs_path):
        with open(jobs_path, "r", encoding="utf-8", errors="replace") as handle:
            row.update(parse_jobs(handle.read()))
        row["jobs_present"] = True
    else:
        row.update(parse_jobs(""))
        row["jobs_present"] = False
    if os.path.isfile(watchdog_path):
        with open(watchdog_path, "r", encoding="utf-8", errors="replace") as handle:
            row.update(parse_watchdog(handle.read()))
        row["watchdog_present"] = True
    else:
        row.update(parse_watchdog(""))
        row["watchdog_present"] = False
    if os.path.isfile(workflow_path):
        with open(workflow_path, "r", encoding="utf-8", errors="replace") as handle:
            row.update(parse_workflow(handle.read()))
        row["workflow_present"] = True
    else:
        row.update(parse_workflow(""))
        row["workflow_present"] = False
    if os.path.isfile(catalog_path):
        with open(catalog_path, "r", encoding="utf-8", errors="replace") as handle:
            catalog = load_catalog(handle.read())
        row["catalog_present"] = True
        row["hands_off"] = catalog.get("hands_off") or []
    else:
        row["catalog_present"] = False
        row["hands_off"] = []
    if run_job and row.get("jobs_present") and row.get("watchdog_present"):
        row.update(run_real_job())
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure an MCP/wake real job, not a Slack pivot"
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
    missing = classify({"measured": True, "jobs_present": False})
    assert missing["state"] == "NOT_LANDED"
    candidate = classify(
        {
            "measured": True,
            "jobs_present": True,
            "watchdog_present": True,
            "workflow_present": True,
            "has_result_address_on_head": True,
            "has_page_exists": True,
            "ran": False,
            "wrote_wake_jobs": False,
        }
    )
    assert candidate["state"] == "CANDIDATE"
    leaked = classify(
        {
            "measured": True,
            "jobs_present": True,
            "watchdog_present": True,
            "workflow_present": True,
            "has_result_address_on_head": True,
            "has_page_exists": True,
            "ran": True,
            "wrote_wake_jobs": True,
        }
    )
    assert leaked["state"] == "NOT_LANDED"
    ungated = classify(
        {
            "measured": True,
            "jobs_present": True,
            "watchdog_present": True,
            "workflow_present": True,
            "has_result_address_on_head": True,
            "has_page_exists": True,
            "ran": True,
            "wrote_wake_jobs": False,
            "missing_page_refused": False,
        }
    )
    assert ungated["state"] == "NOT_LANDED"
    ok = classify(
        {
            "measured": True,
            "jobs_present": True,
            "watchdog_present": True,
            "workflow_present": True,
            "has_result_address_on_head": True,
            "has_page_exists": True,
            "ran": True,
            "wrote_wake_jobs": False,
            "missing_page_refused": True,
            "done_status": "DONE",
            "after_invoke_model": False,
            "watchdog_invoke_model": False,
            "watchdog_process_model_invocations": 0,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    return True


if __name__ == "__main__":
    sys.exit(main())
