"""Fail-closed, network-free acceptance rail for print/mail API integrations.

This module validates synthetic or buyer-approved evidence.  It never calls a
mail provider, submits a City bid, authorizes spending, or treats provider
submission as physical delivery.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple
from urllib.parse import urlparse

SCHEMA_VERSION = 1
EXPECTED_BID_ID = "2027BID000033"
EXPECTED_TITLE = "CONTRACT- Print & Mail API"
EXPECTED_SOURCE_HOST = "www.stlouis-mo.gov"
EXPECTED_SOURCE_PATH = "/government/procurement/single-procurement-view.cfm"
ALLOWED_ENVIRONMENTS = {"TEST", "LIVE"}
ALLOWED_EFFECT_STATES = {"NONE", "SUBMITTED", "UNKNOWN_EFFECT"}
ALLOWED_PROVIDER_EVENTS = {
    "ACCEPTED",
    "MAILED",
    "IN_TRANSIT",
    "DELIVERED",
    "RETURNED",
    "CANCELED",
}
TERMINAL_PROVIDER_EVENTS = {"DELIVERED", "RETURNED", "CANCELED"}


class FixtureError(ValueError):
    """Raised when acceptance evidence is structurally invalid."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FixtureError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise FixtureError(f"{name} must be an array")
    return value


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FixtureError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise FixtureError(f"{name} must not have surrounding whitespace")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:  # bool/int aliasing must fail closed
        raise FixtureError(f"{name} must be a boolean")
    return value


def _require_nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise FixtureError(f"{name} must be a non-negative integer")
    return value


def _require_sha256(value: Any, name: str) -> str:
    text = _require_nonempty_str(value, name)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise FixtureError(f"{name} must be a lowercase sha256 hex digest")
    return text


def _optional_sha256(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, name)


