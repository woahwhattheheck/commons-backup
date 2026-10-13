from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import re
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

ACTIVE_STATES = ("QUEUED", "CLAIMED", "ATTEMPTING", "UNCERTAIN")
FINAL_STATES = ("SENT", "INVALIDATED", "SUPPRESSED", "CANCELLED")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SUBJECT_PREFIX_RE = re.compile(r"^(?:(?:re|fw|fwd)\s*:\s*)+", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")


class CoordinationError(RuntimeError):
    code = "COORDINATION_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code or self.code
        self.details = details or {}


class ConflictError(CoordinationError):
    code = "CONFLICT"


class NotFoundError(CoordinationError):
    code = "NOT_FOUND"


class ValidationError(CoordinationError):
    code = "VALIDATION_ERROR"


@dataclasses.dataclass(frozen=True)
class Envelope:
    sender: str
    to: tuple[str, ...]
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    subject: str = ""
    body: str = ""

    @property
    def recipients(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.to, *self.cc, *self.bcc)))


@dataclasses.dataclass(frozen=True)
class QueueRequest:
    operation_id: str
    mailbox: str
    envelope: Envelope
    conversation_key: str | None = None
    inbound_message_id: str | None = None
    inbound_received_at: float | None = None
    message_id: str | None = None


@dataclasses.dataclass(frozen=True)
class Claim:
    claim_id: str
    message_id: str
    worker_id: str
    lease_until: float
    body_sha256: str
    envelope: Envelope


@dataclasses.dataclass(frozen=True)
class QueueResult:
    status: str
    message_id: str
    reason: str | None = None
    conflicts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _require_text(name: str, value: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be a string", details={"field": name})
    value = value.strip()
    if not value:
        raise ValidationError(f"{name} is required", details={"field": name})
    if len(value) > max_length:
        raise ValidationError(f"{name} exceeds {max_length} characters", details={"field": name})
    return value


def normalize_address(value: str) -> str:
    value = _require_text("email address", value, max_length=320).casefold()
    if not EMAIL_RE.fullmatch(value):
        raise ValidationError("invalid email address", details={"address": value})
    return value


def normalize_subject(value: str) -> str:
    value = SPACE_RE.sub(" ", SUBJECT_PREFIX_RE.sub("", value or "").strip()).casefold()
    return value or "(no subject)"


def normalize_key(name: str, value: str | None, *, max_length: int = 1024) -> str | None:
    if value is None:
        return None
    return _require_text(name, value, max_length=max_length)


def body_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def utc_now() -> float:
    return time.time()


def stable_identifier(kind: str, operation_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"commons:mail-coordinator:{kind}:{operation_id}"))


