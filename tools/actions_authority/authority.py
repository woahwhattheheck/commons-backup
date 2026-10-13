from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .common import (
    INPUT_SCHEMA,
    MAX_RUNS,
    OUTPUT_SCHEMA,
    RED_CONCLUSIONS,
    REPO_RE,
    SHA_RE,
    ZERO_STEP_WAIT_STATUSES,
    EvidenceError,
    _format_time,
    _require_list,
    _require_text,
    _sha256,
    _time,
    _validate_exact_fields,
)
from .model import _parse_inventory, _parse_policy, _parse_run


def _job_zero_step_unassigned(job: dict[str, Any]) -> bool:
    return (
        job["runner_id"] is None
        and job["runner_name"] is None
        and job["steps"] in (None, [])
        and (
            job["status"] in ZERO_STEP_WAIT_STATUSES
            or (job["status"] == "completed" and job["conclusion"] == "cancelled")
        )
    )


def _job_success_executed(job: dict[str, Any]) -> bool:
    if not (
        job["status"] == "completed"
        and job["conclusion"] == "success"
        and job["runner_id"] is not None
        and job["runner_name"] is not None
        and job["started_at"] is not None
        and job["completed_at"] is not None
        and type(job["steps"]) is list
        and job["steps"]
    ):
        return False
    steps = job["steps"]
    if any(step["status"] != "completed" for step in steps):
        return False
    if any(step["conclusion"] not in {"success", "skipped"} for step in steps):
        return False
    return any(step["conclusion"] == "success" for step in steps)


def _run_classification(run: dict[str, Any]) -> tuple[str, str]:
    status = run["status"]
    conclusion = run["conclusion"]
    jobs = run["jobs"]

    if status == "completed" and conclusion == "success":
        if run["started_at"] is None or run["completed_at"] is None:
            return "HOLD", "successful workflow lacks executed run timestamps"
        if not jobs:
            return "HOLD", "successful workflow has no job evidence"
        bad = [job for job in jobs if job["conclusion"] not in {"success", "skipped"}]
        if bad:
            return "HOLD", "workflow success conflicts with non-success job evidence"
        successful = [job for job in jobs if job["conclusion"] == "success"]
        if not successful:
            return "HOLD", "workflow success has no successful job"
        if any(not _job_success_executed(job) for job in successful):
            return "HOLD", "successful job lacks affirmative runner, chronology, or completed-step evidence"
        return "GREEN", "latest workflow run and attempt-bound job evidence prove terminal execution success"

    if status == "completed" and conclusion in RED_CONCLUSIONS:
        return "RED", f"latest workflow run completed with {conclusion}"

    if status == "completed" and conclusion == "cancelled":
        if jobs and all(_job_zero_step_unassigned(job) for job in jobs):
            return "BACKLOG", "latest run attempt was cancelled before any runner or step execution"
        return "HOLD", "cancelled workflow has execution or incomplete zero-step evidence"

    if status == "completed" and conclusion in {"neutral", "skipped"}:
        return "HOLD", f"required workflow concluded {conclusion}, not success"

    if status in ZERO_STEP_WAIT_STATUSES:
        if jobs and all(
            _job_zero_step_unassigned(job) and job["status"] in ZERO_STEP_WAIT_STATUSES
            for job in jobs
        ):
            return "BACKLOG", "latest run attempt is queued and unassigned with zero executed steps"
        return "WAIT", "latest workflow run has not completed or job state contradicts queue backlog"

    if status == "in_progress":
        return "WAIT", "latest workflow run is executing"

    return "WAIT", "latest workflow run has not reached terminal classification"


def _identity(run: dict[str, Any]) -> tuple[int, str, str]:
    return (run["workflow_id"], run["workflow_path"], run["workflow_name"])


