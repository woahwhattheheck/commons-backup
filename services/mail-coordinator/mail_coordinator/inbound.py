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


class InboundMixin:
    def record_inbound(
        self,
        *,
        operation_id: str,
        mailbox: str,
        conversation_key: str,
        provider_message_id: str,
        received_at: float,
    ) -> dict[str, Any]:
        operation_id = _require_text("operation_id", operation_id)
        mailbox = normalize_address(mailbox)
        conversation_key = _require_text("conversation_key", conversation_key, max_length=1024)
        provider_message_id = _require_text("provider_message_id", provider_message_id, max_length=1024)
        received_at = float(received_at)
        if received_at < 0:
            raise ValidationError("received_at must be non-negative")
        at = float(self.clock())
        request = {
            "mailbox": mailbox,
            "conversation_key": conversation_key,
            "provider_message_id": provider_message_id,
            "received_at": received_at,
        }
        request_hash = canonical_hash(request)
        with self._write() as connection:
            prior = self._operation_read(connection, operation_id, "record_inbound", request_hash)
            if prior is not None:
                return prior
            duplicate = connection.execute(
                "SELECT received_at,conversation_key FROM inbounds WHERE mailbox=? AND provider_message_id=?",
                (mailbox, provider_message_id),
            ).fetchone()
            if duplicate is not None:
                if duplicate["conversation_key"] != conversation_key or float(duplicate["received_at"]) != received_at:
                    raise ConflictError("provider inbound ID was reused with different metadata", code="INBOUND_ID_REUSE")
            else:
                connection.execute(
                    "INSERT INTO inbounds(mailbox,conversation_key,provider_message_id,received_at,operation_id,created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (mailbox, conversation_key, provider_message_id, received_at, operation_id, at),
                )
            invalidated, unresolved = self._invalidate_older(
                connection,
                mailbox=mailbox,
                conversation_key=conversation_key,
                received_at=received_at,
                now=at,
                replacement_inbound=provider_message_id,
            )
            result = {
                "status": "RECORDED",
                "provider_message_id": provider_message_id,
                "invalidated": invalidated,
                "unresolved": unresolved,
            }
            self._event(connection, "INBOUND_RECORDED", now=at, data=request | result)
            self._operation_write(connection, operation_id, "record_inbound", request_hash, result, at)
            return result

    def _invalidate_older(
        self,
        connection: sqlite3.Connection,
        *,
        mailbox: str,
        conversation_key: str,
        received_at: float,
        now: float,
        replacement_inbound: str,
    ) -> tuple[list[str], list[str]]:
        rows = connection.execute(
            "SELECT message_id,state FROM messages WHERE mailbox=? AND conversation_key=? "
            "AND COALESCE(inbound_received_at,-1) < ? AND state IN ('QUEUED','CLAIMED','ATTEMPTING','UNCERTAIN')",
            (mailbox, conversation_key, received_at),
        ).fetchall()
        invalidated: list[str] = []
        unresolved: list[str] = []
        for row in rows:
            message_id = row["message_id"]
            if row["state"] in ("ATTEMPTING", "UNCERTAIN"):
                unresolved.append(message_id)
                self._event(
                    connection,
                    "NEWER_INBOUND_WITH_UNRESOLVED_ATTEMPT",
                    now=now,
                    message_id=message_id,
                    data={"replacement_inbound": replacement_inbound},
                )
                continue
            connection.execute(
                "UPDATE messages SET state='INVALIDATED',state_reason=?,current_claim_id=NULL,updated_at=? WHERE message_id=?",
                (f"newer inbound {replacement_inbound}", now, message_id),
            )
            connection.execute(
                "UPDATE claims SET state='RELEASED',released_at=? WHERE message_id=? AND state='CLAIMED'",
                (now, message_id),
            )
            invalidated.append(message_id)
            self._event(
                connection,
                "INVALIDATED_BY_NEWER_INBOUND",
                now=now,
                message_id=message_id,
                data={"replacement_inbound": replacement_inbound},
            )
        return invalidated, unresolved
