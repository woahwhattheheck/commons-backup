"""Strict offline classifier for captured GitHub Actions run/job evidence."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

RUN_SCHEMA = "github-actions-workflow-run-capture/v1"
JOBS_SCHEMA = "github-actions-jobs-capture/v1"
RECEIPT_SCHEMA = "commons-actions-execution-truth-receipt/v1"
VERIFY_SCHEMA = "commons-actions-execution-truth-verification/v1"
STATES = (
    "EXECUTED_GREEN", "EXECUTED_NON_GREEN", "EXECUTION_INTERRUPTED",
    "NOT_EXECUTED_RUNNER_UNASSIGNED", "NOT_EXECUTED_AFTER_ASSIGNMENT",
    "PENDING_EXECUTION", "INCONCLUSIVE_TERMINAL",
)
NONTERMINAL = {"queued", "in_progress", "waiting", "requested", "pending"}
RUN_STATUSES = NONTERMINAL | {"completed"}
JOB_STATUSES = {"queued", "in_progress", "waiting", "pending", "completed"}
STEP_STATUSES = {"queued", "in_progress", "pending", "completed"}
CONCLUSIONS = {
    "success", "failure", "cancelled", "timed_out", "action_required",
    "neutral", "skipped", "stale", "startup_failure",
}
EXECUTED_STEP_CONCLUSIONS = CONCLUSIONS - {"skipped", "stale"}
HARD_STEP_CONCLUSIONS = {"failure", "timed_out", "action_required", "startup_failure"}
MAX_CASES = 128
MAX_JOBS = 4096
MAX_STEPS_PER_JOB = 1024
MAX_TEXT = 512
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class EvidenceError(ValueError):
    pass


def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def reject_constant(value: str) -> None:
    raise EvidenceError(f"non-finite JSON number is not allowed: {value}")


def loads_strict(data: bytes, *, label: str) -> Any:
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{label}: input is not UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=strict_pairs, parse_constant=reject_constant)
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{label}: invalid JSON: {exc.msg}") from exc


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _exact(obj: Any, keys: set[str], *, where: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise EvidenceError(f"{where}: expected object")
    actual = set(obj)
    if actual != keys:
        raise EvidenceError(f"{where}: schema mismatch missing={sorted(keys-actual)} extra={sorted(actual-keys)}")
    return obj


def _text(value: Any, *, where: str, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise EvidenceError(f"{where}: expected non-empty string <= {max_len} characters")
    return value


def _positive_int(value: Any, *, where: str) -> int:
    if type(value) is not int or value <= 0:
        raise EvidenceError(f"{where}: expected positive integer (bool is not int)")
    return value


def _runner_id(value: Any, *, where: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise EvidenceError(f"{where}: expected null or non-negative integer (bool is not int)")
    return value


def _enum(value: Any, choices: set[str], *, where: str) -> str:
    if type(value) is not str or value not in choices:
        raise EvidenceError(f"{where}: unexpected enum value {value!r}")
    return value


def _conclusion(value: Any, *, status: str, where: str) -> str | None:
    if status == "completed":
        if type(value) is not str or value not in CONCLUSIONS:
            raise EvidenceError(f"{where}: completed status requires known non-null conclusion")
        return value
    if value is not None:
        raise EvidenceError(f"{where}: nonterminal status requires null conclusion")
    return None


def normalize_run(raw: Any) -> dict[str, Any]:
    outer = _exact(raw, {"schema", "run"}, where="run capture")
    if outer["schema"] != RUN_SCHEMA:
        raise EvidenceError("run capture: wrong schema")
    run = _exact(outer["run"], {"id", "run_attempt", "repository", "head_sha", "status", "conclusion"}, where="run capture.run")
    repository = _text(run["repository"], where="run.repository")
    head_sha = _text(run["head_sha"], where="run.head_sha", max_len=40)
    if not _REPO_RE.fullmatch(repository):
        raise EvidenceError("run.repository: expected owner/name")
    if not _SHA_RE.fullmatch(head_sha):
        raise EvidenceError("run.head_sha: expected lowercase 40-hex commit SHA")
    status = _enum(run["status"], RUN_STATUSES, where="run.status")
    return {
        "id": _positive_int(run["id"], where="run.id"),
        "run_attempt": _positive_int(run["run_attempt"], where="run.run_attempt"),
        "repository": repository, "head_sha": head_sha, "status": status,
        "conclusion": _conclusion(run["conclusion"], status=status, where="run.conclusion"),
    }


def _normalize_step(raw: Any, job_id: int) -> dict[str, Any]:
    item = _exact(raw, {"number", "name", "status", "conclusion"}, where=f"job {job_id} step")
    number = _positive_int(item["number"], where=f"job {job_id} step.number")
    status = _enum(item["status"], STEP_STATUSES, where=f"job {job_id} step {number}.status")
    return {
        "number": number,
        "name": _text(item["name"], where=f"job {job_id} step {number}.name"),
        "status": status,
        "conclusion": _conclusion(item["conclusion"], status=status, where=f"job {job_id} step {number}.conclusion"),
    }


def _normalize_job(raw: Any) -> dict[str, Any]:
    item = _exact(raw, {"id", "name", "status", "conclusion", "runner_id", "steps"}, where="job")
    job_id = _positive_int(item["id"], where="job.id")
    status = _enum(item["status"], JOB_STATUSES, where=f"job {job_id}.status")
    if type(item["steps"]) is not list or len(item["steps"]) > MAX_STEPS_PER_JOB:
        raise EvidenceError(f"job {job_id}.steps: expected list with <= {MAX_STEPS_PER_JOB} entries")
    steps = [_normalize_step(step, job_id) for step in item["steps"]]
    numbers = [step["number"] for step in steps]
    if len(numbers) != len(set(numbers)):
        raise EvidenceError(f"job {job_id}.steps: duplicate step number")
    steps.sort(key=lambda step: step["number"])
    return {
        "id": job_id, "name": _text(item["name"], where=f"job {job_id}.name"), "status": status,
        "conclusion": _conclusion(item["conclusion"], status=status, where=f"job {job_id}.conclusion"),
        "runner_id": _runner_id(item["runner_id"], where=f"job {job_id}.runner_id"), "steps": steps,
    }


def normalize_jobs(raw: Any) -> dict[str, Any]:
    outer = _exact(raw, {"schema", "run_id", "run_attempt", "repository", "head_sha", "jobs"}, where="jobs capture")
    if outer["schema"] != JOBS_SCHEMA:
        raise EvidenceError("jobs capture: wrong schema")
    repository = _text(outer["repository"], where="jobs.repository")
    head_sha = _text(outer["head_sha"], where="jobs.head_sha", max_len=40)
    if not _REPO_RE.fullmatch(repository):
        raise EvidenceError("jobs.repository: expected owner/name")
    if not _SHA_RE.fullmatch(head_sha):
        raise EvidenceError("jobs.head_sha: expected lowercase 40-hex commit SHA")
    if type(outer["jobs"]) is not list or len(outer["jobs"]) > MAX_JOBS:
        raise EvidenceError(f"jobs.jobs: expected list with <= {MAX_JOBS} entries")
    jobs = [_normalize_job(job) for job in outer["jobs"]]
    ids = [job["id"] for job in jobs]
    if len(ids) != len(set(ids)):
        raise EvidenceError("jobs.jobs: duplicate job id")
    jobs.sort(key=lambda job: job["id"])
    return {
        "run_id": _positive_int(outer["run_id"], where="jobs.run_id"),
        "run_attempt": _positive_int(outer["run_attempt"], where="jobs.run_attempt"),
        "repository": repository, "head_sha": head_sha, "jobs": jobs,
    }


def _bind(run: dict[str, Any], jobs: dict[str, Any]) -> None:
    for label, left, right in (
        ("run_id", run["id"], jobs["run_id"]),
        ("run_attempt", run["run_attempt"], jobs["run_attempt"]),
        ("repository", run["repository"], jobs["repository"]),
        ("head_sha", run["head_sha"], jobs["head_sha"]),
    ):
        if left != right:
            raise EvidenceError(f"run/jobs binding mismatch: {label}")
