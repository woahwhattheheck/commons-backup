#!/usr/bin/env python3
"""Verify independently frozen digests for canonical expanded JSON rows.

The recipe/source digest and the expanded-row digest are intentionally separate.
A caller can therefore prove the recipe bytes are unchanged without treating that
as proof that generated expected rows are unchanged.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Any, Sequence

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class ExpandedGoldenError(ValueError):
    """Raised when expanded golden evidence is malformed or does not match."""


def _digest_literal(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ExpandedGoldenError(f"{label} must be a 64-character SHA-256 hex string")
    normalized = value.lower()
    if not _HEX64.fullmatch(normalized):
        raise ExpandedGoldenError(f"{label} must be a 64-character SHA-256 hex string")
    return normalized


def _strict_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExpandedGoldenError(f"non-finite number at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _strict_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ExpandedGoldenError(f"non-string object key at {path}")
            _strict_json(item, f"{path}.{key}")
        return
    raise ExpandedGoldenError(f"unsupported JSON value at {path}: {type(value).__name__}")


def _expected_key_tuple(expected_keys: Sequence[str]) -> tuple[str, ...]:
    if isinstance(expected_keys, (str, bytes)) or not isinstance(expected_keys, Sequence):
        raise ExpandedGoldenError("expected_keys must be a sequence of unique strings")
    keys = tuple(expected_keys)
    if any(not isinstance(key, str) for key in keys) or len(set(keys)) != len(keys):
        raise ExpandedGoldenError("expected_keys must be a sequence of unique strings")
    return tuple(sorted(keys))


def canonical_expanded_rows(rows: Sequence[dict[str, Any]]) -> bytes:
    """Return stable UTF-8 JSON bytes for a strict list of object rows."""
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise ExpandedGoldenError("rows must be a sequence of JSON objects")
    materialized = list(rows)
    for index, row in enumerate(materialized):
        if not isinstance(row, dict):
            raise ExpandedGoldenError(f"row {index} must be a JSON object")
        _strict_json(row, f"$[{index}]")
    return json.dumps(
        materialized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def verify_expanded_golden(
    rows: Sequence[dict[str, Any]],
    *,
    expected_expanded_sha256: str,
    expected_count: int,
    expected_keys: Sequence[str],
    recipe_bytes: bytes | None = None,
    expected_recipe_sha256: str | None = None,
) -> dict[str, Any]:
    """Fail closed unless rows match independently frozen expanded truth.

    Recipe evidence is optional, but it is all-or-nothing: supplying recipe bytes
    requires its own expected digest and vice versa. It never substitutes for the
    expanded-row digest.
    """
    expanded_expected = _digest_literal(expected_expanded_sha256, "expected_expanded_sha256")
    if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 0:
        raise ExpandedGoldenError("expected_count must be a non-negative integer")
    keys = _expected_key_tuple(expected_keys)

    if (recipe_bytes is None) != (expected_recipe_sha256 is None):
        raise ExpandedGoldenError("recipe_bytes and expected_recipe_sha256 must be supplied together")
    recipe_actual: str | None = None
    if recipe_bytes is not None:
        if not isinstance(recipe_bytes, bytes):
            raise ExpandedGoldenError("recipe_bytes must be bytes")
        recipe_expected = _digest_literal(expected_recipe_sha256, "expected_recipe_sha256")
        recipe_actual = sha256(recipe_bytes).hexdigest()
        if recipe_actual != recipe_expected:
            raise ExpandedGoldenError(
                f"recipe SHA-256 mismatch: expected {recipe_expected}, got {recipe_actual}"
            )

    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise ExpandedGoldenError("rows must be a sequence of JSON objects")
    if len(rows) != expected_count:
        raise ExpandedGoldenError(f"expanded row count mismatch: expected {expected_count}, got {len(rows)}")

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ExpandedGoldenError(f"row {index} must be a JSON object")
        actual_keys = tuple(sorted(row.keys())) if all(isinstance(key, str) for key in row) else ()
        if actual_keys != keys:
            raise ExpandedGoldenError(
                f"row {index} schema mismatch: expected {list(keys)!r}, got {list(actual_keys)!r}"
            )

    canonical = canonical_expanded_rows(rows)
    expanded_actual = sha256(canonical).hexdigest()
    if expanded_actual != expanded_expected:
        raise ExpandedGoldenError(
            f"expanded golden SHA-256 mismatch: expected {expanded_expected}, got {expanded_actual}"
        )

    receipt: dict[str, Any] = {
        "expanded_count": len(rows),
        "expanded_keys": list(keys),
        "expanded_sha256": expanded_actual,
        "expanded_canonical_bytes": len(canonical),
    }
    if recipe_actual is not None:
        receipt["recipe_sha256"] = recipe_actual
    return receipt
