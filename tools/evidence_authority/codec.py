"""Strict UTF-8 JSON, scalar validation, and canonical digest helpers.

Isolated: no Commons imports. Local default-argument bindings keep the
parser fail-closed under ordinary module rebinding and real `python -O`.
"""

from __future__ import annotations

from datetime import datetime as _DateTime, timezone as _Timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

SCHEMA_CANDIDATE = "evidence-authority-candidate/v1"
SCHEMA_MANIFEST = "evidence-authority-manifest/v1"
SCHEMA_RECORD = "evidence-authority-record/v1"
SCHEMA_RECEIPT = "evidence-authority-receipt/v1"
SCHEMA_FACT = "evidence-authority-fact/v1"
IMPLEMENTATION_CONTRACT = "evidence-authority/v1"

AUTHORITY_CLASSES = ("PROVIDER_AUTHENTICATED", "BUYER_AUTHENTICATED")
CLAIM_SCOPES = ("ACCOUNT", "PRODUCT", "MODEL", "SESSION", "OPPORTUNITY")
CURRENTNESS = (
    "CURRENT_POSITIVE",
    "HISTORICAL_INTEGRITY",
    "NOT_YET_VALID",
    "EXPIRED",
    "HOLD",
)
STATUSES = ("MATCHED", "HOLD")

MAX_SOURCES = 32
MAX_BYTES = 65536
MAX_DEPTH = 8
MAX_INTEGER_ABS = 10**15
MAX_PAYLOAD_KEYS = 32

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class GateError(ValueError):
    """Domain error: malformed input or closed-contract violation."""


def _reject_constant(value: str) -> None:
    raise GateError(f"non-finite JSON number is forbidden: {value}")


def _require_unicode_scalar_text(value: str, where: str) -> None:
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise GateError(f"{where} contains invalid Unicode scalar") from exc
    for char in value:
        cp = ord(char)
        if 0xD800 <= cp <= 0xDFFF:
            raise GateError(f"{where} contains invalid Unicode scalar")