def _validate_identity_maps(runs: list[dict[str, Any]]) -> None:
    by_id: dict[int, tuple[str, str]] = {}
    by_path: dict[str, tuple[int, str]] = {}
    by_name: dict[str, tuple[int, str]] = {}
    for run in runs:
        workflow_id, workflow_path, workflow_name = _identity(run)
        current_id = (workflow_path, workflow_name)
        current_path = (workflow_id, workflow_name)
        current_name = (workflow_id, workflow_path)
        if workflow_id in by_id and by_id[workflow_id] != current_id:
            raise EvidenceError(f"workflow_id {workflow_id} maps to multiple path/name identities")
        if workflow_path in by_path and by_path[workflow_path] != current_path:
            raise EvidenceError(f"workflow_path {workflow_path} maps to multiple id/name identities")
        if workflow_name in by_name and by_name[workflow_name] != current_name:
            raise EvidenceError(f"workflow_name {workflow_name} maps to multiple id/path identities")
        by_id[workflow_id] = current_id
        by_path[workflow_path] = current_path
        by_name[workflow_name] = current_name


def _latest_run(candidates: list[dict[str, Any]], label: str) -> tuple[dict[str, Any], list[int]]:
    by_number: dict[int, dict[str, Any]] = {}
    for run in candidates:
        run_number = run["run_number"]
        if run_number in by_number:
            raise EvidenceError(f"{label} contains duplicate run_number {run_number}")
        by_number[run_number] = run
    latest_number = max(by_number)
    latest = by_number[latest_number]
    older_ids = [row["run_id"] for number, row in sorted(by_number.items()) if number != latest_number]
    return latest, older_ids


