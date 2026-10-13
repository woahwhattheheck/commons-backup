from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

INPUT_SCHEMA = "commons-commercial-experiment-input/v1"
PACKET_SCHEMA = "commons-commercial-experiment-packet/v1"
RECEIPT_SCHEMA = "commons-commercial-experiment-receipt/v1"
READY = "COMMERCIAL_EXPERIMENT_PACKET_READY_FOR_HUMAN_REVIEW"
UPSTREAM_READY = "FUNNEL_PACKET_READY_FOR_HUMAN_REVIEW"
FAMILIES = ("PRODUCT", "SERVICE", "EXPERTISE", "DATA")
STAGES = ("TRAFFIC", "REPLY", "ACCEPTANCE", "DELIVERY", "TRANSFER", "CASH")
STAGE_INDEX = {stage: i for i, stage in enumerate(STAGES)}
MAX_ARMS = 32
MAX_OPPORTUNITIES = 10_000
MAX_STRING = 512
MAX_SAFE_INT = 9_000_000_000_000_000
MAX_ASSIGNMENT_AGE_SECONDS = 366 * 24 * 60 * 60

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SENSITIVE_RE = re.compile(
    r"(?i)(?:\bBearer\s+[A-Za-z0-9._~+/-]+=*|"
    r"(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{8,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|"
    r"\b\d{3}-\d{2}-\d{4}\b)"
)


class LabError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_loads(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise LabError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(value: str) -> None:
        raise LabError(f"non-finite JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)
    except LabError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise LabError("invalid JSON") from exc


def validate_json_scalars(value: Any, field: str = "$") -> None:
    if value is None:
        return
    if isinstance(value, bool):
        raise LabError(f"{field} booleans are not accepted in v1")
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INT:
            raise LabError(f"{field} integer exceeds safe bound")
        return
    if isinstance(value, float):
        raise LabError(f"{field} floats are not accepted")
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            raise LabError(f"{field} string too long")
        if "\x00" in value:
            raise LabError(f"{field} contains NUL")
        if SENSITIVE_RE.search(value):
            raise LabError(f"{field} contains secret/PII-shaped text")
        return
    if isinstance(value, list):
        if len(value) > MAX_OPPORTUNITIES:
            raise LabError(f"{field} array too large")
        for i, item in enumerate(value):
            validate_json_scalars(item, f"{field}[{i}]")
        return
    if isinstance(value, dict):
        if len(value) > MAX_OPPORTUNITIES:
            raise LabError(f"{field} object too large")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise LabError(f"{field} invalid key")
            validate_json_scalars(item, f"{field}.{key}")
        return
    raise LabError(f"{field} unsupported JSON type")


def exact_keys(value: Any, *, required: Iterable[str], optional: Iterable[str] = (), field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise LabError(f"{field} must be an object")
    required_set = set(required)
    allowed = required_set | set(optional)
    keys = set(value)
    missing = required_set - keys
    unknown = keys - allowed
    if missing:
        raise LabError(f"{field} missing keys: {sorted(missing)}")
    if unknown:
        raise LabError(f"{field} unknown keys: {sorted(unknown)}")
    return value


def require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise LabError(f"{field} invalid id")
    return value


def require_slug(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise LabError(f"{field} invalid slug")
    if SENSITIVE_RE.search(value):
        raise LabError(f"{field} contains secret/PII-shaped text")
    return value


def require_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LabError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise LabError(f"{field} outside [{minimum}, {maximum}]")
    return value


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise LabError(f"{field} must be UTC RFC3339 seconds ending Z")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise LabError(f"{field} invalid timestamp") from exc


def utc_now_seconds() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_source(value: Any, field: str) -> dict[str, str]:
    source = exact_keys(value, required=("repository", "commit", "path", "sha256"), field=field)
    repository = source["repository"]
    commit = source["commit"]
    path = source["path"]
    digest = source["sha256"]
    if not isinstance(repository, str) or not REPO_RE.fullmatch(repository):
        raise LabError(f"{field}.repository invalid")
    if not isinstance(commit, str) or not HEX40.fullmatch(commit):
        raise LabError(f"{field}.commit must be lowercase full SHA")
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise LabError(f"{field}.sha256 must be lowercase SHA-256")
    if not isinstance(path, str) or not path or len(path) > 240 or path.startswith("/") or "\\" in path:
        raise LabError(f"{field}.path invalid")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise LabError(f"{field}.path traversal/empty segment")
    if SENSITIVE_RE.search(repository) or SENSITIVE_RE.search(path):
        raise LabError(f"{field} contains secret/PII-shaped text")
    return {"repository": repository, "commit": commit, "path": path, "sha256": digest}


def authority_ceiling() -> dict[str, bool]:
    return {
        "buyer_contact_authorized": False,
        "send_or_resend_authorized": False,
        "mailbox_crm_or_provider_mutation_authorized": False,
        "calendar_booking_authorized": False,
        "proposal_or_bid_submission_authorized": False,
        "contract_or_signature_authorized": False,
        "pricing_commitment_authorized": False,
        "payment_request_or_collection_authorized": False,
        "bank_or_wallet_action_authorized": False,
        "fulfillment_authorized": False,
        "cash_availability_asserted": False,
        "accounting_or_tax_authority": False,
        "revenue_recognition_authorized": False,
    }
