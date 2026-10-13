# SPDX-License-Identifier: Apache-2.0
"""Strict JSON, numeric, identity, and hashing primitives."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

VERSION = "titan-v3-own-value-causal-ledger-gpt56-v1"
SCHEMA = "titan-v3-causal-panel/v1"
REPORT_SCHEMA = "titan-v3-causal-report/v1"
GAME_SCHEMA = "titan-v3-transition-ledger/v1"
_SHA256_LENGTH = 64

class EvidenceError(ValueError):
    """Input evidence is malformed, incomplete, detached, or non-causal."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json_strict(path: str | os.PathLike[str]) -> Any:
    """Load JSON while rejecting duplicate keys and non-finite constants."""
    def bad_constant(value: str) -> Any:
        raise EvidenceError(f"non-finite JSON constant: {value}")

    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            return json.load(
                stream,
                object_pairs_hook=_reject_duplicates,
                parse_constant=bad_constant,
            )
    except EvidenceError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot load strict JSON from {path}: {exc}") from exc


def _validate_json(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvidenceError(f"{path} contains a non-finite float")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceError(f"{path} contains a non-string object key")
            _validate_json(item, f"{path}.{key}")
        return
    raise EvidenceError(f"{path} contains a non-JSON value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Return type-preserving canonical JSON bytes for identity comparisons."""
    _validate_json(value)
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"cannot canonicalize JSON value: {exc}") from exc
    return text.encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{field} must be an object")
    return value


def _sequence(value: Any, field: str, *, length: int | None = None) -> Sequence[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{field} must be an array")
    if length is not None and len(value) != length:
        raise EvidenceError(f"{field} must contain exactly {length} entries")
    return value


def _integer(value: Any, field: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise EvidenceError(f"{field} must be >= {minimum}")
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(f"{field} must be a finite number")
    return result


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise EvidenceError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _git_sha(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise EvidenceError(f"{field} must be a lowercase 40-hex Git commit")
    return value


def _exact_equal(left: Any, right: Any) -> bool:
    return canonical_bytes(left) == canonical_bytes(right)


def _require_exact(left: Any, right: Any, message: str) -> None:
    if not _exact_equal(left, right):
        raise EvidenceError(message)


def _deep_copy(value: Any) -> Any:
    """Detach a recorder value using the same canonical JSON contract."""
    return json.loads(canonical_bytes(value).decode("utf-8"))


def _recorder_pair(value: Any, field: str) -> list[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise EvidenceError(f"{field} must be a two-entry sequence")
    items = list(value)
    if len(items) != 2:
        raise EvidenceError(f"{field} must contain exactly 2 entries")
    return items

