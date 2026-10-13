from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

INPUT_SCHEMA = "commons-commercial-funnel-input/v1"
PACKET_SCHEMA = "commons-commercial-funnel-packet/v1"
RECEIPT_SCHEMA = "commons-commercial-funnel-receipt/v1"
READY = "FUNNEL_PACKET_READY_FOR_HUMAN_REVIEW"
HOLD = "HOLD"
FAMILIES = ("PRODUCT", "SERVICE", "EXPERTISE", "DATA")
STAGES = ("TRAFFIC", "REPLY", "ACCEPTANCE", "DELIVERY", "TRANSFER", "CASH")
SPECIAL_STAGES = ("NONCASH_AWARD", "CASH_REVERSAL")
ALL_STAGES = set(STAGES) | set(SPECIAL_STAGES)
STAGE_INDEX = {stage: i for i, stage in enumerate(STAGES)}
MAX_EVIDENCE_AGE_SECONDS = 366 * 24 * 60 * 60
MAX_OPPORTUNITIES = 10_000
MAX_EVENTS_PER_OPPORTUNITY = 5_000
MAX_MINOR_UNITS = 9_000_000_000_000_000

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SECRET_RE = re.compile(r"(?i)(?:\bBearer\s+[A-Za-z0-9._~+/-]+=*|(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{8,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)")
BLOCKED_KEY_PARTS = {"email", "phone", "telephone", "mobile", "address", "street", "ssn", "social_security", "dob", "date_of_birth", "password", "passwd", "secret", "token", "api_key", "private_key", "authorization", "cookie"}


class FunnelError(ValueError):
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
                raise FunnelError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(value: str) -> None:
        raise FunnelError(f"non-finite JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)
    except FunnelError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise FunnelError("invalid JSON") from exc


def exact_keys(value: Any, *, required: Iterable[str], optional: Iterable[str] = (), field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise FunnelError(f"{field} must be an object")
    required_set = set(required)
    allowed = required_set | set(optional)
    keys = set(value)
    missing = required_set - keys
    unknown = keys - allowed
    if missing:
        raise FunnelError(f"{field} missing keys: {sorted(missing)}")
    if unknown:
        raise FunnelError(f"{field} unknown keys: {sorted(unknown)}")
    return value


def require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise FunnelError(f"{field} invalid")
    safe_text(value, field)
    return value


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise FunnelError(f"{field} must be UTC RFC3339 seconds ending Z")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise FunnelError(f"{field} invalid timestamp") from exc


def require_int(value: Any, field: str, *, minimum: int = 0, maximum: int = MAX_MINOR_UNITS) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise FunnelError(f"{field} must be integer in [{minimum}, {maximum}]")
    return value


def safe_text(value: str, field: str) -> None:
    if SECRET_RE.search(value) or EMAIL_RE.search(value) or SSN_RE.search(value) or PHONE_RE.search(value):
        raise FunnelError(f"{field} contains secret/PII-shaped value")


def validate_json_scalars(value: Any, path: str = "$") -> None:
    # Generic traversal enforces JSON type safety and blocked field names only.
    # Field-aware validators scan human text/identifiers for secret/PII shapes;
    # opaque cryptographic digests are intentionally exempt from heuristic scans.
    if value is None or type(value) in (str, bool, int):
        return
    if isinstance(value, float):
        raise FunnelError(f"{path} floats are not allowed")
    if isinstance(value, list):
        for i, item in enumerate(value):
            validate_json_scalars(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise FunnelError(f"{path} contains non-string key")
            normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            parts = set(normalized.split("_"))
            if normalized in BLOCKED_KEY_PARTS or parts & BLOCKED_KEY_PARTS:
                raise FunnelError(f"{path}.{key} is a blocked secret/PII-shaped field")
            validate_json_scalars(item, f"{path}.{key}")
        return
    raise FunnelError(f"{path} contains unsupported JSON type")


def validate_source(value: Any, field: str) -> dict[str, str]:
    source = exact_keys(value, required=("repository", "commit", "path", "sha256"), field=field)
    repository = source["repository"]
    if not isinstance(repository, str) or not REPO_RE.fullmatch(repository):
        raise FunnelError(f"{field}.repository invalid")
    safe_text(repository, f"{field}.repository")
    # GitHub owner/repository identity is case-insensitive. Canonicalize at the
    # single source-validation boundary so every downstream authority map,
    # event dedupe path, and logical-offer comparison consumes one identity.
    repository = repository.casefold()
    commit = source["commit"]
    if not isinstance(commit, str) or not HEX40.fullmatch(commit):
        raise FunnelError(f"{field}.commit must be immutable lowercase 40-hex commit")
    path = source["path"]
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path or "\x00" in path or any(part in ("", ".", "..") for part in path.split("/")) or len(path) > 512:
        raise FunnelError(f"{field}.path invalid")
    safe_text(path, f"{field}.path")
    digest = source["sha256"]
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise FunnelError(f"{field}.sha256 must be lowercase sha256")
    return {"repository": repository, "commit": commit, "path": path, "sha256": digest}


def validate_money(value: Any, field: str) -> dict[str, Any]:
    money = exact_keys(value, required=("currency", "minor_units"), field=field)
    currency = money["currency"]
    if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
        raise FunnelError(f"{field}.currency must be uppercase 3-letter code")
    return {"currency": currency, "minor_units": require_int(money["minor_units"], f"{field}.minor_units", minimum=1)}


def validate_noncash(value: Any, field: str) -> dict[str, Any]:
    award = exact_keys(value, required=("asset", "quantity"), field=field)
    return {"asset": require_id(award["asset"], f"{field}.asset"), "quantity": require_int(award["quantity"], f"{field}.quantity", minimum=1)}
