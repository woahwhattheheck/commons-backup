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


class QueryMixin:
    def status(self, message_id: str, *, include_body: bool = False) -> dict[str, Any]:
        message_id = _require_text("message_id", message_id)
        with self._connect() as connection:
            message = connection.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone()
            if message is None:
                raise NotFoundError("message not found", details={"message_id": message_id})
            recipients = connection.execute(
                "SELECT address,kind,ordinal FROM message_recipients WHERE message_id=? ORDER BY kind,ordinal",
                (message_id,),
            ).fetchall()
            claims = connection.execute(
                "SELECT claim_id,worker_id,state,claimed_at,lease_until,released_at,attempt_id FROM claims WHERE message_id=? ORDER BY claimed_at",
                (message_id,),
            ).fetchall()
            attempts = connection.execute(
                "SELECT attempt_id,claim_id,state,started_at,updated_at,detail,provider_message_id,provider_accepted_at "
                "FROM attempts WHERE message_id=? ORDER BY started_at",
                (message_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT event_id,event_type,data_json,created_at FROM events WHERE message_id=? ORDER BY event_id",
                (message_id,),
            ).fetchall()
        result = {key: message[key] for key in message.keys() if key != "body"}
        if include_body:
            result["body"] = message["body"]
        grouped: dict[str, list[str]] = {"to": [], "cc": [], "bcc": []}
        for recipient in recipients:
            grouped[recipient["kind"]].append(recipient["address"])
        result["recipients"] = grouped
        result["claims"] = [dict(row) for row in claims]
        result["attempts"] = [dict(row) for row in attempts]
        result["events"] = [dict(row) | {"data": json.loads(row["data_json"])} for row in events]
        for event in result["events"]:
            event.pop("data_json", None)
        return result

    def list_ready(self, *, mailbox: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= int(limit) <= 1000:
            raise ValidationError("limit must be between 1 and 1000")
        values: list[Any] = []
        where = "state='QUEUED'"
        if mailbox is not None:
            where += " AND mailbox=?"
            values.append(normalize_address(mailbox))
        values.append(int(limit))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT message_id,mailbox,sender,subject,body_sha256,conversation_key,inbound_message_id,created_at "
                f"FROM messages WHERE {where} ORDER BY created_at LIMIT ?",
                values,
            ).fetchall()
        return [dict(row) for row in rows]
