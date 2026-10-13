from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

MAX_BYTES = 1_048_576
MAX_SAFE_INT = 9_007_199_254_740_991


class ClaimError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ClaimError(f"not canonical JSON: {exc}") from exc


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_value(value: Any) -> str:
    return sha_bytes(canonical(value))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str:
            raise ClaimError("JSON object key must be a string")
        if key in out:
            raise ClaimError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _parse_int(token: str) -> int:
    if len(token.lstrip("-")) > 16:
        raise ClaimError("integer token too large")
    value = int(token, 10)
    if abs(value) > MAX_SAFE_INT:
        raise ClaimError("integer outside safe range")
    return value


def _reject_float(token: str) -> Any:
    raise ClaimError(f"floats forbidden: {token}")


def _reject_constant(token: str) -> Any:
    raise ClaimError(f"non-finite constant forbidden: {token}")


def strict_loads(text: str) -> Any:
    if type(text) is not str:
        raise ClaimError("strict_loads requires text")
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_int=_parse_int, parse_float=_reject_float, parse_constant=_reject_constant)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ClaimError(f"invalid JSON: {exc}") from exc
    reject_surrogates(value, "$")
    return value


def reject_surrogates(value: Any, where: str) -> None:
    if type(value) is str:
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
            raise ClaimError(f"{where}: lone surrogate forbidden")
    elif type(value) is list:
        for i, item in enumerate(value):
            reject_surrogates(item, f"{where}[{i}]")
    elif type(value) is dict:
        for key, item in value.items():
            reject_surrogates(key, f"{where}.<key>")
            reject_surrogates(item, f"{where}.{key}")


def exact(value: Any, keys: set[str] | frozenset[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise ClaimError(f"{where}: exact object required")
    have, want = set(value), set(keys)
    if have != want:
        raise ClaimError(f"{where}: exact keys required; missing={sorted(want-have)} extra={sorted(have-want)}")
    return value


def text(value: Any, where: str, maximum: int = 512) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise ClaimError(f"{where}: bounded nonempty string required")
    for ch in value:
        code = ord(ch)
        if code < 32 or code == 127 or 0xD800 <= code <= 0xDFFF:
            raise ClaimError(f"{where}: control/surrogate forbidden")
    return value


def enum(value: Any, allowed: frozenset[str], where: str) -> str:
    got = text(value, where, 64)
    if got not in allowed:
        raise ClaimError(f"{where}: unsupported value")
    return got


def integer(value: Any, where: str, minimum: int = 0, maximum: int = MAX_SAFE_INT) -> int:
    if type(value) is not int or not (minimum <= value <= maximum):
        raise ClaimError(f"{where}: bounded integer required")
    return value


def sha256(value: Any, where: str) -> str:
    got = text(value, where, 64)
    if len(got) != 64 or any(ch not in "0123456789abcdef" for ch in got):
        raise ClaimError(f"{where}: lowercase sha256 required")
    return got


def git_sha(value: Any, where: str) -> str:
    got = text(value, where, 40)
    if len(got) != 40 or any(ch not in "0123456789abcdef" for ch in got):
        raise ClaimError(f"{where}: 40-char lowercase git sha required")
    return got


def repo(value: Any, where: str) -> str:
    got = text(value, where, 160)
    if got.count("/") != 1:
        raise ClaimError(f"{where}: owner/name repository required")
    owner, name = got.split("/", 1)
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not owner or not name or any(ch not in allowed for ch in owner + name):
        raise ClaimError(f"{where}: unsafe repository")
    return got


def utc(value: Any, where: str) -> tuple[str, datetime]:
    if type(value) is not str or len(value) != 20 or not value.endswith("Z"):
        raise ClaimError(f"{where}: whole-second UTC RFC3339 Z required")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ClaimError(f"{where}: invalid timestamp") from exc
    return value, dt


def nullable_utc(value: Any, where: str) -> tuple[str | None, datetime | None]:
    if value is None:
        return None, None
    return utc(value, where)
