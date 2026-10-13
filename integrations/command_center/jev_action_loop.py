"""Deterministic Jev action-loop receipts for provider-state routing.

This module is intentionally transport-agnostic.  Connectors perform reads/writes;
this code decides whether a provider observation is current enough to route, gives
the write a stable operation id, and verifies a later provider readback before the
write is considered confirmed.

It does not authenticate Slack/GitHub data by itself.  Callers must populate the
observations and readbacks from installed service connectors.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA = "commons.jev_action_loop/v1"
PLAN_SCHEMA = "commons.jev_action_loop.plan/v1"
RECEIPT_SCHEMA = "commons.jev_action_loop.receipt/v1"
VERIFICATION_SCHEMA = "commons.jev_action_loop.verification/v1"

PROVIDERS = {"slack", "github", "commons", "ci"}
STATUSES = {
    "OPEN", "QUEUED", "IN_PROGRESS", "ACTION_REQUIRED",
    "MERGED", "CLOSED_UNMERGED", "SUCCESS", "FAILURE",
    "SENT", "READBACK_CONFIRMED", "DELIVERY_UNCERTAIN", "UNKNOWN",
}
TERMINAL = {"MERGED", "CLOSED_UNMERGED", "SUCCESS", "FAILURE", "READBACK_CONFIRMED"}
UNCERTAIN = {"DELIVERY_UNCERTAIN", "UNKNOWN"}
NONTERMINAL = STATUSES - TERMINAL - UNCERTAIN
ACTIONS = {"ROUTE_SLACK", "POST_DIGEST", "OPEN_FOLLOWUP", "UPDATE_SHARED_VIEW", "NO_ACTION"}
RECEIPT_OUTCOMES = {"CONFIRMED", "DELIVERY_UNCERTAIN", "REJECTED"}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#@+-]{0,255}\Z")
HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
MAX_JSON_BYTES = 1024 * 1024
MAX_OBSERVATIONS = 512
MAX_RECEIPTS = 256


class ActionLoopError(ValueError):
    """Malformed or semantically contradictory action-loop input."""


def _strict_fields(obj: Any, fields: set[str], where: str) -> dict[str, Any]:
    if type(obj) is not dict or set(obj) != fields:
        raise ActionLoopError(f"{where}: unexpected or missing fields")
    return obj


def _canonical(obj: Any) -> bytes:
    try:
        data = json.dumps(
            obj, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ActionLoopError("not canonical JSON data") from exc
    if len(data) > MAX_JSON_BYTES:
        raise ActionLoopError("canonical JSON exceeds byte limit")
    return data


def _digest(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def strict_loads(raw: bytes | str) -> Any:
    """Parse bounded JSON and reject duplicate keys and non-finite numbers."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_JSON_BYTES:
            raise ActionLoopError("input byte limit exceeded")
        try:
            raw = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ActionLoopError("invalid UTF-8") from exc
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_JSON_BYTES:
        raise ActionLoopError("input byte limit exceeded")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ActionLoopError("duplicate JSON key")
            out[key] = value
        return out

    def bad_constant(_value):
        raise ActionLoopError("non-finite JSON number")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    except ActionLoopError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ActionLoopError("invalid JSON") from exc
    _bounded(value)
    return value


def _bounded(value: Any) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 100_000 or depth > 24:
            raise ActionLoopError("JSON depth/node limit exceeded")
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or len(key) > 256:
                    raise ActionLoopError("invalid object key")
                stack.append((child, depth + 1))
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > 4096:
                raise ActionLoopError("string limit exceeded")
            try:
                item.encode("utf-8")
            except UnicodeError as exc:
                raise ActionLoopError("invalid Unicode") from exc
        elif item is None or type(item) is bool:
            continue
        elif type(item) is int:
            if not -(2**63) <= item < 2**63:
                raise ActionLoopError("integer out of range")
        else:
            raise ActionLoopError("unsupported JSON scalar")
    if len(_canonical(value)) > MAX_JSON_BYTES:
        raise ActionLoopError("input byte limit exceeded")


def _token(value: Any, where: str) -> str:
    if type(value) is not str or TOKEN_RE.fullmatch(value) is None:
        raise ActionLoopError(f"{where}: invalid identifier")
    return value


def _url(value: Any, where: str) -> str:
    if type(value) is not str or len(value) > 2048:
        raise ActionLoopError(f"{where}: invalid source url")
    if not value.startswith(("https://", "http://")):
        raise ActionLoopError(f"{where}: source url must be http(s)")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or HEX64_RE.fullmatch(value) is None:
        raise ActionLoopError(f"{where}: expected lowercase sha256")
    return value


