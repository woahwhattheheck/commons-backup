from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

INPUT_SCHEMA = "commons-actions-evidence/v3"
OUTPUT_SCHEMA = "commons-actions-classification/v3"
POLICY_SCHEMA = "commons-actions-policy/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RUN_STATUSES = {"requested", "waiting", "pending", "queued", "in_progress", "completed"}
CONCLUSIONS = {
    "success", "failure", "cancelled", "timed_out", "action_required",
    "neutral", "skipped", "stale", "startup_failure",
}
RED_CONCLUSIONS = {"failure", "timed_out", "action_required", "stale", "startup_failure"}
ZERO_STEP_WAIT_STATUSES = {"requested", "waiting", "pending", "queued"}
POLICY_SOURCE_KINDS = {"branch_protection", "ruleset", "repository_manifest"}
MAX_REQUIRED_WORKFLOWS = 64
MAX_RUNS = 512
MAX_JOBS_PER_RUN = 512
MAX_STEPS_PER_JOB = 512
MAX_INPUT_BYTES = 8 * 1024 * 1024


class EvidenceError(ValueError):
    pass


class DuplicateKeyError(EvidenceError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def parse_json_bytes(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_INPUT_BYTES:
        raise EvidenceError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise EvidenceError("input must be UTF-8 JSON") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EvidenceError(f"non-finite JSON number is forbidden: {token}")
            ),
        )
    except DuplicateKeyError:
        raise
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON: {exc.msg}") from exc
    return _require_dict(value, "input")


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str, *, maximum: int) -> list[Any]:
    if type(value) is not list:
        raise EvidenceError(f"{label} must be an array")
    if len(value) > maximum:
        raise EvidenceError(f"{label} exceeds {maximum} entries")
    return value


def _require_text(value: Any, label: str, *, maximum: int = 256) -> str:
    if type(value) is not str:
        raise EvidenceError(f"{label} must be a string")
    text = value.strip()
    if not text:
        raise EvidenceError(f"{label} must not be empty")
    if len(text) > maximum:
        raise EvidenceError(f"{label} exceeds {maximum} characters")
    if any(ord(ch) < 32 for ch in text):
        raise EvidenceError(f"{label} contains control characters")
    return text


def _optional_text(value: Any, label: str, *, maximum: int = 256) -> str | None:
    if value is None:
        return None
    return _require_text(value, label, maximum=maximum)


def _require_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise EvidenceError(f"{label} must be an integer >= {minimum}")
    return value


def _require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise EvidenceError(f"{label} must be a boolean")
    return value


def _time(value: Any, label: str) -> datetime:
    text = _require_text(value, label, maximum=64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EvidenceError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _optional_time(value: Any, label: str) -> datetime | None:
    if value is None:
        return None
    return _time(value, label)


def _format_time(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    if value.microsecond:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_exact_fields(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise EvidenceError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
