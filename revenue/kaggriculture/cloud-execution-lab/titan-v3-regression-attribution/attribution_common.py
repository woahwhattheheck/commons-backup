#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed, causal regression attribution for ordered TITAN builds.

The existing paired-game gate is the promotion authority.  This tool answers a
separate question: which adjacent build first regressed, and what was the first
causal action divergence on an identical observation stream?

Every engine, runner, build closure, config, terminal ledger, and step trace is
read exactly once, hashed, and parsed from the captured bytes.  A score change
without an action divergence, or observation drift before the first action
difference, is invalid evidence rather than an attributed regression.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
from typing import Any, Mapping


MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_JSONL_BYTES = 256 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")


class AttributionError(ValueError):
    """Raised when evidence is malformed, incomplete, or not causally aligned."""


@dataclass(frozen=True, order=True)
class CellKey:
    opponent: str
    seed: int
    seat: int

    def as_dict(self) -> dict[str, Any]:
        return {"opponent": self.opponent, "seed": self.seed, "candidate_seat": self.seat}


@dataclass(frozen=True)
class GameCell:
    scores: tuple[float, float]


@dataclass(frozen=True)
class TraceStep:
    observation_sha256: str
    action: Any
    action_sha256: str
    diagnostics: Any | None


@dataclass(frozen=True)
class Snapshot:
    label: str
    path: str
    sha256: str
    bytes: int
    data: bytes

    def receipt(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes}


def _reject_constant(value: str) -> None:
    raise AttributionError(f"non-finite JSON constant is forbidden: {value}")


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AttributionError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _loads_json(data: bytes, label: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AttributionError(f"{label}: input is not UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise AttributionError(f"{label}: invalid JSON: {exc}") from exc


def _loads_jsonl(data: bytes, label: str) -> list[Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AttributionError(f"{label}: input is not UTF-8") from exc
    rows: list[Any] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(
                json.loads(
                    line,
                    object_pairs_hook=_pairs_object,
                    parse_constant=_reject_constant,
                )
            )
        except json.JSONDecodeError as exc:
            raise AttributionError(f"{label}:{line_number}: invalid JSON: {exc}") from exc
    if not rows:
        raise AttributionError(f"{label}: JSONL must contain at least one row")
    return rows


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AttributionError(f"value is not canonical JSON: {exc}") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exact_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(allowed - set(value))
    if unknown or missing:
        raise AttributionError(f"{label}: key mismatch; missing={missing}, unknown={unknown}")


def _key_contract(
    value: Mapping[str, Any], required: set[str], optional: set[str], label: str
) -> None:
    unknown = sorted(set(value) - required - optional)
    missing = sorted(required - set(value))
    if unknown or missing:
        raise AttributionError(f"{label}: key mismatch; missing={missing}, unknown={unknown}")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AttributionError(f"{label}: expected a nonempty string")
    return value.strip()


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AttributionError(f"{label}: expected an integer")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AttributionError(f"{label}: expected a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise AttributionError(f"{label}: expected a finite number")
    return result


def _hex_digest(value: Any, length: int, label: str) -> str:
    text = _nonempty_string(value, label).lower()
    if len(text) != length or any(character not in _HEX for character in text):
        raise AttributionError(f"{label}: expected {length} lowercase hexadecimal characters")
    return text


def _commit(value: Any, label: str) -> str:
    text = _nonempty_string(value, label).lower()
    if len(text) not in (40, 64) or any(character not in _HEX for character in text):
        raise AttributionError(f"{label}: expected a 40- or 64-character hexadecimal commit")
    return text


def _resolved_path(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _read_regular_file(path: Path, label: str, max_bytes: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AttributionError(f"{label}: cannot open regular non-symlink file {path}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise AttributionError(f"{label}: input is not a regular file: {path}")
        if info.st_size > max_bytes:
            raise AttributionError(f"{label}: input exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise AttributionError(f"{label}: input exceeds {max_bytes} bytes")
    finally:
        os.close(fd)

    return data


def _snapshot_file(base: Path, spec: Any, label: str, max_bytes: int) -> Snapshot:
    if not isinstance(spec, Mapping):
        raise AttributionError(f"{label}: expected a path/SHA object")
    _exact_keys(spec, {"path", "sha256"}, label)
    declared_path = _nonempty_string(spec["path"], f"{label}.path")
    expected_sha = _hex_digest(spec["sha256"], 64, f"{label}.sha256")
    path = _resolved_path(base, declared_path)
    data = _read_regular_file(path, label, max_bytes)
    actual_sha = _sha256(data)
    if actual_sha != expected_sha:
        raise AttributionError(
            f"{label}: SHA-256 mismatch; expected {expected_sha}, observed {actual_sha}"
        )
    return Snapshot(label, str(path), actual_sha, len(data), data)


def _snapshot_manifest(path: Path) -> Snapshot:
    data = _read_regular_file(path, "manifest", MAX_MANIFEST_BYTES)
    return Snapshot("manifest", str(path), _sha256(data), len(data), data)


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AttributionError(f"{label}: expected an object")
    return value