def _stamp(value: Any, where: str) -> datetime:
    if type(value) is not str or UTC_RE.fullmatch(value) is None:
        raise ActionLoopError(f"{where}: timestamp must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ActionLoopError(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ActionLoopError(f"{where}: timestamp is not UTC")
    return parsed


def _validate_observation(raw: Any) -> dict[str, Any]:
    row = dict(_strict_fields(
        raw,
        {
            "provider", "scope", "resource_id", "event_id", "status",
            "provider_event_at", "observed_at", "source_url",
        },
        "observation",
    ))
    if row["provider"] not in PROVIDERS:
        raise ActionLoopError("observation: unsupported provider")
    _token(row["scope"], "observation.scope")
    _token(row["resource_id"], "observation.resource_id")
    _token(row["event_id"], "observation.event_id")
    if row["status"] not in STATUSES:
        raise ActionLoopError("observation: unsupported status")
    provider_at = _stamp(row["provider_event_at"], "observation.provider_event_at")
    observed_at = _stamp(row["observed_at"], "observation.observed_at")
    if provider_at > observed_at:
        raise ActionLoopError("observation: provider event is after observation")
    _url(row["source_url"], "observation.source_url")
    return row


def event_key(row: dict[str, Any]) -> str:
    """Stable immutable event identity independent of observation time."""
    validated = _validate_observation(row)
    return _digest({
        "provider": validated["provider"],
        "scope": validated["scope"],
        "event_id": validated["event_id"],
    })


def resource_key(row: dict[str, Any]) -> str:
    """Stable provider-resource identity used for chronology reconciliation."""
    validated = _validate_observation(row)
    return _digest({
        "provider": validated["provider"],
        "scope": validated["scope"],
        "resource_id": validated["resource_id"],
    })


def reconcile_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconcile one provider resource without replaying stale/uncertain state.

    Provider event time, not connector arrival order, controls chronology.
    Repeated reads of one unchanged event collapse to its latest observation.
    DELIVERY_UNCERTAIN/UNKNOWN never overwrite a later known provider state.
    Definitive transitions remain chronological (for example a closed PR may
    reopen and a failed CI run may enter a rerun). A merged GitHub PR cannot
    regress to OPEN, so that impossible transition fails closed. Conflicting
    observations at the same provider event time also fail closed.
    """
    if type(observations) is not list or not 1 <= len(observations) <= MAX_OBSERVATIONS:
        raise ActionLoopError("observations: invalid count")
    rows = [_validate_observation(row) for row in observations]
    rkeys = {resource_key(row) for row in rows}
    if len(rkeys) != 1:
        raise ActionLoopError("observations: multiple provider resources")

    exact_events: dict[str, dict[str, Any]] = {}
    for row in rows:
        ekey = event_key(row)
        previous = exact_events.get(ekey)
        if previous is not None:
            # A provider event may be read repeatedly. Observation time is
            # receipt metadata; only changes to the event itself are collisions.
            prior_event = {key: value for key, value in previous.items() if key != "observed_at"}
            current_event = {key: value for key, value in row.items() if key != "observed_at"}
            if _canonical(prior_event) != _canonical(current_event):
                raise ActionLoopError("observations: provider event identity collision")
            if _stamp(row["observed_at"], "observed_at") <= _stamp(previous["observed_at"], "observed_at"):
                continue
        exact_events[ekey] = row
    rows = list(exact_events.values())

    by_provider_time: dict[str, set[str]] = {}
    for row in rows:
        by_provider_time.setdefault(row["provider_event_at"], set()).add(row["status"])
    if any(len(statuses) > 1 for statuses in by_provider_time.values()):
        return {
            "schema": SCHEMA,
            "resource_key": next(iter(rkeys)),
            "disposition": "HOLD_CONTRADICTORY_PROVIDER_TIME",
            "effective_status": None,
            "effective_event_key": None,
            "latest_observed_event_key": event_key(max(rows, key=lambda r: (_stamp(r["observed_at"], "x"), r["event_id"]))),
            "suppressed_event_keys": [],
            "observation_count": len(rows),
        }

    rows.sort(key=lambda r: (
        _stamp(r["provider_event_at"], "provider_event_at"),
        _stamp(r["observed_at"], "observed_at"),
        r["event_id"],
    ))
    latest = rows[-1]
    definitive = [row for row in rows if row["status"] not in UNCERTAIN]
    effective = latest
    suppressed: list[str] = []
    disposition = "CURRENT"

    if latest["status"] in UNCERTAIN:
        if definitive:
            effective = definitive[-1]
            suppressed = [event_key(latest)]
            disposition = "DEFINITIVE_STATE_HELD_OVER_UNCERTAIN_READ"
        else:
            disposition = "HOLD_LATEST_PROVIDER_STATE_UNCERTAIN"
    else:
        # A merged GitHub PR is not reopenable.  Treat a later different state
        # for the same provider resource as a contradiction, not as a reason to
        # requeue work. Other definitive transitions stay chronological:
        # CLOSED_UNMERGED -> OPEN (reopen) and CI FAILURE -> QUEUED/SUCCESS are
        # legitimate new provider events.
        prior_merged = [
            row for row in rows[:-1]
            if row["provider"] == "github" and row["status"] == "MERGED"
        ]
        if prior_merged and latest["status"] != "MERGED":
            effective = prior_merged[-1]
            suppressed = [event_key(latest)]
            disposition = "HOLD_IMPOSSIBLE_PROVIDER_REGRESSION"

    latest_observed = max(
        rows,
        key=lambda r: (_stamp(r["observed_at"], "latest_observed"), r["event_id"]),
    )
    return {
        "schema": SCHEMA,
        "resource_key": next(iter(rkeys)),
        "disposition": disposition,
        "effective_status": effective["status"],
        "effective_event_key": event_key(effective),
        "latest_observed_event_key": event_key(latest_observed),
        "suppressed_event_keys": sorted(set(suppressed)),
        "observation_count": len(rows),
    }


def _validate_decision(raw: Any) -> dict[str, Any]:
    row = dict(_strict_fields(
        raw,
        {
            "model", "surface", "selected_action", "confidence_ppm",
            "answers_sha256", "decided_at",
        },
        "decision",
    ))
    _token(row["model"], "decision.model")
    _token(row["surface"], "decision.surface")
    if row["selected_action"] not in ACTIONS:
        raise ActionLoopError("decision: unsupported action")
    if type(row["confidence_ppm"]) is not int or not 0 <= row["confidence_ppm"] <= 1_000_000:
        raise ActionLoopError("decision: confidence_ppm out of range")
    _sha(row["answers_sha256"], "decision.answers_sha256")
    _stamp(row["decided_at"], "decision.decided_at")
    return row


def _validate_target(raw: Any) -> dict[str, Any]:
    row = dict(_strict_fields(
        raw, {"provider", "destination_id", "thread_id"}, "target",
    ))
    if row["provider"] not in PROVIDERS:
        raise ActionLoopError("target: unsupported provider")
    _token(row["destination_id"], "target.destination_id")
    if row["thread_id"] is not None:
        _token(row["thread_id"], "target.thread_id")
    return row


def _receipt_body(raw: Any) -> dict[str, Any]:
    row = dict(_strict_fields(
        raw,
        {
            "schema", "operation_id", "plan_sha256", "provider",
            "destination_id", "provider_resource_id",
            "provider_observed_operation_id", "source_url",
            "outcome", "attempted_at", "observed_at", "receipt_sha256",
        },
        "receipt",
    ))
    if row["schema"] != RECEIPT_SCHEMA:
        raise ActionLoopError("receipt: unsupported schema")
    _token(row["operation_id"], "receipt.operation_id")
    _sha(row["plan_sha256"], "receipt.plan_sha256")
    if row["provider"] not in PROVIDERS:
        raise ActionLoopError("receipt: unsupported provider")
    _token(row["destination_id"], "receipt.destination_id")
    if row["provider_resource_id"] is not None:
        _token(row["provider_resource_id"], "receipt.provider_resource_id")
    if row["provider_observed_operation_id"] is not None:
        _token(row["provider_observed_operation_id"], "receipt.provider_observed_operation_id")
    _url(row["source_url"], "receipt.source_url")
    if row["outcome"] not in RECEIPT_OUTCOMES:
        raise ActionLoopError("receipt: unsupported outcome")
    attempted = _stamp(row["attempted_at"], "receipt.attempted_at")
    observed = _stamp(row["observed_at"], "receipt.observed_at")
    if observed < attempted:
        raise ActionLoopError("receipt: readback predates attempted action")
    _sha(row["receipt_sha256"], "receipt.receipt_sha256")
    body = {key: value for key, value in row.items() if key != "receipt_sha256"}
    if _digest(body) != row["receipt_sha256"]:
        raise ActionLoopError("receipt: digest mismatch")
    return row


def verify_receipt(raw: Any) -> dict[str, Any]:
    """Verify semantic integrity of one provider-readback receipt.

    This proves only that the receipt is internally intact and binds an operation
    marker to a provider resource.  Provider authenticity still comes from the
    connector readback that supplied these fields.
    """
    row = _receipt_body(raw)
    confirmed = (
        row["outcome"] == "CONFIRMED"
        and row["provider_resource_id"] is not None
        and row["provider_observed_operation_id"] == row["operation_id"]
    )
    if row["outcome"] == "CONFIRMED" and not confirmed:
        raise ActionLoopError("receipt: confirmed outcome lacks exact operation readback")
    return {
        "schema": VERIFICATION_SCHEMA,
        "operation_id": row["operation_id"],
        "outcome": row["outcome"],
        "confirmed": confirmed,
        "receipt_sha256": row["receipt_sha256"],
    }


def compile_action(
    observations: list[dict[str, Any]],
    decision: dict[str, Any],
    target: dict[str, Any],
    prior_receipts: list[dict[str, Any]] | None = None,
    *,
    min_confidence_ppm: int = 700_000,
) -> dict[str, Any]:
    """Compile an idempotent action plan from provider truth + Jev decision."""
    if type(min_confidence_ppm) is not int or not 0 <= min_confidence_ppm <= 1_000_000:
        raise ActionLoopError("min_confidence_ppm out of range")
    recon = reconcile_observations(observations)
    dec = _validate_decision(decision)
    tgt = _validate_target(target)
    receipts = prior_receipts or []
    if type(receipts) is not list or len(receipts) > MAX_RECEIPTS:
        raise ActionLoopError("prior_receipts: invalid count")
    verified = [_receipt_body(item) for item in receipts]

    if recon["disposition"] in {
        "HOLD_CONTRADICTORY_PROVIDER_TIME",
        "HOLD_LATEST_PROVIDER_STATE_UNCERTAIN",
        "HOLD_IMPOSSIBLE_PROVIDER_REGRESSION",
        "DEFINITIVE_STATE_HELD_OVER_UNCERTAIN_READ",
    }:
        disposition = "HOLD_PROVIDER_STATE"
    elif dec["selected_action"] == "NO_ACTION":
        disposition = "NO_ACTION"
    elif dec["confidence_ppm"] < min_confidence_ppm:
        disposition = "HOLD_LOW_CONFIDENCE"
    else:
        disposition = "ACTION_READY"

    decision_digest = _digest(dec)
    operation_material = {
        "schema": PLAN_SCHEMA,
        "resource_key": recon["resource_key"],
        "effective_status": recon["effective_status"],
        "effective_event_key": recon["effective_event_key"],
        "decision_sha256": decision_digest,
        "target": tgt,
        "selected_action": dec["selected_action"],
    }
    operation_id = "jev16537-" + _digest(operation_material)[:40]
    plan_core = {
        **operation_material,
        "operation_id": operation_id,
        "provider_disposition": recon["disposition"],
        "confidence_ppm": dec["confidence_ppm"],
        "min_confidence_ppm": min_confidence_ppm,
    }
    plan_sha = _digest(plan_core)

    matching = [row for row in verified if row["operation_id"] == operation_id]
    if matching:
        if any(row["plan_sha256"] != plan_sha for row in matching):
            raise ActionLoopError("prior receipt operation id binds another plan generation")
        if any(verify_receipt(row)["confirmed"] for row in matching):
            disposition = "ALREADY_APPLIED"
        elif any(row["outcome"] == "DELIVERY_UNCERTAIN" for row in matching):
            disposition = "HOLD_DELIVERY_UNCERTAIN"
        elif all(row["outcome"] == "REJECTED" for row in matching):
            disposition = "RETRY_SAME_OPERATION_ID"

    final_body = {
        **plan_core,
        "disposition": disposition,
        "plan_sha256": plan_sha,
    }
    return {**final_body, "result_sha256": _digest(final_body)}


def make_readback_receipt(
    plan: dict[str, Any],
    *,
    provider_resource_id: str | None,
    provider_observed_operation_id: str | None,
    source_url: str,
    outcome: str,
    attempted_at: str,
    observed_at: str,
) -> dict[str, Any]:
    """Bind a connector action attempt to exact provider readback."""
    required = {
        "schema", "resource_key", "effective_status", "effective_event_key",
        "decision_sha256", "target", "selected_action", "operation_id",
        "disposition", "provider_disposition", "confidence_ppm",
        "min_confidence_ppm", "plan_sha256", "result_sha256",
    }
    _strict_fields(plan, required, "plan")
    verify_plan(plan)
    if plan["schema"] != PLAN_SCHEMA:
        raise ActionLoopError("plan: unsupported schema")
    _sha(plan["plan_sha256"], "plan.plan_sha256")
    _sha(plan["result_sha256"], "plan.result_sha256")
    if outcome not in RECEIPT_OUTCOMES:
        raise ActionLoopError("receipt: unsupported outcome")
    tgt = _validate_target(plan["target"])
    if provider_resource_id is not None:
        _token(provider_resource_id, "provider_resource_id")
    if provider_observed_operation_id is not None:
        _token(provider_observed_operation_id, "provider_observed_operation_id")
    _url(source_url, "source_url")
    attempted = _stamp(attempted_at, "attempted_at")
    observed = _stamp(observed_at, "observed_at")
    if observed < attempted:
        raise ActionLoopError("readback predates attempted action")
    if outcome == "CONFIRMED" and (
        provider_resource_id is None
        or provider_observed_operation_id != plan["operation_id"]
    ):
        raise ActionLoopError("confirmed readback must expose exact operation id")

    body = {
        "schema": RECEIPT_SCHEMA,
        "operation_id": plan["operation_id"],
        "plan_sha256": plan["plan_sha256"],
        "provider": tgt["provider"],
        "destination_id": tgt["destination_id"],
        "provider_resource_id": provider_resource_id,
        "provider_observed_operation_id": provider_observed_operation_id,
        "source_url": source_url,
        "outcome": outcome,
        "attempted_at": attempted_at,
        "observed_at": observed_at,
    }
    return {**body, "receipt_sha256": _digest(body)}


def verify_plan(plan: Any) -> dict[str, Any]:
    """Recompute a plan's digest and reject post-compilation mutation."""
    required = {
        "schema", "resource_key", "effective_status", "effective_event_key",
        "decision_sha256", "target", "selected_action", "operation_id",
        "disposition", "provider_disposition", "confidence_ppm",
        "min_confidence_ppm", "plan_sha256", "result_sha256",
    }
    row = dict(_strict_fields(plan, required, "plan"))
    if row["schema"] != PLAN_SCHEMA:
        raise ActionLoopError("plan: unsupported schema")
    _sha(row["resource_key"], "plan.resource_key")
    if row["effective_event_key"] is not None:
        _sha(row["effective_event_key"], "plan.effective_event_key")
    _sha(row["decision_sha256"], "plan.decision_sha256")
    _validate_target(row["target"])
    if row["selected_action"] not in ACTIONS:
        raise ActionLoopError("plan: unsupported action")
    _token(row["operation_id"], "plan.operation_id")
    if type(row["confidence_ppm"]) is not int or not 0 <= row["confidence_ppm"] <= 1_000_000:
        raise ActionLoopError("plan: confidence out of range")
    if type(row["min_confidence_ppm"]) is not int or not 0 <= row["min_confidence_ppm"] <= 1_000_000:
        raise ActionLoopError("plan: minimum confidence out of range")
    operation_material = {
        "schema": row["schema"],
        "resource_key": row["resource_key"],
        "effective_status": row["effective_status"],
        "effective_event_key": row["effective_event_key"],
        "decision_sha256": row["decision_sha256"],
        "target": row["target"],
        "selected_action": row["selected_action"],
    }
    expected_operation_id = "jev16537-" + _digest(operation_material)[:40]
    if expected_operation_id != row["operation_id"]:
        raise ActionLoopError("plan: operation id mismatch")
    core_keys = {
        "schema", "resource_key", "effective_status", "effective_event_key",
        "decision_sha256", "target", "selected_action", "operation_id",
        "provider_disposition", "confidence_ppm", "min_confidence_ppm",
    }
    expected_plan = _digest({key: row[key] for key in core_keys})
    if expected_plan != row["plan_sha256"]:
        raise ActionLoopError("plan: core digest mismatch")
    expected_result = _digest({key: value for key, value in row.items() if key != "result_sha256"})
    if expected_result != row["result_sha256"]:
        raise ActionLoopError("plan: result digest mismatch")
    return {
        "schema": VERIFICATION_SCHEMA,
        "operation_id": row["operation_id"],
        "plan_sha256": expected_plan,
        "result_sha256": expected_result,
    }


__all__ = [
    "ActionLoopError", "compile_action", "event_key", "make_readback_receipt",
    "reconcile_observations", "resource_key", "strict_loads", "verify_plan",
    "verify_receipt",
]