def classify(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_seconds: int = 1800,
    max_future_skew_seconds: int = 300,
) -> dict[str, Any]:
    fields = {"schema_version", "repository", "head_sha", "captured_at", "policy", "inventory", "runs"}
    _validate_exact_fields(payload, fields, "input")
    missing = fields - set(payload)
    if missing:
        raise EvidenceError(f"input is missing fields: {', '.join(sorted(missing))}")
    if payload.get("schema_version") != INPUT_SCHEMA:
        raise EvidenceError(
            f"schema_version must equal {INPUT_SCHEMA}; v1/v2 caller-curated or attempt-unbound evidence is rejected"
        )
    repository = _require_text(payload.get("repository"), "repository")
    if not REPO_RE.fullmatch(repository):
        raise EvidenceError("repository must be owner/name")
    head_sha = _require_text(payload.get("head_sha"), "head_sha", maximum=40).lower()
    if not SHA_RE.fullmatch(head_sha):
        raise EvidenceError("head_sha must be exactly 40 lowercase hex characters")
    captured_at = _time(payload.get("captured_at"), "captured_at")
    if type(max_age_seconds) is not int or not 0 <= max_age_seconds <= 604800:
        raise EvidenceError("max_age_seconds must be an integer between 0 and 604800")
    if type(max_future_skew_seconds) is not int or not 0 <= max_future_skew_seconds <= 86400:
        raise EvidenceError("max_future_skew_seconds must be an integer between 0 and 86400")
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise EvidenceError("now must be a timezone-aware datetime")
    now = now.astimezone(timezone.utc)
    if captured_at > now + timedelta(seconds=max_future_skew_seconds):
        raise EvidenceError("captured_at is implausibly in the future")
    if now - captured_at > timedelta(seconds=max_age_seconds):
        raise EvidenceError("evidence snapshot is stale")

    policy = _parse_policy(payload.get("policy"))
    if policy["captured_at"] > captured_at:
        raise EvidenceError("policy was captured after the evidence snapshot")
    if captured_at - policy["captured_at"] > timedelta(seconds=max_age_seconds):
        raise EvidenceError("policy snapshot is stale relative to the evidence snapshot")
    inventory = _parse_inventory(payload.get("inventory"), repository=repository, head_sha=head_sha)

    runs_raw = _require_list(payload.get("runs"), "runs", maximum=MAX_RUNS)
    if inventory["total_count"] != len(runs_raw):
        raise EvidenceError("inventory.total_count does not match supplied complete run inventory")
    runs = [
        _parse_run(row, f"runs[{index}]", expected_repository=repository, expected_head=head_sha)
        for index, row in enumerate(runs_raw)
    ]

    snapshot_ceiling = captured_at + timedelta(seconds=max_future_skew_seconds)
    for run in runs:
        run_times = [run["created_at"], run["started_at"], run["completed_at"]]
        for job in run["jobs"]:
            run_times.extend((job["started_at"], job["completed_at"]))
        if any(value is not None and value > snapshot_ceiling for value in run_times):
            raise EvidenceError(f"run {run['run_id']} contains timestamps after the evidence capture")
    run_ids = [run["run_id"] for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise EvidenceError("runs contains duplicate run ids")
    _validate_identity_maps(runs)

    required = policy["required_workflows"]
    required_keys = {
        (row["workflow_id"], row["workflow_path"], row["workflow_name"]): row
        for row in required
    }
    by_identity: dict[tuple[int, str, str], list[dict[str, Any]]] = {key: [] for key in required_keys}
    extras: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
    for run in runs:
        key = _identity(run)
        if key in by_identity:
            by_identity[key].append(run)
        else:
            extras.setdefault(key, []).append(run)

    workflow_receipts: list[dict[str, Any]] = []
    states: list[str] = []
    for row in required:
        key = (row["workflow_id"], row["workflow_path"], row["workflow_name"])
        candidates = by_identity[key]
        selected: dict[str, Any] | None = None
        older_ids: list[int] = []
        if not candidates:
            state, reason = "MISSING", "no exact-head run exists in the complete inventory"
        else:
            selected, older_ids = _latest_run(candidates, f"workflow {row['workflow_id']}")
            state, reason = _run_classification(selected)
        states.append(state)
        workflow_receipts.append({
            "workflow_id": row["workflow_id"],
            "workflow_path": row["workflow_path"],
            "workflow_name": row["workflow_name"],
            "selected_run_id": selected["run_id"] if selected else None,
            "selected_run_number": selected["run_number"] if selected else None,
            "selected_run_attempt": selected["run_attempt"] if selected else None,
            "selected_jobs_inventory": selected["jobs_inventory"] if selected else None,
            "older_exact_head_run_ids": older_ids,
            "state": state,
            "reason": reason,
        })

    if "HOLD" in states:
        overall = "HOLD"
    elif "RED" in states:
        overall = "TERMINAL_RED"
    elif states and all(state == "GREEN" for state in states):
        overall = "TERMINAL_GREEN"
    elif "WAIT" in states:
        overall = "WAIT_EXECUTION"
    elif "MISSING" in states:
        overall = "WAIT_MISSING"
    elif states and all(state in {"GREEN", "BACKLOG"} for state in states) and "BACKLOG" in states:
        overall = "WAIT_RUNNER_BACKLOG"
    else:
        overall = "HOLD"

    ignored: list[dict[str, Any]] = []
    for key, candidates in sorted(extras.items(), key=lambda item: item[0]):
        latest, older_ids = _latest_run(candidates, f"extra workflow {key[0]}")
        ignored.append({
            "workflow_id": key[0],
            "workflow_path": key[1],
            "workflow_name": key[2],
            "latest_run_id": latest["run_id"],
            "latest_run_number": latest["run_number"],
            "latest_run_attempt": latest["run_attempt"],
            "latest_jobs_inventory": latest["jobs_inventory"],
            "older_exact_head_run_ids": older_ids,
        })

    receipt: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA,
        "repository": repository,
        "head_sha": head_sha,
        "captured_at": _format_time(captured_at),
        "evaluated_at": _format_time(now),
        "evidence_digest": f"sha256:{_sha256(payload)}",
        "policy_digest": f"sha256:{_sha256(payload['policy'])}",
        "inventory_digest": f"sha256:{_sha256({'inventory': payload['inventory'], 'runs': payload['runs']})}",
        "policy_source": {
            "kind": policy["source"]["kind"],
            "locator": policy["source"]["locator"],
            "source_sha256": policy["source"]["source_sha256"],
            "base_ref": policy["base_ref"],
            "base_sha": policy["base_sha"],
            "captured_at": _format_time(policy["captured_at"]),
        },
        "inventory": inventory,
        "decision": overall,
        "declared_policy_green": overall == "TERMINAL_GREEN",
        "merge_authorized": False,
        "authorization_scope": "CLASSIFICATION_ONLY",
        "authorization_reason": "offline evidence cannot independently prove live repository policy, review state, head/base topology, permission, or merge authority",
        "runner_exception_candidate": overall == "WAIT_RUNNER_BACKLOG",
        "side_effects_authorized": False,
        "required_workflows": workflow_receipts,
        "ignored_extra_workflows": ignored,
    }
    digest_subject = {key: value for key, value in receipt.items() if key != "evaluated_at"}
    receipt["receipt_digest"] = f"sha256:{_sha256(digest_subject)}"
    return receipt
