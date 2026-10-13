from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

MAX_JSON_BYTES = 1_048_576
MAX_ITEMS = 128
MAX_TEXT = 4_096
MAX_SAFE_SNIPPET = 1_024

_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class ControlError(ValueError):
    """Raised when an input cannot satisfy the control-plane contract."""


class DuplicateKeyError(ControlError):
    """Raised when strict JSON contains a duplicate object key."""


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ControlError(f"non-finite JSON number is not allowed: {value}")


def _require_unicode_scalars(value: str, label: str) -> str:
    for char in value:
        code = ord(char)
        if 0xD800 <= code <= 0xDFFF:
            raise ControlError(f"{label} contains non-scalar Unicode")
    return value


def parse_json_bytes(data: bytes, *, label: str = "json") -> Any:
    if type(data) is not bytes:
        raise ControlError(f"{label} must be bytes")
    if len(data) > MAX_JSON_BYTES:
        raise ControlError(f"{label} exceeds {MAX_JSON_BYTES} bytes")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ControlError(f"{label} is not strict UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_object,
            parse_constant=_reject_constant,
        )
    except DuplicateKeyError:
        raise
    except ControlError:
        raise
    except json.JSONDecodeError as exc:
        raise ControlError(f"{label} is not valid strict JSON: {exc.msg}") from exc
    except (ValueError, TypeError, RecursionError) as exc:
        raise ControlError(
            f"{label} is not valid strict JSON: {type(exc).__name__}"
        ) from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return format_timestamp(value)
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ControlError("canonical JSON object keys must be strings")
            _require_unicode_scalars(key, "canonical JSON object key")
            converted[key] = _jsonable(item)
        return converted
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if type(value) is str:
        return _require_unicode_scalars(value, "canonical JSON string")
    if value is None or type(value) in {bool, int, float}:
        return value
    raise ControlError(f"value contains unsupported canonical JSON type: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return (text + "\n").encode("utf-8")
    except ControlError:
        raise
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise ControlError(f"value is not canonical-JSON serializable: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    if type(data) is not bytes:
        raise ControlError("sha256 input must be bytes")
    return hashlib.sha256(data).hexdigest()


def digest_object(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def require_object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ControlError(f"{label} must be an object")
    return value


def require_exact_keys(
    value: Mapping[str, Any],
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
    label: str,
) -> None:
    required_set = set(required)
    optional_set = set(optional)
    keys = set(value)
    missing = sorted(required_set - keys)
    extra = sorted(keys - required_set - optional_set)
    if missing:
        raise ControlError(f"{label} missing keys: {', '.join(missing)}")
    if extra:
        raise ControlError(f"{label} has unknown keys: {', '.join(extra)}")


def require_list(value: Any, label: str, *, max_items: int = MAX_ITEMS) -> list[Any]:
    if type(value) is not list:
        raise ControlError(f"{label} must be an array")
    if len(value) > max_items:
        raise ControlError(f"{label} has more than {max_items} items")
    return value


def require_string(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    maximum: int = MAX_TEXT,
    allow_newlines: bool = False,
) -> str:
    if type(value) is not str:
        raise ControlError(f"{label} must be a string")
    _require_unicode_scalars(value, label)
    if not minimum <= len(value) <= maximum:
        raise ControlError(f"{label} length must be {minimum}..{maximum}")
    for char in value:
        code = ord(char)
        if code == 0 or (code < 32 and not (allow_newlines and char == "\n")) or code == 127:
            raise ControlError(f"{label} contains a control character")
    if "\r" in value:
        raise ControlError(f"{label} must not contain carriage returns")
    return value


def require_ref(value: Any, label: str) -> str:
    text = require_string(value, label, maximum=128)
    if not _REF_RE.fullmatch(text):
        raise ControlError(f"{label} is not an opaque reference")
    return text


def require_sha256(value: Any, label: str) -> str:
    text = require_string(value, label, minimum=64, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise ControlError(f"{label} must be a lowercase SHA-256 hex digest")
    return text


def require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ControlError(f"{label} must be a JSON boolean")
    return value


def require_int(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = 2_147_483_647,
) -> int:
    if type(value) is not int:
        raise ControlError(f"{label} must be a JSON integer")
    if not minimum <= value <= maximum:
        raise ControlError(f"{label} must be in {minimum}..{maximum}")
    return value


def require_enum(value: Any, allowed: set[str], label: str) -> str:
    text = require_string(value, label, maximum=128)
    if text not in allowed:
        raise ControlError(f"{label} must be one of: {', '.join(sorted(allowed))}")
    return text


def require_timestamp(value: Any, label: str) -> datetime:
    text = require_string(value, label, minimum=20, maximum=20)
    if not _TIMESTAMP_RE.fullmatch(text):
        raise ControlError(f"{label} must use canonical UTC seconds (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ControlError(f"{label} is not a real UTC timestamp") from exc
    if format_timestamp(parsed) != text:
        raise ControlError(f"{label} is not canonical UTC")
    return parsed


def format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise ControlError("timestamp value must be datetime")
    if value.tzinfo is None:
        raise ControlError("timestamp value must be timezone-aware")
    utc = value.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def require_ref_list(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    items = require_list(value, label)
    if not allow_empty and not items:
        raise ControlError(f"{label} must not be empty")
    parsed = [require_ref(item, f"{label}[{index}]") for index, item in enumerate(items)]
    require_unique(parsed, label)
    return parsed


def require_unique(values: Sequence[Any], label: str) -> None:
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            raise ControlError(f"{label} contains duplicate value: {value!r}")
        seen.add(value)


def sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def ensure_finite(value: Any, label: str) -> None:
    if type(value) is float and not math.isfinite(value):
        raise ControlError(f"{label} must be finite")