def _pairs_no_duplicates(
    pairs: Iterable[tuple[str, Any]],
    _scalar=_require_unicode_scalar_text,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str:
            raise GateError("JSON object key must be a string")
        _scalar(key, "JSON object key")
        if key in out:
            raise GateError("duplicate JSON key")
        out[key] = value
    return out


def _parse_int(token: str, _max=MAX_INTEGER_ABS) -> int:
    negative = token.startswith("-")
    digits = token[1:] if negative else token
    if not digits or not digits.isdigit():
        raise GateError("invalid JSON integer")
    if len(digits) > len(str(_max)):
        raise GateError("integer token exceeds bound")
    try:
        value = int(token)
    except (TypeError, ValueError, OverflowError) as exc:
        raise GateError("integer token exceeds bound") from exc
    if abs(value) > _max:
        raise GateError("integer token exceeds bound")
    return value


def loads_strict_json(
    data: str | bytes,
    *,
    _loads=json.loads,
    _pairs=_pairs_no_duplicates,
    _constant=_reject_constant,
    _int=_parse_int,
    _max_bytes=MAX_BYTES,
) -> Any:
    """Parse strict UTF-8 JSON. Duplicate keys, NaN/Infinity, huge ints fail closed."""
    if type(data) is bytes:
        if len(data) > _max_bytes:
            raise GateError("input exceeds byte bound")
        try:
            data = data.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise GateError("input is not strict UTF-8") from exc
    elif type(data) is str:
        try:
            raw = data.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise GateError("input contains invalid Unicode scalar") from exc
        if len(raw) > _max_bytes:
            raise GateError("input exceeds byte bound")
    else:
        raise GateError("JSON input must be str or bytes")
    try:
        return _loads(
            data,
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_int=_int,
        )
    except GateError:
        raise
    except RecursionError as exc:
        raise GateError("JSON nesting exceeds bound") from exc
    except (json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        raise GateError(f"invalid JSON: {exc}") from exc


def _canonical_bytes(
    value: Any,
    _dumps=json.dumps,
    _max_bytes=MAX_BYTES,
) -> bytes:
    try:
        text = _dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        payload = text.encode("utf-8", "strict")
    except RecursionError as exc:
        raise GateError("value cannot be canonicalized as strict UTF-8 JSON") from exc
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError) as exc:
        raise GateError("value cannot be canonicalized as strict UTF-8 JSON") from exc
    if len(payload) > _max_bytes:
        raise GateError("canonical JSON exceeds byte bound")
    return payload


def sha256_bytes(data: bytes, _sha256=hashlib.sha256) -> str:
    if type(data) is not bytes:
        raise GateError("digest input must be exact bytes")
    return _sha256(data).hexdigest()


def sha256_value(value: Any, _canonical=_canonical_bytes, _sha256=hashlib.sha256) -> str:
    return _sha256(_canonical(value)).hexdigest()


def require_exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    if not isinstance(value, dict):
        raise GateError(f"{where} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise GateError(f"{where} keys mismatch: missing={missing} extra={extra}")


def require_text(
    value: Any,
    where: str,
    *,
    _scalar=_require_unicode_scalar_text,
) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GateError(f"{where} must be a non-empty trimmed string")
    _scalar(value, where)
    if "\x00" in value:
        raise GateError(f"{where} contains NUL")
    return value


def require_id(value: Any, where: str, _text=require_text, _re=_ID_RE) -> str:
    text = _text(value, where)
    if not _re.fullmatch(text):
        raise GateError(f"{where} is not a bounded identity token")
    return text


def require_sha256(value: Any, where: str, _text=require_text, _re=_SHA256_RE) -> str:
    text = _text(value, where)
    if not _re.fullmatch(text):
        raise GateError(f"{where} must be lowercase SHA-256 hex")
    return text


def require_path(value: Any, where: str, _text=require_text, _re=_PATH_RE) -> str:
    text = _text(value, where)
    if (
        not _re.fullmatch(text)
        or text.startswith("/")
        or text.startswith("./")
        or ".." in text.split("/")
        or "//" in text
        or text.endswith("/")
        or "\\" in text
    ):
        raise GateError(f"{where} is not a closed relative source path")
    return text


def require_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise GateError(f"{where} must be a JSON boolean")
    return value


def parse_ts(
    value: Any,
    where: str,
    _text=require_text,
    _datetime=_DateTime,
    _utc=_Timezone.utc,
    _fmt=_TS_FORMAT,
) -> _DateTime:
    text = _text(value, where)
    try:
        parsed = _datetime.strptime(text, _fmt).replace(tzinfo=_utc)
    except ValueError as exc:
        raise GateError(f"{where} must be canonical UTC YYYY-MM-DDTHH:MM:SSZ") from exc
    if _format_ts(parsed) != text:
        raise GateError(f"{where} must be canonical UTC YYYY-MM-DDTHH:MM:SSZ")
    return parsed


def format_ts(value: _DateTime, _utc=_Timezone.utc, _fmt=_TS_FORMAT) -> str:
    if value.tzinfo is None:
        raise GateError("internal timestamp is timezone-naive")
    return value.astimezone(_utc).replace(microsecond=0).strftime(_fmt)


_format_ts = format_ts


def bounded_payload(value: Any, where: str, *, depth: int = 0, _max_depth=MAX_DEPTH) -> Any:
    """Admit only plain JSON for claim payloads. Bool/int aliases fail closed."""
    if depth > _max_depth:
        raise GateError(f"{where} exceeds nesting bound")
    t = type(value)
    if value is None or t is bool or t is str:
        if t is str:
            require_text(value, where)
        return value
    if t is int:
        if abs(value) > MAX_INTEGER_ABS:
            raise GateError(f"{where} integer exceeds bound")
        return value
    if t is list:
        if len(value) > MAX_PAYLOAD_KEYS:
            raise GateError(f"{where} array exceeds bound")
        return [bounded_payload(item, f"{where}[{i}]", depth=depth + 1) for i, item in enumerate(value)]
    if t is dict:
        if len(value) > MAX_PAYLOAD_KEYS:
            raise GateError(f"{where} object exceeds bound")
        out: dict[str, Any] = {}
        for key in sorted(value):
            require_text(key, f"{where} key")
            out[key] = bounded_payload(value[key], f"{where}.{key}", depth=depth + 1)
        return out
    raise GateError(f"{where} is not plain JSON")
