"""Strict bounded JSON, timestamps, and digests."""

from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Tuple
from .constants import MAX_BYTES, MAX_DEPTH, MAX_NODES
from .errors import PacemakerError

UTC = dt.timezone.utc

def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)

def iso(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_time(value: str, label: str = "timestamp") -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PacemakerError(f"{label} must be canonical UTC seconds")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise PacemakerError(f"{label} must be canonical UTC seconds") from exc
    if iso(parsed) != value:
        raise PacemakerError(f"{label} is not canonical")
    return parsed

def _pairs(items: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise PacemakerError(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def validate_json(value: Any) -> None:
    nodes = 0
    stack: List[Tuple[Any, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise PacemakerError("JSON exceeds graph bounds")
        if item is None or type(item) in (str, bool, int):
            continue
        if type(item) is float:
            if not math.isfinite(item):
                raise PacemakerError("non-finite JSON number")
            continue
        if type(item) is list:
            stack.extend((child, depth + 1) for child in reversed(item))
            continue
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise PacemakerError("JSON object key must be string")
            stack.extend((child, depth + 1) for child in item.values())
            continue
        raise PacemakerError("value is outside the JSON data domain")

def canonical_json(value: Any) -> bytes:
    validate_json(value)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise PacemakerError("canonical JSON exceeds byte limit")
    return raw

def parse_json(raw: bytes) -> Any:
    if len(raw) > MAX_BYTES:
        raise PacemakerError("JSON exceeds byte limit")
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs,
                           parse_constant=lambda token: (_ for _ in ()).throw(
                               PacemakerError(f"non-finite JSON number: {token}")))
    except PacemakerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PacemakerError("invalid strict JSON") from exc
    validate_json(value)
    return value

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
