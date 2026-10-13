#!/usr/bin/env python3
"""Bind a logical row ID to the canonical bytes of its first-seen JSON payload.

The helper is deliberately small and side-effect limited: a successful first bind
writes one digest into the caller-supplied binding map. Exact replay is a no-op.
A changed payload for an already-bound ID fails before the map is mutated.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Any

BOUND = "BOUND"
REPLAY_NOOP = "REPLAY_NOOP"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class PayloadBindingError(ValueError):
    """Base class for invalid payload-binding input or stored state."""


class PayloadBindingMismatch(PayloadBindingError):
    """Raised when an existing row ID is replayed with different payload bytes."""


def _validate_json(value: Any, path: str = "$") -> None:
    """Accept only deterministic JSON values; reject Python-only coercions."""
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PayloadBindingError(f"non-finite number at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PayloadBindingError(f"non-string object key at {path}")
            _validate_json(item, f"{path}.{key}")
        return
    raise PayloadBindingError(f"unsupported JSON value at {path}: {type(value).__name__}")


def canonical_payload_sha256(payload: dict[str, Any]) -> str:
    """Return the SHA-256 of stable UTF-8 JSON for one payload object."""
    if not isinstance(payload, dict):
        raise PayloadBindingError("payload must be a JSON object")
    _validate_json(payload)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def bind_first_seen_payload(bindings: dict[str, str], row_id: str, payload: dict[str, Any]) -> str:
    """Bind first-seen payload identity, or prove an exact replay without mutation."""
    if not isinstance(bindings, dict):
        raise PayloadBindingError("bindings must be a dict")
    if not isinstance(row_id, str) or not row_id or not row_id.strip():
        raise PayloadBindingError("row_id must be a non-blank string")
    digest = canonical_payload_sha256(payload)

    if row_id in bindings:
        previous = bindings[row_id]
        if not isinstance(previous, str) or not _HEX64.fullmatch(previous):
            raise PayloadBindingError("stored payload digest is invalid")
        if previous != digest:
            raise PayloadBindingMismatch(f"payload changed for row_id {row_id!r}")
        return REPLAY_NOOP

    bindings[row_id] = digest
    return BOUND
