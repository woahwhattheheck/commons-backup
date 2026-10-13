#!/usr/bin/env python3
"""Paceboard domain store: private, local-first habit support without streak shame.

The module is dependency-free and deliberately owns the current clock for all
ordinary mutations. Historical timestamps only enter through a verified
Paceboard backup during an explicit replace restore.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

SCHEMA_VERSION = 1
BACKUP_FORMAT = "paceboard-backup/v1"
CHECKIN_KINDS = frozenset({"DONE", "PAUSED", "RESUMED"})
FOCUS_STATES = frozenset({"RUNNING", "PAUSED", "FINISHED"})
GOAL_STATES = frozenset({"ACTIVE", "ARCHIVED"})
MAX_BACKUP_BYTES = 4 * 1024 * 1024


class PaceboardError(ValueError):
    """Expected product error with an HTTP-compatible status."""

    def __init__(self, message: str, status: int = 400, code: str = "INVALID_REQUEST") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Clock:
    """Injectable process clock used by tests and the local server."""

    now: Callable[[], datetime]

    def utc(self) -> datetime:
        value = self.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("Paceboard clock must return an aware datetime")
        return value.astimezone(timezone.utc).replace(microsecond=0)


def system_clock() -> Clock:
    return Clock(lambda: datetime.now(timezone.utc))


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PaceboardError(f"{field} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise PaceboardError(f"{field} is not a valid timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise PaceboardError(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _text(value: Any, field: str, *, minimum: int = 0, maximum: int = 1000) -> str:
    if not isinstance(value, str):
        raise PaceboardError(f"{field} must be text")
    normalized = value.strip()
    if len(normalized) < minimum:
        raise PaceboardError(f"{field} must contain at least {minimum} character(s)")
    if len(normalized) > maximum:
        raise PaceboardError(f"{field} must contain at most {maximum} characters")
    if "\x00" in normalized:
        raise PaceboardError(f"{field} may not contain NUL")
    return normalized


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PaceboardError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise PaceboardError(f"{field} must be between {minimum} and {maximum}")
    return value


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not (8 <= len(value) <= 80):
        raise PaceboardError(f"{field} is invalid")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(ch not in allowed for ch in value):
        raise PaceboardError(f"{field} is invalid")
    return value


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "BACKUP_FORMAT", "CHECKIN_KINDS", "Clock", "FOCUS_STATES", "GOAL_STATES",
    "MAX_BACKUP_BYTES", "PaceboardError", "SCHEMA_VERSION", "canonical_json",
    "sha256_bytes", "system_clock",
]
