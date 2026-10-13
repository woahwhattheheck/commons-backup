"""Closed schema primitives for the agentic evaluation evidence gate."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = 2
RECEIPT_SCHEMA_VERSION = 2
DECISION_RELEASE = "RELEASE_CANDIDATE"
DECISION_HOLD = "HOLD"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_CATEGORIES = {"NORMAL", "TOOL_USING", "ADVERSARIAL", "DEGRADED_OBSERVABILITY"}
_ALLOWED_EFFECTS = {"READ_ONLY", "LOCAL_MUTATION", "EXTERNAL_SIDE_EFFECT"}
_ALLOWED_TOOL_RESULT = {"SUCCESS", "FAILURE", "UNKNOWN"}
_ALLOWED_PASSFAIL = {"PASS", "FAIL"}
_ALLOWED_SAFETY = {"PASS", "FAIL", "UNKNOWN"}
_ALLOWED_OBSERVABILITY = {"COMPLETE", "DEGRADED", "MISSING"}

_TOP_KEYS = {
    "schema_version",
    "evaluation_id",
    "evaluation_set",
    "agent_build",
    "rubric",
    "policy",
    "scenarios",
}
_ESET_KEYS = {"set_id", "generation", "sha256", "required_scenarios"}
_BUILD_KEYS = {"agent_id", "version", "sha256"}
_RUBRIC_KEYS = {"rubric_id", "generation", "sha256", "minimum_score_bps"}
_POLICY_KEYS = {
    "max_evidence_age_seconds",
    "require_human_review",
    "require_complete_observability",
}
_SCENARIO_KEYS = {
    "scenario_id",
    "category",
    "agent_build_sha256",
    "rubric_sha256",
    "trace_sha256",
    "result_sha256",
    "evidence_at",
    "automated_result",
    "human_review",
    "safety",
    "observability",
    "tool_calls",
}
_AUTOMATED_KEYS = {
    "scenario_id",
    "status",
    "score_bps",
    "observed_at",
    "evaluator_sha256",
    "agent_build_sha256",
    "rubric_sha256",
    "trace_sha256",
    "result_sha256",
}
_REVIEW_KEYS = {
    "scenario_id",
    "review_id",
    "reviewer_role",
    "decision",
    "decided_at",
    "agent_build_sha256",
    "rubric_sha256",
    "trace_sha256",
    "result_sha256",
}
_SAFETY_KEYS = {
    "scenario_id",
    "status",
    "checks_sha256",
    "observed_at",
    "agent_build_sha256",
    "trace_sha256",
    "result_sha256",
}
_OBS_KEYS = {
    "scenario_id",
    "status",
    "pointer_sha256",
    "observed_at",
    "trace_sha256",
    "result_sha256",
}
_TOOL_KEYS = {
    "scenario_id",
    "call_id",
    "tool",
    "action",
    "effect_class",
    "result_status",
    "trace_sha256",
    "result_sha256",
}

_REASON_ORDER = [
    "INVALID_SCHEMA_VERSION",
    "INVALID_EVALUATION_ID",
    "INVALID_EVALUATION_SET",
    "INVALID_AGENT_BUILD",
    "INVALID_RUBRIC",
    "INVALID_POLICY",
    "INVALID_SCENARIO",
    "DUPLICATE_SCENARIO_ID",
    "SCENARIO_UNIVERSE_MISMATCH",
    "SCENARIO_BINDING_MISMATCH",
    "AGENT_BUILD_MISMATCH",
    "RUBRIC_MISMATCH",
    "TRACE_BINDING_MISMATCH",
    "RESULT_BINDING_MISMATCH",
    "FUTURE_EVIDENCE",
    "STALE_EVIDENCE",
    "AUTOMATED_SCORE_BELOW_THRESHOLD",
    "AUTOMATED_EVALUATION_FAILED",
    "HUMAN_REVIEW_MISSING",
    "HUMAN_REVIEW_FAILED",
    "SAFETY_UNKNOWN",
    "SAFETY_FAILED",
    "OBSERVABILITY_INCOMPLETE",
    "TOOL_RESULT_UNKNOWN",
    "TOOL_RESULT_FAILED",
]


class EvidenceError(ValueError):
    """Raised when evidence cannot be interpreted without ambiguity."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def sha256_object(value: Any) -> str:
    """Return the SHA-256 of canonical JSON bytes."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_dict(value: Any, *, name: str, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{name}: expected object")
    unknown = set(value) - keys
    missing = keys - set(value)
    if unknown or missing:
        raise EvidenceError(
            f"{name}: keys mismatch missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    return value


def _require_str(value: Any, *, name: str, allowed: set[str] | None = None) -> str:
    if type(value) is not str or not value:
        raise EvidenceError(f"{name}: expected non-empty string")
    if allowed is not None and value not in allowed:
        raise EvidenceError(f"{name}: invalid value")
    return value


def _require_id(value: Any, *, name: str) -> str:
    text = _require_str(value, name=name)
    if not _ID_RE.fullmatch(text):
        raise EvidenceError(f"{name}: invalid identifier")
    return text


def _require_sha(value: Any, *, name: str) -> str:
    text = _require_str(value, name=name)
    if not _SHA_RE.fullmatch(text):
        raise EvidenceError(f"{name}: invalid sha256")
    return text


def _require_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise EvidenceError(f"{name}: expected integer in [{minimum}, {maximum}]")
    return value


def _require_bool(value: Any, *, name: str) -> bool:
    if type(value) is not bool:
        raise EvidenceError(f"{name}: expected boolean")
    return value


def _parse_utc(value: Any, *, name: str) -> datetime:
    text = _require_str(value, name=name)
    if not text.endswith("Z"):
        raise EvidenceError(f"{name}: must be UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{name}: invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise EvidenceError(f"{name}: must be UTC")
    canonical = parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if text != canonical:
        raise EvidenceError(f"{name}: non-canonical timestamp")
    return parsed


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceError("evaluation instant must be timezone-aware")
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _validate_time(
    value: Any,
    *,
    name: str,
    evaluated_at: datetime,
    max_age_seconds: int,
    reasons: set[str],
) -> datetime:
    observed = _parse_utc(value, name=name)
    if observed > evaluated_at:
        reasons.add("FUTURE_EVIDENCE")
    elif int((evaluated_at - observed).total_seconds()) > max_age_seconds:
        reasons.add("STALE_EVIDENCE")
    return observed


def _bound_sha(
    value: Any,
    *,
    expected: str,
    name: str,
    reason: str,
    reasons: set[str],
) -> str:
    actual = _require_sha(value, name=name)
    if actual != expected:
        reasons.add(reason)
    return actual


def _ordered_reasons(reasons: Iterable[str]) -> list[str]:
    values = set(reasons)
    known = [reason for reason in _REASON_ORDER if reason in values]
    unknown = sorted(values - set(_REASON_ORDER))
    return known + unknown
