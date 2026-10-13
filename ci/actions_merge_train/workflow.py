"""Conservative merge-train composition over retained Actions execution truth."""
from __future__ import annotations

from collections import defaultdict

from .contract import *  # noqa:F401,F403

HOLD_PRIORITY = (
    "TOPOLOGY_NOT_CURRENT",
    "SOURCE_REVIEW_RED",
    "SOURCE_REVIEW_NOT_GREEN",
    "EXECUTION_EVIDENCE_INCOMPLETE",
    "EXECUTION_AMBIGUOUS",
    "SOURCE_EXECUTED_RED",
    "EXECUTION_EVIDENCE_ABSENT",
    "PROVIDER_QUEUED",
    "PROVIDER_STARVATION",
)
OVERALL_BY_REASON = {
    "TOPOLOGY_NOT_CURRENT": "HOLD_TOPOLOGY",
    "SOURCE_REVIEW_RED": "HOLD_SOURCE_REVIEW_RED",
    "SOURCE_REVIEW_NOT_GREEN": "HOLD_SOURCE_REVIEW",
    "EXECUTION_EVIDENCE_INCOMPLETE": "HOLD_EVIDENCE_INCOMPLETE",
    "EXECUTION_AMBIGUOUS": "HOLD_AMBIGUOUS",
    "SOURCE_EXECUTED_RED": "HOLD_SOURCE_EXECUTED_RED",
    "EXECUTION_EVIDENCE_ABSENT": "HOLD_EVIDENCE_ABSENT",
    "PROVIDER_QUEUED": "HOLD_PROVIDER_QUEUED",
    "PROVIDER_STARVATION": "HOLD_PROVIDER_STARVATION",
}


def row_disposition(row):
    state = row["classification"]
    if state == "EXECUTED_GREEN":
        return "SOURCE_EXECUTED_GREEN"
    if state == "EXECUTED_NON_GREEN":
        return "SOURCE_EXECUTED_RED"
    if state == "NOT_EXECUTED_RUNNER_UNASSIGNED":
        return "PROVIDER_CANCELLED_BEFORE_EXECUTION" if row["run_conclusion"] == "cancelled" else "PROVIDER_NO_RUN"
    if state == "PENDING_EXECUTION" and row["run_status"] in {"queued", "waiting", "requested", "pending"}:
        return "PROVIDER_QUEUED"
    return "HOLD_AMBIGUOUS"


def workflow_result(workflow, repository, head):
    observation = workflow["observation"]
    rows = []
    seen = set()
    by_run = defaultdict(list)
    for case in workflow["cases"]:
        row = classify_case(case["run"], case["jobs"])
        if row["repository"] != repository or row["head_sha"] != head:
            raise EvidenceError(f"workflow {workflow['name']}: run evidence does not bind capture repository/head")
        key = (row["run_id"], row["run_attempt"])
        if key in seen:
            raise EvidenceError(f"workflow {workflow['name']}: duplicate run_id/run_attempt")
        seen.add(key)
        rows.append(row)
        by_run[row["run_id"]].append(row)
    rows.sort(key=lambda row: (row["run_id"], row["run_attempt"]))

    if not observation["pagination_exhausted"]:
        disposition = "EVIDENCE_INCOMPLETE"
    elif not rows:
        disposition = "EVIDENCE_ABSENT"
    else:
        disposition = None

    latest = []
    replaced = []
    for run_id in sorted(by_run):
        ordered = sorted(by_run[run_id], key=lambda row: row["run_attempt"])
        latest.append(ordered[-1])
        replaced.extend(ordered[:-1])

    if disposition is None:
        kinds = {row_disposition(row) for row in latest}
        if "HOLD_AMBIGUOUS" in kinds or {"SOURCE_EXECUTED_GREEN", "SOURCE_EXECUTED_RED"} <= kinds:
            disposition = "HOLD_AMBIGUOUS"
        elif "SOURCE_EXECUTED_RED" in kinds:
            disposition = "SOURCE_EXECUTED_RED"
        elif kinds == {"SOURCE_EXECUTED_GREEN"}:
            disposition = "SOURCE_EXECUTED_GREEN"
        elif "PROVIDER_QUEUED" in kinds:
            disposition = "PROVIDER_QUEUED"
        elif "PROVIDER_NO_RUN" in kinds:
            disposition = "PROVIDER_NO_RUN"
        elif "PROVIDER_CANCELLED_BEFORE_EXECUTION" in kinds:
            disposition = "PROVIDER_CANCELLED_BEFORE_EXECUTION"
        else:
            disposition = "HOLD_AMBIGUOUS"

    holds = sum(
        row_disposition(row) in {"PROVIDER_NO_RUN", "PROVIDER_QUEUED", "PROVIDER_CANCELLED_BEFORE_EXECUTION"}
        for row in rows
    )
    if disposition in {"SOURCE_EXECUTED_GREEN", "SOURCE_EXECUTED_RED"}:
        advice = "NO_PROVIDER_RERUN_ADVICE_SOURCE_EXECUTED"
    elif disposition == "EVIDENCE_INCOMPLETE":
        advice = "COMPLETE_CAPTURE_PAGINATION_FIRST"
    elif disposition == "EVIDENCE_ABSENT":
        advice = "CAPTURE_EVIDENCE_FIRST"
    elif disposition == "HOLD_AMBIGUOUS":
        advice = "DO_NOT_RERUN_AMBIGUOUS"
    elif disposition == "PROVIDER_QUEUED":
        advice = "WAIT_FOR_PROVIDER_QUEUE"
    elif holds >= 2:
        advice = "BACKOFF_PROVIDER_STORM"
    else:
        advice = "BACKOFF_UNTIL_PROVIDER_HEALTH_CONFIRMED"

    mini = lambda row: {
        "run_id": row["run_id"],
        "run_attempt": row["run_attempt"],
        "classification": row["classification"],
        "operational_disposition": row_disposition(row),
        "run_status": row["run_status"],
        "run_conclusion": row["run_conclusion"],
        "executed_step_count": row["executed_step_count"],
        "capture_projection_sha256": row["capture_projection_sha256"],
    }
    short = lambda row: {
        "run_id": row["run_id"],
        "run_attempt": row["run_attempt"],
        "classification": row["classification"],
        "operational_disposition": row_disposition(row),
        "capture_projection_sha256": row["capture_projection_sha256"],
    }
    return {
        "name": workflow["name"],
        "observation": observation,
        "disposition": disposition,
        "latest_attempts": [mini(row) for row in latest],
        "replaced_attempts": [short(row) for row in replaced],
        "all_attempt_count": len(rows),
        "provider_hold_attempt_count": holds,
        "rerun_advice": advice,
        "source_regression_proven": False,
        "merge_authorized": False,
    }