def _parse_time(value: Any, name: str) -> datetime:
    text = _require_nonempty_str(value, name)
    if not text.endswith("Z"):
        raise FixtureError(f"{name} must be UTC and end in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise FixtureError(f"{name} must be ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise FixtureError(f"{name} must be UTC")
    return parsed


def _validate_source_url(value: Any) -> str:
    text = _require_nonempty_str(value, "contract.source_url")
    parsed = urlparse(text)
    if parsed.scheme != "https" or parsed.hostname != EXPECTED_SOURCE_HOST:
        raise FixtureError("contract.source_url must be the official City HTTPS host")
    if parsed.path != EXPECTED_SOURCE_PATH:
        raise FixtureError("contract.source_url must be the official procurement detail path")
    if not parsed.query.startswith("id="):
        raise FixtureError("contract.source_url must identify the procurement detail record")
    if parsed.fragment or parsed.username or parsed.password or parsed.port:
        raise FixtureError("contract.source_url contains forbidden URL components")
    return text


def _validate_contract(contract: Mapping[str, Any]) -> Dict[str, Any]:
    bid_id = _require_nonempty_str(contract.get("bid_id"), "contract.bid_id")
    if bid_id != EXPECTED_BID_ID:
        raise FixtureError(f"contract.bid_id must equal {EXPECTED_BID_ID}")
    title = _require_nonempty_str(contract.get("title"), "contract.title")
    if title != EXPECTED_TITLE:
        raise FixtureError(f"contract.title must equal {EXPECTED_TITLE!r}")
    source_url = _validate_source_url(contract.get("source_url"))
    packet_sha = _optional_sha256(contract.get("product_spec_sha256"), "contract.product_spec_sha256")
    packet_bound = _require_bool(contract.get("product_spec_bound"), "contract.product_spec_bound")
    if packet_bound != (packet_sha is not None):
        raise FixtureError("product_spec_bound must exactly reflect product_spec_sha256 presence")
    return {
        "bid_id": bid_id,
        "title": title,
        "source_url": source_url,
        "product_spec_bound": packet_bound,
        "product_spec_sha256": packet_sha,
    }


def _validate_departments(raw: Any) -> Dict[str, Dict[str, Any]]:
    departments = _require_mapping(raw, "departments")
    if not departments:
        raise FixtureError("departments must not be empty")
    result: Dict[str, Dict[str, Any]] = {}
    for raw_id, raw_policy in departments.items():
        dept_id = _require_nonempty_str(raw_id, "department id")
        policy = _require_mapping(raw_policy, f"departments.{dept_id}")
        if set(policy) != {"budget_cents", "live_authorizers"}:
            raise FixtureError(f"departments.{dept_id} has unknown or missing keys")
        budget = _require_nonnegative_int(policy["budget_cents"], f"departments.{dept_id}.budget_cents")
        auths = _require_list(policy["live_authorizers"], f"departments.{dept_id}.live_authorizers")
        if not auths:
            raise FixtureError(f"departments.{dept_id}.live_authorizers must not be empty")
        normalized = [_require_nonempty_str(v, f"departments.{dept_id}.live_authorizers[]") for v in auths]
        if len(set(normalized)) != len(normalized):
            raise FixtureError(f"departments.{dept_id}.live_authorizers contains duplicates")
        result[dept_id] = {"budget_cents": budget, "live_authorizers": tuple(sorted(normalized))}
    return result


def _validate_provider_events(
    events_raw: Any,
    *,
    job_id: str,
    provider_request_id: str | None,
    submission_time: datetime | None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    events = _require_list(events_raw, f"mail_jobs.{job_id}.provider_events")
    seen_ids: set[str] = set()
    result: List[Dict[str, Any]] = []
    errors: List[str] = []
    last_time: datetime | None = None
    terminal_seen = False
    for idx, item in enumerate(events):
        event = _require_mapping(item, f"mail_jobs.{job_id}.provider_events[{idx}]")
        if set(event) != {"event_id", "type", "provider_request_id", "observed_at"}:
            raise FixtureError(f"mail_jobs.{job_id}.provider_events[{idx}] has unknown or missing keys")
        event_id = _require_nonempty_str(event["event_id"], f"mail_jobs.{job_id}.provider_events[{idx}].event_id")
        if event_id in seen_ids:
            errors.append(f"{job_id}: duplicate provider event id {event_id}")
        seen_ids.add(event_id)
        event_type = _require_nonempty_str(event["type"], f"mail_jobs.{job_id}.provider_events[{idx}].type")
        if event_type not in ALLOWED_PROVIDER_EVENTS:
            errors.append(f"{job_id}: unsupported provider event {event_type}")
        event_request_id = _require_nonempty_str(
            event["provider_request_id"], f"mail_jobs.{job_id}.provider_events[{idx}].provider_request_id"
        )
        if provider_request_id is None or event_request_id != provider_request_id:
            errors.append(f"{job_id}: provider event is not bound to the submission request")
        when = _parse_time(event["observed_at"], f"mail_jobs.{job_id}.provider_events[{idx}].observed_at")
        if submission_time is None or when < submission_time:
            errors.append(f"{job_id}: provider event predates submission")
        if last_time is not None and when < last_time:
            errors.append(f"{job_id}: provider events are out of observed-time order")
        if terminal_seen:
            errors.append(f"{job_id}: provider event occurs after terminal provider state")
        if event_type in TERMINAL_PROVIDER_EVENTS:
            terminal_seen = True
        last_time = when
        result.append(
            {
                "event_id": event_id,
                "type": event_type,
                "provider_request_id": event_request_id,
                "observed_at": event["observed_at"],
            }
        )
    return result, errors


def _validate_job(
    raw: Any,
    *,
    departments: Mapping[str, Mapping[str, Any]],
) -> Tuple[Dict[str, Any], List[str]]:
    job = _require_mapping(raw, "mail job")
    required = {
        "job_id",
        "department_id",
        "environment",
        "artifact_sha256",
        "proof",
        "authorization",
        "submission",
        "expected_cost_cents",
        "provider_events",
    }
    if set(job) != required:
        raise FixtureError("mail job has unknown or missing keys")

    job_id = _require_nonempty_str(job["job_id"], "mail_jobs[].job_id")
    dept_id = _require_nonempty_str(job["department_id"], f"mail_jobs.{job_id}.department_id")
    environment = _require_nonempty_str(job["environment"], f"mail_jobs.{job_id}.environment")
    if environment not in ALLOWED_ENVIRONMENTS:
        raise FixtureError(f"mail_jobs.{job_id}.environment must be TEST or LIVE")
    artifact_sha = _require_sha256(job["artifact_sha256"], f"mail_jobs.{job_id}.artifact_sha256")
    expected_cost = _require_nonnegative_int(job["expected_cost_cents"], f"mail_jobs.{job_id}.expected_cost_cents")
    errors: List[str] = []
    if dept_id not in departments:
        errors.append(f"{job_id}: unknown department {dept_id}")

    proof = _require_mapping(job["proof"], f"mail_jobs.{job_id}.proof")
    if set(proof) != {"artifact_sha256", "render_sha256", "observed_at"}:
        raise FixtureError(f"mail_jobs.{job_id}.proof has unknown or missing keys")
    proof_artifact = _require_sha256(proof["artifact_sha256"], f"mail_jobs.{job_id}.proof.artifact_sha256")
    render_sha = _require_sha256(proof["render_sha256"], f"mail_jobs.{job_id}.proof.render_sha256")
    proof_time = _parse_time(proof["observed_at"], f"mail_jobs.{job_id}.proof.observed_at")
    if proof_artifact != artifact_sha:
        errors.append(f"{job_id}: proof artifact does not match job artifact")

    auth = _require_mapping(job["authorization"], f"mail_jobs.{job_id}.authorization")
    if set(auth) != {"approved", "artifact_sha256", "render_sha256", "authorizer_id", "authorized_at"}:
        raise FixtureError(f"mail_jobs.{job_id}.authorization has unknown or missing keys")
    approved = _require_bool(auth["approved"], f"mail_jobs.{job_id}.authorization.approved")
    auth_artifact = _require_sha256(auth["artifact_sha256"], f"mail_jobs.{job_id}.authorization.artifact_sha256")
    auth_render = _require_sha256(auth["render_sha256"], f"mail_jobs.{job_id}.authorization.render_sha256")
    authorizer = _require_nonempty_str(auth["authorizer_id"], f"mail_jobs.{job_id}.authorization.authorizer_id")
    auth_time = _parse_time(auth["authorized_at"], f"mail_jobs.{job_id}.authorization.authorized_at")
    if auth_time < proof_time:
        errors.append(f"{job_id}: authorization predates proof")
    if auth_artifact != artifact_sha or auth_render != render_sha:
        errors.append(f"{job_id}: authorization is not bound to exact artifact and render")
    if environment == "LIVE":
        if not approved:
            errors.append(f"{job_id}: live job lacks affirmative authorization")
        if dept_id in departments and authorizer not in departments[dept_id]["live_authorizers"]:
            errors.append(f"{job_id}: authorizer is not permitted for department")

    submission = _require_mapping(job["submission"], f"mail_jobs.{job_id}.submission")
    if set(submission) != {
        "effect_state",
        "idempotency_key",
        "provider_request_id",
        "submitted_at",
        "physical_effect",
    }:
        raise FixtureError(f"mail_jobs.{job_id}.submission has unknown or missing keys")
    effect_state = _require_nonempty_str(submission["effect_state"], f"mail_jobs.{job_id}.submission.effect_state")
    if effect_state not in ALLOWED_EFFECT_STATES:
        raise FixtureError(f"mail_jobs.{job_id}.submission.effect_state unsupported")
    idempotency_key = _require_nonempty_str(submission["idempotency_key"], f"mail_jobs.{job_id}.submission.idempotency_key")
    physical_effect = _require_bool(submission["physical_effect"], f"mail_jobs.{job_id}.submission.physical_effect")
    provider_request_id: str | None
    submitted_time: datetime | None
    if effect_state == "NONE":
        if submission["provider_request_id"] is not None or submission["submitted_at"] is not None:
            errors.append(f"{job_id}: NONE submission cannot carry provider request/time")
        provider_request_id = None
        submitted_time = None
        if physical_effect:
            errors.append(f"{job_id}: NONE submission cannot claim physical effect")
    else:
        provider_request_id = _require_nonempty_str(
            submission["provider_request_id"], f"mail_jobs.{job_id}.submission.provider_request_id"
        )
        submitted_time = _parse_time(submission["submitted_at"], f"mail_jobs.{job_id}.submission.submitted_at")
        if submitted_time < auth_time:
            errors.append(f"{job_id}: submission predates authorization")
        if effect_state == "UNKNOWN_EFFECT":
            errors.append(f"{job_id}: submission effect is unknown")

    if environment == "TEST" and physical_effect:
        errors.append(f"{job_id}: TEST environment may not create a physical effect")
    if environment == "LIVE" and effect_state == "SUBMITTED" and not physical_effect:
        errors.append(f"{job_id}: LIVE submitted job must explicitly record intended physical effect")

    events, event_errors = _validate_provider_events(
        job["provider_events"],
        job_id=job_id,
        provider_request_id=provider_request_id,
        submission_time=submitted_time,
    )
    errors.extend(event_errors)
    if events and effect_state == "NONE":
        errors.append(f"{job_id}: provider events exist without a submission")

    return (
        {
            "job_id": job_id,
            "department_id": dept_id,
            "environment": environment,
            "artifact_sha256": artifact_sha,
            "proof": {
                "artifact_sha256": proof_artifact,
                "render_sha256": render_sha,
                "observed_at": proof["observed_at"],
            },
            "authorization": {
                "approved": approved,
                "artifact_sha256": auth_artifact,
                "render_sha256": auth_render,
                "authorizer_id": authorizer,
                "authorized_at": auth["authorized_at"],
            },
            "submission": {
                "effect_state": effect_state,
                "idempotency_key": idempotency_key,
                "provider_request_id": provider_request_id,
                "submitted_at": submission["submitted_at"],
                "physical_effect": physical_effect,
            },
            "expected_cost_cents": expected_cost,
            "provider_events": events,
        },
        errors,
    )


def evaluate_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate a fixture and return a deterministic, integrity-bound receipt.

    The strongest possible result is OWNER_REVIEW.  A result never authorizes a
    bid, provider mutation, purchase, spend, signature, or City submission.
    """

    root = _require_mapping(copy.deepcopy(fixture), "fixture")
    if set(root) != {"schema_version", "contract", "departments", "mail_jobs"}:
        raise FixtureError("fixture has unknown or missing top-level keys")
    if root["schema_version"] != SCHEMA_VERSION or type(root["schema_version"]) is not int:
        raise FixtureError(f"schema_version must equal integer {SCHEMA_VERSION}")

    contract = _validate_contract(_require_mapping(root["contract"], "contract"))
    departments = _validate_departments(root["departments"])
    jobs_raw = _require_list(root["mail_jobs"], "mail_jobs")
    if not jobs_raw:
        raise FixtureError("mail_jobs must not be empty")

    jobs: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen_jobs: set[str] = set()
    seen_idempotency: set[str] = set()
    live_spend: Dict[str, int] = {dept_id: 0 for dept_id in departments}

    for raw in jobs_raw:
        job, job_errors = _validate_job(raw, departments=departments)
        job_id = job["job_id"]
        if job_id in seen_jobs:
            errors.append(f"{job_id}: duplicate job id")
        seen_jobs.add(job_id)
        idem = job["submission"]["idempotency_key"]
        if idem in seen_idempotency:
            errors.append(f"{job_id}: duplicate idempotency key {idem}")
        seen_idempotency.add(idem)
        if (
            job["environment"] == "LIVE"
            and job["submission"]["effect_state"] == "SUBMITTED"
            and job["department_id"] in live_spend
        ):
            live_spend[job["department_id"]] += job["expected_cost_cents"]
        jobs.append(job)
        errors.extend(job_errors)

    for dept_id, spend in sorted(live_spend.items()):
        budget = departments[dept_id]["budget_cents"]
        if spend > budget:
            errors.append(f"{dept_id}: live expected cost {spend} exceeds budget {budget}")

    jobs.sort(key=lambda item: item["job_id"])
    errors = sorted(set(errors))
    technical_status = "PASS" if not errors else "HOLD_CONTROL_FAILURE"
    procurement_status = "PACKET_BOUND_OWNER_REVIEW" if contract["product_spec_bound"] else "PACKET_REQUIRED"
    if errors:
        overall = "HOLD_CONTROL_FAILURE"
    elif procurement_status == "PACKET_REQUIRED":
        overall = "HOLD_PACKET_REQUIRED"
    else:
        overall = "OWNER_REVIEW"

    receipt_core: Dict[str, Any] = {
        "receipt_version": 1,
        "source_fixture_sha256": _sha256(root),
        "contract": contract,
        "technical_status": technical_status,
        "procurement_status": procurement_status,
        "overall_status": overall,
        "errors": errors,
        "counts": {
            "departments": len(departments),
            "mail_jobs": len(jobs),
            "live_submitted": sum(
                1
                for job in jobs
                if job["environment"] == "LIVE" and job["submission"]["effect_state"] == "SUBMITTED"
            ),
            "test_jobs": sum(1 for job in jobs if job["environment"] == "TEST"),
        },
        "live_expected_cost_cents_by_department": dict(sorted(live_spend.items())),
        "jobs": jobs,
        "authority": {
            "bid_submission": False,
            "provider_mutation": False,
            "purchase_or_spend": False,
            "signature_or_notarization": False,
            "city_contact": False,
            "compliance_claim": False,
            "award_or_revenue_claim": False,
        },
    }
    receipt = dict(receipt_core)
    receipt["receipt_sha256"] = _sha256(receipt_core)
    return receipt


def verify_receipt_integrity(receipt: Mapping[str, Any]) -> bool:
    """Verify self-integrity only; does not establish currentness or compliance."""

    if not isinstance(receipt, Mapping):
        return False
    digest = receipt.get("receipt_sha256")
    if not isinstance(digest, str):
        return False
    core = dict(receipt)
    core.pop("receipt_sha256", None)
    try:
        return digest == _sha256(core)
    except (TypeError, ValueError):
        return False
