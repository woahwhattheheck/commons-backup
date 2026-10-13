from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

from .models import (
    ACTIVE_STATES, Claim, ConflictError, CoordinationError, Envelope,
    NotFoundError, QueueRequest, QueueResult, ValidationError, body_digest,
    canonical_hash, normalize_address, normalize_key, normalize_subject,
    stable_identifier, utc_now, _require_text,
)

from .schema import SCHEMA


class BaseCoordinator:
    def __init__(
        self,
        database: str | Path,
        *,
        clock: Callable[[], float] = utc_now,
        recipient_cooldown_seconds: float = 120.0,
    ) -> None:
        self.database = str(database)
        self.clock = clock
        self.recipient_cooldown_seconds = float(recipient_cooldown_seconds)
        if self.recipient_cooldown_seconds < 0:
            raise ValueError("recipient_cooldown_seconds must be non-negative")

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    @contextlib.contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        event_type: str,
        *,
        now: float,
        message_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO events(message_id,event_type,data_json,created_at) VALUES(?,?,?,?)",
            (message_id, event_type, json.dumps(data or {}, sort_keys=True), now),
        )

    @staticmethod
    def _operation_read(
        connection: sqlite3.Connection,
        operation_id: str,
        action: str,
        request_sha256: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT action,request_sha256,result_json FROM operations WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        if row["action"] != action or row["request_sha256"] != request_sha256:
            raise ConflictError(
                "operation_id was already used for different input",
                code="OPERATION_ID_REUSE",
                details={"operation_id": operation_id, "existing_action": row["action"]},
            )
        return json.loads(row["result_json"])

    @staticmethod
    def _operation_write(
        connection: sqlite3.Connection,
        operation_id: str,
        action: str,
        request_sha256: str,
        result: dict[str, Any],
        now: float,
    ) -> None:
        connection.execute(
            "INSERT INTO operations(operation_id,action,request_sha256,result_json,created_at) VALUES(?,?,?,?,?)",
            (operation_id, action, request_sha256, json.dumps(result, sort_keys=True), now),
        )

    @staticmethod
    def _normalize_envelope(envelope: Envelope) -> Envelope:
        sender = normalize_address(envelope.sender)
        if not isinstance(envelope.body, str):
            raise ValidationError("body must be a string", details={"field": "body"})
        if len(envelope.body.encode("utf-8")) > 2_000_000:
            raise ValidationError("body exceeds 2 MB", details={"field": "body"})
        subject = envelope.subject.strip()
        if len(subject) > 998:
            raise ValidationError("subject exceeds 998 characters", details={"field": "subject"})

        def addresses(values: Sequence[str], field: str) -> tuple[str, ...]:
            if isinstance(values, (str, bytes)):
                raise ValidationError(f"{field} must be a sequence", details={"field": field})
            normalized = tuple(dict.fromkeys(normalize_address(value) for value in values))
            return normalized

        result = Envelope(
            sender=sender,
            to=addresses(envelope.to, "to"),
            cc=addresses(envelope.cc, "cc"),
            bcc=addresses(envelope.bcc, "bcc"),
            subject=subject,
            body=envelope.body,
        )
        if not result.recipients:
            raise ValidationError("at least one recipient is required", details={"field": "recipients"})
        return result
