from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from ._constants import MAX_JSON_BYTES, MAX_STRING_BYTES, QualificationInputError, _HEX64, _ID


def _reject_constant(value: str) -> None:
    raise QualificationInputError(f"non-finite JSON constant is forbidden: {value}")


def _utf8_scalar(value: Any, name: str) -> bytes:
    if type(value) is not str:
        raise QualificationInputError(f"{name} must be text")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise QualificationInputError(f"{name} must contain valid UTF-8 scalar text") from exc


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _utf8_scalar(key, "JSON object key")
        if key in result:
            raise QualificationInputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_json_data(value: Any) -> None:
    """Validate JSON-domain types and Unicode without recursive Python traversal."""
    stack = [value]
    while stack:
        item = stack.pop()
        item_type = type(item)
        if item_type is dict:
            for key, child in item.items():
                _utf8_scalar(key, "JSON object key")
                stack.append(child)
        elif item_type is list:
            stack.extend(item)
        elif item_type is str:
            _utf8_scalar(item, "JSON string")
        elif item is None or item_type is bool or item_type is int:
            continue
        elif item_type is float:
            if not math.isfinite(item):
                raise QualificationInputError("non-finite JSON number is forbidden")
        else:
            raise QualificationInputError("input must be canonical JSON data")


def strict_json_loads(raw: bytes, name: str = "JSON") -> Any:
    if type(raw) is not bytes or len(raw) > MAX_JSON_BYTES:
        raise QualificationInputError(f"{name} must be bounded bytes")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except QualificationInputError:
        raise
    except UnicodeDecodeError as exc:
        raise QualificationInputError(f"{name} must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise QualificationInputError(f"{name} is malformed JSON") from exc
    except (ValueError, RecursionError) as exc:
        raise QualificationInputError(f"{name} is outside supported JSON limits") from exc
    _validate_json_data(value)
    return value


def _canonical_bytes(value: Any) -> bytes:
    _validate_json_data(value)
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise QualificationInputError("input must be canonical JSON data") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise QualificationInputError("canonical JSON exceeds 1 MiB")
    return raw


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _object(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise QualificationInputError(f"{name} must be an object")
    return value


def _keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    got = set(value)
    if got != expected:
        raise QualificationInputError(
            f"{name} fields mismatch; missing={sorted(expected - got)}, extra={sorted(got - expected)}"
        )


def _string(value: Any, name: str, *, max_bytes: int = MAX_STRING_BYTES) -> str:
    if type(value) is not str or not value:
        raise QualificationInputError(f"{name} must be a non-empty bounded string")
    if len(_utf8_scalar(value, name)) > max_bytes:
        raise QualificationInputError(f"{name} must be a non-empty bounded string")
    return value


def _identifier(value: Any, name: str) -> str:
    value = _string(value, name, max_bytes=128)
    if _ID.fullmatch(value) is None:
        raise QualificationInputError(f"{name} must be a canonical identifier")
    return value


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise QualificationInputError(f"{name} must be boolean")
    return value


def _hex64(value: Any, name: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise QualificationInputError(f"{name} must be lowercase 64-hex SHA-256")
    return value
