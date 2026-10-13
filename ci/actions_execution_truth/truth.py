"""Classification and deterministic receipt logic for Actions captures."""
from __future__ import annotations

import re
from typing import Any, Sequence

from schema import (
    RECEIPT_SCHEMA, VERIFY_SCHEMA, STATES, MAX_CASES, EXECUTED_STEP_CONCLUSIONS,
    HARD_STEP_CONCLUSIONS, EvidenceError, digest, normalize_run, normalize_jobs, _bind,
)


def classify_case(run_raw: Any, jobs_raw: Any) -> dict[str, Any]:
    run, jobs_capture = normalize_run(run_raw), normalize_jobs(jobs_raw)
    _bind(run, jobs_capture)
    jobs = jobs_capture["jobs"]
    executed: list[tuple[int, int, str]] = []
    hard_bad: list[tuple[int, int, str]] = []
    assigned = 0
    reasons: list[str] = []
    for job in jobs:
        if (job["runner_id"] or 0) > 0:
            assigned += 1
        if run["status"] == "completed" and job["status"] != "completed":
            reasons.append(f"TERMINAL_RUN_HAS_NONTERMINAL_JOB:{job['id']}")
        job_executed = 0
        job_hard = False
        for step in job["steps"]:
            if job["status"] == "completed" and step["status"] != "completed":
                reasons.append(f"TERMINAL_JOB_HAS_NONTERMINAL_STEP:{job['id']}:{step['number']}")
            conclusion = step["conclusion"]
            if step["status"] == "completed" and conclusion in EXECUTED_STEP_CONCLUSIONS:
                executed.append((job["id"], step["number"], conclusion)); job_executed += 1
            if step["status"] == "completed" and conclusion in HARD_STEP_CONCLUSIONS:
                hard_bad.append((job["id"], step["number"], conclusion)); job_hard = True
        if job["conclusion"] == "success" and job_hard:
            reasons.append(f"JOB_SUCCESS_WITH_NON_GREEN_STEP:{job['id']}")
        if job["conclusion"] == "success" and job_executed == 0:
            reasons.append(f"JOB_SUCCESS_WITHOUT_EXECUTED_STEP:{job['id']}")
        if job["conclusion"] == "skipped" and job_executed:
            reasons.append(f"JOB_SKIPPED_WITH_EXECUTED_STEP:{job['id']}")
    if run["status"] == "completed" and not jobs:
        reasons.append("TERMINAL_RUN_WITHOUT_JOBS")
    if run["conclusion"] == "success":
        for job in jobs:
            if job["conclusion"] not in {"success", "neutral", "skipped"}:
                reasons.append(f"RUN_SUCCESS_WITH_NON_GREEN_JOB:{job['id']}")
        if hard_bad:
            reasons.append("RUN_SUCCESS_WITH_NON_GREEN_STEP")
    if run["status"] == "completed" and run["conclusion"] == "success" and not executed:
        reasons.append("RUN_SUCCESS_WITHOUT_EXECUTED_STEP")
    reasons = sorted(set(reasons))

    if run["status"] != "completed": state = "PENDING_EXECUTION"
    elif reasons: state = "INCONCLUSIVE_TERMINAL"
    elif run["conclusion"] == "success": state = "EXECUTED_GREEN"
    elif hard_bad: state = "EXECUTED_NON_GREEN"
    elif executed: state = "EXECUTION_INTERRUPTED"
    elif assigned: state = "NOT_EXECUTED_AFTER_ASSIGNMENT"
    else: state = "NOT_EXECUTED_RUNNER_UNASSIGNED"

    projection = {"run": run, "jobs": jobs_capture}
    return {
        "repository": run["repository"], "run_id": run["id"], "run_attempt": run["run_attempt"],
        "head_sha": run["head_sha"], "run_status": run["status"], "run_conclusion": run["conclusion"],
        "classification": state, "executed_step_count": len(executed),
        "terminal_non_green_executed_step_count": len(hard_bad), "runner_assigned_job_count": assigned,
        "job_count": len(jobs), "reasons": reasons, "github_actions_green": state == "EXECUTED_GREEN",
        "source_regression_proven": False, "capture_projection_sha256": digest(projection),
    }


def compile_receipt(raw_cases: Sequence[tuple[Any, Any]]) -> dict[str, Any]:
    if not raw_cases or len(raw_cases) > MAX_CASES:
        raise EvidenceError(f"expected 1..{MAX_CASES} run/jobs cases")
    rows = [classify_case(run, jobs) for run, jobs in raw_cases]
    rows.sort(key=lambda row: (row["repository"], row["run_id"], row["run_attempt"], row["head_sha"]))
    ids = [(row["repository"], row["run_id"], row["run_attempt"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise EvidenceError("duplicate repository/run_id/run_attempt case")
    counts = {state: 0 for state in STATES}
    for row in rows: counts[row["classification"]] += 1
    not_exec = [row for row in rows if row["classification"] in {"NOT_EXECUTED_RUNNER_UNASSIGNED", "NOT_EXECUTED_AFTER_ASSIGNMENT"}]
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "runs": rows,
        "aggregate": {
            "run_count": len(rows), "classification_counts": counts, "not_executed_run_count": len(not_exec),
            "not_executed_repositories": sorted({row["repository"] for row in not_exec}),
            "descriptive_not_executed_burst": len(not_exec) >= 2,
            "billing_cause_inferred": False, "source_regression_proven": False,
        },
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def verify_receipt(supplied: Any, raw_cases: Sequence[tuple[Any, Any]]) -> dict[str, Any]:
    recomputed = compile_receipt(raw_cases)
    reasons: list[str] = []
    supplied_sha: str | None = None
    if type(supplied) is not dict:
        reasons.append("SUPPLIED_RECEIPT_NOT_OBJECT")
    else:
        value = supplied.get("receipt_sha256")
        if type(value) is str: supplied_sha = value
        if supplied.get("schema") != RECEIPT_SCHEMA: reasons.append("SUPPLIED_RECEIPT_SCHEMA_MISMATCH")
        if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
            reasons.append("SUPPLIED_RECEIPT_DIGEST_INVALID")
        else:
            projection = dict(supplied); projection.pop("receipt_sha256", None)
            if digest(projection) != value: reasons.append("SUPPLIED_RECEIPT_DIGEST_MISMATCH")
        if supplied != recomputed: reasons.append("RECEIPT_RECOMPUTE_MISMATCH")
    return {
        "schema": VERIFY_SCHEMA, "valid": not reasons, "reason_codes": sorted(set(reasons)),
        "supplied_receipt_sha256": supplied_sha, "recomputed_receipt_sha256": recomputed["receipt_sha256"],
    }
