"""Shared, durable execution road for authenticated grok.com browser hosts.

The existing Commons JobStore remains the only queue.  This adapter adds the
Grok-specific run envelope and submit-once state machine.  It stores no browser
credentials and performs no provider call.  Runtime writers must publish the
updated wake_jobs/<job_id>.json with an exact Git blob/content-SHA compare so a
second host cannot win the same transition.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from independent_commons_mcp.envelope import ID_RE
from independent_commons_mcp.jobs import (
    TERMINAL,
    JobError,
    JobStore,
    iso,
    parse_ts,
    public_job,
    utc_now,
)


SCHEMA = "commons-grok-executor-job/v1"
GROK_HARNESS = "grok.com authenticated browser via Commons MCP"
GROK_URL_RE = re.compile(r"^https://grok\.com/c/([A-Za-z0-9_-]+)(?:[/?#].*)?$")
BLOCKER_STATES = frozenset({
    "CLOUDFLARE",
    "PROVIDER_SIGN_IN",
    "BROWSER_UNAVAILABLE",
    "PAGE_BACKEND_UNAVAILABLE",
    "PAGE_UNCONFIRMED",
    "CONNECTOR_UNAVAILABLE",
})
PRE_SUBMIT = frozenset({"NOT_SUBMITTED", "CAPTURE_STARTED"})
POST_SUBMIT = frozenset({"SUBMITTING", "SUBMITTED", "RESULT_CAPTURED"})
SECRET_KEYS = frozenset({
    "cookie", "cookies", "credential", "credentials", "password", "passkey",
    "authorization", "proxy_authorization", "access_token", "refresh_token",
    "id_token", "browser_storage", "request_headers", "session_cookie",
})


def _copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise JobError("SCHEMA", "Grok queue values must be JSON-serializable", state="SCHEMA") from exc


def _text(value: Any, field: str, *, required: bool = False, maximum: int = 1_000_000) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise JobError("SCHEMA", "%s must be a string" % field, state="SCHEMA")
    if required and not value.strip():
        raise JobError("SCHEMA", "%s must not be empty" % field, state="SCHEMA")
    if len(value) > maximum:
        raise JobError("SCHEMA", "%s exceeds %s characters" % (field, maximum), state="SCHEMA")
    return value


def _worker(value: Any) -> str:
    worker = _text(value, "executor_id", required=True, maximum=80).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,80}", worker):
        raise JobError("SCHEMA", "executor_id must be 2-80 route characters", state="SCHEMA")
    return worker


def _timestamp(value: Any) -> str:
    text = _text(value or utc_now(), "now", required=True, maximum=128).strip()
    if parse_ts(text) is None:
        raise JobError("SCHEMA", "now must be ISO-8601", state="SCHEMA")
    return text


def _canonical_url(value: Any) -> str:
    text = _text(value, "conversation_url", maximum=2_000).strip()
    if not text:
        return ""
    match = GROK_URL_RE.fullmatch(text)
    if not match:
        raise JobError(
            "SCHEMA",
            "conversation_url must be an actual https://grok.com/c/... URL",
            state="SCHEMA",
        )
    return "https://grok.com/c/" + match.group(1)


def _digest(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _reject_secrets(value: Any, path: str = "job") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in SECRET_KEYS:
                raise JobError(
                    "SECRET_FIELD",
                    "%s.%s is not allowed in a Git/Commons job envelope" % (path, key),
                    state="SCHEMA",
                )
            _reject_secrets(child, "%s.%s" % (path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secrets(child, "%s[%s]" % (path, index))


def _execution(checkpoint: dict[str, Any]) -> dict[str, Any]:
    row = checkpoint.get("execution")
    if not isinstance(row, dict):
        raise JobError("CORRUPT", "Grok job execution state is missing", state="ERROR")
    return row


def _queue_checkpoint(job: dict[str, Any]) -> dict[str, Any]:
    checkpoint = job.get("checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("schema") != SCHEMA:
        raise JobError("SCHEMA", "job is not a shared Grok executor envelope", state="SCHEMA")
    return checkpoint


class GrokExecutorQueue:
    """Grok-specific transitions over the existing Commons JobStore."""

    def __init__(self, directory: str | Path | None = None):
        self.store = JobStore(directory)

    def _find(self, *, run_key: str = "", conversation_url: str = "") -> tuple[str, dict[str, Any]] | None:
        for job_id in self.store.list_ids():
            job = self.store.get(job_id)
            checkpoint = job.get("checkpoint") or {}
            if checkpoint.get("schema") != SCHEMA:
                continue
            if run_key and checkpoint.get("run_key") == run_key:
                return job_id, job
            result_url = str((checkpoint.get("result") or {}).get("conversation_url") or "")
            queued_url = str(checkpoint.get("conversation_url") or "")
            if conversation_url and conversation_url in {result_url, queued_url}:
                return job_id, job
        return None

    def enqueue(self, request: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise JobError("SCHEMA", "request must be an object", state="SCHEMA")
        _reject_secrets(request)
        job_id = _text(request.get("job_id"), "job_id", required=True, maximum=80).strip()
        if not ID_RE.fullmatch(job_id):
            raise JobError("SCHEMA", "job_id must be 8-80 Commons ID characters", state="SCHEMA")
        run_key = _text(request.get("run_key"), "run_key", required=True, maximum=512).strip()
        prompts = request.get("exact_prompts")
        if not isinstance(prompts, list) or not prompts:
            raise JobError("SCHEMA", "exact_prompts must be a non-empty array", state="SCHEMA")
        prompts = [_text(item, "exact_prompts", required=True) for item in prompts]
        origin = request.get("origin")
        if not isinstance(origin, dict):
            raise JobError("SCHEMA", "origin must be an object", state="SCHEMA")
        origin = _copy(origin)
        if not origin.get("task_id") and not origin.get("session_id"):
            raise JobError("SCHEMA", "origin needs task_id or session_id", state="SCHEMA")
        lineage = _copy(request.get("lineage")) if request.get("lineage") else None
        conversation_url = _canonical_url(request.get("conversation_url"))
        at = _timestamp(now)
        request_identity = {
            "run_key": run_key,
            "exact_prompts": prompts,
            "origin": origin,
            "lineage": lineage,
            "conversation_url": conversation_url,
        }
        request_sha = _digest(request_identity)
        prior = self._find(run_key=run_key)
        if prior:
            prior_id, prior_job = prior
            prior_checkpoint = _queue_checkpoint(prior_job)
            if prior_checkpoint.get("request_sha256") != request_sha:
                raise JobError(
                    "RUN_KEY_COLLISION",
                    "run_key already belongs to different exact bytes",
                    state="DUPLICATE",
                    job_id=prior_id,
                )
            return {
                "ok": True,
                "state": "DUPLICATE",
                "dedupe": "RUN_KEY",
                "job_id": prior_id,
                "prompt_action": "DO_NOT_SUBMIT",
                "job": public_job(prior_job),
            }
        if conversation_url:
            prior = self._find(conversation_url=conversation_url)
            if prior:
                return {
                    "ok": True,
                    "state": "DUPLICATE",
                    "dedupe": "EXACT_URL",
                    "job_id": prior[0],
                    "prompt_action": "DO_NOT_SUBMIT",
                    "job": public_job(prior[1]),
                }

        capture_start = {
            "tool": "start_grok_capture",
            "arguments": {
                "run_key": run_key,
                "origin": origin,
                "exact_prompts": prompts,
            },
        }
        if lineage:
            capture_start["arguments"]["parent_run_key"] = lineage.get("parent_run_key", "")
            capture_start["arguments"]["conversation_url"] = lineage.get("parent_conversation_url", "")
        checkpoint = {
            "schema": SCHEMA,
            "step": 0,
            "task": prompts[0],
            "run_key": run_key,
            "request_sha256": request_sha,
            "origin": origin,
            "lineage": lineage,
            "exact_prompts": prompts,
            "conversation_url": conversation_url,
            "capture_start": capture_start,
            "receipt_contract": {
                "conversation_url_prefix": "https://grok.com/c/",
                "required": [
                    "exact_prompts", "exact_final_result", "completion_state",
                    "provider_evidence", "artifact_evidence", "origin", "timestamps",
                ],
                "structural_start_before_submit": True,
                "fabricated_receipts_forbidden": True,
            },
            "execution": {
                "state": "QUEUED",
                "submission_state": "NOT_SUBMITTED",
                "prompt_replay_allowed": True,
                "active_attempt_id": "",
                "active_executor": "",
                "failed_executors": [],
                "blockers": [],
                "capture_ack": None,
                "submitted_at": "",
            },
            "result": None,
        }
        now_dt = parse_ts(at)
        assert now_dt is not None
        queued = self.store.upsert({
            "job_id": job_id,
            "owner_claim": "GROK_EXECUTOR",
            "harness": GROK_HARNESS,
            "objective": "Execute one intentional grok.com run and return its verified structural capture.",
            "checkpoint": checkpoint,
            "next_wake_at": at,
            "deadline": iso(now_dt + timedelta(days=30)),
            "backoff_seconds": int(request.get("backoff_seconds") or 30),
            "max_backoff_seconds": int(request.get("max_backoff_seconds") or 600),
            "lease_seconds": int(request.get("lease_seconds") or 300),
            "max_attempts": int(request.get("max_attempts") or 8),
            "budget_tokens": int(request.get("budget_tokens") or 1_000_000),
            "tokens_used": 0,
            "completion_predicate": {"type": "result_address_on_head"},
        })
        return {
            "ok": True,
            "state": "QUEUED",
            "job_id": job_id,
            "run_key": run_key,
            "action": "CLAIM_ONE_HEALTHY_AUTHENTICATED_EXECUTOR",
            "capture_start": capture_start,
            "job": queued["job"],
        }

    # Compatibility name for direct adapter callers; action_executor uses the
    # non-activation routing verb so its existing Muhlnickel observation import
    # closure remains behaviorally unchanged.
    submit = enqueue

    def _require_live(
        self,
        job: dict[str, Any],
        *,
        attempt_id: str,
        lease_id: str,
        executor_id: str,
        now: str,
        require_executor_claim: bool = True,
    ) -> None:
        lease = job.get("lease") or {}
        until = parse_ts(str(lease.get("until") or ""))
        now_dt = parse_ts(now)
        claims = [
            row for row in (job.get("event_receipts") or [])
            if row.get("event") == "grok_executor_claim"
            and row.get("attempt_id") == attempt_id
            and row.get("lease_id") == lease_id
        ]
        if (
            job.get("status") != "LEASED"
            or lease.get("lease_id") != lease_id
            or lease.get("holder") != executor_id
            or (require_executor_claim and not claims)
            or until is None
            or now_dt is None
            or now_dt >= until
        ):
            raise JobError(
                "STALE_ATTEMPT",
                "transition requires the current live Grok executor lease",
                state="STALE_ATTEMPT",
                job_id=job.get("job_id"),
            )

    def claim(self, job_id: str, executor_id: str, *, now: str | None = None) -> dict[str, Any]:
        executor = _worker(executor_id)
        at = _timestamp(now)
        current = self.store.get(job_id)
        checkpoint = _queue_checkpoint(current)
        execution = _execution(checkpoint)
        if current.get("status") in TERMINAL:
            return {"ok": True, "state": current["status"], "invoke_grok": False, "job": public_job(current)}
        if executor in execution.get("failed_executors", []):
            return {
                "ok": True,
                "state": "EXECUTOR_RELEASED_FOR_JOB",
                "action": "TRY_ANOTHER_HEALTHY_EXECUTOR",
                "invoke_grok": False,
                "job": public_job(current),
            }
        wake = self.store.tick(job_id, now=at, worker_id=executor)
        if wake.get("action") != "WAKE":
            return {
                "ok": True,
                "state": "QUEUED",
                "action": wake.get("action"),
                "reason": wake.get("reason"),
                "invoke_grok": False,
                "job": wake.get("job"),
            }
        attempt_id = str(wake["attempt_id"])
        lease_id = str(wake["lease_id"])
        claimed = self.store.claim_attempt(job_id, attempt_id, worker_id=executor, now=at)
        if claimed.get("state") != "CLAIMED":
            return claimed
        with self.store._transaction():
            job = self.store._get_unlocked(job_id)
            self._require_live(
                job,
                attempt_id=attempt_id,
                lease_id=lease_id,
                executor_id=executor,
                now=at,
                require_executor_claim=False,
            )
            checkpoint = _copy(_queue_checkpoint(job))
            execution = _execution(checkpoint)
            execution.update({
                "state": "LEASED",
                "active_attempt_id": attempt_id,
                "active_executor": executor,
            })
            job["checkpoint"] = checkpoint
            job.setdefault("event_receipts", []).append({
                "attempt_id": attempt_id,
                "lease_id": lease_id,
                "ts": at,
                "event": "grok_executor_claim",
                "worker_id": executor,
                "submission_state": execution["submission_state"],
            })
            job["updated_at"] = at
            self.store._save(job)
            public = public_job(job)
        submission = execution["submission_state"]
        action = (
            "START_STRUCTURAL_CAPTURE"
            if submission == "NOT_SUBMITTED"
            else "PREPARE_ONE_SUBMISSION"
            if submission == "CAPTURE_STARTED"
            else "CAPTURE_OUTPUT_ONLY_DO_NOT_RESUBMIT"
        )
        return {
            "ok": True,
            "state": "CLAIMED",
            "job_id": job_id,
            "attempt_id": attempt_id,
            "lease_id": lease_id,
            "executor_id": executor,
            "action": action,
            "invoke_grok": submission in PRE_SUBMIT,
            "exact_prompts": checkpoint["exact_prompts"],
            "capture_start": checkpoint["capture_start"],
            "job": public,
        }

    def heartbeat(
        self,
        job_id: str,
        *,
        attempt_id: str,
        lease_id: str,
        executor_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        executor = _worker(executor_id)
        at = _timestamp(now)
        now_dt = parse_ts(at)
        assert now_dt is not None
        with self.store._transaction():
            job = self.store._get_unlocked(job_id)
            self._require_live(
                job, attempt_id=attempt_id, lease_id=lease_id, executor_id=executor, now=at
            )
            job["lease"]["until"] = iso(
                now_dt + timedelta(seconds=int(job.get("lease_seconds") or 300))
            )
            job.setdefault("event_receipts", []).append({
                "attempt_id": attempt_id,
                "lease_id": lease_id,
                "ts": at,
                "event": "grok_executor_heartbeat",
                "worker_id": executor,
            })
            job["updated_at"] = at
            self.store._save(job)
            return {
                "ok": True,
                "state": "LEASED",
                "action": "CONTINUE_CURRENT_ATTEMPT",
                "lease": _copy(job["lease"]),
                "job": public_job(job),
            }

    def _mutate_claimed(
        self,
        job_id: str,
        *,
        attempt_id: str,
        lease_id: str,
        executor_id: str,
        now: str | None,
        event: str,
        mutate: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        executor = _worker(executor_id)
        at = _timestamp(now)
        with self.store._transaction():
            job = self.store._get_unlocked(job_id)
            self._require_live(
                job, attempt_id=attempt_id, lease_id=lease_id, executor_id=executor, now=at
            )
            checkpoint = _copy(_queue_checkpoint(job))
            execution = _execution(checkpoint)
            extra = mutate(checkpoint, execution)
            _reject_secrets(checkpoint)
            job["checkpoint"] = checkpoint
            job.setdefault("event_receipts", []).append({
                "attempt_id": attempt_id,
                "lease_id": lease_id,
                "ts": at,
                "event": event,
                "worker_id": executor,
                "submission_state": execution.get("submission_state"),
            })
            job["updated_at"] = at
            self.store._save(job)
            return {
                "ok": True,
                "state": execution.get("state"),
                "job_id": job_id,
                "attempt_id": attempt_id,
                "lease_id": lease_id,
                "executor_id": executor,
                "job": public_job(job),
                **extra,
            }

    def acknowledge_capture_start(
        self,
        job_id: str,
        capture_ack: dict[str, Any],
        *,
        attempt_id: str,
        lease_id: str,
        executor_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(capture_ack, dict) or capture_ack.get("write_ahead_ack") is not True:
            raise JobError(
                "CAPTURE_START_REQUIRED",
                "write_ahead_ack=true is required before provider submission",
                state="CAPTURE_START_REQUIRED",
            )
        _reject_secrets(capture_ack)

        def mutate(checkpoint: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
            if execution["submission_state"] not in {"NOT_SUBMITTED", "CAPTURE_STARTED"}:
                return {"action": "CAPTURE_OUTPUT_ONLY_DO_NOT_RESUBMIT", "submit_allowed": False}
            captured = capture_ack.get("capture") or {}
            if captured.get("run_key") != checkpoint["run_key"]:
                raise JobError("RUN_KEY_COLLISION", "capture ACK run_key mismatch", state="SCHEMA")
            execution.update({
                "state": "CAPTURE_STARTED",
                "submission_state": "CAPTURE_STARTED",
                "prompt_replay_allowed": True,
                "capture_ack": {
                    "run_id": captured.get("run_id"),
                    "revision": captured.get("revision"),
                    "state": captured.get("state"),
                    "snapshot_sha256": (capture_ack.get("persistence") or {}).get("sha256"),
                    "snapshot_size_bytes": (capture_ack.get("persistence") or {}).get("size_bytes"),
                },
            })
            return {"action": "PREPARE_ONE_SUBMISSION", "submit_allowed": False}

        return self._mutate_claimed(
            job_id,
            attempt_id=attempt_id,
            lease_id=lease_id,
            executor_id=executor_id,
            now=now,
            event="grok_capture_started",
            mutate=mutate,
        )

    def prepare_submission(
        self,
        job_id: str,
        *,
        attempt_id: str,
        lease_id: str,
        executor_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        def mutate(checkpoint: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
            state = execution["submission_state"]
            if state in POST_SUBMIT:
                return {
                    "action": "CAPTURE_OUTPUT_ONLY_DO_NOT_RESUBMIT",
                    "submit_allowed": False,
                    "exact_prompts": [],
                }
            if state != "CAPTURE_STARTED":
                raise JobError(
                    "CAPTURE_START_REQUIRED",
                    "structural capture START must be durable before submit intent",
                    state="CAPTURE_START_REQUIRED",
                )
            execution.update({
                "state": "SUBMITTING",
                "submission_state": "SUBMITTING",
                "prompt_replay_allowed": False,
            })
            return {
                "action": "SUBMIT_EXACT_PROMPTS_NOW_ONCE",
                "submit_allowed": True,
                "exact_prompts": checkpoint["exact_prompts"],
                "submission_key": _digest({
                    "job_id": job_id,
                    "run_key": checkpoint["run_key"],
                    "attempt_id": attempt_id,
                })[:32],
            }

        return self._mutate_claimed(
            job_id,
            attempt_id=attempt_id,
            lease_id=lease_id,
            executor_id=executor_id,
            now=now,
            event="grok_submit_intent",
            mutate=mutate,
        )

    def mark_submitted(
        self,
        job_id: str,
        *,
        attempt_id: str,
        lease_id: str,
        executor_id: str,
        conversation_url: str = "",
        now: str | None = None,
    ) -> dict[str, Any]:
        at = _timestamp(now)
        canonical = _canonical_url(conversation_url)

        def mutate(checkpoint: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
            if execution["submission_state"] == "SUBMITTED":
                return {"action": "CAPTURE_OUTPUT_ONLY", "submit_allowed": False}
            if execution["submission_state"] != "SUBMITTING":
                raise JobError("REPLAY_FENCE", "mark_submitted requires SUBMITTING", state="REPLAY_FENCE")
            execution.update({
                "state": "SUBMITTED",
                "submission_state": "SUBMITTED",
                "prompt_replay_allowed": False,
                "submitted_at": at,
            })
            if canonical:
                checkpoint["conversation_url"] = canonical
            return {"action": "CAPTURE_OUTPUT_ONLY", "submit_allowed": False}

        return self._mutate_claimed(
            job_id,
            attempt_id=attempt_id,
            lease_id=lease_id,
            executor_id=executor_id,
            now=at,
            event="grok_prompt_submitted",
            mutate=mutate,
        )

    def release(
        self,
        job_id: str,
        blocker_state: str,
        detail: str,
        *,
        attempt_id: str,
        lease_id: str,
        executor_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        blocker = _text(blocker_state, "blocker_state", required=True, maximum=64).strip().upper()
        if blocker not in BLOCKER_STATES:
            raise JobError("SCHEMA", "unsupported Grok executor blocker", state="SCHEMA")
        detail_text = _text(detail, "detail", maximum=16_000)
        executor = _worker(executor_id)
        at = _timestamp(now)
        with self.store._transaction():
            job = self.store._get_unlocked(job_id)
            self._require_live(
                job, attempt_id=attempt_id, lease_id=lease_id, executor_id=executor, now=at
            )
            checkpoint = _copy(_queue_checkpoint(job))
            execution = _execution(checkpoint)
            submitted_state = execution["submission_state"]
            pre_submit = submitted_state in PRE_SUBMIT
            failed = list(execution.get("failed_executors") or [])
            if executor not in failed:
                failed.append(executor)
            execution["failed_executors"] = failed
            execution.setdefault("blockers", []).append({
                "state": blocker,
                "detail": detail_text,
                "executor_id": executor,
                "attempt_id": attempt_id,
                "at": at,
                "submission_state": submitted_state,
                "provider_tokens_spent_by_failed_attempt": 0 if pre_submit else "OBSERVE_VISIBLE_EVIDENCE",
            })
            if pre_submit:
                capture_started = submitted_state == "CAPTURE_STARTED"
                execution.update({
                    "state": "QUEUED",
                    "submission_state": "CAPTURE_STARTED" if capture_started else "NOT_SUBMITTED",
                    "prompt_replay_allowed": True,
                    "active_attempt_id": "",
                    "active_executor": "",
                })
                if not capture_started:
                    execution["capture_ack"] = None
                action = "FAILOVER_TO_ANOTHER_HEALTHY_EXECUTOR"
            else:
                execution.update({
                    "state": "RECOVER_OUTPUT_ONLY",
                    "prompt_replay_allowed": False,
                    "active_attempt_id": "",
                    "active_executor": "",
                })
                action = "CAPTURE_OUTPUT_ONLY_DO_NOT_RESUBMIT"
            job["checkpoint"] = checkpoint
            job["status"] = "OPEN"
            job["lease"] = None
            job["next_wake_at"] = at
            job["updated_at"] = at
            job.setdefault("event_receipts", []).append({
                "attempt_id": attempt_id,
                "lease_id": lease_id,
                "ts": at,
                "event": "grok_executor_release",
                "worker_id": executor,
                "blocker_state": blocker,
                "submission_state": submitted_state,
            })
            self.store._save(job)
            return {
                "ok": True,
                "state": execution["state"],
                "job_id": job_id,
                "action": action,
                "prompt_replay_allowed": execution["prompt_replay_allowed"],
                "zero_spend_before_submission": pre_submit,
                "job": public_job(job),
            }

    def complete(
        self,
        job_id: str,
        capture: dict[str, Any],
        *,
        result_address: str,
        page_exists: Callable[[str], bool],
        attempt_id: str,
        lease_id: str,
        executor_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(capture, dict):
            raise JobError("SCHEMA", "capture must be an object", state="SCHEMA")
        _reject_secrets(capture)
        if capture.get("state") not in {"VERIFIED_COMPLETE", "RECEIPT_EMITTED"}:
            raise JobError("NOT_COMPLETE", "capture is not verified complete", state="NOT_COMPLETE")
        canonical = _canonical_url(capture.get("conversation_url"))
        result_text = _text(capture.get("exact_final_result"), "exact_final_result", required=True)
        at = _timestamp(now)
        current = self.store.get(job_id)
        checkpoint = _queue_checkpoint(current)
        if capture.get("run_key") != checkpoint["run_key"]:
            raise JobError("RUN_KEY_COLLISION", "capture run_key mismatch", state="SCHEMA")
        duplicate = self._find(conversation_url=canonical)
        if duplicate and duplicate[0] != job_id:
            return {
                "ok": True,
                "state": "DUPLICATE",
                "dedupe": "EXACT_URL",
                "job_id": duplicate[0],
                "prompt_action": "DO_NOT_SUBMIT",
                "job": public_job(duplicate[1]),
            }

        def mutate(checkpoint: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
            if execution["submission_state"] not in POST_SUBMIT:
                raise JobError("REPLAY_FENCE", "verified result requires a submitted/recovery run", state="REPLAY_FENCE")
            checkpoint["conversation_url"] = canonical
            checkpoint["result"] = _copy(capture)
            execution.update({
                "state": "RESULT_CAPTURED",
                "submission_state": "RESULT_CAPTURED",
                "prompt_replay_allowed": False,
            })
            return {"action": "VERIFY_DURABLE_RESULT_ADDRESS"}

        transition = self._mutate_claimed(
            job_id,
            attempt_id=attempt_id,
            lease_id=lease_id,
            executor_id=executor_id,
            now=at,
            event="grok_result_captured",
            mutate=mutate,
        )
        done = self.store.complete(
            job_id,
            result={
                "kind": "grok_capture_verified",
                "run_key": capture["run_key"],
                "conversation_url": canonical,
                "result_sha256": _digest(result_text),
                "capture_state": capture["state"],
            },
            result_address=result_address,
            page_exists=page_exists,
            worker_id=_worker(executor_id),
            now=at,
        )
        return {
            "ok": True,
            "state": "DONE",
            "job_id": job_id,
            "conversation_url": canonical,
            "return_to_requester": checkpoint["origin"],
            "next": "GPT_REVIEW_THEN_FRESH_MAIN_LANDING",
            "transition": transition,
            "job": done["job"],
        }

    def recover(self, job_id: str, *, now: str | None = None) -> dict[str, Any]:
        at = _timestamp(now)
        job = self.store.get(job_id)
        checkpoint = _queue_checkpoint(job)
        execution = _execution(checkpoint)
        submission = execution["submission_state"]
        lease = job.get("lease") or {}
        until = parse_ts(str(lease.get("until") or ""))
        now_dt = parse_ts(at)
        lease_live = bool(until and now_dt and now_dt < until and lease.get("holder"))
        if job.get("status") == "DONE":
            action = "RETURN_CAPTURE_TO_REQUESTER"
        elif submission in POST_SUBMIT:
            action = "CAPTURE_OUTPUT_ONLY_DO_NOT_RESUBMIT"
        elif lease_live:
            action = "WAIT_FOR_LIVE_EXECUTOR"
        else:
            action = "CLAIM_ANOTHER_HEALTHY_EXECUTOR"
        return {
            "ok": True,
            "state": job.get("status"),
            "job_id": job_id,
            "run_key": checkpoint["run_key"],
            "action": action,
            "prompt_replay_allowed": bool(execution.get("prompt_replay_allowed")),
            "origin": checkpoint["origin"],
            "job": public_job(job),
        }
